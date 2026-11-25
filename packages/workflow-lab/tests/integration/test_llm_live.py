"""Integration tests for ClaudeLLM.

Talks to the Claude API (cheapest model, 2 short calls); checks structure, not exact wording.
Run: `uv run pytest -m integration packages/workflow-lab/tests/integration`
Needs Claude credentials: `ant auth login` (local), or ANTHROPIC_API_KEY in .env (unattended runs).
The `require_anthropic_credentials` fixture fails the test if neither is available.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from workflow_lab.llm import ClaudeLLM, Message

pytestmark = pytest.mark.integration

MODEL = "claude-haiku-5-5"  # cheapest current model


class Capital(BaseModel):
    country: str
    capital: str


@pytest.fixture
def llm(require_anthropic_credentials) -> ClaudeLLM:
    return ClaudeLLM(MODEL, max_tokens=1000)


def test_complete_returns_text(llm):
    reply = llm.complete(
        [
            Message("system", "Answer in one word."),
            Message("user", "What is the capital of France?"),
        ]
    )

    assert reply.role == "assistant"
    assert "paris" in reply.content.lower()


def test_complete_structured_returns_schema_instance(llm):
    result = llm.complete_structured(
        [Message("user", "What is the capital of Japan? Fill in country and capital.")], Capital
    )

    assert isinstance(result, Capital)
    assert result.country.lower() == "japan"
    assert result.capital.lower() == "tokyo"
