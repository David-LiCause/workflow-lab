"""Row models and tables."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

COMPANIES_TABLE = "companies"
REVIEW_QUEUE_TABLE = "review_queue"

YesNoUnknown = Literal["yes", "no", "unknown"]
Confidence = Literal["high", "medium", "low"]

# Row models: one per research report, with the columns from its prompt in research/prompts/.
# Each field's description tells the LLM what to extract into it. Every report's ``confidence``
# and ``sources`` columns are renamed ``research_confidence`` and ``research_sources`` so they
# don't clash with the extraction's own confidence.


class IncumbentRow(BaseModel):
    """One organization from the incumbents report (research/prompts/incumbents.md)."""

    name: str = Field(description="Current official name of the organization.")
    website: str = Field(description="Main website URL, e.g. https://www.example.org.")
    sector: Literal["health_system", "payer", "pharma", "biotech", "medtech_diagnostics"] = Field(
        description="The report's sector value."
    )
    also_academic: Literal["yes", "no"] = Field(
        description="Whether it is also an academic medical center."
    )
    ownership: str = Field(
        "", description="public, private, nonprofit, or subsidiary (of whom), as in the report."
    )
    ticker: str = Field("", description="Stock ticker if public; empty otherwise.")
    boston_presence: str = Field(
        "", description="hq or major_site, plus the town(s), as in the report."
    )
    employees_boston: str = Field(
        "", description="Approximate Boston-area headcount as written, or 'unknown'."
    )
    employees_total: str = Field(
        "", description="Approximate total headcount as written, or 'unknown'."
    )
    data_ml_presence: YesNoUnknown = Field(
        "unknown", description="Evidence of data science, ML, AI or data engineering teams."
    )
    data_ml_evidence: str = Field(
        "", description="The report's one-line evidence of data/ML teams, with any URL."
    )
    careers_url: str = Field("", description="Careers or jobs page URL.")
    recent_layoffs: str = Field(
        "", description="Layoffs, restructuring or site closures as written, or 'none found'."
    )
    stability_notes: str = Field("", description="The report's stability and bandwidth notes.")
    research_confidence: Confidence = Field(
        description="The report's own 'confidence' column for the row."
    )
    research_sources: str = Field(
        "", description="The report's 'sources' column: semicolon-separated URLs."
    )
    last_verified: date | None = Field(
        None, description="The report's 'last_verified' date (YYYY-MM-DD)."
    )


class BigTechRow(BaseModel):
    """One health unit inside a big tech company or AI lab (research/prompts/big_tech.md)."""

    name: str = Field(description="The unit's name, e.g. 'Google Health'.")
    parent_company: str = Field(description="The parent company's name, e.g. 'Alphabet'.")
    website: str = Field("", description="The unit's page, or the parent's main site.")
    sector: Literal["big_tech", "ai_lab", "other_tech"] = Field(
        description="The report's sector value."
    )
    unit_type: Literal["research", "product", "cloud_platform", "care_delivery", "subsidiary"] = (
        Field(description="The report's unit_type value.")
    )
    focus: str = Field("", description="One line on what the unit works on.")
    ownership: str = Field(
        "", description="public, private, or subsidiary (of whom), as in the report."
    )
    ticker: str = Field("", description="Parent company's stock ticker if public; else empty.")
    boston_presence: str = Field(
        "", description="office_with_team, office_only or none, plus the location, as written."
    )
    remote_friendly: YesNoUnknown = Field("unknown", description="The report's remote_friendly.")
    data_ml_presence: YesNoUnknown = Field(
        "unknown", description="Evidence of data science, ML or AI work in the unit."
    )
    data_ml_evidence: str = Field(
        "", description="The report's one-line evidence of data/ML work, with any URL."
    )
    careers_url: str = Field("", description="Careers page URL, filtered to the unit if given.")
    recent_layoffs: str = Field(
        "", description="Layoffs or reorganizations affecting the unit, or 'none found'."
    )
    bandwidth_notes: str = Field("", description="The report's bandwidth_notes column.")
    stability_notes: str = Field("", description="The report's notes on the unit's trajectory.")
    research_confidence: Confidence = Field(
        description="The report's own 'confidence' column for the row."
    )
    research_sources: str = Field(
        "", description="The report's 'sources' column: semicolon-separated URLs."
    )
    last_verified: date | None = Field(
        None, description="The report's 'last_verified' date (YYYY-MM-DD)."
    )


class LandscapeRow(BaseModel):
    """One health tech company from the landscape report (research/prompts/landscape.md)."""

    name: str = Field(description="Current official name of the company.")
    website: str = Field(description="Main website URL.")
    category: str = Field("", description="The report's short category, e.g. clinical_ai.")
    focus: str = Field("", description="One line on what the company does.")
    stage: str = Field("", description="The report's stage value, e.g. series_c or public.")
    ticker: str = Field("", description="Stock ticker if public; empty otherwise.")
    total_funding_usd: str = Field("", description="Approximate total funding as written.")
    last_funding: str = Field("", description="Most recent round, amount and date as written.")
    key_investors: str = Field("", description="Lead or notable investors, semicolon-separated.")
    hq_location: str = Field("", description="City and state of headquarters.")
    boston_presence: str = Field(
        "", description="hq, office_with_team, office_only or none, plus the town, as written."
    )
    remote_friendly: YesNoUnknown = Field("unknown", description="The report's remote_friendly.")
    employees_total: str = Field("", description="Approximate headcount as written.")
    found_on: str = Field("", description="Lists the company appeared on, semicolon-separated.")
    found_on_count: int | None = Field(None, description="Number of distinct lists in found_on.")
    data_ml_presence: YesNoUnknown = Field(
        "unknown", description="Evidence of data science, ML, AI or data engineering teams."
    )
    data_ml_evidence: str = Field(
        "", description="The report's one-line evidence of data/ML teams, with any URL."
    )
    careers_url: str = Field("", description="Careers or jobs page URL.")
    recent_layoffs: str = Field("", description="Layoffs or restructuring, or 'none found'.")
    stability_notes: str = Field("", description="The report's trajectory and stability notes.")
    research_confidence: Confidence = Field(
        description="The report's own 'confidence' column for the row."
    )
    research_sources: str = Field(
        "", description="The report's 'sources' column: semicolon-separated URLs."
    )
    last_verified: date | None = Field(
        None, description="The report's 'last_verified' date (YYYY-MM-DD)."
    )


class Extracted(BaseModel):
    """Fields added to every extracted row. Key: ``key`` (see ``Company.key``)."""

    key: str
    domain: str  # normalized website domain; "" if none
    source_file: str  # report the row came from, relative to the storage root
    extraction_confidence: float  # 0-1, from the LLM
    extraction_notes: str = ""


class ExtractedIncumbent(IncumbentRow, Extracted):
    """A row of ``extracted_incumbents``."""


class ExtractedBigTech(BigTechRow, Extracted):
    """A row of ``extracted_big_tech``."""


class ExtractedLandscape(LandscapeRow, Extracted):
    """A row of ``extracted_landscape``."""


class Company(BaseModel):
    """A row of the ``companies`` table: Discovery's output. Key: ``key``."""

    key: str  # domain; "<parent>/<unit>" for a big tech unit; "name:<name>" if no website
    name: str
    parent_company: str = ""  # big tech units only
    website: str = ""
    domain: str = ""
    archetype: str  # healthcare_incumbent, big_tech_ai_lab or health_tech
    sources: list[str] = Field(default_factory=list)  # e.g. research_incumbents
    source_files: list[str] = Field(default_factory=list)
    extraction_confidence: float  # lowest across the row's sources
    first_seen: date | None = None
    last_seen: date | None = None
    status: Literal["new", "active", "missing"] = "new"


class ReviewItem(BaseModel):
    """A row that was not loaded, with the reason. Key: ``(source_file, item)``."""

    source_file: str
    item: int  # 1-based position among this file's review items
    kind: str  # validation_error, low_confidence, duplicate
    reason: str
    raw: dict[str, Any] | str
    extraction_confidence: float | None = None
