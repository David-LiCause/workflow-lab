"""Integration tests for db.

Talks to Postgres: create a uniquely named table, upsert, read, then drop it.
Run: `uv run pytest -m integration tests/components/db`
Needs TEST_DATABASE_URL in .env. Call `require_env("TEST_DATABASE_URL")`,
which fails the test if the var is missing.

These repeat the SQLite unit-test behaviors on Postgres, where the SQL dialect differs.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel, Field

from agents_playground.components.db import Database, UpsertResult

pytestmark = pytest.mark.integration


class Company(BaseModel):
    domain: str
    name: str
    status: str = "new"
    sources: list[str] = Field(default_factory=list)
    meta: dict[str, Any] | None = None
    employees: int | None = None
    score: float | None = None
    active: bool = True
    founded: date | None = None
    seen_at: datetime | None = None


class Edge(BaseModel):
    src: str
    dst: str
    weight: int = 1


@dataclass
class Live:
    db: Database
    table: Callable[[str], str]  # unique table name for this run


@pytest.fixture
def live(require_env: Callable[..., dict[str, str]]) -> Iterator[Live]:
    url = require_env("TEST_DATABASE_URL")["TEST_DATABASE_URL"]
    db = Database(url)
    run = uuid.uuid4().hex[:8]
    names: list[str] = []

    def table(base: str) -> str:
        names.append(f"it_{base}_{run}")
        return names[-1]

    try:
        yield Live(db, table)
    finally:
        with db.engine.begin() as conn:
            for name in names:
                conn.execute(sa.schema.DropTable(sa.Table(name, sa.MetaData()), if_exists=True))
        db.close()


def company(domain: str = "a.com", **kw: Any) -> Company:
    return Company(domain=domain, name=kw.pop("name", domain.upper()), **kw)


def test_ensure_table_creates_composite_key(live: Live) -> None:
    name = live.table("edges")
    live.db.ensure_table(name, Edge, key=["src", "dst"])
    live.db.ensure_table(name, Edge, key=["src", "dst"])  # idempotent

    insp = sa.inspect(live.db.engine)
    assert {c["name"] for c in insp.get_columns(name)} == {"src", "dst", "weight"}
    assert set(insp.get_pk_constraint(name)["constrained_columns"]) == {"src", "dst"}


def test_upsert_counts_and_same_rows_twice_is_noop(live: Live) -> None:
    name = live.table("companies")
    live.db.ensure_table(name, Company, key="domain")
    rows = [
        company(
            "a.com",
            sources=["vc"],
            meta={"k": [1, 2], "nested": {"x": True}},
            founded=date(2020, 1, 1),
            seen_at=datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=2))),
            score=0.1,
            employees=10,
        ),
        company("b.com"),
    ]

    assert live.db.upsert(name, rows) == UpsertResult(2, 0)
    assert live.db.upsert(name, rows) == UpsertResult(0, 0)

    changed = [company("a.com", name="renamed"), company("c.com")]
    assert live.db.upsert(name, changed) == UpsertResult(inserted=1, updated=1)
    assert [r.domain for r in live.db.read(name, Company)] == ["a.com", "b.com", "c.com"]


def test_composite_key_upsert(live: Live) -> None:
    name = live.table("edges")
    live.db.ensure_table(name, Edge, key=["src", "dst"])

    assert live.db.upsert(name, [Edge(src="a", dst="b"), Edge(src="a", dst="c")]) == (2, 0)
    assert live.db.upsert(name, [Edge(src="a", dst="b", weight=5), Edge(src="b", dst="a")]) == (
        1,
        1,
    )
    assert live.db.upsert(name, [Edge(src="a", dst="b", weight=5)]) == (0, 0)
    assert [(e.src, e.dst, e.weight) for e in live.db.read(name, Edge)] == [
        ("a", "b", 5),
        ("a", "c", 1),
        ("b", "a", 1),
    ]


def test_json_fields_round_trip(live: Live) -> None:
    name = live.table("companies")
    live.db.ensure_table(name, Company, key="domain")
    row = company("a.com", sources=["vc", "news"], meta={"a": 1, "nested": {"b": [1, 2]}})
    empty = company("b.com", meta=None)
    live.db.upsert(name, [row, empty])

    back = {c.domain: c for c in live.db.read(name, Company)}
    assert back["a.com"] == row
    assert isinstance(back["a.com"].sources, list)
    assert isinstance(back["a.com"].meta, dict)
    assert back["b.com"].meta is None
    with live.db.engine.connect() as conn:
        stored = conn.execute(sa.text(f"select meta from \"{name}\" where domain = 'b.com'"))
        assert stored.scalar() is None  # SQL NULL, not JSON null


def test_dates_and_datetimes_round_trip(live: Live) -> None:
    name = live.table("companies")
    live.db.ensure_table(name, Company, key="domain")
    eastern = timezone(timedelta(hours=-5))
    aware = datetime(2026, 11, 25, 9, 30, 15, 123456, tzinfo=eastern)
    naive = datetime(2026, 1, 2, 3, 4, 5)
    live.db.upsert(
        name,
        [
            company("a.com", founded=date(2019, 3, 31), seen_at=aware),
            company("b.com", seen_at=naive),
            company("c.com"),
        ],
    )

    a, b, c = live.db.read(name, Company)
    assert a.founded == date(2019, 3, 31)
    assert type(a.founded) is date
    assert a.seen_at == aware
    assert a.seen_at is not None
    assert a.seen_at.utcoffset() == timedelta(0)
    assert b.seen_at == naive.replace(tzinfo=UTC)
    assert c.founded is None
    assert c.seen_at is None


def test_upsert_is_all_or_nothing_when_one_row_fails(live: Live) -> None:
    name = live.table("companies")
    live.db.ensure_table(name, Company, key="domain")
    live.db.upsert(name, [company("keep.com")])

    rows = [
        company("keep.com", status="changed"),  # would be an update
        company("new.com"),  # would be an insert
        company("bad.com", employees=2**70),  # does not fit a Postgres bigint
    ]
    with pytest.raises(sa.exc.DataError):
        live.db.upsert(name, rows)

    after = live.db.read(name, Company)
    assert [(c.domain, c.status) for c in after] == [("keep.com", "new")]


def test_read_where_filter(live: Live) -> None:
    name = live.table("companies")
    live.db.ensure_table(name, Company, key="domain")
    live.db.upsert(
        name,
        [
            company("a.com", status="new", founded=date(2020, 1, 1), seen_at=datetime(2026, 1, 1)),
            company("b.com", status="reviewed", employees=5),
            company("c.com", status="new", active=False),
        ],
    )

    def domains(**where: Any) -> list[str]:
        return [c.domain for c in live.db.read(name, Company, where=where)]

    assert domains(status="new") == ["a.com", "c.com"]
    assert domains(status="new", active=False) == ["c.com"]
    assert domains(employees=None) == ["a.com", "c.com"]
    assert domains(founded=date(2020, 1, 1)) == ["a.com"]
    assert domains(seen_at=datetime(2026, 1, 1, tzinfo=UTC)) == ["a.com"]
    assert domains() == ["a.com", "b.com", "c.com"]
    with pytest.raises(ValueError, match="sources"):
        live.db.read(name, Company, where={"sources": ["vc"]})
