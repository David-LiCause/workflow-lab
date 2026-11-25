"""The backend contract every fetcher implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import FetchRequest, FetchResult


@runtime_checkable
class Fetcher(Protocol):
    """A single way of fetching a page (local browser, unblocker API, test fake, ...)."""

    name: str

    async def fetch(self, request: FetchRequest) -> FetchResult:
        """Fetch the page. Raise `BackendError` on failure."""
        ...
