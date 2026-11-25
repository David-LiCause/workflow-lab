"""Paper models and tables."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

PAPERS_TABLE = "papers"
REVIEW_QUEUE_TABLE = "review_queue"


class Paper(BaseModel):
    """One arXiv paper, as the API returns it."""

    arxiv_id: str  # without version, e.g. "2611.01234"
    title: str
    authors: list[str] = Field(default_factory=list)
    published: date
    categories: list[str] = Field(default_factory=list)
    abstract: str
    url: str


class PaperFindings(BaseModel):
    """What Claude extracts from one abstract. Each description tells it what goes in the field."""

    is_health_ai: bool = Field(
        description="True only if the paper applies AI or ML to health, medicine or healthcare."
    )
    one_line_summary: str = Field(
        description="One plain-English sentence on what the paper does and finds."
    )
    task: str = Field(
        description="The task the method performs, e.g. diagnosis, segmentation, triage, "
        "clinical documentation, risk prediction. 'not stated' if unclear."
    )
    clinical_area: str = Field(
        description="Clinical specialty or area, lowercase, e.g. radiology, oncology, "
        "cardiology, mental health, public health; 'general' if broad; 'none' if not health."
    )
    data_modality: Literal[
        "imaging", "clinical_text", "ehr_structured", "genomics", "signals", "multimodal", "other"
    ] = Field(description="Main kind of data the method uses.")
    datasets: str = Field(description="Named datasets used, comma-separated, or 'not stated'.")
    model_approach: str = Field(
        description="The kind of model, e.g. LLM, vision transformer, CNN, gradient boosting."
    )
    headline_result: str = Field(
        description="The main quantitative result as stated, or 'not stated'."
    )


class PaperRow(Paper, PaperFindings):
    """A row of the ``papers`` table. Key: ``arxiv_id``."""

    extraction_confidence: float  # 0-1, from the LLM
    extraction_notes: str = ""
    first_seen: date | None = None  # run date of the first run that found it


class ReviewItem(BaseModel):
    """A paper whose findings were not accepted, with the reason. Key: ``arxiv_id``."""

    arxiv_id: str
    kind: str  # validation_error, low_confidence, no_findings
    reason: str
    raw: dict[str, Any] | str
    extraction_confidence: float | None = None
