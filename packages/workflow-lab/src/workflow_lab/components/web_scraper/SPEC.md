# web_scraper

## 1. Purpose

Fetch a web page, including JavaScript-rendered content, as Markdown, HTML and/or a screenshot.
A local headless browser (Crawl4AI) is tried first; if it fails or the page looks blocked, the
fetch escalates to a Bright Data Web Unlocker fallback. It returns pages, not extracted records.

## 2. Interface

```python
@dataclass(frozen=True)
class Action:
    kind: Literal["scroll_to_bottom", "click_until_gone", "wait_for"]
    selector: str | None = None  # CSS selector (click_until_gone, wait_for)
    js: str | None = None  # JS condition (wait_for)
    max_iterations: int = 20  # cap for click_until_gone


@dataclass(frozen=True)
class FetchRequest:
    url: str
    render: bool = True  # run JavaScript in a real browser
    actions: tuple[Action, ...] = ()
    formats: tuple[Literal["markdown", "html", "screenshot"], ...] = ("markdown", "html")
    timeout_s: float = 60.0
    required_selector: str | None = None
    min_chars: int = 0


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    backend: str  # which backend produced this result
    fetched_at: datetime  # UTC
    html: str | None = None
    markdown: str | None = None
    screenshot_png: bytes | None = None
    content_sha256: str | None = None
    cost_estimate_usd: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class SiteConfig:
    backend: str | None = None
    actions: tuple[Action, ...] = ()
    required_selector: str | None = None
    min_chars: int | None = None
    rate_limit_s: float | None = None  # reserved, not enforced


@dataclass
class ScraperConfig:
    backend: str = "crawl4ai"
    fallbacks: list[str] = ["brightdata"]
    min_chars: int = 1500
    rate_limit_s: float = 3.0  # reserved, not enforced
    user_agent: str = "web-scraper (set a contact here)"
    sites: dict[str, SiteConfig] = {}  # host -> overrides

    @classmethod
    def from_yaml(cls, path: str | Path) -> ScraperConfig: ...  # not implemented


class Fetcher(Protocol):
    name: str

    async def fetch(self, request: FetchRequest) -> FetchResult: ...


class Scraper:
    def __init__(
        self,
        config: ScraperConfig | None = None,
        backends: dict[str, Fetcher] | None = None,
    ) -> None: ...

    backends: dict[str, Fetcher]

    async def fetch(self, url: str, request: FetchRequest | None = None) -> FetchResult: ...
    def fetch_sync(self, url: str, request: FetchRequest | None = None) -> FetchResult: ...


class Crawl4AIFetcher:  # name = "crawl4ai"
    def __init__(self, user_agent: str | None = None, headless: bool = True) -> None: ...


class BrightDataFetcher:  # name = "brightdata"
    def __init__(
        self,
        api_key: str | None = None,
        zone: str | None = None,
        country: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None: ...


def validate(request: FetchRequest, result: FetchResult) -> list[str]: ...  # in .validation
```

## 3. Inputs and outputs

- `url`: the page to fetch. When `request` is omitted, `FetchRequest(url=url)` is used.
- `request`: per-call options. Fields the caller sets win over site config and config defaults.
- `formats`: which of `markdown`, `html`, `screenshot` to capture. Only the requested formats are
  filled in on the result.
- `Scraper.fetch` returns one valid `FetchResult` (a failed fetch raises, so a result is never
  partial). `content_sha256` is set; `warnings` lists earlier backend failures and backend notes.
- `validate` returns a list of problem strings. An empty list means the result is valid.

## 4. Behavior rules

### Routing and escalation (`Scraper`)

- **R1** `fetch` calls the primary backend first and returns its result when it is valid. A result
  that needed no escalation has no warnings.
- **R2** The backend chain is the site's `backend` (sites match on the URL's exact host, including
  any port) or else `config.backend`, followed by `config.fallbacks` in order. The primary is not
  repeated if it also appears in `fallbacks`.
