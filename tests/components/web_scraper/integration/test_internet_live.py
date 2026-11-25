"""One real-internet fetch with the default Crawl4AI backend. Run: pytest -m integration

Uses https://example.com (IANA's documentation page, meant for this) with no fallback, so a
failure is Crawl4AI's and no Bright Data request is made.
"""

import hashlib

import pytest

from agents_playground.components.web_scraper import FetchRequest, Scraper, ScraperConfig

pytestmark = pytest.mark.integration

URL = "https://example.com"


async def test_fetches_example_com_with_crawl4ai():
    # min_chars=0 and a required selector: the page is tiny, and Crawl4AI's anti-bot check can
    # reject tiny pages that are not fully rendered yet (see README "Known behavior").
    scraper = Scraper(ScraperConfig(fallbacks=[], min_chars=0))
    request = FetchRequest(url=URL, formats=("markdown",), required_selector="p", timeout_s=30)

    result = await scraper.fetch(URL, request)

    assert result.backend == "crawl4ai"
    assert result.status == 200
    assert "This domain is for use in documentation examples" in result.markdown
    assert result.final_url.rstrip("/") == URL
    assert result.content_sha256 == hashlib.sha256(result.markdown.encode("utf-8")).hexdigest()
    assert not result.warnings
