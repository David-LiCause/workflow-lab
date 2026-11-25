# workflow-lab

A workspace for building agentic workflows: reusable components, and LangGraph workflows built
from them.

## Layout

```
packages/     # reusable libraries
  workflow-lab/   # components: LLM client, storage, database, text → structured data, web scraping
workflows/    # LangGraph workflows built from the components, one package per project
apps/         # (later) app to run workflows and view results
notebooks/    # marimo notebooks for querying workflow data
data/         # git-ignored: workflow data from local runs (see "Workflow data")
```

| Part | Status | What it holds |
| --- | --- | --- |
| [`packages/workflow-lab`](packages/workflow-lab/README.md) | Done | Plain-Python components with no LangGraph imports; installable on its own with optional extras |
| [`workflows/health-ai-research-digest`](workflows/health-ai-research-digest/README.md) | In progress | Weekly digest of new health AI research: fetches arXiv papers, structures each abstract with an LLM, and writes a summary by clinical area |
| [`workflows/healthtech-news-events`](workflows/healthtech-news-events/README.md) | Done | Tracks health tech industry news (funding rounds, acquisitions, IPOs, layoffs) scraped from news sites into a database |
| [`workflows/healthtech-market-landscape-boston`](workflows/healthtech-market-landscape-boston/README.md) | In progress | Maps the Boston healthcare and health tech ecosystem: extracts organizations from research reports and merges them into one deduplicated table |
| `apps/` | Later | A fuller app with extra tooling (start runs, watch progress, browse results). Until then, use LangGraph Studio (see "View and debug workflows") |

Each folder under `packages/`, `workflows/` and `apps/` is a uv workspace member with its own
`pyproject.toml`. Adding one is just creating the folder; they share one `uv.lock` and `.env`.

## Workflows

Each project under `workflows/` is one package with one LangGraph graph per workflow:

```
workflows/<project>/
  src/<package>/
    context.py        # Context: plain settings (storage root, db URL, ...) → storage, db
    models.py         # row models and tables shared by the project's workflows
    <workflow>/       # e.g. discovery/, later enrichment/
      state.py        # typed state; lists written by parallel nodes get a reducer
      nodes.py        # one function per node: read state, call a component, return an update
      graph.py        # wires the nodes; exports the compiled `graph`
      __main__.py     # run entry point
  tests/
```

- Nodes get their services from LangGraph's runtime context (`runtime.context`), not globals, so
  tests point them at temp folders.
- Run a workflow from the workspace root: `uv run python -m <package>.<workflow>`.
- Code that becomes useful across projects moves into `packages/workflow-lab`.

## View and debug workflows

LangGraph Studio is the tool for now. From the workspace root:

```bash
make studio        # runs `uv run langgraph dev` on http://127.0.0.1:2024 and opens Studio
```

Studio shows each graph registered in `langgraph.json`, runs it, and shows the state after each
node. Its web UI needs a free LangSmith login; graphs still run locally, against the same `data/`
folder as the CLI. Runs started in Studio use the `Context` defaults (env vars, then `data/`)
unless you set context values in Studio's assistant settings.

To add a workflow to Studio, add its package to `dependencies` and its graph to `graphs` in
`langgraph.json`, as `"<package>.<workflow>.graph:graph"`. Context must stay JSON-serializable:
plain settings, with nodes opening services from them.

To print a graph without Studio:

```bash
uv run python -c "from <package>.<workflow>.graph import graph; print(graph.get_graph().draw_mermaid())"
```

## Query workflow data

```bash
make notebook      # opens notebooks/explore.py in marimo
```

The notebook attaches every workflow's database read-only to marimo's built-in DuckDB engine,
one database per workflow: SQLite files in `data/db/<workflow>/`, plus any
`<WORKFLOW>_DATABASE_URL` in `.env` (SQLite or Postgres). Browse tables in marimo's Data Sources
panel and query them in SQL cells as `<database>.<table>`; tables from different workflows can be
joined. Add notebooks alongside it; they're plain `.py` files and hold no data.

## Workflow data

Workflow code is committed. The data a workflow reads and writes is not: locally it lives in the
git-ignored `data/` folder, split by type so it maps onto cloud storage and a cloud database.

```
data/
  storage/<workflow>/     # files: reports, snapshots, extraction cache, run logs → later a bucket
  db/<workflow>/<name>.db # SQLite database → later Postgres
```

Each workflow gets two settings, with these local defaults:

| Setting | Default | Used by |
| --- | --- | --- |
| `<WORKFLOW>_STORAGE_ROOT` | `data/storage/<workflow>` | `Storage(root)` |
| `<WORKFLOW>_DATABASE_URL` | `sqlite:///data/db/<workflow>/<name>.db` | `Database(url)` |

To move a workflow to the cloud, set both in `.env` (for example `s3://my-bucket/<workflow>` and a
Supabase URL). The code does not change. The defaults are relative paths, so run workflows from the
workspace root. `data/` exists only in this clone, so back it up if you need it.

## Develop

```bash
uv sync --all-packages           # all members + dev tools
cp .env.example .env             # then fill in what you need
uv run pytest                    # unit tests (integration: add -m integration)
uv run ruff check . && uv run ruff format .
```

New components are built with the `new-component` skill (`.agents/skills/`). Testing details are
in the [workflow-lab package README](packages/workflow-lab/README.md#testing).
