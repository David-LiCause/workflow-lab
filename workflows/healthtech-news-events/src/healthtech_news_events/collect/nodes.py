"""Collect nodes. Each reads state, does one job, and returns a partial update."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langgraph.runtime import Runtime

from workflow_lab.components.text_to_structured_data import extract as extract_rows
from workflow_lab.components.web_scraper import AllBackendsFailed, FetchRequest

from ..context import Context, get_context
from ..models import (
    EVENTS_TABLE,
    REVIEW_QUEUE_TABLE,
    Event,
    EventRow,
    ExtractedEvent,
    ReviewItem,
)
from .sources import SOURCES, NewsSource
from .state import CollectState

CACHE_DIR = "cache/extract"  # under the storage root

Node = Callable[[CollectState, Runtime[Context]], dict[str, Any]]


def make_scrape_node(source: NewsSource) -> Node:
    """Node: fetch each of ``source``'s pages, snapshot it, extract its events with the LLM.

    A page that fails to load is logged in ``errors``; the source's other pages still run.
    """

    def scrape(state: CollectState, runtime: Runtime[Context]) -> dict[str, Any]:
        context = get_context(runtime)
        snapshots: list[str] = []
        rows: list[ExtractedEvent] = []
        review: list[ReviewItem] = []
        errors: list[str] = []

        for i, (page, url) in enumerate(source.pages):
            if i:
                time.sleep(source.crawl_delay_s)  # one page at a time, politely
            try:
                fetched = context.scraper.fetch_sync(
                    url, FetchRequest(url=url, formats=("markdown",))
                )
            except AllBackendsFailed as exc:
                errors.append(f"{source.name}/{page}: {exc}")
                continue

            path = f"snapshots/news/{source.name}-{page}_{context.run_date.isoformat()}.md"
            text = clean_markdown(fetched.markdown or "")
            context.storage.write_text(path, text)
            snapshots.append(path)

            result = extract_rows(
                text,
                EventRow,
                context.llm,
                source.instructions(context.run_date),
                cache_dir=_local_cache_dir(context.storage_root),
            )
            review.extend(
                ReviewItem(
                    source_file=path,
                    item=n,
                    kind=rejected.kind,
                    reason=rejected.reason,
                    raw=rejected.raw,
                    extraction_confidence=rejected.extraction_confidence,
                )
                for n, rejected in enumerate(result.rejected, start=1)
            )
            for extracted in result.rows:
                row = extracted.row
                rows.append(
                    ExtractedEvent(
                        **row.model_dump(),
                        key=event_key(row.company, row.event_type, row.event_date.isoformat()),
                        source=source.name,
                        source_file=path,
                        extraction_confidence=extracted.extraction_confidence,
                        extraction_notes=extracted.extraction_notes,
                    )
                )
        return {
            "snapshots": {source.name: snapshots},
            "extracted": {source.name: rows},
            "review_queue": review,
            "errors": errors,
        }

    scrape.__name__ = source.node
    return scrape


def merge(state: CollectState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Map every source's rows to events and dedupe by key.

    The same story on several pages or sites becomes one event that lists every source and URL,
    keeps the lowest extraction confidence, and fills gaps (amount, headcount) from any copy.
    """
    events: dict[str, Event] = {}
    extracted = state.get("extracted", {})
    for source in SOURCES:
        for row in extracted.get(source.name, []):
            event = events.get(row.key)
            if event is None:
                events[row.key] = Event(
                    **row.model_dump(
                        include=set(Event.model_fields)
                        - {"sources", "article_urls", "source_files"}
                    ),
                    sources=[source.name],
                    article_urls=[row.article_url],
                    source_files=[row.source_file],
                )
                continue
            event.sources = _union(event.sources, [source.name])
            event.article_urls = _union(event.article_urls, [row.article_url])
            event.source_files = _union(event.source_files, [row.source_file])
            event.extraction_confidence = min(
                event.extraction_confidence, row.extraction_confidence
            )
            if event.amount_usd is None:
                event.amount_usd = row.amount_usd
            if event.employees_affected is None:
                event.employees_affected = row.employees_affected
            event.summary = event.summary or row.summary
            event.counterparty = event.counterparty or row.counterparty
    return {"events": list(events.values())}


def export(state: CollectState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Write the events table and the review queue.

    Events are facts, so they are never removed. An event found again keeps its ``first_seen``,
    and gains any new sources and URLs.
    """
    context = get_context(runtime)
    db, today = context.db, context.run_date
    db.ensure_table(REVIEW_QUEUE_TABLE, ReviewItem, key=["source_file", "item"])
    db.upsert(REVIEW_QUEUE_TABLE, state.get("review_queue", []))

    db.ensure_table(EVENTS_TABLE, Event, key="key")
    previous = {e.key: e for e in db.read(EVENTS_TABLE, Event)}
    rows: list[Event] = []
    for event in state.get("events", []):
        old = previous.get(event.key)
        if old is None:
            rows.append(event.model_copy(update={"first_seen": today}))
            continue
        rows.append(
            event.model_copy(
                update={
                    "first_seen": old.first_seen,
                    "sources": _union(old.sources, event.sources),
                    "article_urls": _union(old.article_urls, event.article_urls),
                    "source_files": _union(old.source_files, event.source_files),
                    "extraction_confidence": min(
                        old.extraction_confidence, event.extraction_confidence
                    ),
                }
            )
        )
    result = db.upsert(EVENTS_TABLE, rows)
    return {"inserted": result.inserted, "updated": result.updated}


def clean_markdown(markdown: str) -> str:
    """Drop images and the site navigation above the first article, to cut what the LLM reads."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    first_article = re.search(r"^#{2,4}\s+\[", text, re.MULTILINE)  # a linked headline
    if first_article:
        text = text[first_article.start() :]
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def event_key(company: str, event_type: str, event_date: str) -> str:
    return f"{normalize_name(company)}|{event_type}|{event_date}"


_SUFFIXES = re.compile(r"\b(inc|incorporated|llc|ltd|corp|corporation|co|plc|holdings)\b")


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation and suffixes: ``"Acme Health, Inc."`` -> ``"acme health"``."""
    words = re.sub(r"[^\w\s]", " ", name.lower())
    return " ".join(_SUFFIXES.sub(" ", words).split())


def _union(left: list[str], right: list[str]) -> list[str]:
    return left + [x for x in right if x not in left]


def _local_cache_dir(storage_root: str) -> Path | None:
    """The extraction cache lives under a local storage root; no cache for bucket URLs yet."""
    if "://" in storage_root:
        return None
    return Path(storage_root).expanduser() / CACHE_DIR
