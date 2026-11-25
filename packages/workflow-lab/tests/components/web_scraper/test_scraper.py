"""Scraper escalation, error handling and hashing (R1, R5-R10)."""

import hashlib

import pytest

from workflow_lab.components.web_scraper import (
    AllBackendsFailed,
    BackendError,
    FetchRequest,
    FetchResult,
    Scraper,
    ScraperConfig,
)

GOOD = "real content " * 200


class FakeFetcher:
    def __init__(
        self,
        name: str,
        markdown: str | None = GOOD,
        html: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.markdown = markdown
        self.html = html
        self.error = error

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if self.error:
            raise self.error
        return FetchResult(
            url=request.url,
            final_url=request.url,
            status=200,
            backend=self.name,
            markdown=self.markdown,
            html=self.html,
        )


def failing(name: str) -> FakeFetcher:
    return FakeFetcher(name, error=BackendError("boom"))


def make(primary: FakeFetcher, fallback: FakeFetcher) -> Scraper:
    cfg = ScraperConfig(backend=primary.name, fallbacks=[fallback.name])
    return Scraper(cfg, backends={primary.name: primary, fallback.name: fallback})


async def test_r1_primary_backend_used():
    result = await make(FakeFetcher("a"), FakeFetcher("b")).fetch("https://x.test")
    assert result.backend == "a"
    assert not result.warnings


async def test_r5_escalates_on_backend_error():
    result = await make(failing("a"), FakeFetcher("b")).fetch("https://x.test")
    assert result.backend == "b"


async def test_r5_unconfigured_fallback_is_recorded_not_fatal(monkeypatch):
    from workflow_lab.components.web_scraper import BrightDataFetcher

    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    cfg = ScraperConfig(backend="a", fallbacks=["brightdata"])
    scraper = Scraper(cfg, backends={"a": failing("a"), "brightdata": BrightDataFetcher()})
    with pytest.raises(AllBackendsFailed, match="BRIGHTDATA_API_KEY"):
        await scraper.fetch("https://x.test")


async def test_r6_escalates_on_challenge_page():
    blocked = FakeFetcher("a", markdown="Just a moment... " * 200)
    result = await make(blocked, FakeFetcher("b")).fetch("https://x.test")
    assert result.backend == "b"


async def test_r7_warning_names_each_earlier_failure():
    result = await make(failing("a"), FakeFetcher("b")).fetch("https://x.test")
    assert result.warnings == ["earlier attempt failed: a: boom"]


async def test_r8_all_backends_failed():
    scraper = make(failing("a"), failing("b"))
    with pytest.raises(AllBackendsFailed) as exc_info:
        await scraper.fetch("https://x.test")
    assert str(exc_info.value) == "https://x.test: a: boom | b: boom"


async def test_r9_not_implemented_error_propagates():
    placeholder = FakeFetcher("a", error=NotImplementedError("placeholder"))
    with pytest.raises(NotImplementedError):
        await make(placeholder, FakeFetcher("b")).fetch("https://x.test")


async def test_r10_content_hash_is_sha256_of_markdown():
    result = await make(FakeFetcher("a"), FakeFetcher("b")).fetch("https://x.test")
    assert result.content_sha256 == hashlib.sha256(GOOD.encode("utf-8")).hexdigest()


async def test_r10_content_hash_falls_back_to_html():
    html = "<p>" + "real content " * 200 + "</p>"
    result = await make(FakeFetcher("a", markdown=None, html=html), FakeFetcher("b")).fetch(
        "https://x.test"
    )
    assert result.content_sha256 == hashlib.sha256(html.encode("utf-8")).hexdigest()
