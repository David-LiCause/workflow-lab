import json
from datetime import date

import pytest
from pydantic import BaseModel

from healthtech_news_events import context as context_module
from healthtech_news_events.collect import nodes as nodes_module
from healthtech_news_events.collect.graph import graph
from healthtech_news_events.collect.nodes import clean_markdown, event_key, normalize_name
from healthtech_news_events.collect.sources import SOURCES
from healthtech_news_events.context import (
    DATABASE_URL_VAR,
    DEFAULT_DATABASE_URL,
    STORAGE_ROOT_VAR,
    Context,
)
from healthtech_news_events.models import EVENTS_TABLE, REVIEW_QUEUE_TABLE, Event, ReviewItem
from workflow_lab.components.web_scraper import AllBackendsFailed, FetchResult

DAY1, DAY2 = date(2026, 11, 25), date(2026, 12, 1)
FUNDING = {
    "company": "Acme Health",
    "event_type": "funding",
    "event_date": "2026-11-24",
    "headline": "Acme Health raises $50M",
    "article_url": "https://dive.example/acme",
}
LAYOFF = {
    "company": "Beta AI",
    "event_type": "layoff",
    "event_date": "2026-11-23",
    "headline": "Beta AI cuts 100 jobs",
    "employees_affected": 100,
    "article_url": "https://dive.example/beta",
}


def raw(data, confidence=0.9):
    return {
        "data_json": json.dumps(data),
        "extraction_confidence": confidence,
        "extraction_notes": "",
    }


REPLIES = {  # source name -> the LLM's rows for each of its pages
    "healthcaredive": [raw(FUNDING), raw(LAYOFF)],
    "fierce": [
        raw(
            {
                **FUNDING,
                "company": "Acme Health, Inc.",  # same event as healthcaredive's, other site
                "amount_usd": 50_000_000,
                "counterparty": "Big VC",
                "article_url": "https://fierce.example/acme",
            },
            confidence=0.7,
        ),
        raw({**FUNDING, "company": "Bad Co", "event_type": "partnership"}),  # rejected
    ],
    "medcity": [raw({**FUNDING, "company": "Gamma Bio", "event_type": "ipo"}, confidence=0.3)],
}


class FakeLLM:
    """Answers each source's calls from REPLIES, matched on the site named in the instructions
    (sources run in parallel, so call order is not fixed)."""

    model = "fake"

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def complete_structured(self, messages, schema: type[BaseModel]):
        self.calls.append(messages)
        source = next(s for s in SOURCES if f"from {s.site}," in messages[0].content)
        return schema.model_validate({"rows": self.replies[source.name]})


class FakeScraper:
    """Returns a small listing page per URL; URLs in ``fail`` raise as if every backend failed."""

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.fetched = []

    def fetch_sync(self, url, request=None):
        self.fetched.append(url)
        if url in self.fail:
            raise AllBackendsFailed(f"{url}: blocked")
        markdown = (
            f"Home | Menu\n\n![logo](x.png)\n\n### [Headline for {url}]({url}/a)\n\nNov. 24, 2026"
        )
        return FetchResult(url=url, final_url=url, status=200, backend="fake", markdown=markdown)


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM(REPLIES)
    monkeypatch.setattr(context_module, "ClaudeLLM", lambda model: fake)
    return fake


@pytest.fixture
def scraper(monkeypatch):
    fake = FakeScraper()
    monkeypatch.setattr(context_module, "Scraper", lambda config: fake)
    monkeypatch.setattr(nodes_module.time, "sleep", lambda seconds: None)
    return fake


def make_context(tmp_path, run_date=DAY1):
    return Context(
        storage_root=str(tmp_path / "storage"),
        database_url=f"sqlite:///{tmp_path}/events.db",
        run_date=run_date,
    )


@pytest.fixture
def context(tmp_path, llm, scraper):
    return make_context(tmp_path)


def events(context):
    return {e.key: e for e in context.db.read(EVENTS_TABLE, Event)}


def test_scrapes_every_page_and_snapshots_it(context, scraper):
    state = graph.invoke({}, context=context)

    assert not state.get("errors")
    pages = [(s, page) for s in SOURCES for page, _ in s.pages]
    assert sorted(scraper.fetched) == sorted(url for s in SOURCES for _, url in s.pages)
    for source, page in pages:
        path = f"snapshots/news/{source.name}-{page}_2026-11-25.md"
        assert path in state["snapshots"][source.name]
        text = context.storage.read_text(path)
        assert text.startswith("### [Headline for")  # navigation and images are stripped
        assert "logo" not in text


