"""Runtime context: settings every node uses, passed in at invoke time.

The context holds plain, JSON-serializable settings, so LangGraph Studio can show and edit them;
nodes open ``storage``, ``db`` and ``llm`` from them. Any setting left out falls back to its env
var, then to the local default under the git-ignored ``data/`` folder (relative to the workspace
root).
"""

from __future__ import annotations

import os
from datetime import date
from functools import cached_property

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from workflow_lab.components.db import Database
from workflow_lab.components.storage import Storage
from workflow_lab.llm import ClaudeLLM
from workflow_lab.llm.claude import DEFAULT_MODEL

WORKFLOW = "health-ai-research-digest"
STORAGE_ROOT_VAR = "HEALTH_AI_RESEARCH_DIGEST_STORAGE_ROOT"
DATABASE_URL_VAR = "HEALTH_AI_RESEARCH_DIGEST_DATABASE_URL"
DEFAULT_STORAGE_ROOT = f"data/storage/{WORKFLOW}"
DEFAULT_DATABASE_URL = f"sqlite:///data/db/{WORKFLOW}/papers.db"


class Context(BaseModel):
    storage_root: str = Field(
        default_factory=lambda: os.environ.get(STORAGE_ROOT_VAR) or DEFAULT_STORAGE_ROOT,
        description="Local path or bucket URL for feed snapshots, digests and the cache",
    )
    database_url: str = Field(
        default_factory=lambda: os.environ.get(DATABASE_URL_VAR) or DEFAULT_DATABASE_URL,
        description="SQLAlchemy URL for the papers and review_queue tables",
    )
    model: str = Field(DEFAULT_MODEL, description="Claude model used for extraction")
    run_date: date = Field(default_factory=date.today, description="Last day of the window")
    lookback_days: int = Field(7, ge=1, description="Days of submissions to include")
    max_papers: int = Field(50, ge=1, description="Most papers to fetch per run")

    @cached_property
    def storage(self) -> Storage:
        return Storage(self.storage_root)

    @cached_property
    def db(self) -> Database:
        return Database(self.database_url)

    @cached_property
    def llm(self) -> ClaudeLLM:
        return ClaudeLLM(self.model)


def get_context(runtime: Runtime[Context]) -> Context:
    """``runtime.context``, or all defaults when the caller passed none (e.g. a Studio run)."""
    return runtime.context or Context()
