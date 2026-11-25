"""Live Bright Data call. Fails unless BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE are set.

Uses one markdown request (billed against the free tier).
"""

import pytest

from agents_playground.components.web_scraper import BrightDataFetcher, FetchRequest

pytestmark = pytest.mark.integration


async def test_live_unlock_example_com(require_env):
    require_env("BRIGHTDATA_API_KEY", "BRIGHTDATA_ZONE")
    result = await BrightDataFetcher().fetch(
        FetchRequest(url="https://example.com", formats=("markdown",))
    )
    assert result.status == 200
    assert "This domain is for use in documentation examples" in result.markdown
