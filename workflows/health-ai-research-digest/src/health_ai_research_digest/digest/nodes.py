"""Digest nodes. Each reads state, does one job, and returns a partial update."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

import httpx
from langgraph.runtime import Runtime

from workflow_lab.components.text_to_structured_data import extract as extract_rows

from ..context import Context, get_context
from ..models import PAPERS_TABLE, REVIEW_QUEUE_TABLE, PaperFindings, PaperRow, ReviewItem
from .arxiv import build_query, fetch_feed, parse_feed
from .state import DigestState

CACHE_DIR = "cache/extract"  # under the storage root

INSTRUCTIONS = """\
The text is the title and abstract of one research paper. Return exactly one row describing it.
Base every field only on the title and abstract; do not add outside knowledge. Use 'not stated'
when the abstract doesn't say."""


def fetch_papers(state: DigestState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Fetch the window's papers from arXiv, or reuse today's saved feed."""
    context = get_context(runtime)
    path = f"feeds/arxiv_{context.run_date}.xml"
    if not context.storage.exists(path):
        query = build_query(context.run_date, context.lookback_days)
        try:
            xml = fetch_feed(query, context.max_papers)
        except httpx.HTTPError as exc:
            return {"feed_path": None, "papers": [], "errors": [f"arXiv fetch failed: {exc}"]}
        context.storage.write_text(path, xml)
    try:
        papers = parse_feed(context.storage.read_text(path))
    except (ValueError, ParseError) as exc:  # arXiv error entry, or malformed XML
        return {"feed_path": path, "papers": [], "errors": [f"{path}: {exc}"]}
    return {"feed_path": path, "papers": papers}


def extract(state: DigestState, runtime: Runtime[Context]) -> dict[str, Any]:
    """One LLM call per paper (cached per paper); rejects go to the review queue."""
    context = get_context(runtime)
    rows: list[PaperRow] = []
    review: list[ReviewItem] = []
    for paper in state.get("papers", []):
        result = extract_rows(
            f"# {paper.title}\n\n{paper.abstract}",
            PaperFindings,
            context.llm,
            INSTRUCTIONS,
            cache_dir=_local_cache_dir(context.storage_root),
        )
        if result.rows:
            found = result.rows[0]
            rows.append(
                PaperRow(
                    **paper.model_dump(),
                    **found.row.model_dump(),
                    extraction_confidence=found.extraction_confidence,
                    extraction_notes=found.extraction_notes,
                )
            )
        elif result.rejected:
            bad = result.rejected[0]
            review.append(
                ReviewItem(
                    arxiv_id=paper.arxiv_id,
                    kind=bad.kind,
                    reason=bad.reason,
                    raw=bad.raw,
                    extraction_confidence=bad.extraction_confidence,
                )
            )
        else:
            review.append(
                ReviewItem(
                    arxiv_id=paper.arxiv_id,
                    kind="no_findings",
                    reason="the LLM returned no row for this paper",
                    raw=paper.title,
                )
            )
    return {"rows": rows, "review_queue": review}


def export(state: DigestState, runtime: Runtime[Context]) -> dict[str, Any]:
    """Upsert papers (keeping first_seen) and the review queue; write the Markdown digest."""
    context = get_context(runtime)
    db = context.db
    db.ensure_table(PAPERS_TABLE, PaperRow, key="arxiv_id")
    db.ensure_table(REVIEW_QUEUE_TABLE, ReviewItem, key="arxiv_id")

    first_seen = {r.arxiv_id: r.first_seen for r in db.read(PAPERS_TABLE, PaperRow)}
    rows = [
        r.model_copy(update={"first_seen": first_seen.get(r.arxiv_id) or context.run_date})
        for r in state.get("rows", [])
    ]
    result = db.upsert(PAPERS_TABLE, rows)
    db.upsert(REVIEW_QUEUE_TABLE, state.get("review_queue", []))

    digest_path = f"digests/digest_{context.run_date}.md"
    context.storage.write_text(digest_path, render_digest(rows, context))
    return {"inserted": result.inserted, "updated": result.updated, "digest_path": digest_path}


def render_digest(rows: list[PaperRow], context: Context) -> str:
    """Health AI papers grouped by clinical area, one line each."""
    start = context.run_date - timedelta(days=context.lookback_days - 1)
    health = [r for r in rows if r.is_health_ai]
    lines = [
        f"# Health AI research digest: {start} to {context.run_date}",
        "",
        f"{len(rows)} arXiv papers summarized; {len(health)} apply AI to health.",
    ]
    by_area: dict[str, list[PaperRow]] = defaultdict(list)
    for row in health:
        by_area[row.clinical_area.strip().lower() or "general"].append(row)
    for area in sorted(by_area):
        lines += ["", f"## {area.capitalize()}", ""]
        for r in sorted(by_area[area], key=lambda r: r.title.lower()):
            lines.append(f"- [{r.title}]({r.url}): {r.one_line_summary}")
    return "\n".join(lines) + "\n"


def _local_cache_dir(storage_root: str) -> Path | None:
    """The extraction cache lives under a local storage root; no cache for bucket URLs yet."""
    if "://" in storage_root:
        return None
    return Path(storage_root).expanduser() / CACHE_DIR
