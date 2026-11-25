"""Store and read Pydantic rows in a SQL database. See ``SPEC.md`` for the rules."""

from __future__ import annotations

import os
import types
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypeVar, Union, get_args, get_origin

try:
    import sqlalchemy as sa
    from pydantic import BaseModel, ValidationError
except ImportError as exc:  # pragma: no cover - exercised via sys.modules patching in tests
    raise ImportError(
        "The db component needs SQLAlchemy and Pydantic. Install the extra: uv sync --extra db"
    ) from exc

T = TypeVar("T", bound=BaseModel)

_SCALAR_KINDS = {"str", "int", "float", "bool", "date", "datetime"}


class UnknownTableError(LookupError):
    """The table was not set up with ``Database.ensure_table``."""


class RowMismatchError(ValueError):
    """A row does not match the table's model."""


class SchemaMismatchError(ValueError):
    """An existing table's columns or primary key differ from the model."""


class UpsertResult(NamedTuple):
    inserted: int
    updated: int


def normalize_url(url: str) -> str:
    """Rewrite ``postgres://`` to ``postgresql://``, the scheme SQLAlchemy accepts."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _to_utc(value: datetime) -> datetime:
    """Aware values become UTC; naive values are taken to be UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class _UTCDateTime(sa.types.TypeDecorator):
    """Timestamp stored in UTC and always returned as an aware UTC datetime."""

    impl = sa.DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        return None if value is None else _to_utc(value)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return None if value is None else _to_utc(value)


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Return ``(annotation without None, whether None was allowed)``."""
    if annotation is None or annotation is type(None):
        return Any, True
    if get_origin(annotation) in (Union, types.UnionType):
        args = get_args(annotation)
        rest = [a for a in args if a is not type(None)]
        nullable = len(rest) != len(args)
        if len(rest) == 1:
            return rest[0], nullable
        return annotation, nullable
    return annotation, False


def _kind(annotation: Any) -> str:
    """Storage kind for a (non-optional) annotation: a scalar kind, or ``"json"``."""
    if get_origin(annotation) is Literal:
        values = get_args(annotation)
        if all(isinstance(v, str) for v in values):
            return "str"
        if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            return "int"
        return "json"
    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            values = [m.value for m in annotation]
            if values and all(isinstance(v, str) for v in values):
                return "str"
            if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
                return "int"
            return "json"
        if issubclass(annotation, bool):
            return "bool"
        if issubclass(annotation, str):
            return "str"
        if issubclass(annotation, int):
            return "int"
        if issubclass(annotation, float):
            return "float"
        if issubclass(annotation, datetime):  # before date: datetime subclasses date
            return "datetime"
        if issubclass(annotation, date):
            return "date"
    return "json"


def _column_type(kind: str) -> Any:
    return {
        "str": sa.Text(),
        "int": sa.BigInteger(),
        "float": sa.Float(),
        "bool": sa.Boolean(),
        "date": sa.Date(),
        "datetime": _UTCDateTime(),
        "json": sa.JSON(none_as_null=True),
    }[kind]


def _to_db_scalar(value: Any) -> Any:
    """Convert a scalar value (or filter value) into what the column stores."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _to_utc(value)
    return value


@dataclass
class _Registered:
    model: type[BaseModel]
    key: tuple[str, ...]
    table: Any  # sa.Table
    kinds: dict[str, str]


