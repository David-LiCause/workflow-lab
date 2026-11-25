# storage

Read, write and list files through one interface, rooted at a local path now and an `s3://` or
`gs://` URL later. Switching is a config change. Rules are in [SPEC.md](SPEC.md).

## Signature

```python
Storage(root: str | os.PathLike)          # local path or URL

read_text(path) -> str                    # UTF-8; FileNotFoundError if missing
write_text(path, text) -> None            # creates parent folders, overwrites
read_bytes(path) -> bytes
write_bytes(path, data) -> None
exists(path) -> bool                      # files only
list(pattern="**/*") -> list[str]         # sorted, relative to root, files only
latest(pattern) -> str | None             # newest YYYY-MM-DD in the filename
```

Paths are relative to the root. Anything that escapes it (`..`, absolute paths) raises
`PathEscapesRootError`.

Install: `uv sync --extra storage`. Cloud backends (`s3fs`, `gcsfs`) and credentials are yours to add.

Integration tests will be added with cloud backend support.

## Example

```python
from agents_playground.components.storage import Storage

store = Storage("data")  # later: Storage("s3://my-bucket/health-tech")
store.write_text("snapshots/vc/a16z_2026-11-20.md", "# a16z portfolio\n...")

store.list("snapshots/vc/*.md")  # ["snapshots/vc/a16z_2026-11-20.md"]
path = store.latest("research/incumbents_*.md")
report = store.read_text(path) if path else ""
```

## Using it in LangGraph

```python
from typing import TypedDict

from langgraph.graph import StateGraph

from agents_playground.components.storage import Storage


class State(TypedDict, total=False):
    storage_root: str
    report_path: str | None
    report: str


def load_latest_report(state: State) -> dict:
    store = Storage(state["storage_root"])
    path = store.latest("research/incumbents_*.md")
    return {"report_path": path, "report": store.read_text(path) if path else ""}


graph = StateGraph(State)
graph.add_node("load_latest_report", load_latest_report)
```
