from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..models import Event, ExtractedEvent, ReviewItem


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class CollectState(TypedDict, total=False):
    # Source nodes run in parallel, so everything they write has a reducer that combines.
    snapshots: Annotated[dict[str, list[str]], merge_dicts]  # source name -> snapshot paths
    extracted: Annotated[dict[str, list[ExtractedEvent]], merge_dicts]  # source name -> rows
    review_queue: Annotated[list[ReviewItem], operator.add]
    errors: Annotated[list[str], operator.add]
    events: list[Event]  # from merge
    inserted: int  # events counts, from export
    updated: int