class Database:
    """Pydantic rows in a SQL database (SQLite now, Postgres later)."""

    def __init__(self, url: str | None = None) -> None:
        """Connect to ``url``, or to the ``DATABASE_URL`` env var when ``url`` is None."""
        url = url or os.environ.get("DATABASE_URL") or ""
        if not url:
            raise ValueError("No database URL: pass url=... or set the DATABASE_URL env var")
        url = normalize_url(url)
        parsed = sa.engine.make_url(url)
        if parsed.get_backend_name() == "sqlite":
            path = parsed.database
            if path and path != ":memory:" and not path.startswith("file:"):
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._engine = sa.create_engine(url)
        self._metadata = sa.MetaData()
        self._tables: dict[str, _Registered] = {}

    @property
    def engine(self) -> sa.Engine:
        """The underlying SQLAlchemy engine."""
        return self._engine

    # -- tables -----------------------------------------------------------------------------

    def ensure_table(self, name: str, model: type[BaseModel], key: str | Sequence[str]) -> None:
        """Create table ``name`` from ``model`` if missing; ``key`` field(s) are the primary key."""
        keys = (key,) if isinstance(key, str) else tuple(key)
        fields = model.model_fields
        if not keys:
            raise ValueError(f"Table {name!r}: key must name at least one field")
        if len(set(keys)) != len(keys):
            raise ValueError(f"Table {name!r}: key repeats a field: {list(keys)}")

        kinds: dict[str, str] = {}
        nullable: dict[str, bool] = {}
        for field_name, info in fields.items():
            inner, allows_none = _unwrap_optional(info.annotation)
            kinds[field_name] = _kind(inner)
            nullable[field_name] = allows_none
        for k in keys:
            if k not in fields:
                raise ValueError(
                    f"Table {name!r}: key field {k!r} is not a field of {model.__name__}"
                )
            if kinds[k] not in _SCALAR_KINDS:
                raise ValueError(
                    f"Table {name!r}: key field {k!r} is stored as JSON and cannot be a key"
                )

        existing = self._tables.get(name)
        if existing is not None:
            if existing.model is model and existing.key == keys:
                return
            raise ValueError(
                f"Table {name!r} is already set up with {existing.model.__name__} "
                f"and key {list(existing.key)}"
            )

        table = sa.Table(
            name,
            self._metadata,
            *[
                sa.Column(
                    field_name,
                    _column_type(kinds[field_name]),
                    primary_key=field_name in keys,
                    nullable=nullable[field_name] and field_name not in keys,
                )
                for field_name in fields
            ],
        )
        try:
            self._create_or_check(name, table, set(fields), set(keys))
        except Exception:
            self._metadata.remove(table)
            raise
        self._tables[name] = _Registered(model=model, key=keys, table=table, kinds=kinds)

    def _create_or_check(self, name: str, table: Any, columns: set[str], keys: set[str]) -> None:
        insp = sa.inspect(self._engine)
        if insp.has_table(name):
            actual_cols = {c["name"] for c in insp.get_columns(name)}
            actual_pk = set(insp.get_pk_constraint(name)["constrained_columns"])
            if actual_cols != columns or actual_pk != keys:
                raise SchemaMismatchError(
                    f"Table {name!r} already exists with columns {sorted(actual_cols)} and "
                    f"primary key {sorted(actual_pk)}, but the model has columns "
                    f"{sorted(columns)} and key {sorted(keys)}. Migrations are not supported."
                )
            return
        with self._engine.begin() as conn:
            table.create(conn, checkfirst=True)

    def _get(self, name: str) -> _Registered:
        try:
            return self._tables[name]
        except KeyError:
            raise UnknownTableError(
                f"Unknown table {name!r}: call ensure_table({name!r}, model, key) first"
            ) from None

    # -- upsert -----------------------------------------------------------------------------

    def _encode(self, reg: _Registered, row: BaseModel) -> dict[str, Any]:
        """Column values for ``row``, in the form the columns store and return them."""
        as_python = row.model_dump(mode="python")
        as_json = row.model_dump(mode="json")
        values: dict[str, Any] = {}
        for field_name, kind in reg.kinds.items():
            if kind == "json":
                values[field_name] = as_json[field_name]
            else:
                value = as_python[field_name]
                values[field_name] = None if value is None else _to_db_scalar(value)
        return values

    def upsert(self, name: str, rows: Iterable[BaseModel]) -> UpsertResult:
        """Insert new rows and update existing ones by key, in one transaction."""
        reg = self._get(name)
        rows = list(rows)
        encoded: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            if not isinstance(row, reg.model):
                raise RowMismatchError(
                    f"Table {name!r} holds {reg.model.__name__} rows, got {type(row).__name__}"
                )
            values = self._encode(reg, row)
            key_value = tuple(values[k] for k in reg.key)
            if key_value in seen:
                raise ValueError(f"Table {name!r}: duplicate key in one upsert call: {key_value}")
            seen.add(key_value)
            encoded.append(values)
        if not encoded:
            return UpsertResult(0, 0)

        table = reg.table
        inserted = updated = 0
        with self._engine.begin() as conn:
            for values in encoded:
                match = sa.and_(*[table.c[k] == values[k] for k in reg.key])
                current = conn.execute(sa.select(table).where(match)).mappings().first()
                if current is None:
                    conn.execute(table.insert().values(**values))
                    inserted += 1
                elif any(current[c] != v for c, v in values.items()):
                    rest = {c: v for c, v in values.items() if c not in reg.key}
                    conn.execute(table.update().where(match).values(**rest))
                    updated += 1
        return UpsertResult(inserted, updated)

    # -- read -------------------------------------------------------------------------------

    def read(self, name: str, model: type[T], where: Mapping[str, Any] | None = None) -> list[T]:
        """Return rows of ``name`` as ``model`` instances, optionally filtered by equality."""
        reg = self._get(name)
        table = reg.table
        query = sa.select(table)
        for column, value in (where or {}).items():
            if column not in reg.kinds:
                raise ValueError(f"Table {name!r} has no column {column!r} to filter on")
            if reg.kinds[column] == "json":
                raise ValueError(f"Cannot filter on JSON column {column!r} of table {name!r}")
            query = query.where(table.c[column] == _to_db_scalar(value))
        query = query.order_by(*[table.c[k] for k in reg.key])

        with self._engine.connect() as conn:
            records = [dict(r) for r in conn.execute(query).mappings()]
        try:
            return [model.model_validate(r) for r in records]
        except ValidationError as exc:
            raise RowMismatchError(
                f"Rows of table {name!r} do not match {model.__name__}: {exc}"
            ) from exc

    def close(self) -> None:
        """Release database connections."""
        self._engine.dispose()
