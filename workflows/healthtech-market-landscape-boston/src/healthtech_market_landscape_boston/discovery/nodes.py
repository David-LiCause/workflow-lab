"""Discovery nodes. Each reads state, does one job, and returns a partial update."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langgraph.runtime import Runtime

from workflow_lab.components.text_to_structured_data import extract as extract_rows

from ..context import Context, get_context
from ..models import COMPANIES_TABLE, REVIEW_QUEUE_TABLE, Company, Extracted, ReviewItem
from .sources import SOURCES, ReportSource
from .state import DiscoveryState

CACHE_DIR = "cache/extract"  # under the storage root

Node = Callable[[DiscoveryState, Runtime[Context]], dict[str, Any]]


def make_extract_node(source: ReportSource) -> Node:
    """Node: newest report for ``source`` -> rows via the LLM; rejects go to the review queue."""

    def extract(state: DiscoveryState, runtime: Runtime[Context]) -> dict[str, Any]:
        context = get_context(runtime)
        path = context.storage.latest(source.report_pattern)
        if path is None:
            return {"errors": [f"{source.name}: no report matches {source.report_pattern}"]}

        result = extract_rows(
            context.storage.read_text(path),
            source.row_model,
            context.llm,
            source.instructions,
            cache_dir=_local_cache_dir(context.storage_root),
        )
        rows: list[Extracted] = []
        review: list[ReviewItem] = []

        def to_review(kind: str, reason: str, raw: Any, confidence: float | None) -> None:
            review.append(
                ReviewItem(
                    source_file=path,
                    item=len(review) + 1,
                    kind=kind,
                    reason=reason,
                    raw=raw,
                    extraction_confidence=confidence,
                )
            )

        for rejected in result.rejected:
            to_review(rejected.kind, rejected.reason, rejected.raw, rejected.extraction_confidence)

        seen: set[str] = set()
        for extracted in result.rows:
            row, confidence = extracted.row, extracted.extraction_confidence
            domain = normalize_domain(row.website)
            if source.units_of_parent:
                key = f"{_slug(row.parent_company)}/{_slug(row.name)}"
            else:
                key = domain or f"name:{normalize_name(row.name)}"
            if key in seen:
                to_review(
                    "duplicate", f"duplicate key {key!r}", row.model_dump(mode="json"), confidence
                )
                continue
            seen.add(key)
            rows.append(
                source.extracted_model(
                    **row.model_dump(),
                    key=key,
                    domain=domain,
                    source_file=path,
                    extraction_confidence=confidence,
                    extraction_notes=extracted.extraction_notes,
                )
            )
        return {
            "report_paths": {source.name: path},
            "extracted": {source.name: rows},
            "review_queue": review,
        }

    extract.__name__ = source.node
    return extract


def merge(state: DiscoveryState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Map every source's rows to companies and dedupe.

    Rows with a domain merge by domain. A row without a website merges into a company with the
    same normalized name, if there is one. Big tech units are keyed parent/unit, so units that
    share their parent's website stay separate.
    """
    companies: dict[str, Company] = {}
    by_name: dict[str, str] = {}  # normalized name -> company key
    extracted = state.get("extracted", {})

    pairs = [(s, row) for s in SOURCES for row in extracted.get(s.name, [])]
    pairs.sort(key=lambda pair: pair[1].key.startswith("name:"))  # name-only rows last
    for source, row in pairs:
        key = row.key
        if key.startswith("name:"):
            key = by_name.get(key.removeprefix("name:"), key)
        company = companies.get(key)
        if company is None:
            company = companies[key] = Company(
                key=key,
                name=row.name,
                parent_company=getattr(row, "parent_company", "") if source.units_of_parent else "",
                website=row.website,
                domain=row.domain,
                archetype=source.archetype,
                extraction_confidence=row.extraction_confidence,
            )
            by_name.setdefault(normalize_name(row.name), key)
        company.sources = _union(company.sources, [source.source_id])
        company.source_files = _union(company.source_files, [row.source_file])
        company.extraction_confidence = min(
            company.extraction_confidence, row.extraction_confidence
        )
    return {"companies": list(companies.values())}


def export(state: DiscoveryState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Write each source's rows, the companies table and the review queue.

    Companies keep their ``first_seen``. A company found this run is ``new`` on the day it was
    first seen and ``active`` after; one not found is ``missing`` (never deleted), unless all of
    its sources failed this run.
    """
    context = get_context(runtime)
    db, today = context.db, context.run_date
    extracted = state.get("extracted", {})
    for source in SOURCES:
        db.ensure_table(source.table, source.extracted_model, key="key")
        if source.name in extracted:
            db.upsert(source.table, extracted[source.name])
    db.ensure_table(REVIEW_QUEUE_TABLE, ReviewItem, key=["source_file", "item"])
    db.upsert(REVIEW_QUEUE_TABLE, state.get("review_queue", []))

    db.ensure_table(COMPANIES_TABLE, Company, key="key")
    previous = {c.key: c for c in db.read(COMPANIES_TABLE, Company)}
    found = {c.key for c in state.get("companies", [])}
    ran = {s.source_id for s in SOURCES if s.name in extracted}

    rows: list[Company] = []
    for company in state.get("companies", []):
        first_seen = previous[company.key].first_seen if company.key in previous else today
        status = "new" if first_seen == today else "active"
        rows.append(
            company.model_copy(
                update={"first_seen": first_seen, "last_seen": today, "status": status}
            )
        )
    missing = [
        old.model_copy(update={"status": "missing"})
        for key, old in previous.items()
        if key not in found and set(old.sources) & ran
    ]
    result = db.upsert(COMPANIES_TABLE, rows + missing)
    return {
        "inserted": result.inserted,
        "updated": result.updated,
        "missing": sum(c.status == "missing" for c in [*rows, *missing]),
    }


def normalize_domain(url: str) -> str:
    """``"https://www.Example.com/about"`` -> ``"example.com"``; ``""`` if there is no host."""
    url = url.strip().lower()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return (urlparse(url).hostname or "").removeprefix("www.")


_SUFFIXES = re.compile(r"\b(inc|incorporated|llc|ltd|corp|corporation|co|plc|holdings)\b")


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation and suffixes: ``"Acme Health, Inc."`` -> ``"acme health"``."""
    words = re.sub(r"[^\w\s]", " ", name.lower())
    return " ".join(_SUFFIXES.sub(" ", words).split())


def _slug(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def _union(left: list[str], right: list[str]) -> list[str]:
    return left + [x for x in right if x not in left]


def _local_cache_dir(storage_root: str) -> Path | None:
    """The extraction cache lives under a local storage root; no cache for bucket URLs yet."""
    if "://" in storage_root:
        return None
    return Path(storage_root).expanduser() / CACHE_DIR
