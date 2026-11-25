"""Integration tests for text_to_structured_data.

Talks to the Claude API (cheapest model, ~3 calls in total); checks structure and key facts, not
exact wording.
Run: `uv run pytest -m integration packages/workflow-lab/tests/components/text_to_structured_data`
Needs Claude credentials: `ant auth login` (local), or ANTHROPIC_API_KEY in .env (unattended runs).
The `require_anthropic_credentials` fixture fails the test if neither is available.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from workflow_lab.components.text_to_structured_data import extract, split_into_chunks
from workflow_lab.llm import ClaudeLLM, Message

pytestmark = pytest.mark.integration

MODEL = "claude-haiku-5-5"  # cheapest current model

TABLE = """\
| Company | HQ | Raised |
| --- | --- | --- |
| Acme Health | Boston, MA | $12M Series A |
| Beta Care | Austin, TX | $3.5M seed |
| Gamma Labs | Denver, CO | $40M Series B |
"""
EXPECTED = {"acme health", "beta care", "gamma labs"}
INSTRUCTIONS = "One row per company in the table."


class Company(BaseModel):
    name: str = Field(description="Company name as written in the text.")
    hq: str | None = Field(None, description="City where the company is headquartered.")


class CountingLLM:
    """Wraps a real LLM and counts structured calls."""

    def __init__(self, inner: ClaudeLLM) -> None:
        self.inner = inner
        self.model = inner.model
        self.calls = 0

    def complete(self, messages: list[Message]) -> Message:
        return self.inner.complete(messages)

    def complete_structured(self, messages, schema):
        self.calls += 1
        return self.inner.complete_structured(messages, schema)


def names(result) -> set[str]:
    return {r.row.name.strip().lower() for r in result.rows}


_BASELINE: dict = {}  # filled once per run so the plain and cache tests share one API call


@pytest.fixture
def llm(require_anthropic_credentials) -> CountingLLM:
    return CountingLLM(ClaudeLLM(MODEL, max_tokens=4000))


@pytest.fixture
def baseline(llm, tmp_path_factory) -> dict:
    """The plain extraction with a cache dir: the run's only API call for the single-chunk case."""
    if not _BASELINE:
        cache = tmp_path_factory.mktemp("cache")
        _BASELINE.update(
            cache=cache, result=extract(TABLE, Company, llm, INSTRUCTIONS, cache_dir=cache)
        )
        _BASELINE["calls"] = llm.calls
    return _BASELINE


def test_extracts_three_known_companies(baseline):
    result = baseline["result"]

    assert names(result) == EXPECTED
    assert result.rejected == []
    assert all(0 <= r.extraction_confidence <= 1 for r in result.rows)
    assert all(isinstance(r.row, Company) for r in result.rows)
    assert baseline["calls"] == 1


def test_multi_chunk_gives_same_companies(llm):
    max_chars = 100  # header + first row in chunk one; the other rows in chunk two
    assert len(split_into_chunks(TABLE, max_chars)) >= 2

    result = extract(TABLE, Company, llm, INSTRUCTIONS, max_chunk_chars=max_chars)

    assert names(result) == EXPECTED
    assert llm.calls >= 2


def test_cache_hit_makes_no_api_call(llm, baseline):
    second = extract(TABLE, Company, llm, INSTRUCTIONS, cache_dir=baseline["cache"])

    assert llm.calls == 0  # served from the cache the baseline call wrote
    assert second == baseline["result"]
