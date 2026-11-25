"""Unit tests for the Crawl4AI backend (R19-R27). No browser is launched."""

import base64
import sys
from types import SimpleNamespace

import pytest

from workflow_lab.components.web_scraper import Action, BackendError, FetchRequest
from workflow_lab.components.web_scraper.backends.crawl4ai import (
    Crawl4AIFetcher,
    build_run_options,
)


def test_r19_basic_options():
    kwargs, warnings = build_run_options(FetchRequest(url="https://x.test", timeout_s=30))
    assert kwargs["page_timeout"] == 30000
    assert kwargs["screenshot"] is False
    assert warnings == []


def test_r20_scroll_click_and_wait_actions():
    req = FetchRequest(
        url="https://x.test",
        actions=(
            Action("scroll_to_bottom"),
            Action("click_until_gone", selector="button.more", max_iterations=7),
            Action("wait_for", selector=".item"),
        ),
        formats=("markdown", "screenshot"),
    )
    kwargs, _ = build_run_options(req)
    assert kwargs["scan_full_page"] is True
    assert kwargs["screenshot"] is True
    assert kwargs["wait_for"] == "css:.item"
    (js,) = kwargs["js_code"]
    assert js.startswith("return (async") and '"button.more"' in js and "i < 7" in js


def test_r21_required_selector_becomes_wait_for():
    kwargs, _ = build_run_options(FetchRequest(url="https://x.test", required_selector=".card"))
    assert kwargs["wait_for"] == "css:.card"


def test_r22_extra_wait_for_warns():
    req = FetchRequest(
        url="https://x.test",
        actions=(Action("wait_for", selector="a"), Action("wait_for", js="window.ready")),
    )
    kwargs, warnings = build_run_options(req)
    assert kwargs["wait_for"] == "css:a"
    assert warnings


def test_r23_click_without_selector_rejected():
    with pytest.raises(ValueError):
        build_run_options(FetchRequest(url="https://x.test", actions=(Action("click_until_gone"),)))


def test_r24_to_result_maps_fields():
    crawl = SimpleNamespace(
        url="https://x.test",
        redirected_url="https://x.test/final",
        status_code=200,
        html="<p>hi</p>",
        markdown=SimpleNamespace(raw_markdown="hi"),
        screenshot=base64.b64encode(b"png").decode(),
    )
    req = FetchRequest(url="https://x.test", formats=("markdown", "html", "screenshot"))
    result = Crawl4AIFetcher._to_result(req, crawl, ["w"])
    assert result.final_url == "https://x.test/final"
    assert (result.status, result.html, result.markdown) == (200, "<p>hi</p>", "hi")
    assert result.screenshot_png == b"png"
    assert result.backend == "crawl4ai" and result.warnings == ["w"]


def test_r24_to_result_respects_requested_formats():
    crawl = SimpleNamespace(
        url="https://x.test", status_code=200, html="<p>hi</p>", markdown="hi", screenshot=None
    )
    result = Crawl4AIFetcher._to_result(
        FetchRequest(url="https://x.test", formats=("html",)), crawl, []
    )
    assert result.markdown is None and result.html == "<p>hi</p>"


def test_r23_wait_for_without_selector_or_js_rejected():
    with pytest.raises(ValueError):
        build_run_options(FetchRequest(url="https://x.test", actions=(Action("wait_for"),)))


def install_fake_crawl4ai(monkeypatch, *, crawl=None, error=None) -> dict:
    """Replace the `crawl4ai` module with a stub whose crawler returns `crawl` or raises `error`."""
    seen: dict = {}

    class FakeCrawler:
        def __init__(self, config):
            seen["browser"] = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def arun(self, url, config):
            seen["run"] = config
            if error:
                raise error
            return crawl

    module = SimpleNamespace(
        AsyncWebCrawler=FakeCrawler,
        BrowserConfig=lambda **kw: kw,
        CacheMode=SimpleNamespace(BYPASS="bypass"),
        CrawlerRunConfig=lambda **kw: kw,
    )
    monkeypatch.setitem(sys.modules, "crawl4ai", module)
    return seen


OK_CRAWL = SimpleNamespace(
    success=True, url="https://x.test", status_code=200, html="<p>hi</p>", markdown="hi"
)


async def test_r25_missing_crawl4ai_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "crawl4ai", None)  # makes `import crawl4ai` fail
    with pytest.raises(ImportError, match="scraper"):
        await Crawl4AIFetcher().fetch(FetchRequest(url="https://x.test"))


async def test_r26_unsuccessful_crawl_raises_backend_error(monkeypatch):
    failed = SimpleNamespace(success=False, error_message="blocked by anti-bot")
    install_fake_crawl4ai(monkeypatch, crawl=failed)
    with pytest.raises(BackendError, match="blocked by anti-bot"):
        await Crawl4AIFetcher().fetch(FetchRequest(url="https://x.test"))


async def test_r26_browser_exception_raises_backend_error(monkeypatch):
    install_fake_crawl4ai(monkeypatch, error=RuntimeError("browser died"))
    with pytest.raises(BackendError, match="browser died"):
        await Crawl4AIFetcher().fetch(FetchRequest(url="https://x.test"))


async def test_r27_browser_config_from_fetcher_and_request(monkeypatch):
    seen = install_fake_crawl4ai(monkeypatch, crawl=OK_CRAWL)
    fetcher = Crawl4AIFetcher(user_agent="ua", headless=False)
    result = await fetcher.fetch(FetchRequest(url="https://x.test", render=False))
    assert seen["browser"] == {"headless": False, "java_script_enabled": False, "user_agent": "ua"}
    assert seen["run"]["cache_mode"] == "bypass"
    assert result.backend == "crawl4ai" and result.markdown == "hi"
