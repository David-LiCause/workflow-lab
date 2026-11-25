# healthtech-news-events

Tracks funding rounds, layoffs, acquisitions and IPOs in health tech, from news sites. Workflow 1,
**Collect**, scrapes a few news listing pages and stores the events it finds.

Collect reads each site in parallel, merges the events, and writes the `events` table:

```
START ─┬─ scrape_healthcaredive ─┐
       ├─ scrape_fierce ─────────┼─► merge ─► export ─► END
       └─ scrape_medcity ────────┘
```

- Sources are defined in `collect/sources.py`: a site and its listing pages (Healthcare Dive and
  Fierce Healthcare: health IT / health tech and finance; MedCity News: health tech). Each
  `scrape_<site>` node fetches its pages one at a time, with a delay between them, through the
  `web_scraper` component (local browser only: the paid Bright Data fallback is off unless
  `use_unlocker` is set). A page that fails to load is logged as an error; the other pages and
  sites still run.
- Each page is cleaned (images and the navigation above the first article are dropped), saved to
  `snapshots/news/<site>-<page>_<YYYY-MM-DD>.md`, and sent to Claude through
  `text_to_structured_data`. Output is cached under `cache/extract/`, so an unchanged page makes no
  API calls. The instructions tell the LLM to keep only funding, layoff, acquisition and IPO
  articles and to skip everything else.
- Each event gets a `key`: `<normalized company>|<event_type>|<event_date>`. `merge` dedupes by key,
  so one story on several pages or sites becomes one event that lists every source and URL, with
  the lowest extraction confidence.
- `export` writes `events` and `review_queue` (rows that failed validation or had low confidence).
  Events are never removed; an event found again keeps its `first_seen` and gains any new sources.

```bash
uv run python -m healthtech_news_events.collect   # from the workspace root
uv run pytest workflows/healthtech-news-events
```

Needs the local browser (`uv run crawl4ai-setup`, once) and Claude credentials (`ANTHROPIC_API_KEY`
or an `ant auth login` sign-in). Nodes get `storage`, `db`, `llm` and `scraper` from the runtime
`Context` (`context.py`), which holds plain settings. In Studio (`make studio`) this graph is
`healthtech_news_collect`. Data goes to the git-ignored `data/` folder unless these are set:

| Env var | Default |
| --- | --- |
| `HEALTHTECH_NEWS_EVENTS_STORAGE_ROOT` | `data/storage/healthtech-news-events` |
| `HEALTHTECH_NEWS_EVENTS_DATABASE_URL` | `sqlite:///data/db/healthtech-news-events/events.db` |

## Adding a site

Check its `robots.txt` and terms of use first. Left out so far: STAT, MobiHealthNews and Healthcare
IT News (they block AI crawlers such as `anthropic-ai` and `ClaudeBot`) and Becker's (a captcha).
Then add a `NewsSource` to `SOURCES`; the graph builds its node.

## Known limits

- It reads headlines and summaries on listing pages, not full articles.
- A merger can produce one event per party (for example Rush and Endeavor).
- Different dates on the same story (for example, two sites a day apart) make separate events.
- `normalize_name` is copied from the Discovery workflow; move it to `workflow-lab` if a third
  workflow needs it.
