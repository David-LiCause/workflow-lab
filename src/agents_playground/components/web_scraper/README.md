# web_scraper

Fetch a web page, including JavaScript-rendered content, as Markdown, HTML and/or a screenshot.
A local headless browser (Crawl4AI) goes first; if it fails or the page looks like a bot-challenge
page, the fetch escalates to a Bright Data Web Unlocker fallback. Rules are in
[SPEC.md](SPEC.md).

## Signature

```python
Scraper(config: ScraperConfig | None = None, backends: dict[str, Fetcher] | None = None)

await scraper.fetch(url, request: FetchRequest | None = None) -> FetchResult
scraper.fetch_sync(url, request=None) -> FetchResult      # blocking; not inside an event loop
```

`FetchRequest` options (all optional except `url`):

| Field | Default | Meaning |
| --- | --- | --- |
| `render` | `True` | Run JavaScript (`False` turns it off in Crawl4AI) |
| `actions` | `()` | Browser interactions, see below |
| `formats` | `("markdown", "html")` | Any of `markdown`, `html`, `screenshot`; only these are filled in |
| `timeout_s` | `60` | Page timeout |
| `required_selector` | `None` | Waited for, and checked by validation |
| `min_chars` | `0` | Minimum content length; falls back to the site, then `ScraperConfig.min_chars` (1500) |

| Action | Crawl4AI | Bright Data |
| --- | --- | --- |
| `Action("scroll_to_bottom")` | Scrolls to load lazy content | Ignored, with a warning |
| `Action("click_until_gone", selector="button.more", max_iterations=20)` | Clicks until the element is gone or the cap is hit | Ignored, with a warning |
| `Action("wait_for", selector=".item")` or `Action("wait_for", js="window.ready")` | Waits for it (only the first is used) | Ignored, with a warning |

`FetchResult` has `url`, `final_url`, `status`, `backend`, `fetched_at` (UTC), `html`, `markdown`,
`screenshot_png`, `content_sha256`, `cost_estimate_usd` and `warnings` (earlier backend failures
appear here). If every backend fails, `fetch` raises `AllBackendsFailed` listing each reason, so a
result is never partial.

Per-site settings go in `ScraperConfig`, keyed by exact host. Request fields win over site config:

```python
ScraperConfig(
    backend="crawl4ai",
    fallbacks=["brightdata"],
    sites={
        "a16z.com": SiteConfig(
            actions=(Action("click_until_gone", selector="button.load-more"),),
            required_selector=".portfolio-item",
        ),
        "hard-site.com": SiteConfig(backend="brightdata"),  # skip straight to the unlocker
    },
)
```

Any object with a `name` and `async fetch(request) -> FetchResult` can be a backend:
`Scraper(cfg, backends={"mine": MyFetcher(), "crawl4ai": Crawl4AIFetcher()})`. Raise
`BackendError` to trigger escalation.

## Setup

```bash
uv sync --extra scraper     # crawl4ai + httpx
uv run crawl4ai-setup       # one time: downloads Chromium
```

The Bright Data fallback needs `BRIGHTDATA_API_KEY` and `BRIGHTDATA_ZONE` (see `.env.example`;
load them into your shell, since the component does not read `.env`). Without them the fallback
is skipped and the reason shows up in `AllBackendsFailed`. Costs and sign-up:
[docs/brightdata-setup.md](docs/brightdata-setup.md).

## Example

```python
from agents_playground.components.web_scraper import (
    Action,
    FetchRequest,
    Scraper,
    ScraperConfig,
    SiteConfig,
)

scraper = Scraper(
    ScraperConfig(
        sites={
            "example.com": SiteConfig(
                actions=(Action("scroll_to_bottom"),), required_selector="main"
            )
        }
    )
)

result = await scraper.fetch("https://example.com")  # or scraper.fetch_sync(...)
print(result.status, result.backend, result.warnings)
print(result.markdown)

# One-off options, markdown only (halves Bright Data usage if it escalates):
page = await scraper.fetch(url, FetchRequest(url=url, formats=("markdown",), min_chars=500))
```

To keep a snapshot, write the result with the `storage` component, for example
`Storage("data").write_text(f"snapshots/{host}_{date}.md", result.markdown)`.

## Using it in LangGraph

```python
from typing import TypedDict

from langgraph.graph import StateGraph

from agents_playground.components.web_scraper import AllBackendsFailed, Scraper

scraper = Scraper()


class State(TypedDict, total=False):
    url: str
    markdown: str
    content_sha256: str
    scrape_error: str | None


async def scrape_page(state: State) -> dict:
    try:
        result = await scraper.fetch(state["url"])
    except AllBackendsFailed as exc:
        return {"scrape_error": str(exc)}
    return {
        "markdown": result.markdown or "",
        "content_sha256": result.content_sha256,
        "scrape_error": None,
    }


graph = StateGraph(State)
graph.add_node("scrape_page", scrape_page)
```

## Known behavior

- Crawl4AI has its own anti-bot check: a very small page (a few dozen visible characters) can
  fail as "blocked" and escalate. Set `required_selector` so the page is fully rendered first.
- Web Unlocker does not report redirects, so `final_url` equals `url` for that backend.
- The `required_selector` validation is a substring check, not a real CSS match.

## Tests

```bash
uv run pytest tests/components/web_scraper                  # unit tests: offline, fakes only
uv run pytest -m integration tests/components/web_scraper   # real Chromium, a local server, one example.com fetch
```

Integration tests fail, rather than skip, when something they need is missing: Chromium (run
`uv run crawl4ai-setup`; if Playwright complains about a missing browser build, re-run it so the
browser matches the installed Playwright) or `BRIGHTDATA_API_KEY` / `BRIGHTDATA_ZONE` in `.env`
(needed by the escalation and live Bright Data tests). Real requests: one Crawl4AI fetch of
`https://example.com`, and one Bright Data request (free tier) to the same page.
