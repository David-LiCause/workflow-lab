"""Fixtures for integration tests: a local web server and a real-browser availability check."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

LOAD_MORE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Portfolio</title></head>
<body><h1>Portfolio companies</h1><ul id="list"></ul>
<button class="load-more" onclick="more()">Load more</button>
<script>
let n = 0;
function more() {
  setTimeout(() => {
    for (let i = 0; i < 5; i++) {
      const li = document.createElement('li');
      li.className = 'portfolio-item';
      li.textContent = 'Company ' + (++n) + ' - a health tech company with a long description.';
      document.getElementById('list').appendChild(li);
    }
    if (n >= 15) document.querySelector('.load-more').remove();
  }, 200);
}
more();
</script></body></html>"""

BLOCKED_PAGE = (
    "<!doctype html><html><head><title>Just a moment...</title></head>"
    "<body><h1>Just a moment...</h1><p>Verify you are human.</p></body></html>"
)

PAGES = {"/list": (200, LOAD_MORE_PAGE), "/blocked": (200, BLOCKED_PAGE), "/missing": (404, "nope")}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib name)
        status, body = PAGES.get(self.path, (404, "not found"))
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # keep test output quiet
        pass


@pytest.fixture(scope="session")
def site() -> Iterator[str]:
    """Base URL of a local server serving /list, /blocked and /missing."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session", autouse=True)
def require_browser() -> None:
    """Fail the whole integration suite if Playwright can't launch Chromium."""
    from playwright.async_api import async_playwright

    async def probe() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            await browser.close()

    try:
        asyncio.run(probe())
    except Exception as exc:
        pytest.fail(
            f"Chromium not available (run `crawl4ai-setup`): {str(exc)[:80]}", pytrace=False
        )
