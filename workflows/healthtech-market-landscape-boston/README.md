# healthtech-market-landscape-boston

Builds a market map of Boston-area healthcare and health tech companies, for market research. Workflow 1,
**Discovery**, finds the companies; Workflow 2, Enrichment, is planned.

Discovery reads three research reports in parallel, merges them, and writes the `companies`
table:

```
START ─┬─ extract_incumbents ─┐
       ├─ extract_big_tech ───┼─► merge ─► export ─► END
       └─ extract_landscape ──┘
```

- Sources are defined in `discovery/sources.py` (report prefix, row model, CSV columns,
  archetype). Each `extract_<source>` node takes the newest
  `research/reports/<source>_<YYYY-MM-DD>.md` and sends it to Claude through the
  `text_to_structured_data` component (in ~8,000-character chunks; the instructions give the CSV
  column order). Output is cached under `cache/extract/`, so unchanged reports make no API calls.
  A missing report is logged as an error; the other sources still run.
- Each row gets a `key`: its website domain, or `name:<normalized name>` if it has no website. Big
  tech units are keyed `<parent>/<unit>` (e.g. `alphabet/isomorphic-labs`), since several share
  the parent's site.
- `merge` dedupes across sources by key, folding a row without a website into a company with the
  same normalized name. It keeps every source, and the lowest extraction confidence.
- `export` writes the full rows to `extracted_<source>`, rejects and in-source duplicates to
  `review_queue`, and companies to `companies` with `first_seen`, `last_seen` and `status`
  (`new` on the first day, then `active`; `missing` when no longer found, never deleted).

```bash
uv run python -m healthtech_market_landscape_boston.discovery   # from the workspace root
uv run pytest workflows/healthtech-market-landscape-boston
```

Nodes get `storage`, `db`, `llm` and `run_date` from the runtime `Context` (`context.py`), which
holds plain settings (including `model`, the Claude model). Claude credentials come from
`ANTHROPIC_API_KEY` or an `ant auth login` sign-in. In Studio (`make studio` from the workspace root) this graph is
`healthtech_discovery`. Data goes to the git-ignored `data/` folder unless these are set:

| Env var | Default |
| --- | --- |
| `HEALTHTECH_MARKET_LANDSCAPE_BOSTON_STORAGE_ROOT` | `data/storage/healthtech-market-landscape-boston` |
| `HEALTHTECH_MARKET_LANDSCAPE_BOSTON_DATABASE_URL` | `sqlite:///data/db/healthtech-market-landscape-boston/companies.db` |