- **R3** A backend name in the chain that is not in `Scraper.backends` raises `ValueError` naming
  it, before any fetch.
- **R4** Site config fills in what the request leaves unset: `actions`, `required_selector` and
  `min_chars`. Fields set on the request win. `min_chars` falls back request, then site, then
  `config.min_chars`.
- **R5** A `BackendError` (including `BackendUnavailable`) from a backend is recorded and the next
  backend in the chain is tried.
- **R6** A result with validation problems (R14 to R18) is recorded and the next backend is tried.
- **R7** A valid result that follows failures gets one warning per failure, in order:
  `earlier attempt failed: <backend>: <reason>`.
- **R8** If every backend fails, `fetch` raises `AllBackendsFailed` with the message
  `<url>: <backend>: <reason> | <backend>: <reason> ...`.
- **R9** `NotImplementedError` from a backend is not escalated; it propagates unchanged, so a
  placeholder backend is visible rather than silently skipped.
- **R10** `content_sha256` is the SHA-256 hex digest (UTF-8) of the markdown if it is not `None`,
  else of the HTML (empty string if neither).
- **R11** `fetch_sync(url, request)` runs `fetch` to completion with `asyncio.run` and returns the
  same result. It cannot be called from inside a running event loop.
- **R12** `Scraper()` with no `backends` uses `Crawl4AIFetcher` (given `config.user_agent`) as
  `"crawl4ai"` and `BrightDataFetcher` as `"brightdata"`. A `backends` dict replaces both.
- **R13** `ScraperConfig()` defaults to `backend="crawl4ai"`, `fallbacks=["brightdata"]`,
  `min_chars=1500` and no sites. `ScraperConfig.from_yaml` raises `NotImplementedError`.

### Validation (`validate`)

- **R14** A result with no problems gives `[]`.
- **R15** HTTP status 400 or higher is a problem (`HTTP status <n>`).
- **R16** If the markdown (else the HTML) contains a bot-challenge phrase, case-insensitive, it is a
  problem (`looks like a bot-challenge page`). Phrases: `just a moment...`, `attention required`,
  `verify you are human`, `enable javascript and cookies to continue`.
- **R17** Content shorter than `request.min_chars` is a problem (`content too short`). Length is
  measured on the markdown, else the HTML.
- **R18** When `required_selector` is set and the result has HTML, the selector is a problem if
  absent. This is a substring check on the selector without its leading `.` or `#`, not a real CSS
  match.

### Crawl4AI backend (`Crawl4AIFetcher`)

- **R19** The request becomes Crawl4AI run options: `page_timeout` is `timeout_s` in milliseconds
  and `screenshot` is true only when `screenshot` is in `formats`.
- **R20** `scroll_to_bottom` turns on full-page scanning; `click_until_gone` adds JS that clicks
  the selector until it disappears or `max_iterations` is reached; `wait_for` waits for
  `css:<selector>` or a JS condition.
- **R21** If `required_selector` is set and no `wait_for` action exists, the backend waits for
  `css:<required_selector>` before capturing HTML.
- **R22** Crawl4AI takes one `wait_for`. The first is used; extra `wait_for` actions are dropped and
  a warning says so.
- **R23** `click_until_gone` without a selector, and `wait_for` without a selector or JS condition,
  raise `ValueError`.
- **R24** The Crawl4AI result carries only the requested formats. `final_url` is the redirected URL
  when there is one, else the requested URL. `backend` is `"crawl4ai"` and cost is 0.
- **R25** If `crawl4ai` is not installed, `fetch` raises `ImportError` that points to the
  `scraper` extra. It is a setup error and is not escalated.
- **R26** An unsuccessful crawl, or any exception from the browser (timeout, launch failure,
  unreachable host), raises `BackendError`.
