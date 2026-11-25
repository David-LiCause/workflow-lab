"""Checks that a fetched page is real content, not a block page or empty shell."""

from __future__ import annotations

from .models import FetchRequest, FetchResult

CHALLENGE_SIGNATURES = (
    "just a moment...",
    "attention required",
    "verify you are human",
    "enable javascript and cookies to continue",
)


def validate(request: FetchRequest, result: FetchResult) -> list[str]:
    """Return a list of problems. An empty list means the result is valid."""
    problems: list[str] = []
    if result.status >= 400:
        problems.append(f"HTTP status {result.status}")
    text = (result.markdown or result.html or "").lower()
    if any(sig in text for sig in CHALLENGE_SIGNATURES):
        problems.append("looks like a bot-challenge page")
    if len(text) < request.min_chars:
        problems.append(f"content too short ({len(text)} < {request.min_chars} chars)")
    if request.required_selector and result.html is not None:
        # TODO: real CSS-selector check (e.g. with selectolax/lxml); substring is a stand-in.
        if request.required_selector.lstrip(".#") not in result.html:
            problems.append(f"required selector not found: {request.required_selector}")
    return problems
