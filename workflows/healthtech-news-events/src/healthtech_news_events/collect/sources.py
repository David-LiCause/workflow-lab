"""The news sites Collect reads. Each becomes one ``scrape_<name>`` node.

Chosen after checking each site's robots.txt: these three allow general crawlers. STAT,
MobiHealthNews and Healthcare IT News block AI crawlers (``anthropic-ai`` / ``ClaudeBot``), and
Becker's sits behind a captcha, so they are left out. Re-check robots.txt and the terms of use
before adding a site.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class NewsSource:
    name: str  # node scrape_<name>; snapshots/news/<name>-<page>_<date>.md
    site: str  # for the LLM instructions
    pages: tuple[tuple[str, str], ...]  # (page name, listing page URL)
    crawl_delay_s: float = 5.0  # wait between pages of this site (Healthcare Dive asks for 5)

    @property
    def node(self) -> str:
        return f"scrape_{self.name}"

    def instructions(self, fetched_on: date) -> str:
        return f"""\
The text is part of a news listing page from {self.site}, fetched on {fetched_on.isoformat()}. \
Return one row per article reporting a funding round, a layoff, an acquisition or merger, or an \
IPO (or IPO filing). Skip every other article, and all sponsored posts, opinion, podcasts, \
newsletters and navigation. If this part of the text has no such articles, return no rows.
- Copy the company name and headline as written; do not research or guess. Use null for an amount \
or headcount the page does not state.
- Each article's date is shown next to its headline. Resolve relative dates ("2 hours ago", \
"yesterday") from the fetch date above. If an article shows no date, still return the row and use \
the fetch date.
- article_url is the full URL of the link on the headline.
- If one article is about several companies, return one row per company."""


SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        name="healthcaredive",
        site="Healthcare Dive",
        pages=(
            ("health-it", "https://www.healthcaredive.com/topic/health-it/"),
            ("finance", "https://www.healthcaredive.com/topic/finance/"),
        ),
    ),
    NewsSource(
        name="fierce",
        site="Fierce Healthcare",
        pages=(
            ("health-tech", "https://www.fiercehealthcare.com/health-tech"),
            ("finance", "https://www.fiercehealthcare.com/finance"),
        ),
    ),
    NewsSource(
        name="medcity",
        site="MedCity News",
        pages=(("health-tech", "https://medcitynews.com/category/health-tech/"),),
    ),
)