- **R27** `render=False` turns JavaScript off; `user_agent` and `headless` from the fetcher are
  passed to the browser; the page cache is bypassed.

### Bright Data backend (`BrightDataFetcher`)

- **R28** Each request is `POST https://api.brightdata.com/request` with `Authorization: Bearer
  <key>` and a JSON body of `zone`, `url`, `format: "raw"`, plus `data_format: "markdown"` for the
  Markdown call and `country` when set. Markdown and HTML are separate calls, so asking for both
  makes two. Cost is `$0.0015` per call.
- **R29** Markdown is requested only when `markdown` is in `formats`. HTML is requested when `html`
  is in `formats` or when markdown is not requested, so `("markdown",)` makes one call and
  `("html",)` or `("screenshot",)` makes one HTML call.
- **R30** Actions and screenshots are not supported. Each adds a warning, actions are ignored, and
  `screenshot_png` stays `None`.
- **R31** `status` is the target site's status from the `x-brd-status-code` header (falling back
  to the HTTP status). `final_url` equals the requested URL, since redirects are not reported.
- **R32** An `x-brd-error` header raises `BackendError` that includes `x-brd-error-code`. Any
  non-200 HTTP response (bad key, unknown zone) raises `BackendError` with the status. A target
  4xx/5xx is not an error here: it comes back as a result and R15 decides whether to escalate.
- **R33** Timeouts and connection errors (`httpx.HTTPError`) raise `BackendError`.
- **R34** Credentials come from the constructor, else `BRIGHTDATA_API_KEY` and `BRIGHTDATA_ZONE`.
  If either is missing, `fetch` raises `BackendUnavailable` naming both variables.
- **R35** If `httpx` is not installed, importing the package still works and `fetch` raises
  `ImportError` that points to the `scraper` extra.

### Package

- **R36** The package exports `Scraper`, `ScraperConfig`, `SiteConfig`, `Action`, `FetchRequest`,
  `FetchResult`, `Fetcher`, `Crawl4AIFetcher`, `BrightDataFetcher` and the errors in section 5.

## 5. Errors

| Raised | When |
| --- | --- |
| `ScraperError` | Base class for the errors below |
| `BackendError` | A backend failed to fetch (R26, R32, R33). Escalated (R5) |
| `BackendUnavailable` (a `BackendError`) | Bright Data credentials missing (R34). Escalated (R5) |
| `AllBackendsFailed` | Every backend in the chain failed or returned an invalid page (R8) |
| `ValidationFailed` | Defined for callers, not raised by the scraper: problems are escalated or end in `AllBackendsFailed` |
| `ValueError` | Unknown backend in the chain (R3); malformed actions (R23) |
| `ImportError` | `crawl4ai` or `httpx` missing (R25, R35). Not escalated |
| `NotImplementedError` | A placeholder backend, or `ScraperConfig.from_yaml` (R9, R13). Not escalated |

## 6. Config and dependencies

- Optional extra `scraper`: `crawl4ai>=0.8.7` (earlier versions have critical CVEs) and `httpx`.
  Install with `uv sync --extra scraper`, then run `uv run crawl4ai-setup` once to download
  Chromium.
- Env vars (Bright Data fallback only): `BRIGHTDATA_API_KEY`, `BRIGHTDATA_ZONE`. See
  `.env.example`. The component reads the environment and does not load `.env` itself.
- Tests: unit tests use fakes and `httpx.MockTransport`. Integration tests need Chromium and are
  deselected by default (`uv run pytest -m integration`); the live Bright Data test also needs the
  env vars and uses free-tier quota.
- Setup and cost notes for Bright Data: `docs/brightdata-setup.md`.

## 7. Out of scope

Saving snapshots (use the `storage` component), extracting records from pages, per-domain rate
limiting, `robots.txt` checks, retries with backoff, YAML config loading, and extra backends such
as Zyte or Firecrawl. `rate_limit_s` exists in the config but is not enforced yet.
