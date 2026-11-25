import marimo

__generated_with = "0.26.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Workflow data

    Every workflow's database is attached **read-only** to marimo's built-in DuckDB engine, one
    database per workflow. Browse tables in the **Data Sources** panel, and query them in SQL cells
    as `<workflow>.<table>`, for example `healthtech_market_landscape_boston.companies`. Tables
    from different workflows can be joined.

    Sources found: SQLite files in `data/db/<workflow>/`, plus any `<WORKFLOW>_DATABASE_URL` set in
    `.env` (SQLite or Postgres), which takes the place of that workflow's local file.
    """)


@app.cell
def _(mo):
    import os
    import re
    from pathlib import Path

    from dotenv import load_dotenv

    ROOT = mo.notebook_dir().parent  # workspace root
    load_dotenv(ROOT / ".env")

    def _name(text: str) -> str:
        return re.sub(r"\W+", "_", text).strip("_").lower()

    def find_sources() -> dict[str, tuple[str, str]]:
        """Database name -> (DuckDB attach type, target) for every workflow database."""
        sources: dict[str, tuple[str, str]] = {}
        for folder in sorted(p for p in (ROOT / "data" / "db").glob("*") if p.is_dir()):
            files = sorted(folder.glob("*.db"))
            for file in files:
                name = folder.name if len(files) == 1 else f"{folder.name}_{file.stem}"
                sources[_name(name)] = ("sqlite", str(file))
        for var, url in sorted(os.environ.items()):
            if not var.endswith("_DATABASE_URL") or var == "TEST_DATABASE_URL" or not url:
                continue
            name = _name(var.removesuffix("_DATABASE_URL"))
            scheme, _, rest = url.partition("://")
            if scheme == "sqlite":
                path = Path(rest.removeprefix("/")).expanduser()
                sources[name] = ("sqlite", str(path if path.is_absolute() else ROOT / path))
            elif scheme.split("+")[0] in ("postgres", "postgresql"):
                sources[name] = ("postgres", f"postgresql://{rest}")
        return sources

    return (find_sources,)


@app.cell
def _(find_sources, mo):
    # ATTACH runs through mo.sql (not duckdb.sql) so marimo refreshes its Data Sources panel.
    # Placeholders stay inside quotes so marimo can parse the statement.
    _rows = []
    for _name_, (_kind, _target) in find_sources().items():
        _path = f"{_kind}:{_target}".replace("'", "''")  # e.g. sqlite:/path/to/file.db
        try:
            mo.sql(
                f"""ATTACH IF NOT EXISTS '{_path}' AS "{_name_}" (READ_ONLY)""",
                output=False,
            )
            _status = "attached"
        except Exception as exc:
            _status = f"failed: {exc}"
        _shown = _target if _kind == "sqlite" else _target.split("@")[-1]  # hide credentials
        _rows.append({"database": _name_, "type": _kind, "location": _shown, "status": _status})

    attached = [r["database"] for r in _rows if r["status"] == "attached"]
    mo.ui.table(_rows, label="Workflow databases", selection=None)
    return (attached,)


@app.cell
def _(attached, mo):
    _df = mo.sql(
        f"""
        -- Every table in the attached workflow databases. Query one with:
        --   SELECT * FROM <database>.<table> LIMIT 100
        SELECT database_name, table_name
        FROM duckdb_tables()
        WHERE database_name IN ({", ".join(f"'{d}'" for d in attached) or "NULL"})
        ORDER BY database_name, table_name
        """
    )


@app.cell
def _(mo):
    _df = mo.sql(
        f"""

        -- select 
        --     archetype,
        --     extraction_confidence,
        --     count(*)
        -- from healthtech_market_landscape_boston_companies.companies
        -- group by archetype,
        --     extraction_confidence
        -- order by archetype,
        --     extraction_confidence

        select 
            archetype,
            count(*)
        from healthtech_market_landscape_boston_companies.companies
        group by archetype
        order by archetype

        -- select *
        -- from healthtech_market_landscape_boston_companies.companies
        -- limit 10


        """
    )


@app.cell
def _():
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
