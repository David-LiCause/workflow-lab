"""Turn Markdown or plain text into validated Pydantic rows using an LLM.

See ``SPEC.md`` for the rules.
"""

from workflow_lab.components.text_to_structured_data.text_to_structured_data import (
    ExtractedRow,
    ExtractionResult,
    RejectedRow,
    extract,
    split_into_chunks,
)

__all__ = ["ExtractedRow", "ExtractionResult", "RejectedRow", "extract", "split_into_chunks"]
