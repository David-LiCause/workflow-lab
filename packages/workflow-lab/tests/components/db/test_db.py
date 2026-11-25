"""Tests for the db component. Rules R1-R27 are defined in SPEC.md. In-memory SQLite only."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import pytest
import sqlalchemy as sa
from pydantic import BaseModel, Field

from workflow_lab.components.db import (
    Database,
    RowMismatchError,
    SchemaMismatchError,
    UnknownTableError,
    UpsertResult,
)
from workflow_lab.components.db.db import normalize_url


class Status(StrEnum):
    NEW = "new"
    DONE = "done"


class Source(BaseModel):
    name: str
    url: str | None = None


class Company(BaseModel):
    domain: str
    name: str
    status: str = "new"
    sources: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    employees: int | None = None
    score: float | None = None
    active: bool = True
    founded: date | None = None
    seen_at: datetime | None = None


class Edge(BaseModel):
    src: str
    dst: str
    weight: int = 1


@pytest.fixture
def db() -> Database:
    database = Database("sqlite://")
    database.ensure_table("companies", Company, key="domain")
    return database


def company(domain: str = "a.com", **kw: Any) -> Company:
    return Company(domain=domain, name=kw.pop("name", domain.upper()), **kw)


# R1: URL and env var


def test_r1_explicit_url_wins_over_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'env.db'}")
    d = Database(f"sqlite:///{tmp_path / 'explicit.db'}")
    d.ensure_table("companies", Company, key="domain")
    assert (tmp_path / "explicit.db").exists()
    assert not (tmp_path / "env.db").exists()


def test_r1_env_var_is_the_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'env.db'}")
    d = Database()
    d.ensure_table("companies", Company, key="domain")
    assert (tmp_path / "env.db").exists()


@pytest.mark.parametrize("value", [None, ""])
def test_r1_no_url_raises_naming_env_var(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Database()


# R2: postgres:// scheme


def test_r2_postgres_scheme_is_rewritten() -> None:
    assert normalize_url("postgres://u:p@host:5432/db") == "postgresql://u:p@host:5432/db"
    assert normalize_url("postgresql://u@h/db") == "postgresql://u@h/db"
    assert normalize_url("sqlite://") == "sqlite://"


# R3: parent folders for file SQLite


def test_r3_creates_parent_folders_for_sqlite_file(tmp_path: Path) -> None:
    path = tmp_path / "data" / "nested" / "companies.db"
    d = Database(f"sqlite:///{path}")
    d.ensure_table("companies", Company, key="domain")
    assert path.exists()


# R4: table creation


def test_r4_creates_columns_and_primary_key(db: Database) -> None:
    insp = sa.inspect(db.engine)
    assert {c["name"] for c in insp.get_columns("companies")} == set(Company.model_fields)
    assert insp.get_pk_constraint("companies")["constrained_columns"] == ["domain"]


def test_r4_composite_key_becomes_primary_key() -> None:
    d = Database("sqlite://")
    d.ensure_table("edges", Edge, key=["src", "dst"])
    pk = sa.inspect(d.engine).get_pk_constraint("edges")["constrained_columns"]
    assert set(pk) == {"src", "dst"}


# R5: idempotent, adopts existing


def test_r5_ensure_table_twice_keeps_rows(db: Database) -> None:
    db.upsert("companies", [company()])
    db.ensure_table("companies", Company, key="domain")
    assert [c.domain for c in db.read("companies", Company)] == ["a.com"]


def test_r5_adopts_existing_table_from_another_instance(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'x.db'}"
    first = Database(url)
    first.ensure_table("companies", Company, key="domain")
    first.upsert("companies", [company(sources=["vc"])])
    first.close()

    second = Database(url)
    second.ensure_table("companies", Company, key="domain")
    assert second.read("companies", Company) == [company(sources=["vc"])]


# R6: conflicting re-registration


def test_r6_different_model_or_key_for_same_name_raises(db: Database) -> None:
    with pytest.raises(ValueError):
        db.ensure_table("companies", Edge, key="src")
    with pytest.raises(ValueError):
        db.ensure_table("companies", Company, key="name")


# R7: existing table differs from the model


def test_r7_existing_table_with_other_columns_raises(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'x.db'}"
    first = Database(url)
    first.ensure_table("t", Edge, key=["src", "dst"])
    first.close()

    class Other(BaseModel):
        src: str
        dst: str
        extra: str = ""

    second = Database(url)
    with pytest.raises(SchemaMismatchError, match="t"):
        second.ensure_table("t", Other, key=["src", "dst"])


def test_r7_existing_table_with_other_primary_key_raises(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'x.db'}"
    first = Database(url)
    first.ensure_table("t", Edge, key=["src", "dst"])
    first.close()
    second = Database(url)
    with pytest.raises(SchemaMismatchError):
        second.ensure_table("t", Edge, key="src")


# R8: invalid keys


@pytest.mark.parametrize("key", [[], "nope", ["domain", "domain"], "sources", ["domain", "meta"]])
def test_r8_invalid_key_raises(key: Any) -> None:
    d = Database("sqlite://")
    with pytest.raises(ValueError):
        d.ensure_table("companies", Company, key=key)


# R9: only registered tables work


def test_r9_registration_is_per_instance(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'x.db'}"
    first = Database(url)
    first.ensure_table("companies", Company, key="domain")
    second = Database(url)
    with pytest.raises(UnknownTableError):
        second.read("companies", Company)


# R10: column types


def test_r10_scalar_types_map_to_native_columns(db: Database) -> None:
    cols = {c["name"]: c["type"] for c in sa.inspect(db.engine).get_columns("companies")}
    assert isinstance(cols["domain"], sa.Text)
    assert isinstance(cols["employees"], sa.BigInteger)
    assert isinstance(cols["score"], sa.Float)
    assert isinstance(cols["active"], sa.Boolean)
    assert isinstance(cols["founded"], sa.Date)
    assert isinstance(cols["seen_at"], sa.DateTime)
    assert isinstance(cols["sources"], sa.JSON)
    assert isinstance(cols["meta"], sa.JSON)


def test_r10_optional_fields_are_nullable_and_required_are_not(db: Database) -> None:
    cols = {c["name"]: c for c in sa.inspect(db.engine).get_columns("companies")}
    assert cols["employees"]["nullable"] is True
    assert cols["name"]["nullable"] is False


def test_r10_enum_and_literal_use_scalar_columns() -> None:
    class Row(BaseModel):
        id: str
        status: Status
        kind: Literal["a", "b"]
        level: Literal[1, 2]
        mixed: Literal["a", 1]

    d = Database("sqlite://")
    d.ensure_table("r", Row, key="id")
    cols = {c["name"]: c["type"] for c in sa.inspect(d.engine).get_columns("r")}
    assert isinstance(cols["status"], sa.Text)
    assert isinstance(cols["kind"], sa.Text)
    assert isinstance(cols["level"], sa.BigInteger)
    assert isinstance(cols["mixed"], sa.JSON)

    d.upsert("r", [Row(id="1", status=Status.DONE, kind="b", level=2, mixed=1)])
    (back,) = d.read("r", Row)
    assert back.status is Status.DONE
    assert back.mixed == 1
    assert d.read("r", Row, where={"status": Status.DONE}) == [back]
    assert d.read("r", Row, where={"status": "new"}) == []


# R11: JSON fields


def test_r11_lists_and_dicts_round_trip_as_same_type(db: Database) -> None:
    row = company(sources=["vc", "news"], meta={"a": 1, "nested": {"b": [1, 2]}, "ok": True})
    db.upsert("companies", [row])
    (back,) = db.read("companies", Company)
    assert back == row
    assert isinstance(back.sources, list)
    assert isinstance(back.meta, dict)
    assert back.meta["nested"]["b"] == [1, 2]


def test_r11_nested_models_round_trip() -> None:
    class Page(BaseModel):
        id: str
        origin: Source
        extras: list[Source] = []
        note: dict[str, int] | None = None

    d = Database("sqlite://")
    d.ensure_table("pages", Page, key="id")
    row = Page(id="1", origin=Source(name="vc", url="https://x"), extras=[Source(name="n")])
    d.upsert("pages", [row])
    (back,) = d.read("pages", Page)
    assert back == row
    assert isinstance(back.origin, Source)


def test_r11_none_in_optional_json_field_is_null() -> None:
    class Page(BaseModel):
        id: str
        note: dict[str, int] | None = None

    d = Database("sqlite://")
    d.ensure_table("pages", Page, key="id")
    d.upsert("pages", [Page(id="1")])
    (back,) = d.read("pages", Page)
    assert back.note is None
    with d.engine.connect() as conn:
        assert conn.execute(sa.text("select note from pages")).scalar() is None


# R12: dates and datetimes


def test_r12_date_round_trips(db: Database) -> None:
    db.upsert("companies", [company(founded=date(2019, 3, 31))])
    (back,) = db.read("companies", Company)
    assert back.founded == date(2019, 3, 31)
    assert type(back.founded) is date


def test_r12_aware_datetime_returns_same_instant_in_utc(db: Database) -> None:
    eastern = timezone(timedelta(hours=-5))
    moment = datetime(2026, 11, 25, 9, 30, 15, 123456, tzinfo=eastern)
    db.upsert("companies", [company(seen_at=moment)])
    (back,) = db.read("companies", Company)
    assert back.seen_at == moment
    assert back.seen_at is not None
    assert back.seen_at.utcoffset() == timedelta(0)


def test_r12_naive_datetime_is_taken_as_utc(db: Database) -> None:
    db.upsert("companies", [company(seen_at=datetime(2026, 1, 2, 3, 4, 5))])
    (back,) = db.read("companies", Company)
    assert back.seen_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


# R13: None


def test_r13_none_round_trips_for_every_optional_type(db: Database) -> None:
    db.upsert("companies", [company()])
    (back,) = db.read("companies", Company)
    assert back.employees is None
    assert back.score is None
    assert back.founded is None
    assert back.seen_at is None


def test_r13_scalar_values_round_trip(db: Database) -> None:
    row = company(employees=120, score=0.75, active=False)
    db.upsert("companies", [row])
    assert db.read("companies", Company) == [row]


# R14: insert and update, counts


def test_r14_inserts_new_and_updates_existing(db: Database) -> None:
    assert db.upsert("companies", [company("a.com"), company("b.com")]) == UpsertResult(2, 0)
    result = db.upsert("companies", [company("a.com", status="reviewed"), company("c.com")])
    assert result == UpsertResult(inserted=1, updated=1)
    by_domain = {c.domain: c for c in db.read("companies", Company)}
    assert set(by_domain) == {"a.com", "b.com", "c.com"}
    assert by_domain["a.com"].status == "reviewed"
    assert by_domain["b.com"].status == "new"


def test_r14_result_unpacks(db: Database) -> None:
    inserted, updated = db.upsert("companies", [company()])
    assert (inserted, updated) == (1, 0)


# R15: unchanged rows are a no-op


def test_r15_upserting_same_rows_twice_is_a_noop(db: Database) -> None:
    rows = [
        company(
            "a.com",
            sources=["vc"],
            meta={"k": [1]},
            founded=date(2020, 1, 1),
            seen_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))),
            score=0.1,
        ),
        company("b.com"),
    ]
    assert db.upsert("companies", rows) == UpsertResult(2, 0)
    assert db.upsert("companies", rows) == UpsertResult(0, 0)


def test_r15_changed_json_value_counts_as_update(db: Database) -> None:
    db.upsert("companies", [company(sources=["vc"])])
    assert db.upsert("companies", [company(sources=["vc", "news"])]) == UpsertResult(0, 1)
    assert db.read("companies", Company)[0].sources == ["vc", "news"]


# R16: composite keys


def test_r16_composite_key_matches_on_all_fields() -> None:
    d = Database("sqlite://")
    d.ensure_table("edges", Edge, key=["src", "dst"])
    assert d.upsert("edges", [Edge(src="a", dst="b"), Edge(src="a", dst="c")]) == (2, 0)
    assert d.upsert("edges", [Edge(src="a", dst="b", weight=5), Edge(src="b", dst="a")]) == (1, 1)
    assert [(e.src, e.dst, e.weight) for e in d.read("edges", Edge)] == [
        ("a", "b", 5),
        ("a", "c", 1),
        ("b", "a", 1),
    ]


# R17: atomic upsert


def test_r17_failure_midway_writes_nothing(db: Database) -> None:
    db.upsert("companies", [company("keep.com")])

    @sa.event.listens_for(db.engine, "before_cursor_execute")
    def explode(conn: Any, cursor: Any, statement: str, parameters: Any, *args: Any) -> None:
        if "explode.com" in str(parameters):
            raise RuntimeError("boom")

    rows = [company("keep.com", status="changed"), company("new.com"), company("explode.com")]
    with pytest.raises(Exception, match="boom"):
        db.upsert("companies", rows)

    sa.event.remove(db.engine, "before_cursor_execute", explode)
    after = db.read("companies", Company)
    assert [(c.domain, c.status) for c in after] == [("keep.com", "new")]


# R18: duplicate keys in a call


def test_r18_duplicate_keys_in_one_call_raise_and_write_nothing(db: Database) -> None:
    with pytest.raises(ValueError, match="a.com"):
        db.upsert("companies", [company("b.com"), company("a.com"), company("a.com", name="x")])
    assert db.read("companies", Company) == []


# R19: rows must match the model


def test_r19_dict_row_raises_and_writes_nothing(db: Database) -> None:
    with pytest.raises(RowMismatchError, match="companies"):
        db.upsert("companies", [company("ok.com"), {"domain": "x.com", "name": "X"}])  # type: ignore[list-item]
    assert db.read("companies", Company) == []


def test_r19_instance_of_other_model_raises(db: Database) -> None:
    with pytest.raises(RowMismatchError, match="companies"):
        db.upsert("companies", [Edge(src="a", dst="b")])


# R20: empty rows


def test_r20_empty_rows_is_a_noop(db: Database) -> None:
    assert db.upsert("companies", []) == UpsertResult(0, 0)
    assert db.read("companies", Company) == []


# R21: read all, ordered by key


def test_r21_read_returns_models_ordered_by_key(db: Database) -> None:
    db.upsert("companies", [company("c.com"), company("a.com"), company("b.com")])
    rows = db.read("companies", Company)
    assert [r.domain for r in rows] == ["a.com", "b.com", "c.com"]
    assert all(isinstance(r, Company) for r in rows)


def test_r21_read_empty_table_returns_empty_list(db: Database) -> None:
    assert db.read("companies", Company) == []


# R22: where filters


def test_r22_where_filters_by_equality(db: Database) -> None:
    db.upsert(
        "companies",
        [
            company("a.com", status="new", active=True),
            company("b.com", status="reviewed", active=True),
            company("c.com", status="new", active=False),
        ],
    )
    assert [r.domain for r in db.read("companies", Company, where={"status": "new"})] == [
        "a.com",
        "c.com",
    ]
    both = db.read("companies", Company, where={"status": "new", "active": False})
    assert [r.domain for r in both] == ["c.com"]


def test_r22_where_none_matches_null(db: Database) -> None:
    db.upsert("companies", [company("a.com", employees=5), company("b.com")])
    assert [r.domain for r in db.read("companies", Company, where={"employees": None})] == ["b.com"]


def test_r22_empty_where_returns_everything(db: Database) -> None:
    db.upsert("companies", [company("a.com"), company("b.com")])
    assert len(db.read("companies", Company, where={})) == 2
    assert len(db.read("companies", Company, where=None)) == 2


def test_r22_where_converts_dates_and_naive_datetimes(db: Database) -> None:
    db.upsert(
        "companies",
        [
            company("a.com", founded=date(2020, 1, 1), seen_at=datetime(2026, 1, 1, 12)),
            company("b.com", founded=date(2021, 1, 1)),
        ],
    )
    assert [
        r.domain for r in db.read("companies", Company, where={"founded": date(2020, 1, 1)})
    ] == ["a.com"]
    hit = db.read("companies", Company, where={"seen_at": datetime(2026, 1, 1, 12)})
    assert [r.domain for r in hit] == ["a.com"]


# R23: bad where


def test_r23_unknown_or_json_column_in_where_raises(db: Database) -> None:
    with pytest.raises(ValueError, match="nope"):
        db.read("companies", Company, where={"nope": 1})
    with pytest.raises(ValueError, match="sources"):
        db.read("companies", Company, where={"sources": ["vc"]})


# R24: stored row cannot become the model


def test_r24_read_with_incompatible_model_raises(db: Database) -> None:
    db.upsert("companies", [company()])
    with pytest.raises(RowMismatchError, match="companies"):
        db.read("companies", Edge)


def test_r24_read_with_subset_model_works(db: Database) -> None:
    class Slim(BaseModel):
        domain: str
        name: str

    db.upsert("companies", [company("a.com")])
    assert db.read("companies", Slim) == [Slim(domain="a.com", name="A.COM")]


# R25: unknown table


def test_r25_unknown_table_raises_with_hint(db: Database) -> None:
    with pytest.raises(UnknownTableError, match="ensure_table") as exc:
        db.read("nope", Company)
    assert "nope" in str(exc.value)
    with pytest.raises(UnknownTableError, match="nope"):
        db.upsert("nope", [company()])
    assert isinstance(exc.value, LookupError)


# R26: close


def test_r26_close_releases_connections(tmp_path: Path) -> None:
    d = Database(f"sqlite:///{tmp_path / 'x.db'}")
    d.ensure_table("companies", Company, key="domain")
    d.upsert("companies", [company()])
    d.close()
    d.close()  # closing twice is harmless
    again = Database(f"sqlite:///{tmp_path / 'x.db'}")
    again.ensure_table("companies", Company, key="domain")
    assert len(again.read("companies", Company)) == 1


# R27: missing extra


@pytest.mark.parametrize("missing", ["sqlalchemy", "pydantic"])
def test_r27_import_without_extra_explains_how_to_install(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in [m for m in sys.modules if m.startswith("workflow_lab.components.db")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, missing, None)
    with pytest.raises(ImportError, match="db"):
        importlib.import_module("workflow_lab.components.db")
