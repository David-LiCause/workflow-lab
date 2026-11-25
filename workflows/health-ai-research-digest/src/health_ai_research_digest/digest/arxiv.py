"""The arXiv API: build the query, fetch the Atom feed, parse it into papers.

API docs: https://info.arxiv.org/help/api/user-manual.html. One request per run, well within
arXiv's limit of one request every three seconds.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

from ..models import Paper

API_URL = "https://export.arxiv.org/api/query"
CATEGORIES = ("cs.LG", "cs.AI", "cs.CL", "cs.CV", "eess.IV")
HEALTH_TERMS = ("clinical", "medical", "health", "patient", "hospital")
_NS = {"atom": "http://www.w3.org/2005/Atom"}


def build_query(end: date, lookback_days: int) -> str:
    """AI/ML papers whose abstract mentions health terms, submitted in the window."""
    start = end - timedelta(days=lookback_days - 1)
    cats = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    terms = " OR ".join(f"abs:{t}" for t in HEALTH_TERMS)
    window = f"submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
    return f"({cats}) AND ({terms}) AND {window}"


def fetch_feed(query: str, max_results: int, client: httpx.Client | None = None) -> str:
    """The raw Atom XML for ``query``, newest first. Raises ``httpx.HTTPError`` on failure."""
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    with client or httpx.Client(timeout=60, follow_redirects=True) as http:
        response = http.get(API_URL, params=params)
        response.raise_for_status()
        return response.text


def parse_feed(xml: str) -> list[Paper]:
    """Papers in an Atom feed. Raises ``ValueError`` if arXiv returned an error entry."""
    root = ET.fromstring(xml)
    papers = []
    for entry in root.findall("atom:entry", _NS):
        entry_id = _text(entry, "atom:id")
        if "/api/errors" in entry_id:
            raise ValueError(f"arXiv API error: {_text(entry, 'atom:summary')}")
        arxiv_id = re.sub(r"v\d+$", "", entry_id.rsplit("/abs/", 1)[-1])
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_text(entry, "atom:title"),
                authors=[_text(a, "atom:name") for a in entry.findall("atom:author", _NS)],
                published=date.fromisoformat(_text(entry, "atom:published")[:10]),
                categories=[c.get("term", "") for c in entry.findall("atom:category", _NS)],
                abstract=_text(entry, "atom:summary"),
                url=f"https://arxiv.org/abs/{arxiv_id}",
            )
        )
    return papers


def _text(element: ET.Element, path: str) -> str:
    """Text of the child at ``path``, with whitespace collapsed (titles wrap across lines)."""
    child = element.find(path, _NS)
    return " ".join((child.text or "").split()) if child is not None else ""
