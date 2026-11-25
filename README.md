# agents-playground

Reusable building blocks for composing agentic **workflows**: graphs that mix deterministic steps
with AI steps. LangGraph (or similar) does the wiring; this library provides the pieces that
workflow nodes call. See `PRD.md` for intent and roadmap.

## Layout

```
src/agents_playground/
  llm/          # LLM interface + MockLLM, so model providers and mocks are swappable
  components/   # reusable building blocks that workflow nodes call
```

| Folder | Holds | Status |
| --- | --- | --- |
| `llm/` | `LLM` interface (`complete`, `complete_structured`), `Message`, `MockLLM`, `ClaudeLLM` | Done. `ClaudeLLM` needs the `llm` extra |
| `components/` | `text_to_structured_data` (text → structured rows), `db` (database read/write), `storage` (file read/write), `web_scraper` (page fetching) | `storage`, `db`, `text_to_structured_data`, `web_scraper` done |

### Components

| Component | What it does | Extra |
| --- | --- | --- |
| [`storage`](src/agents_playground/components/storage/README.md) | Read, write and list files under one root: local path now, `s3://` / `gs://` later | `storage` |
| [`db`](src/agents_playground/components/db/README.md) | Store and read Pydantic rows in a SQL database: SQLite now, Postgres later by changing the URL | `db` |
| [`text_to_structured_data`](src/agents_playground/components/text_to_structured_data/README.md) | Turn Markdown or plain text into validated Pydantic rows with an LLM; bad or low-confidence rows are returned as rejected, with the reason | `llm` |
| [`web_scraper`](src/agents_playground/components/web_scraper/README.md) | Fetch a page (including JavaScript-rendered content) as Markdown, HTML or a screenshot; escalates from a local browser (Crawl4AI) to Bright Data when blocked | `scraper` |

Components are plain Python with no workflow-framework imports, so they stay reusable and testable
on their own. Each project's workflow nodes are thin wrappers that call them.

## Planned later (not included yet)

- `nodes/`: LangGraph node factories, once node wrappers start repeating across projects
- `evals/`: run tracing and golden-case tests
- `examples/`: small runnable example workflows

## Develop

```bash
uv sync
uv run pytest && uv run ruff check .
```

## Testing

| Tier | Where | Runs | Needs |
| --- | --- | --- | --- |
| Unit | `tests/components/<name>/test_<name>.py` | By default | Nothing: fakes, temp files, local SQLite |
| Integration | `tests/components/<name>/integration/` | Only with `-m integration` | Real services and keys from `.env` |

```bash
uv run pytest                                      # unit only (default)
uv run pytest -m integration                       # all integration tests
uv run pytest -m integration tests/components/db   # one component
```

- Copy `.env.example` to `.env` and fill in what you need.
- `ANTHROPIC_API_KEY` is optional locally: if you are signed in with `ant auth login`, the
  Anthropic SDK uses that sign-in. Set the key for unattended runs (CI or cloud jobs). Claude tests
  use the `require_anthropic_credentials` fixture, which **fails** if neither is available.
- Other integration tests call `require_env("VAR")` (from `tests/conftest.py`), which **fails** the test
  when a variable is missing, so an unrun test is visible.
- Use dedicated test resources, unique names or prefixes per run, and clean up afterwards.

### Local Postgres for `db` integration tests

```bash
docker run -d --rm --name agents-playground-test-db -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=agents_playground_test -p 5432:5432 postgres:17
```

Then put this in `.env` and run `uv run pytest -m integration tests/components/db`:

```
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agents_playground_test
```

Stop it with `docker stop agents-playground-test-db` (`--rm` deletes the container). The tests
create `it_*` tables with a random suffix and drop them afterwards.
