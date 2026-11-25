"""Bright Data Web Unlocker backend: the paid/free-tier fallback for blocked sites.

Uses the Direct API (`POST https://api.brightdata.com/request`, Bearer auth). The outer HTTP
response is 200 once the request reaches the unlocker; the target site's real status is in the
`x-brd-status-code` header, and unlocker-level failures are described by `x-brd-error` and
`x-brd-error-code`. Docs: https://docs.brightdata.com/products/web-unlocker
"""

from __future__ import annotations

import asyncio
import os

try:
    import httpx
except ImportError:  # optional `scraper` extra; BrightDataFetcher.fetch raises a clear error
    httpx = None  # type: ignore[assignment]

from ..errors import BackendError, BackendUnavailable
from ..models import FetchRequest, FetchResult

API_URL = "https://api.brightdata.com/request"
API_KEY_ENV = "BRIGHTDATA_API_KEY"
ZONE_ENV = "BRIGHTDATA_ZONE"
# Nominal pay-as-you-go price ($1.50 per 1,000 successful requests). The first 5K requests a
# month are free, so the real cost is often $0; this is an upper-bound estimate for budgeting.
COST_PER_REQUEST_USD = 0.0015


class BrightDataFetcher:
    """Fallback backend. Calls Bright Data's Web Unlocker API.

    Web Unlocker is a single fetch: it can't click or scroll, so `request.actions` are ignored.
    Markdown and HTML are separate requests (each billed), so asking for both costs two.
    Screenshots are not supported.
    """

    name = "brightdata"

    def __init__(
        self,
        api_key: str | None = None,
        zone: str | None = None,
        country: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # Credentials come from the environment (.env) unless passed in; never hard-code them.
        self.api_key = api_key or os.environ.get(API_KEY_ENV)
        self.zone = zone or os.environ.get(ZONE_ENV)
        self.country = country  # optional two-letter geo, e.g. "us"
        self._client = client  # injectable for tests

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if httpx is None:  # missing dependency is a setup error, not a fetch failure
            raise ImportError(
                "httpx is not installed. Install the `scraper` extra: `uv sync --extra scraper`."
            )
        if not self.api_key or not self.zone:
            raise BackendUnavailable(f"{API_KEY_ENV} and {ZONE_ENV} must be set")

        warnings: list[str] = []
        if request.actions:
            warnings.append("brightdata ignores actions (single fetch, no clicking or scrolling)")
        if "screenshot" in request.formats:
            warnings.append("brightdata does not return screenshots")

        want_markdown = "markdown" in request.formats
        want_html = "html" in request.formats or not want_markdown
        client = self._client or httpx.AsyncClient()
        try:
            markdown_call = self._call(client, request, markdown=True) if want_markdown else None
            html_call = self._call(client, request, markdown=False) if want_html else None
            calls = [c for c in (markdown_call, html_call) if c is not None]
            responses = await asyncio.gather(*calls)
        finally:
            if self._client is None:
                await client.aclose()

        it = iter(responses)
        md_resp = next(it) if want_markdown else None
        html_resp = next(it) if want_html else None
        primary = md_resp or html_resp
        assert primary is not None

        return FetchResult(
            url=request.url,
            final_url=request.url,  # Web Unlocker doesn't report redirects
            status=_target_status(primary),
            backend=self.name,
            html=html_resp.text if html_resp is not None else None,
            markdown=md_resp.text if md_resp is not None else None,
            cost_estimate_usd=COST_PER_REQUEST_USD * len(responses),
            warnings=warnings,
        )

    async def _call(
        self, client: httpx.AsyncClient, request: FetchRequest, *, markdown: bool
    ) -> httpx.Response:
        payload: dict[str, str] = {"zone": self.zone or "", "url": request.url, "format": "raw"}
        if markdown:
            payload["data_format"] = "markdown"
        if self.country:
            payload["country"] = self.country
        try:
            response = await client.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=request.timeout_s,
            )
        except httpx.HTTPError as exc:  # timeouts, connection errors
            raise BackendError(f"brightdata request error: {exc!r}") from exc
        _raise_for_unlocker_error(response)
        return response


def _target_status(response: httpx.Response) -> int:
    """The target site's HTTP status (the outer response is always 200 once unlocking starts)."""
    try:
        return int(response.headers.get("x-brd-status-code", response.status_code))
    except ValueError:
        return response.status_code


def _raise_for_unlocker_error(response: httpx.Response) -> None:
    """Raise BackendError for auth/validation rejections and unlocker-level failures.

    Target-site 4xx/5xx statuses are *not* errors here: they come back as a normal result with
    that status, and `validate()` decides whether to escalate.
    """
    error = response.headers.get("x-brd-error")
    if error:
        code = response.headers.get("x-brd-error-code", "unknown")
        raise BackendError(f"brightdata unlocker error [{code}]: {error}")
    if response.status_code != 200:  # 401 bad key, 400 unknown zone / invalid URL, ...
        raise BackendError(f"brightdata HTTP {response.status_code}: {response.text[:200]}")
