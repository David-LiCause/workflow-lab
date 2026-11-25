"""Package exports (R36)."""

import agents_playground.components.web_scraper as web_scraper


def test_r36_public_api():
    expected = {
        "Action",
        "AllBackendsFailed",
        "BackendError",
        "BackendUnavailable",
        "BrightDataFetcher",
        "Crawl4AIFetcher",
        "FetchRequest",
        "FetchResult",
        "Fetcher",
        "Scraper",
        "ScraperConfig",
        "ScraperError",
        "SiteConfig",
        "ValidationFailed",
    }
    assert set(web_scraper.__all__) == expected
    assert all(hasattr(web_scraper, name) for name in expected)
