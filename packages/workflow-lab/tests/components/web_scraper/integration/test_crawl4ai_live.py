"""Real-browser tests of the default backend against a local server. Run: pytest -m integration"""

import pytest

from workflow_lab.components.web_scraper import (
    Action,
    AllBackendsFailed,
    BackendError,
    Crawl4AIFetcher,
    FetchRequest,
    Scraper,
    ScraperConfig,
)

pytestmark = pytest.mark.integration


async def test_renders_javascript_content(site):
    req = FetchRequest(url=f"{site}/list", required_selector=".portfolio-item", timeout_s=30)
    result = await Crawl4AIFetcher().fetch(req)
    assert result.status == 200 and result.backend == "crawl4ai"
    assert 'class="portfolio-item"' in result.html  # absent from the static HTML
    assert "Company 1 " in result.markdown


async def test_click_until_gone_loads_everything(site):
    req = FetchRequest(
        url=f"{site}/list",
        actions=(Action("click_until_gone", selector="button.load-more"),),
        timeout_s=60,
    )
    result = await Crawl4AIFetcher().fetch(req)
    assert result.html.count('class="portfolio-item"') == 15
    assert "<button" not in result.html


async def test_screenshot_is_png(site):
    req = FetchRequest(
        url=f"{site}/list",
        formats=("screenshot",),
        required_selector=".portfolio-item",
        timeout_s=30,
    )
    result = await Crawl4AIFetcher().fetch(req)
    assert result.screenshot_png.startswith(b"\x89PNG")
    assert result.markdown is None and result.html is None


async def test_unreachable_host_raises_backend_error():
    with pytest.raises(BackendError):
        await Crawl4AIFetcher().fetch(FetchRequest(url="http://127.0.0.1:9/", timeout_s=10))


async def test_scraper_end_to_end(site):
    cfg = ScraperConfig(fallbacks=[], min_chars=0)
    req = FetchRequest(url=f"{site}/list", required_selector=".portfolio-item", timeout_s=30)
    result = await Scraper(cfg).fetch(req.url, req)
    assert result.content_sha256 and not result.warnings


async def test_blocked_page_rejected_without_fallback(site):
    # Crawl4AI's own anti-bot detection (or our validator) rejects the challenge page.
    cfg = ScraperConfig(fallbacks=[], min_chars=0)
    with pytest.raises(AllBackendsFailed, match="(?i)anti-bot|challenge"):
        await Scraper(cfg).fetch(
            f"{site}/blocked", FetchRequest(url=f"{site}/blocked", timeout_s=30)
        )
