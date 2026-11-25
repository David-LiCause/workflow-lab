import json
from datetime import date

import pytest
from pydantic import BaseModel

from healthtech_market_landscape_boston import context as context_module
from healthtech_market_landscape_boston.context import (
    DATABASE_URL_VAR,
    DEFAULT_DATABASE_URL,
    STORAGE_ROOT_VAR,
    Context,
)
from healthtech_market_landscape_boston.discovery.graph import graph
from healthtech_market_landscape_boston.discovery.nodes import normalize_domain, normalize_name
from healthtech_market_landscape_boston.discovery.sources import SOURCES
from healthtech_market_landscape_boston.models import (
    COMPANIES_TABLE,
    REVIEW_QUEUE_TABLE,
    Company,
    ExtractedBigTech,
    ReviewItem,
)

DAY1, DAY2 = date(2026, 11, 25), date(2026, 12, 1)
INCUMBENT = {
    "name": "Acme Health",
    "website": "https://www.acme.org",
    "sector": "health_system",
    "also_academic": "yes",
    "research_confidence": "high",
}
BIG_TECH = {
    "parent_company": "Alphabet",
    "website": "https://health.google/",
    "sector": "big_tech",
    "unit_type": "research",
    "research_confidence": "high",
}
LANDSCAPE = {"website": "https://beta.ai", "research_confidence": "medium"}


def raw(data, confidence=0.9):
    return {
        "data_json": json.dumps(data),
        "extraction_confidence": confidence,
        "extraction_notes": "",
    }


REPLIES = {  # source name -> the LLM's rows for that report
    "incumbents": [
        raw(INCUMBENT),
        raw({**INCUMBENT, "name": "Bad Co", "sector": "not_a_sector"}),  # rejected
        raw({**INCUMBENT, "name": "No Site Clinic", "website": ""}),  # keyed by name
    ],
    "big_tech": [  # two units share the parent's site: kept apart by parent/unit key
        raw({**BIG_TECH, "name": "Google Health"}, confidence=0.8),
        raw({**BIG_TECH, "name": "DeepMind Health"}),
        raw({**BIG_TECH, "name": "Google Health"}),  # duplicate key
    ],
    "landscape": [
        raw({**LANDSCAPE, "name": "Beta AI"}),
        raw({**LANDSCAPE, "name": "Acme Health Inc.", "website": "acme.org"}, confidence=0.7),
        raw({**LANDSCAPE, "name": "No Site Clinic, LLC", "website": ""}),  # merges by name
    ],
}


class FakeLLM:
    """Answers each source's calls from REPLIES, matched on the instructions (sources run in
    parallel, so call order is not fixed)."""

    model = "fake"

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def complete_structured(self, messages, schema: type[BaseModel]):
        self.calls.append(messages)
        source = next(s for s in SOURCES if s.instructions in messages[0].content)
        return schema.model_validate({"rows": self.replies[source.name]})


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM(REPLIES)
    monkeypatch.setattr(context_module, "ClaudeLLM", lambda model: fake)
    return fake


def make_context(tmp_path, run_date=DAY1):
    return Context(
        storage_root=str(tmp_path / "storage"),
        database_url=f"sqlite:///{tmp_path}/companies.db",
        run_date=run_date,
    )


@pytest.fixture
def context(tmp_path, llm):
    ctx = make_context(tmp_path)
    ctx.storage.write_text("research/reports/incumbents_2026-11-01.md", "old, ignored")
    for source in SOURCES:
        ctx.storage.write_text(f"research/reports/{source.name}_2026-11-25.md", f"# {source.name}")
    return ctx


def companies(context):
    return {c.key: c for c in context.db.read(COMPANIES_TABLE, Company)}


def test_extracts_every_source_from_its_latest_report(context, llm):
    state = graph.invoke({}, context=context)

    assert not state.get("errors")
    assert state["report_paths"] == {
        s.name: f"research/reports/{s.name}_2026-11-25.md" for s in SOURCES
    }
    assert {name: len(rows) for name, rows in state["extracted"].items()} == {
        "incumbents": 2,
        "big_tech": 2,
        "landscape": 3,
    }
    assert len(llm.calls) == 3
    [unit, *_] = context.db.read("extracted_big_tech", ExtractedBigTech)
    assert unit.key == "alphabet/deepmind-health" and unit.domain == "health.google"


