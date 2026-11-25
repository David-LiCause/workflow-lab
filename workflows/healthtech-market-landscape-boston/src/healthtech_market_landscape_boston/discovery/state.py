from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..models import Company, Extracted, ReviewItem


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class DiscoveryState(TypedDict, total=False):
    # Source nodes run in parallel, so everything they write has a reducer that combines.
    report_paths: Annotated[dict[str, str], merge_dicts]  # source name -> report used
    extracted: Annotated[dict[str, list[Extracted]], merge_dicts]  # source name -> rows
    review_queue: Annotated[list[ReviewItem], operator.add]
    errors: Annotated[list[str], operator.add]
    companies: list[Company]  # from merge
    inserted: int  # companies counts, from export
    updated: int
    missing: int
