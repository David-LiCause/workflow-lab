# text_to_structured_data

Turn Markdown or plain text into validated Pydantic rows using an LLM. Works for any text and any
row model. Rows that fail validation or have low confidence come back in `rejected` with the
reason, not silently dropped. Rules are in [SPEC.md](SPEC.md).

## Signature

```python
extract(
    text: str,
    row_model: type[BaseModel],
    llm: LLM,                       # ClaudeLLM, or MockLLM in tests
    instructions: str | None = None,
    *,
    min_confidence: float = 0.5,    # rows below this are rejected
    max_chunk_chars: int = 8000,    # long text is split on heading/paragraph boundaries
    cache_dir: str | PathLike | None = None,   # JSON cache; a hit makes no LLM call
) -> ExtractionResult

result.rows      # list[ExtractedRow]: .row (row_model), .extraction_confidence, .extraction_notes
result.rejected  # list[RejectedRow]: .raw, .reason, .kind, .extraction_confidence, .extraction_notes
```

Install: `uv sync --extra llm`. `ClaudeLLM` reads `ANTHROPIC_API_KEY` from the environment or a
git-ignored `.env` (copy `.env.example`). Empty text or no rows found gives an empty result.

The cache key is the text, the row model's schema, the instructions and the model name. The cache
holds the LLM's raw output, so changing `min_confidence` reuses it. Changing `max_chunk_chars`
does not invalidate it.

## Example

`row_model` is the template for one row. **Every field needs a `description`**: it's sent to the
LLM as the instruction for what goes in that field, and `extract` raises `ValueError` if one is
missing.

```python
from pydantic import BaseModel, Field

from workflow_lab.components.text_to_structured_data import extract
from workflow_lab.llm import ClaudeLLM


class Company(BaseModel):
    name: str = Field(description="Company name as written in the text.")
    hq: str | None = Field(None, description="City where the company is headquartered.")
    raised_usd: int | None = Field(
        None, description="Total funding raised, in whole US dollars (e.g. $12M -> 12000000)."
    )


report = "| Company | HQ | Raised |\n| --- | --- | --- |\n| Acme Health | Boston | $12M |"
result = extract(report, Company, ClaudeLLM("claude-sonnet-5-5"), cache_dir=".cache/extract")

for item in result.rows:
    print(item.row.name, item.extraction_confidence)
for bad in result.rejected:
    print("rejected:", bad.raw, bad.reason)
```

## Using it in LangGraph

```python
from typing import TypedDict

from langgraph.graph import StateGraph

from workflow_lab.components.text_to_structured_data import extract
from workflow_lab.llm import ClaudeLLM


class State(TypedDict, total=False):
    report: str
    companies: list[Company]
    rejected: list[dict]


def extract_companies(state: State) -> dict:
    result = extract(state["report"], Company, ClaudeLLM(), cache_dir=".cache/extract")
    return {
        "companies": [r.row for r in result.rows],
        "rejected": [{"raw": r.raw, "reason": r.reason} for r in result.rejected],
    }


graph = StateGraph(State)
graph.add_node("extract_companies", extract_companies)
```