def test_merge_dedupes_by_domain_then_name_and_keeps_units_apart(context):
    graph.invoke({}, context=context)

    rows = companies(context)
    assert set(rows) == {
        "acme.org",
        "name:no site clinic",
        "alphabet/google-health",
        "alphabet/deepmind-health",
        "beta.ai",
    }
    acme = rows["acme.org"]
    assert acme.sources == ["research_incumbents", "research_landscape"]
    assert acme.archetype == "healthcare_incumbent"  # first source wins
    assert acme.extraction_confidence == 0.7  # lowest across sources
    assert rows["name:no site clinic"].sources == ["research_incumbents", "research_landscape"]
    google = rows["alphabet/google-health"]
    assert (google.parent_company, google.archetype) == ("Alphabet", "big_tech_ai_lab")
    assert all(c.status == "new" and c.first_seen == DAY1 for c in rows.values())


def test_rejects_and_duplicates_go_to_review_queue(context):
    graph.invoke({}, context=context)

    kinds = {
        (r.source_file.split("/")[-1], r.kind)
        for r in context.db.read(REVIEW_QUEUE_TABLE, ReviewItem)
    }
    assert kinds == {
        ("incumbents_2026-11-25.md", "validation_error"),
        ("big_tech_2026-11-25.md", "duplicate"),
    }


def test_rerun_is_cached_and_tracks_status(context, llm, tmp_path):
    graph.invoke({}, context=context)
    state = graph.invoke({}, context=context)
    assert len(llm.calls) == 3  # second run hit the extraction cache
    assert (state["inserted"], state["updated"]) == (0, 0)

    llm.replies = {**REPLIES, "landscape": [raw({**LANDSCAPE, "name": "Beta AI"})]}
    later = make_context(tmp_path, run_date=DAY2)
    later.storage.write_text("research/reports/landscape_2026-12-01.md", "# new landscape")
    graph.invoke({}, context=later)

    rows = companies(later)
    assert rows["beta.ai"].status == "active" and rows["beta.ai"].first_seen == DAY1
    assert rows["acme.org"].status == "active"  # still in the incumbents report
    assert rows["acme.org"].sources == ["research_incumbents"]


def test_company_no_longer_found_is_marked_missing(context, llm, tmp_path):
    graph.invoke({}, context=context)

    llm.replies = {**REPLIES, "landscape": []}
    later = make_context(tmp_path, run_date=DAY2)
    later.storage.write_text("research/reports/landscape_2026-12-01.md", "# empty landscape")
    state = graph.invoke({}, context=later)

    assert companies(later)["beta.ai"].status == "missing"
    assert state["missing"] == 1


def test_missing_report_is_an_error_and_other_sources_still_run(tmp_path, llm):
    ctx = make_context(tmp_path)
    ctx.storage.write_text("research/reports/incumbents_2026-11-25.md", "# incumbents")

    state = graph.invoke({}, context=ctx)

    assert sorted(state["errors"]) == [
        "big_tech: no report matches research/reports/big_tech_*.md",
        "landscape: no report matches research/reports/landscape_*.md",
    ]
    assert set(companies(ctx)) == {"acme.org", "name:no site clinic"}


def test_context_falls_back_to_env_then_defaults(monkeypatch):
    monkeypatch.delenv(DATABASE_URL_VAR, raising=False)
    monkeypatch.setenv(STORAGE_ROOT_VAR, "s3://bucket/wf")

    context = Context.model_validate({"run_date": "2026-11-25"})  # as Studio sends it

    assert context.storage_root == "s3://bucket/wf"
    assert context.database_url == DEFAULT_DATABASE_URL
    assert context.run_date == date(2026, 11, 25)


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://www.Example.com/about", "example.com"),
        ("example.com", "example.com"),
        ("http://jobs.example.com:8080", "jobs.example.com"),
        ("", ""),
    ],
)
def test_normalize_domain(url, domain):
    assert normalize_domain(url) == domain


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("Acme Health, Inc.", "acme health"),
        ("No Site Clinic, LLC", "no site clinic"),
        ("AT&T", "at t"),
    ],
)
def test_normalize_name(name, normalized):
    assert normalize_name(name) == normalized
