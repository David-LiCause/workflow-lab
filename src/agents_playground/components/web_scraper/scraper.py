"""The public entry point: `Scraper.fetch(url)`."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from urllib.parse import urlparse

from .backends import BrightDataFetcher, Crawl4AIFetcher, Fetcher
from .config import ScraperConfig
from .errors import AllBackendsFailed, BackendError
from .models import FetchRequest, FetchResult
from .validation import validate


class Scraper:
    """Fetches pages via a primary backend, escalating to fallbacks when a fetch fails.

    No LangGraph (or other framework) dependency: call it from anywhere.
    """

    def __init__(
        self,
        config: ScraperConfig | None = None,
        backends: dict[str, Fetcher] | None = None,
    ) -> None:
        self.config = config or ScraperConfig()
        self.backends: dict[str, Fetcher] = backends or {
            "crawl4ai": Crawl4AIFetcher(user_agent=self.config.user_agent),
            "brightdata": BrightDataFetcher(),
        }

    async def fetch(self, url: str, request: FetchRequest | None = None) -> FetchResult:
        """Fetch `url`, validate it, escalate on failure, and return the result."""
        request = self._apply_site_config(request or FetchRequest(url=url))
        chain = self._backend_chain(request.url)
        failures: list[str] = []

        for name in chain:
            backend = self.backends[name]
            try:
                result = await backend.fetch(request)
            except NotImplementedError:
                raise  # placeholder backend: surface it instead of silently escalating
            except BackendError as exc:
                failures.append(f"{name}: {exc}")
                continue

            problems = validate(request, result)
            if problems:
                failures.append(f"{name}: {'; '.join(problems)}")
                continue

            result.content_sha256 = _content_hash(result)
            result.warnings.extend(f"earlier attempt failed: {f}" for f in failures)
            return result

        raise AllBackendsFailed(f"{request.url}: " + " | ".join(failures))

    def fetch_sync(self, url: str, request: FetchRequest | None = None) -> FetchResult:
        """Blocking wrapper around `fetch` for scripts and non-async callers."""
        return asyncio.run(self.fetch(url, request))

    # -- internals ---------------------------------------------------------------------------

    def _backend_chain(self, url: str) -> list[str]:
        site = self.config.sites.get(urlparse(url).netloc)
        primary = site.backend if site and site.backend else self.config.backend
        chain = [primary, *(b for b in self.config.fallbacks if b != primary)]
        unknown = [b for b in chain if b not in self.backends]
        if unknown:
            raise ValueError(f"unknown backend(s) in config: {unknown}")
        return chain

    def _apply_site_config(self, request: FetchRequest) -> FetchRequest:
        site = self.config.sites.get(urlparse(request.url).netloc)
        min_chars = request.min_chars or self.config.min_chars
        if site is None:
            return replace(request, min_chars=min_chars)
        return replace(
            request,
            actions=request.actions or site.actions,
            required_selector=request.required_selector or site.required_selector,
            min_chars=request.min_chars or site.min_chars or self.config.min_chars,
        )


def _content_hash(result: FetchResult) -> str:
    """SHA-256 of the captured content (markdown preferred, else html), for change detection."""
    content = result.markdown if result.markdown is not None else (result.html or "")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
