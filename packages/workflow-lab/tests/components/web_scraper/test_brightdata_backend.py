"""Bright Data backend tests (R28-R35) using httpx's mock transport. No network, no credentials."""

import json

import httpx
import pytest

from workflow_lab.components.web_scraper import (
    Action,
    BackendError,
    BackendUnavailable,
    BrightDataFetcher,
    FetchRequest,
)
from workflow_lab.components.web_scraper.backends import brightdata as brightdata_module


def fetcher(handler, **kwargs) -> BrightDataFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BrightDataFetcher(api_key="key", zone="zone1", client=client, **kwargs)


def ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    text = "# markdown" if body.get("data_format") == "markdown" else "<h1>html</h1>"
    return httpx.Response(200, text=text, headers={"x-brd-status-code": "200"})


async def test_r28_markdown_and_html_two_requests():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer key"
        return ok(request)

    result = await fetcher(handler, country="us").fetch(FetchRequest(url="https://x.test"))
    assert (result.markdown, result.html) == ("# markdown", "<h1>html</h1>")
    assert result.status == 200 and result.backend == "brightdata"
    assert result.cost_estimate_usd == pytest.approx(0.003)
    assert {b.get("data_format") for b in seen} == {"markdown", None}
    assert all(b["zone"] == "zone1" and b["format"] == "raw" and b["country"] == "us" for b in seen)


async def test_r29_markdown_only_is_one_request():
    result = await fetcher(ok).fetch(FetchRequest(url="https://x.test", formats=("markdown",)))
    assert result.markdown == "# markdown" and result.html is None
    assert result.cost_estimate_usd == pytest.approx(0.0015)


async def test_r30_warns_on_actions_and_screenshot():
    req = FetchRequest(
        url="https://x.test",
        actions=(Action("scroll_to_bottom"),),
        formats=("markdown", "screenshot"),
    )
    result = await fetcher(ok).fetch(req)
    assert len(result.warnings) == 2 and result.screenshot_png is None


async def test_r31_target_status_from_header():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Not found", headers={"x-brd-status-code": "404"})

    result = await fetcher(handler).fetch(FetchRequest(url="https://x.test", formats=("html",)))
    assert result.status == 404


async def test_r32_unlocker_error_header_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"x-brd-error": "nav failed", "x-brd-error-code": "net_err"}
        )

    with pytest.raises(BackendError, match="net_err"):
        await fetcher(handler).fetch(FetchRequest(url="https://x.test"))


async def test_r32_auth_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="User authentication is required")

    with pytest.raises(BackendError, match="401"):
        await fetcher(handler).fetch(FetchRequest(url="https://x.test"))


async def test_r33_timeout_raises_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(BackendError):
        await fetcher(handler).fetch(FetchRequest(url="https://x.test"))


async def test_r34_missing_credentials(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    with pytest.raises(BackendUnavailable):
        await BrightDataFetcher().fetch(FetchRequest(url="https://x.test"))


async def test_r29_html_only_is_one_request_without_markdown_format():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return ok(request)

    result = await fetcher(handler).fetch(FetchRequest(url="https://x.test", formats=("html",)))
    assert result.html == "<h1>html</h1>" and result.markdown is None
    assert len(seen) == 1 and "data_format" not in seen[0]


async def test_r29_screenshot_only_still_fetches_html():
    req = FetchRequest(url="https://x.test", formats=("screenshot",))
    result = await fetcher(ok).fetch(req)
    assert result.html == "<h1>html</h1>" and result.markdown is None


async def test_r31_final_url_equals_url():
    result = await fetcher(ok).fetch(FetchRequest(url="https://x.test/a", formats=("html",)))
    assert result.final_url == "https://x.test/a"


async def test_r34_credentials_read_from_environment(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "env-key")
    monkeypatch.setenv("BRIGHTDATA_ZONE", "env-zone")
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"auth": request.headers["authorization"], **json.loads(request.content)})
        return ok(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await BrightDataFetcher(client=client).fetch(FetchRequest(url="https://x.test"))
    assert all(b["auth"] == "Bearer env-key" and b["zone"] == "env-zone" for b in seen)


async def test_r35_missing_httpx_raises_import_error(monkeypatch):
    monkeypatch.setattr(brightdata_module, "httpx", None)
    with pytest.raises(ImportError, match="scraper"):
        await BrightDataFetcher(api_key="key", zone="zone1").fetch(
            FetchRequest(url="https://x.test")
        )
