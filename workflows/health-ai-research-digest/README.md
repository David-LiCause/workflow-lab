# health-ai-research-digest

A weekly digest of new health AI papers. It pulls the week's arXiv submissions in AI/ML
categories whose abstracts mention health terms, has Claude turn each abstract into structured
findings, stores them, and writes a short Markdown digest grouped by clinical area.

```
START → fetch_papers → extract → export → END
```

- `fetch_papers`: one arXiv API request (`digest/arxiv.py`) for papers submitted in the
  `lookback_days` ending `run_date`, in `cs.LG`, `cs.AI`, `cs.CL`, `cs.CV` or `eess.IV`, whose
  abstract mentions clinical, medical, health, patient or hospital; up to `max_papers`. The raw
  feed is saved to `feeds/arxiv_<run_date>.xml` and reused if the run is repeated that day.
- `extract`: one `text_to_structured_data` call per paper (title + abstract → `PaperFindings`:
  whether it's health AI, a one-line summary, task, clinical area, data modality, datasets, model
  approach, headline result). Output is cached per paper under `cache/extract/`, so reruns only
  pay for new papers. Rejected findings go to the review queue.
- `export`: upserts the `papers` table (key `arxiv_id`, keeping `first_seen`) and
  `review_queue`, and writes `digests/digest_<run_date>.md`.

```bash
uv run python -m health_ai_research_digest.digest   # from the workspace root
uv run pytest workflows/health-ai-research-digest   # add -m integration for a real arXiv request
```

Nodes get `storage`, `db`, `llm` and settings from the runtime `Context` (`context.py`):
`run_date`, `lookback_days` (7), `max_papers` (50) and `model`. In Studio (`make studio`) the
graph is `health_ai_digest`; `make notebook` shows its tables. Data goes to the git-ignored
`data/` folder unless these are set:

| Env var | Default |
| --- | --- |
| `HEALTH_AI_RESEARCH_DIGEST_STORAGE_ROOT` | `data/storage/health-ai-research-digest` |
| `HEALTH_AI_RESEARCH_DIGEST_DATABASE_URL` | `sqlite:///data/db/health-ai-research-digest/papers.db` |
