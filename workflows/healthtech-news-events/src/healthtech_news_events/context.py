"""Runtime context: settings every node uses, passed in at invoke time.

The context holds plain, JSON-serializable settings, so LangGraph Studio can show and edit them;
nodes open ``storage``, ``db``, ``llm`` and ``scraper`` from them. Any setting left out falls back
to its env var, then to the local default under the git-ignored ``data/`` folder (relative to the
workspace root).
"""

from __future__ import annotations

import os
from datetime import date
from functools import cached_property

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from workflow_lab.components.db import Database
from workflow_lab.components.storage import Storage
from workflow_lab.components.web_scraper import Scraper, ScraperConfig
from workflow_lab.llm import ClaudeLLM
from workflow_lab.llm.claude import DEFAULT_MODEL

WORKFLOW = "healthtech-news-events"
STORAGE_ROOT_VAR = "HEALTHTECH_NEWS_EVENTS_STORAGE_ROOT"
DATABASE_URL_VAR = "HEALTHTECH_NEWS_EVENTS_DATABASE_URL"
DEFAULT_STORAGE_ROOT = f"data/storage/{WORKFLOW}"
DEFAULT_DATABASE_URL = f"sqlite:///data/db/{WORKFLOW}/events.db"


class Context(BaseModel):
    storage_root: str = Field(
        default_factory=lambda: os.environ.get(STORAGE_ROOT_VAR) or DEFAULT_STORAGE_ROOT,
        description="Local path or bucket URL for page snapshots and the extraction cache",
    )
    database_url: str = Field(
        default_factory=lambda: os.environ.get(DATABASE_URL_VAR) or DEFAULT_DATABASE_URL,
        description="SQLAlchemy URL for the events and review_queue tables",
    )
    model: str = Field(DEFAULT_MODEL, description="Claude model used for extraction")
    run_date: date = Field(default_factory=date.today, description="Date recorded on rows")
    use_unlocker: bool = Field(
        False,
        description="Fall back to Bright Data when a page is blocked (paid; off by default)",
    )

    @cached_property
    def storage(self) -> Storage:
        return Storage(self.storage_root)

    @cached_property
    def db(self) -> Database:
        return Database(self.database_url)

    @cached_property
    def llm(self) -> ClaudeLLM:
        return ClaudeLLM(self.model)

    @cached_property
    def scraper(self) -> Scraper:
        return Scraper(
            ScraperConfig(
                fallbacks=["brightdata"] if self.use_unlocker else [],
                min_chars=500,  # listing pages are short; the default (1500) is for full pages
                user_agent=f"{WORKFLOW} (personal research)",
            )
        )


def get_context(runtime: Runtime[Context]) -> Context:
    """``runtime.context``, or all defaults when the caller passed none (e.g. a Studio run)."""
    return runtime.context or Context()
