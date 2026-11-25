"""Row models and tables."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

EVENTS_TABLE = "events"
REVIEW_QUEUE_TABLE = "review_queue"

EventType = Literal["funding", "layoff", "acquisition", "ipo"]


class EventRow(BaseModel):
    """One event reported on a news listing page. Each field's description tells the LLM what to
    extract into it."""

    company: str = Field(
        description="The company the event is about: the one raising money, laying off staff, "
        "being acquired or going public. Its name as written, without 'Inc.' or similar."
    )
    event_type: EventType = Field(
        description="funding (a raise or round), layoff (job cuts or restructuring), "
        "acquisition (a company being bought or merged), or ipo (a listing or IPO filing)."
    )
    event_date: date = Field(
        description="The article's publication date, YYYY-MM-DD. Use the date shown next to the "
        "headline; resolve relative dates ('2 hours ago') from the fetch date given in the "
        "instructions."
    )
    headline: str = Field(description="The article headline, as written.")
    summary: str = Field(
        "", description="One line on the event, using only what the page says about it."
    )
    amount_usd: int | None = Field(
        None,
        description="Money in whole US dollars: the round size for funding, the deal value for "
        "an acquisition, the amount raised for an IPO (e.g. $12M -> 12000000). Null if not given.",
    )
    employees_affected: int | None = Field(
        None, description="Number of jobs cut, for a layoff. Null if not given."
    )
    counterparty: str = Field(
        "",
        description="The acquirer for an acquisition, or the lead or named investors for "
        "funding, semicolon-separated. Empty otherwise.",
    )
    article_url: str = Field(description="The article's full URL, from the link on its headline.")


class ExtractedEvent(EventRow):
    """One event as extracted from one page. Key: see ``event_key``."""

    key: str
    source: str  # the news source's name, e.g. healthcaredive
    source_file: str  # snapshot the row came from, relative to the storage root
    extraction_confidence: float  # 0-1, from the LLM
    extraction_notes: str = ""


class Event(BaseModel):
    """A row of the ``events`` table: Collect's output. Key: ``key``.

    One row per company, event type and day; the same event on several sites merges into one.
    """

    key: str  # "<normalized company>|<event_type>|<event_date>"
    company: str
    event_type: EventType
    event_date: date
    headline: str
    summary: str = ""
    amount_usd: int | None = None
    employees_affected: int | None = None
    counterparty: str = ""
    sources: list[str] = Field(default_factory=list)  # e.g. healthcaredive, fierce
    article_urls: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    extraction_confidence: float  # lowest across the row's sources
    first_seen: date | None = None  # first run that found the event


class ReviewItem(BaseModel):
    """A row that was not loaded, with the reason. Key: ``(source_file, item)``."""

    source_file: str
    item: int  # 1-based position among this file's review items
    kind: str  # validation_error, low_confidence
    reason: str
    raw: dict[str, Any] | str
    extraction_confidence: float | None = None
