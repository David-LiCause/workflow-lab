from datetime import date

import pytest

from health_ai_research_digest.digest.arxiv import build_query, fetch_feed, parse_feed

pytestmark = pytest.mark.integration


def test_real_arxiv_query_returns_papers():
    xml = fetch_feed(build_query(date.today(), 7), max_results=5)

    papers = parse_feed(xml)

    assert 0 < len(papers) <= 5
    assert all(p.arxiv_id and p.title and p.abstract for p in papers)
