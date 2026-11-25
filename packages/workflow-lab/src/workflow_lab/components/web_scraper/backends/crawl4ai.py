"""Crawl4AI backend: local Playwright-based crawler (the default backend)."""

from __future__ import annotations

import base64
import json
from typing import Any

from ..errors import BackendError
from ..models import Action, FetchRequest, FetchResult

# Pause between scroll steps when loading lazy content (seconds).
SCROLL_DELAY_S = 0.5


def _click_until_gone_js(selector: str, max_iterations: int) -> str:
    """JS that clicks `selector` repeatedly until it disappears or the cap is hit.

    Crawl4AI wraps js_code in a plain function and only awaits it if it *returns* a Promise,
    hence the `return` before the async IIFE.
    """
    sel = json.dumps(selector)
    return (
        "return (async () => {"
        f"for (let i = 0; i < {int(max_iterations)}; i++) {{"
        f"  const el = document.querySelector({sel});"
        "  if (!el) break;"
        "  el.scrollIntoView(); el.click();"
        "  await new Promise(r => setTimeout(r, 1000));"
        "}"
        "})();"
    )


def _wait_for_expr(action: Action) -> str | None:
    """Crawl4AI `wait_for` syntax: 'css:<selector>' or 'js:() => <condition>'."""
    if action.selector:
        return f"css:{action.selector}"
    if action.js:
        return f"js:() => {{ return Boolean({action.js}); }}"
    return None


def build_run_options(request: FetchRequest) -> tuple[dict[str, Any], list[str]]:
    """Translate a FetchRequest into CrawlerRunConfig kwargs (plain dict, easy to unit test).

    Returns (kwargs, warnings).
    """
    kwargs: dict[str, Any] = {
        "page_timeout": int(request.timeout_s * 1000),
        "screenshot": "screenshot" in request.formats,
    }
    warnings: list[str] = []
    js_snippets: list[str] = []
    wait_exprs: list[str] = []

    for action in request.actions:
        if action.kind == "scroll_to_bottom":
            kwargs["scan_full_page"] = True
            kwargs["scroll_delay"] = SCROLL_DELAY_S
        elif action.kind == "click_until_gone":
            if not action.selector:
                raise ValueError("click_until_gone requires a selector")
            js_snippets.append(_click_until_gone_js(action.selector, action.max_iterations))
        elif action.kind == "wait_for":
            expr = _wait_for_expr(action)
            if expr is None:
                raise ValueError("wait_for requires a selector or js condition")
            wait_exprs.append(expr)

    if js_snippets:
        kwargs["js_code"] = js_snippets
    if wait_exprs:
        kwargs["wait_for"] = wait_exprs[0]
        if len(wait_exprs) > 1:
            warnings.append("crawl4ai supports one wait_for; extra wait_for actions were ignored")
    # Make sure a required selector is present before the HTML is captured.
    if request.required_selector and "wait_for" not in kwargs:
        kwargs["wait_for"] = f"css:{request.required_selector}"
    return kwargs, warnings


class Crawl4AIFetcher:
    """Default backend. Runs a local headless browser via the `crawl4ai` library."""

    name = "crawl4ai"

    def __init__(self, user_agent: str | None = None, headless: bool = True) -> None:
        self.user_agent = user_agent
        self.headless = headless

    async def fetch(self, request: FetchRequest) -> FetchResult:
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        except ImportError as exc:  # missing dependency is a setup error, not a fetch failure
            raise ImportError(
                "crawl4ai is not installed. Install the `scraper` extra "
                "(`uv sync --extra scraper`), then run `uv run crawl4ai-setup`."
            ) from exc

        browser_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "java_script_enabled": request.render,
        }
        if self.user_agent:
            browser_kwargs["user_agent"] = self.user_agent

        run_kwargs, warnings = build_run_options(request)
        run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, **run_kwargs)

        try:
            async with AsyncWebCrawler(config=BrowserConfig(**browser_kwargs)) as crawler:
                crawl = await crawler.arun(url=request.url, config=run_config)
        except Exception as exc:  # playwright timeouts, browser launch errors, etc.
            raise BackendError(f"crawl4ai error: {exc}") from exc

        if not crawl.success:
            raise BackendError(f"crawl4ai failed: {crawl.error_message or 'unknown error'}")

        return self._to_result(request, crawl, warnings)

    @staticmethod
    def _to_result(request: FetchRequest, crawl: Any, warnings: list[str]) -> FetchResult:
        markdown = None
        if "markdown" in request.formats and crawl.markdown is not None:
            # MarkdownGenerationResult (str() gives raw_markdown) or a plain str on older versions
            markdown = getattr(crawl.markdown, "raw_markdown", None) or str(crawl.markdown)

        screenshot = None
        if "screenshot" in request.formats and crawl.screenshot:
            screenshot = base64.b64decode(crawl.screenshot)

        return FetchResult(
            url=request.url,
            final_url=getattr(crawl, "redirected_url", None) or crawl.url,
            status=crawl.status_code or 0,
            backend=Crawl4AIFetcher.name,
            html=crawl.html if "html" in request.formats else None,
            markdown=markdown,
            screenshot_png=screenshot,
            cost_estimate_usd=0.0,
            warnings=warnings,
        )
