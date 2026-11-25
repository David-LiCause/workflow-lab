# db

Store and read Pydantic rows in a SQL database through one small interface. SQLite today;
Postgres later by changing only the URL. Rules are in [SPEC.md](SPEC.md).

## Signature

```python
Database(url: str | None = None)             # default: DATABASE_URL env var

ensure_table(name, model, key) -> None       # key: field name or list of names (primary key)
upsert(name, rows) -> UpsertResult           # (inserted, updated); one transaction
read(name, model, where=None) -> list[model] # where: equality filters, e.g. {"status": "new"}
close() -> None
```

- Lists, dicts and nested models are stored as JSON and come back as the same type.
- Dates round-trip. Datetimes are stored in UTC and come back timezone-aware (naive in = UTC).
- Upserting unchanged rows returns `(0, 0)`.
- Errors: `UnknownTableError`, `RowMismatchError`, `SchemaMismatchError`. Call `ensure_table` on
  every `Database` before `upsert` or `read`. It is cheap and does nothing if the table exists.
- `where` can't filter on JSON fields (lists, dicts, nested models).

Install: `uv sync --extra db`. No Postgres driver is included. To move to Postgres, add one
(for example `uv add "psycopg[binary]"`) and set `DATABASE_URL` to
`postgresql+psycopg://user:pass@host:5432/dbname`. Name the driver in the URL: a plain
`postgresql://` or `postgres://` URL (Supabase) makes SQLAlchemy look for `psycopg2` instead.

## Example

```python
from pydantic import BaseModel, Field

from workflow_lab.components.db import Database


class Company(BaseModel):
    domain: str
    name: str
    status: str = "new"
    sources: list[str] = Field(default_factory=list)


db = Database("sqlite:///data/companies.db")  # later: Database() with DATABASE_URL set
db.ensure_table("companies", Company, key="domain")

db.upsert("companies", [Company(domain="acme.com", name="Acme", sources=["vc"])])
# UpsertResult(inserted=1, updated=0)
db.upsert("companies", [Company(domain="acme.com", name="Acme", sources=["vc"])])
# UpsertResult(inserted=0, updated=0)

new = db.read("companies", Company, where={"status": "new"})
```

## Using it in LangGraph

```python
from typing import TypedDict

from langgraph.graph import StateGraph

from workflow_lab.components.db import Database

db = Database()  # DATABASE_URL
db.ensure_table("companies", Company, key="domain")


class State(TypedDict, total=False):
    companies: list[Company]
    saved: dict[str, int]


def save_companies(state: State) -> dict:
    result = db.upsert("companies", state["companies"])
    return {"saved": {"inserted": result.inserted, "updated": result.updated}}


graph = StateGraph(State)
graph.add_node("save_companies", save_companies)
```
