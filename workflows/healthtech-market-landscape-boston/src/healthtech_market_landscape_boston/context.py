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

WORKFLOW = "healthtech-market-landscape-boston"
STORAGE_ROOT_VAR = "HEALTHTECH_MARKET_LANDSCAPE_BOSTON_STORAGE_ROOT"
DATABASE_URL_VAR = "HEALTHTECH_MARKET_LANDSCAPE_BOSTON_DATABASE_URL"
DEFAULT_STORAGE_ROOT = f"data/storage/{WORKFLOW}"
DEFAULT_DATABASE_URL = f"sqlite:///data/db/{WORKFLOW}/companies.db"


class Context(BaseModel):
    storage_root: str = Field(
        default_factory=lambda: os.environ.get(STORAGE_ROOT_VAR) or DEFAULT_STORAGE_ROOT,
        description="Local path or bucket URL for reports and other files",
    )
    database_url: str = Field(
        default_factory=lambda: os.environ.get(DATABASE_URL_VAR) or DEFAULT_DATABASE_URL,
        description="SQLAlchemy URL for the incumbents and review_queue tables",
    )
    model: str = Field(DEFAULT_MODEL, description="Claude model used for extraction")
    run_date: date = Field(default_factory=date.today, description="Date recorded on rows")

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
