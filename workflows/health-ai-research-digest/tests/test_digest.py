import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from health_ai_research_digest import context as context_module
from health_ai_research_digest.context import Context
from health_ai_research_digest.digest import nodes
from health_ai_research_digest.digest.arxiv import build_query, fetch_feed, parse_feed
from health_ai_research_digest.digest.graph import graph
from health_ai_research_digest.models import (
    PAPERS_TABLE,
    REVIEW_QUEUE_TABLE,
    PaperRow,
    ReviewItem,
)
from workflow_lab.llm import MockLLM

FEED = (Path(__file__).parent / "fixtures" / "arxiv_feed.xml").read_text()
RUN_DATE = date(2026, 11, 25)
CXR = {
    "is_health_ai": True,
    "one_line_summary": "A vision transformer triages chest X-rays.",
    "task": "triage",
    "clinical_area": "Radiology",
    "data_modality": "imaging",
    "datasets": "MIMIC-CXR",
    "model_approach": "vision transformer",
    "headline_result": "AUROC 0.94",
}
OPTIMIZER = {
    **CXR,
    "is_health_ai": False,
    "one_line_summary": "Benchmarks optimizers.",
    "clinical_area": "none",
    "data_modality": "other",
}
BAD = {**CXR, "data_modality": "not_a_modality"}  # fails validation


def batch(data, confidence=0.9):
    return {
        "rows": [
            {
                "data_json": json.dumps(data),
                "extraction_confidence": confidence,
                "extraction_notes": "",
            }
        ]
    }


@pytest.fixture
def llm(monkeypatch):
    mock = MockLLM(structured_replies=[batch(CXR), batch(OPTIMIZER), batch(BAD)])  # feed order
    monkeypatch.setattr(context_module, "ClaudeLLM", lambda model: mock)
    return mock


@pytest.fixture
def context(tmp_path, llm):
    ctx = Context(
        storage_root=str(tmp_path / "storage"),
        database_url=f"sqlite:///{tmp_path}/papers.db",
        run_date=RUN_DATE,
    )
    ctx.storage.write_text(f"feeds/arxiv_{RUN_DATE}.xml", FEED)  # saved feed: no network
    return ctx


def test_parse_feed():
    papers = parse_feed(FEED)

    assert [p.arxiv_id for p in papers] == ["2611.00001", "2611.00002", "2611.00003"]
    cxr = papers[0]
    assert cxr.title == "A Vision Transformer for Chest X-ray Triage"  # wrapped title joined
    assert cxr.authors == ["Ada Lovelace", "Alan Turing"]
    assert cxr.categories == ["cs.CV", "eess.IV"]
    assert cxr.published == date(2026, 11, 24)
    assert cxr.url == "https://arxiv.org/abs/2611.00001"


def test_parse_feed_raises_on_api_error():
    error = FEED.replace("http://arxiv.org/abs/2611.00001v2", "http://arxiv.org/api/errors#x")
    with pytest.raises(ValueError, match="arXiv API error"):
        parse_feed(error)


def test_build_query_covers_window():
    query = build_query(RUN_DATE, 7)
    assert "submittedDate:[202611190000 TO 202611252359]" in query
    assert "cat:cs.LG" in query and "abs:clinical" in query


def test_fetch_feed_sends_query():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, text=FEED)

    xml = fetch_feed("q", 5, client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert xml == FEED
    assert (seen["search_query"], seen["max_results"]) == ("q", "5")


def test_writes_papers_review_queue_and_digest(context, llm):
    state = graph.invoke({}, context=context)

    assert state["feed_path"] == f"feeds/arxiv_{RUN_DATE}.xml"
    assert len(llm.calls) == 3  # one per paper
    assert "Chest X-ray Triage" in llm.calls[0][-1].content
    rows = {r.arxiv_id: r for r in context.db.read(PAPERS_TABLE, PaperRow)}
    assert set(rows) == {"2611.00001", "2611.00002"}
    cxr = rows["2611.00001"]
    assert (cxr.task, cxr.datasets, cxr.extraction_confidence) == ("triage", "MIMIC-CXR", 0.9)
    assert cxr.authors == ["Ada Lovelace", "Alan Turing"] and cxr.first_seen == RUN_DATE
    [review] = context.db.read(REVIEW_QUEUE_TABLE, ReviewItem)
    assert (review.arxiv_id, review.kind) == ("2611.00003", "validation_error")

    digest = context.storage.read_text(state["digest_path"])
    assert digest.startswith("# Health AI research digest: 2026-11-19 to 2026-11-25")
    assert "2 arXiv papers summarized; 1 apply AI to health." in digest
    assert "## Radiology" in digest
    assert (
        "- [A Vision Transformer for Chest X-ray Triage](https://arxiv.org/abs/2611.00001)"
        in digest
    )
    assert "Faster Optimizers" not in digest  # not health AI


def test_rerun_uses_cache(context, llm):
    graph.invoke({}, context=context)
    state = graph.invoke({}, context=context)

    assert len(llm.calls) == 3  # second run made no LLM calls
    assert (state["inserted"], state["updated"]) == (0, 0)


def test_fetch_error_is_recorded_and_run_ends(tmp_path, llm, monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(nodes, "fetch_feed", fail)
    ctx = Context(storage_root=str(tmp_path / "s"), database_url=f"sqlite:///{tmp_path}/p.db")

    state = graph.invoke({}, context=ctx)

    assert state["errors"] == ["arXiv fetch failed: offline"]
    assert "digest_path" not in state and llm.calls == []