def test_merges_the_same_event_from_two_sites(context):
    graph.invoke({}, context=context)

    acme = events(context)[event_key("Acme Health", "funding", "2026-11-24")]
    assert acme.company == "Acme Health"
    assert acme.sources == ["healthcaredive", "fierce"]
    assert acme.article_urls == ["https://dive.example/acme", "https://fierce.example/acme"]
    assert acme.amount_usd == 50_000_000  # filled in from the copy that had it
    assert acme.counterparty == "Big VC"
    assert acme.extraction_confidence == 0.7  # lowest across sources
    assert acme.first_seen == DAY1
    beta = events(context)[event_key("Beta AI", "layoff", "2026-11-23")]
    assert beta.employees_affected == 100


def test_the_same_story_on_two_pages_of_one_site_is_one_event(context):
    graph.invoke({}, context=context)

    assert len(events(context)) == 2  # Acme (both sites, both pages) and Beta AI


def test_rejects_go_to_the_review_queue(context):
    graph.invoke({}, context=context)

    queue = context.db.read(REVIEW_QUEUE_TABLE, ReviewItem)
    kinds = {item.kind for item in queue}
    assert "validation_error" in kinds  # event_type "partnership"
    assert "low_confidence" in kinds  # the 0.3 IPO
    assert all(item.source_file.startswith("snapshots/news/") for item in queue)
    assert not any(e.company == "Gamma Bio" for e in events(context).values())


def test_a_failed_page_is_logged_and_the_rest_still_run(context, scraper):
    scraper.fail = {"https://www.fiercehealthcare.com/finance"}

    state = graph.invoke({}, context=context)

    assert len(state["errors"]) == 1
    assert state["errors"][0].startswith("fierce/finance: ")
    assert state["snapshots"]["fierce"] == ["snapshots/news/fierce-health-tech_2026-11-25.md"]
    assert len(events(context)) == 2


def test_rerun_on_unchanged_pages_changes_nothing_and_skips_the_llm(context, llm):
    graph.invoke({}, context=context)
    calls = len(llm.calls)

    state = graph.invoke({}, context=context)

    assert (state["inserted"], state["updated"]) == (0, 0)
    assert len(llm.calls) == calls  # extraction cache hit


def test_a_later_run_adds_new_events_and_keeps_first_seen(tmp_path, llm, scraper):
    graph.invoke({}, context=make_context(tmp_path, DAY1))
    llm.replies = {
        **REPLIES,
        "healthcaredive": [raw(FUNDING), raw({**LAYOFF, "company": "Delta Care"})],
    }

    later = make_context(tmp_path, DAY2)
    state = graph.invoke({}, context=later)

    assert state["inserted"] == 1
    found = events(later)
    assert found[event_key("Acme Health", "funding", "2026-11-24")].first_seen == DAY1
    assert found[event_key("Delta Care", "layoff", "2026-11-23")].first_seen == DAY2
    assert event_key("Beta AI", "layoff", "2026-11-23") in found  # never removed


def test_clean_markdown_drops_images_and_navigation():
    page = "Menu\n![a](b.png)\n\n\n\n## [Story](https://x/y)\n![](img)   \nBody\n"

    assert clean_markdown(page) == "## [Story](https://x/y)\n\nBody"
    assert clean_markdown("no articles here") == "no articles here"


def test_names_are_normalized_for_the_key():
    assert normalize_name("Acme Health, Inc.") == "acme health"
    assert event_key("Acme Health, Inc.", "funding", "2026-11-24") == (
        "acme health|funding|2026-11-24"
    )


def test_context_settings_fall_back_to_env_then_defaults(monkeypatch):
    monkeypatch.delenv(STORAGE_ROOT_VAR, raising=False)
    monkeypatch.delenv(DATABASE_URL_VAR, raising=False)
    assert Context().database_url == DEFAULT_DATABASE_URL

    monkeypatch.setenv(STORAGE_ROOT_VAR, "s3://bucket/news")
    assert Context().storage_root == "s3://bucket/news"
    assert Context().use_unlocker is False
