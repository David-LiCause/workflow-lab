"""validate() rules (R14-R18)."""

from workflow_lab.components.web_scraper import FetchRequest, FetchResult
from workflow_lab.components.web_scraper.validation import validate


def result(markdown="x" * 50, html=None, status=200) -> FetchResult:
    return FetchResult(
        url="https://x.test",
        final_url="https://x.test",
        status=status,
        backend="t",
        markdown=markdown,
        html=html,
    )


def test_r14_valid_result_has_no_problems():
    assert validate(FetchRequest(url="https://x.test", min_chars=10), result()) == []


def test_r15_http_error_status():
    assert any("404" in p for p in validate(FetchRequest(url="u"), result(status=404)))


def test_r16_challenge_page_detected():
    problems = validate(FetchRequest(url="u"), result(markdown="Just a moment... please wait"))
    assert any("challenge" in p for p in problems)


def test_r17_too_short():
    problems = validate(FetchRequest(url="u", min_chars=100), result(markdown="tiny"))
    assert any("too short" in p for p in problems)


def test_r18_required_selector_missing_and_present():
    req = FetchRequest(url="u", required_selector=".card")
    assert validate(req, result(html="<div class='nope'></div>"))
    assert validate(req, result(html="<div class='card'></div>")) == []


def test_r17_html_used_when_no_markdown():
    problems = validate(FetchRequest(url="u", min_chars=5), result(markdown=None, html="<p>hi</p>"))
    assert not any("too short" in p for p in problems)
