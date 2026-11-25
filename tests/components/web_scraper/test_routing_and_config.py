"""Backend chain, site config merging, defaults and the sync wrapper (R2-R4, R11-R13)."""

import pytest

from agents_playground.components.web_scraper import (
    Action,
    FetchRequest,
    FetchResult,
    Scraper,
    ScraperConfig,
    SiteConfig,
)

GOOD = "content " * 300


class Recorder:
    """Fake backend that remembers the request it received."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: FetchRequest | None = None

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.seen = request
        return FetchResult(
            url=request.url, final_url=request.url, status=200, backend=self.name, markdown=GOOD
        )


def scraper(cfg: ScraperConfig, **backends: Recorder) -> Scraper:
    return Scraper(cfg, backends=backends)


async def test_r2_site_backend_override():
    a, b = Recorder("a"), Recorder("b")
    cfg = ScraperConfig(backend="a", fallbacks=[], sites={"hard.test": SiteConfig(backend="b")})
    s = scraper(cfg, a=a, b=b)
    assert (await s.fetch("https://hard.test/x")).backend == "b"
    assert (await s.fetch("https://easy.test/x")).backend == "a"


async def test_r4_site_config_applied_to_request():
    a = Recorder("a")
    site = SiteConfig(actions=(Action("scroll_to_bottom"),), required_selector=".item", min_chars=5)
    s = scraper(ScraperConfig(backend="a", fallbacks=[], sites={"x.test": site}), a=a)
    await s.fetch("https://x.test/page")
    assert a.seen.actions == site.actions
    assert a.seen.required_selector == ".item"
    assert a.seen.min_chars == 5


async def test_r4_explicit_request_wins_over_site_config():
    a = Recorder("a")
    site = SiteConfig(required_selector=".site")
    s = scraper(ScraperConfig(backend="a", fallbacks=[], sites={"x.test": site}), a=a)
    await s.fetch("https://x.test", FetchRequest(url="https://x.test", required_selector=".mine"))
    assert a.seen.required_selector == ".mine"


async def test_r4_default_min_chars_from_config():
    a = Recorder("a")
    await scraper(ScraperConfig(backend="a", fallbacks=[], min_chars=123), a=a).fetch(
        "https://x.test"
    )
    assert a.seen.min_chars == 123


async def test_r2_primary_not_repeated_in_fallbacks():
    cfg = ScraperConfig(backend="a", fallbacks=["a", "b"])
    assert scraper(cfg, a=Recorder("a"), b=Recorder("b"))._backend_chain("https://x.test") == [
        "a",
        "b",
    ]


async def test_r3_unknown_backend_rejected():
    with pytest.raises(ValueError, match="nope"):
        await scraper(ScraperConfig(backend="nope", fallbacks=[]), a=Recorder("a")).fetch(
            "https://x.test"
        )


def test_r13_from_yaml_not_implemented():
    with pytest.raises(NotImplementedError):
        ScraperConfig.from_yaml("config.yaml")


def test_r11_fetch_sync(monkeypatch):
    s = scraper(ScraperConfig(backend="a", fallbacks=[]), a=Recorder("a"))
    assert s.fetch_sync("https://x.test").backend == "a"


def test_r12_default_backends():
    s = Scraper(ScraperConfig(user_agent="ua"))
    assert set(s.backends) == {"crawl4ai", "brightdata"}
    assert s.backends["crawl4ai"].user_agent == "ua"


def test_r12_injected_backends_replace_defaults():
    only_a = {"a": Recorder("a")}
    assert Scraper(backends=only_a).backends == only_a


def test_r13_config_defaults():
    cfg = ScraperConfig()
    assert (cfg.backend, cfg.fallbacks, cfg.min_chars) == ("crawl4ai", ["brightdata"], 1500)
    assert cfg.sites == {}
