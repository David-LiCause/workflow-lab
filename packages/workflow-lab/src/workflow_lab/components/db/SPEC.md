# db

## 1. Purpose

Store and read Pydantic rows in a SQL database through one small interface. SQLite works today;
Postgres (for example Supabase) works later by changing only the connection URL.

## 2. Interface

```python
class UnknownTableError(LookupError): ...  # table not set up with ensure_table


class RowMismatchError(ValueError): ...  # row does not match the table's model


class SchemaMismatchError(ValueError): ...  # existing table differs from the model


class UpsertResult(NamedTuple):
    inserted: int
    updated: int


class Database:
    def __init__(self, url: str | None = None) -> None: ...

    engine: sqlalchemy.Engine  # read-only property

    def ensure_table(self, name: str, model: type[BaseModel], key: str | Sequence[str]) -> None: ...
    def upsert(self, name: str, rows: Iterable[BaseModel]) -> UpsertResult: ...
    def read(
        self, name: str, model: type[T], where: Mapping[str, Any] | None = None
    ) -> list[T]: ...
    def close(self) -> None: ...
```

## 3. Inputs and outputs

- `url`: a SQLAlchemy database URL (`"sqlite:///data/companies.db"`, `"sqlite://"` for in-memory,
  later `"postgresql://..."`). Defaults to the `DATABASE_URL` env var.
- `name`: the table name.
- `model`: a Pydantic model class. One column is created per field, named after the field.
- `key`: a field name, or a list of field names, that together form the primary key.
- `rows`: instances of the model registered for `name`.
- `where`: equality filters, `{"status": "new"}`. All entries must match (AND).
- `read` returns model instances, ordered by primary key.

## 4. Behavior rules

**Connecting**

- **R1** An explicit `url` wins; otherwise `DATABASE_URL` is used. If neither is set (or both are
  empty), the constructor raises `ValueError` that names `DATABASE_URL`.
- **R2** A `postgres://` URL scheme is rewritten to `postgresql://` (the form SQLAlchemy accepts;
  Supabase hands out the first form).
- **R3** For a file-based SQLite URL, missing parent folders of the database file are created.

**Tables**

- **R4** `ensure_table` creates the table if it does not exist: one column per model field, and a
  primary key made of the `key` fields.
- **R5** `ensure_table` is idempotent: calling it again with the same model and key changes
  nothing and keeps existing rows. It also adopts a table that already exists in the database
  (created by an earlier `Database` or process) when its columns and primary key match.
- **R6** In one `Database`, calling `ensure_table` for an existing name with a different model or
  key raises `ValueError`.
- **R7** If the table already exists in the database but its column names or primary key differ
  from the model and key, `ensure_table` raises `SchemaMismatchError`. The table is never altered.
- **R8** `key` is invalid, and `ensure_table` raises `ValueError`, when it is empty, repeats a
  name, names a field the model does not have, or names a field stored as JSON (R10).
- **R9** `ensure_table` registers the table, model and key with the `Database` instance. `upsert`
  and `read` only work on registered tables.

**Column types**

- **R10** Field types map to columns: `str` text, `int` big integer, `float` float, `bool`
  boolean, `date` date, `datetime` timestamp with time zone. `Optional[...]` fields use the type
  of the non-None member and allow NULL. `Enum` and `Literal` fields whose values are all `str`
  (or all `int`) use the text (or integer) column and store the value. Every other type (lists,
  dicts, nested models, unions, and so on) is stored as JSON.
- **R11** JSON fields come back as the same type that went in (a `list[str]` field returns a
  `list[str]`, a nested model returns that model). `None` in an optional JSON field is stored as
  NULL and returns `None`.
- **R12** Dates round-trip unchanged. Datetimes are stored in UTC and returned as timezone-aware
  UTC values: an aware value comes back as the same instant, and a naive value is taken to be UTC.
- **R13** `None` round-trips for every optional field type.

**Upsert**

- **R14** `upsert` inserts rows whose key is not in the table and updates rows whose key is
  already there. It returns `UpsertResult(inserted, updated)`.
- **R15** A row whose key exists and whose values are all unchanged counts as neither inserted nor
  updated. Upserting the same rows twice therefore returns `(0, 0)` the second time.
- **R16** Composite keys match on all key fields together.
- **R17** One `upsert` call is one transaction. If anything fails, no row from that call is
  written.
- **R18** Two rows with the same key in one call raise `ValueError` and nothing is written.
- **R19** Every row must be an instance of the model registered for the table. Anything else (a
  dict, an instance of another model) raises `RowMismatchError` that names the table, and nothing
  is written.
- **R20** An empty `rows` returns `UpsertResult(0, 0)` and writes nothing.

**Read**

- **R21** `read(name, model)` returns every row as a `model` instance, ordered by primary key.
- **R22** `where` keeps rows whose columns equal every given value. A `None` value matches NULL.
  `None` or `{}` returns everything. Values use the same conversion as writes (a naive datetime is
  taken to be UTC, an enum member matches its value).
- **R23** A `where` key that is not a column, or is a JSON column, raises `ValueError`.
- **R24** If a stored row cannot be built into `model`, `read` raises `RowMismatchError` that
  names the table.

**Unknown table, missing extra**

- **R25** `upsert` and `read` on a name not set up with `ensure_table` raise `UnknownTableError`.
  The message names the table and says to call `ensure_table` first.
- **R26** `close()` releases the database connections.
- **R27** If `sqlalchemy` or `pydantic` is not installed, importing the component raises
  `ImportError` with a message that says to install the `db` extra.

## 5. Errors

| Raised | When |
| --- | --- |
| `ValueError` | R1, R6, R8, R18, R23 |
| `SchemaMismatchError` (a `ValueError`) | R7 |
| `UnknownTableError` (a `LookupError`) | R25 |
| `RowMismatchError` (a `ValueError`) | R19, R24 |
| `ImportError` | R27 |

Database errors (connection refused, missing driver, constraint failures) propagate unchanged.
Pydantic validation errors are wrapped in `RowMismatchError`.

## 6. Config and dependencies

- Env var: `DATABASE_URL`, used when no `url` is passed.
- Optional extra `db`: `sqlalchemy`, `pydantic`. Install with `uv sync --extra db`.
- No Postgres driver is installed. To use Postgres, add one (for example `psycopg`) and set the URL.

## 7. Out of scope

Schema migrations, joins or complex queries, async, connection pool tuning, filters other than
equality, deleting rows, concurrent-writer conflict handling.
