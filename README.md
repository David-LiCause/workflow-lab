# workflow-lab

A workspace for building agentic workflows: reusable components, LangGraph workflows built from
them, and an app to run them.

## Layout

```
packages/     # reusable libraries
  workflow-lab/   # components: LLM client, storage, database, text → structured data, web scraping
workflows/    # (planned) LangGraph workflows built from the components
apps/         # (planned) app to run workflows and view results
```

| Part | Status | What it holds |
| --- | --- | --- |
| [`packages/workflow-lab`](packages/workflow-lab/README.md) | Done | Plain-Python components with no LangGraph imports; installable on its own with optional extras |
| `workflows/` | Planned | One folder per LangGraph workflow: state, thin node wrappers over components, a run entry point |
| `apps/` | Planned | A runner app: start a workflow, watch progress, browse results. Start with `langgraph dev` (LangGraph Studio) for debugging and a small Streamlit app for running; host it later in a container |

Each folder under `packages/`, `workflows/` and `apps/` is a uv workspace member with its own
`pyproject.toml`. Adding one is just creating the folder; they share one `uv.lock` and `.env`.

## Develop

```bash
uv sync --all-packages           # all members + dev tools
cp .env.example .env             # then fill in what you need
uv run pytest                    # unit tests (integration: add -m integration)
uv run ruff check . && uv run ruff format .
```

New components are built with the `new-component` skill (`.agents/skills/`). Testing details are
in the [workflow-lab package README](packages/workflow-lab/README.md#testing).
