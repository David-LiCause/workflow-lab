from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..models import Paper, PaperRow, ReviewItem


class DigestState(TypedDict, total=False):
    feed_path: str | None  # feed snapshot used, relative to the storage root
    papers: list[Paper]
    rows: list[PaperRow]
    review_queue: Annotated[list[ReviewItem], operator.add]
    errors: Annotated[list[str], operator.add]
    inserted: int
    updated: int
    digest_path: str
