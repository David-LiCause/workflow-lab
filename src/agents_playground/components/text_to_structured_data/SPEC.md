# text_to_structured_data

## 1. Purpose

Turn Markdown or plain text into validated Pydantic rows using an LLM. Works for any text and any
row model. Rows that fail validation or confidence are returned separately, not dropped.

## 2. Interface

```python
T = TypeVar("T", bound=BaseModel)


@dataclass
class ExtractedRow(Generic[T]):
    row: T  # validated instance of row_model
    extraction_confidence: float  # 0-1, from the LLM
    extraction_notes: str


@dataclass
class RejectedRow:
    raw: dict[str, Any] | str  # the LLM's row data (parsed JSON object, or the raw string)
    reason: str  # validation error text, or why confidence was too low
    kind: Literal["validation_error", "low_confidence"]
    extraction_confidence: float | None
    extraction_notes: str


@dataclass
class ExtractionResult(Generic[T]):
    rows: list[ExtractedRow[T]]
    rejected: list[RejectedRow]


def extract(
    text: str,
    row_model: type[T],
    llm: LLM,
    instructions: str | None = None,
    *,
    min_confidence: float = 0.5,
    max_chunk_chars: int = 8000,
    cache_dir: str | os.PathLike[str] | None = None,
) -> ExtractionResult[T]: ...


def split_into_chunks(text: str, max_chars: int) -> list[str]: ...
```

LLM interface used: `llm.complete_structured(messages, schema)` and `llm.model` (see `llm/`).

## 3. Inputs and outputs

- `text`: Markdown or plain text.
- `row_model`: any Pydantic model; one row is extracted per record found in the text. **Every
  field must have a description** (`Field(description=...)`) saying what the LLM should extract
  into it (R19). The model does not declare `extraction_confidence` / `extraction_notes`; they are
  added by the component.
- `instructions`: optional extra guidance appended to the prompt (what counts as a record, how to
  fill ambiguous fields).
- `min_confidence`: rows with `extraction_confidence` below this are rejected.
- `max_chunk_chars`: target maximum size of one chunk sent to the LLM.
- `cache_dir`: if given, results are cached there as JSON files.
- Output: `ExtractionResult`; `rows` and `rejected` are in text order.

## 4. Behavior rules

- **R1** Empty or whitespace-only `text` returns an empty result and makes no LLM call.
- **R2** Text no longer than `max_chunk_chars` is sent to the LLM as one chunk.
- **R3** Longer text is split into chunks at heading or paragraph boundaries. A line is never split.
  A new heading line (`#`...) always starts a new paragraph unit. Chunks hold whole units, packed
  greedily up to `max_chunk_chars`.
- **R4** A single paragraph longer than `max_chunk_chars` (e.g. a big table) is split between
  lines. A single line longer than `max_chunk_chars` becomes its own chunk, unsplit.
- **R5** Each chunk is one `complete_structured` call. The prompt contains the row model's JSON
  schema (including each field's description), the instructions (if any) and the chunk text, and
  tells the LLM to follow each field's description. Rows from all chunks are combined in order.
- **R6** A row that passes validation and has confidence >= `min_confidence` goes to `rows`, with
  its confidence and notes.
- **R7** A row whose data fails `row_model` validation goes to `rejected` (kind
  `validation_error`) with the validation error as the reason and the raw data kept.
- **R8** A row whose data is not valid JSON, or not a JSON object, is rejected the same way.
- **R9** A valid row with confidence below `min_confidence` goes to `rejected` (kind
  `low_confidence`). Confidence equal to `min_confidence` is accepted.
- **R10** A row whose confidence is outside 0-1 is rejected (kind `validation_error`).
- **R11** Validation is checked before confidence: a row that is both invalid and low-confidence
  is rejected as `validation_error`.
- **R12** If the LLM returns zero rows (for every chunk), the result is empty, not an error.
- **R13** With `cache_dir`, the LLM's raw output is stored as JSON at
  `<cache_dir>/<key>.json`, `key` = SHA-256 of the text, the row model's JSON schema, the
  instructions and `llm.model`. `cache_dir` is created if missing.
- **R14** A cache hit makes no LLM call and gives the same result as the original call.
- **R15** The cache holds raw LLM output, before validation and the confidence threshold, so
  changing `min_confidence` (or editing the row model's validators) does not need a new LLM call.
  `max_chunk_chars` is not part of the key.
- **R16** Changing any of text, schema, instructions or model name is a cache miss.
- **R17** A corrupt or unreadable cache file is treated as a miss and overwritten.
- **R18** Without `cache_dir`, no files are written.
- **R19** Every top-level field of `row_model` must have a non-empty description. Otherwise
  `extract` raises `ValueError` naming the fields without one, before any LLM call (also for
  empty text).

## 5. Errors

- Raises `ValueError` if `min_confidence` is outside 0-1, `max_chunk_chars` < 1, or a
  `row_model` field has no description (R19).
- Errors from the LLM (API errors, refusals, `ClaudeError`) propagate. Nothing is cached when any
  chunk fails.
- Validation problems in LLM output never raise; they become `rejected` items (R7-R10).

## 6. Config and dependencies

- Needs `pydantic` (extra `llm`). The component itself imports no provider SDK.
- The real client is `llm.ClaudeLLM` (extra `llm`: `anthropic`, `python-dotenv`); it reads
  `ANTHROPIC_API_KEY` from the environment or `.env`. See `.env.example`.

## 7. Out of scope

Fetching or reading files, deduplication across rows, retries beyond the Anthropic SDK defaults,
providers other than Claude, repeating a Markdown table's header row in later chunks.
