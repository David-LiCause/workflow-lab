"""The research reports Discovery reads. Each becomes one ``extract_<name>`` node."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from ..models import (
    BigTechRow,
    Extracted,
    ExtractedBigTech,
    ExtractedIncumbent,
    ExtractedLandscape,
    IncumbentRow,
    LandscapeRow,
)


@dataclass(frozen=True)
class ReportSource:
    name: str  # report file prefix; node extract_<name>; table extracted_<name>
    description: str  # what the report lists, for the LLM instructions
    row_model: type[BaseModel]
    extracted_model: type[Extracted]
    columns: tuple[str, ...]  # the report's CSV header, in order
    archetype: str
    units_of_parent: bool = False  # rows are units of a parent company (keyed parent/unit)

    @property
    def node(self) -> str:
        return f"extract_{self.name}"

    @property
    def table(self) -> str:
        return f"extracted_{self.name}"

    @property
    def source_id(self) -> str:
        return f"research_{self.name}"

    @property
    def report_pattern(self) -> str:
        return f"research/reports/{self.name}_*.md"

    @property
    def instructions(self) -> str:
        return f"""\
The text is all or part of a research report listing {self.description}. Return one row per \
entry in its main list (the CSV block), in order. Do not add entries from the narrative, \
"Adjacent" or "Gaps" sections. If this part of the report has no CSV rows, return no rows.
- The CSV columns, in order, are: {", ".join(self.columns)}. Rows may appear without the header row.
- The report's "confidence" and "sources" columns go in research_confidence and research_sources.
- Copy values from the report as written; do not research or rewrite them.
- Some CSV rows have commas inside unquoted fields. Use the column meanings to place each value in \
the right field.
- Remove citation markers such as \\[12\\] or [12] from values.
- Some URLs are written with look-alike characters (https∶//www·example·com). Restore them to \
normal URLs (https://www.example.com).
- Use an empty string for empty cells."""


def _csv_columns(model: type[BaseModel]) -> tuple[str, ...]:
    renamed = {"research_confidence": "confidence", "research_sources": "sources"}
    return tuple(renamed.get(f, f) for f in model.model_fields)


SOURCES: tuple[ReportSource, ...] = (
    ReportSource(
        name="incumbents",
        description="established healthcare organizations in Greater Boston",
        row_model=IncumbentRow,
        extracted_model=ExtractedIncumbent,
        columns=_csv_columns(IncumbentRow),
        archetype="healthcare_incumbent",
    ),
    ReportSource(
        name="big_tech",
        description="health-focused units inside big tech companies and AI labs",
        row_model=BigTechRow,
        extracted_model=ExtractedBigTech,
        columns=_csv_columns(BigTechRow),
        archetype="big_tech_ai_lab",
        units_of_parent=True,
    ),
    ReportSource(
        name="landscape",
        description="health tech companies",
        row_model=LandscapeRow,
        extracted_model=ExtractedLandscape,
        columns=_csv_columns(LandscapeRow),
        archetype="health_tech",
    ),
)
