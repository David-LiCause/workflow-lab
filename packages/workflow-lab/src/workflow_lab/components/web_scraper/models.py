"""Request / result types. Plain dataclasses with no third-party dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

OutputFormat = Literal["markdown", "html", "screenshot"]


@dataclass(frozen=True)
class Action:
    """A browser interaction to run before capturing the page."""

    kind: Literal["scroll_to_bottom", "click_until_gone", "wait_for"]
    selector: str | None = None  # CSS selector (click_until_gone, wait_for)
    js: str | None = None  # JS condition (wait_for)
    max_iterations: int = 20  # safety cap for click_until_gone


@dataclass(frozen=True)
class FetchRequest:
    """What to fetch and how."""

    url: str
    render: bool = True  # run JavaScript in a real browser
    actions: tuple[Action, ...] = ()
    formats: tuple[OutputFormat, ...] = ("markdown", "html")
    timeout_s: float = 60.0
    required_selector: str | None = None  # must be present for the fetch to count as valid
    min_chars: int = 0  # minimum length of the markdown/html for the fetch to count as valid


@dataclass
class FetchResult:
    """The captured page plus provenance."""

    url: str
    final_url: str
    status: int
    backend: str  # which backend produced this result
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    html: str | None = None
    markdown: str | None = None
    screenshot_png: bytes | None = None
    content_sha256: str | None = None
    cost_estimate_usd: float = 0.0
    warnings: list[str] = field(default_factory=list)
