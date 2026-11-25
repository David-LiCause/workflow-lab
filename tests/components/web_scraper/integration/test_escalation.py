"""Real Crawl4AI primary + mocked Bright Data fallback: the full escalation path.

Bright Data is mocked (no request is sent), but the test still requires the Bright Data env vars
so that the whole escalation setup is known to be configured.
"""

import httpx
import pytest

from agents_playground.components.web_scraper import (
    BrightDataFetcher,
    Crawl4AIFetcher,
    FetchRequest,
    Scraper,
    ScraperConfig,
)

pytestmark = pytest.mark.integration


def unlocked(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, text="# Unlocked\n" + "real content " * 50, headers={"x-brd-status-code": "200"}
    )


async def test_blocked_page_escalates_to_brightdata(site, require_env):
    require_env("BRIGHTDATA_API_KEY", "BRIGHTDATA_ZONE")
    client = httpx.AsyncClient(transport=httpx.MockTransport(unlocked))
    scraper = Scraper(
        ScraperConfig(backend="crawl4ai", fallbacks=["brightdata"], min_chars=0),
        backends={
            "crawl4ai": Crawl4AIFetcher(),
            "brightdata": BrightDataFetcher(api_key="k", zone="z", client=client),
        },
    )
    url = f"{site}/blocked"
    result = await scraper.fetch(url, FetchRequest(url=url, formats=("markdown",), timeout_s=30))
    assert result.backend == "brightdata"
    assert result.markdown.startswith("# Unlocked")
    assert any("earlier attempt failed: crawl4ai" in w for w in result.warnings)
