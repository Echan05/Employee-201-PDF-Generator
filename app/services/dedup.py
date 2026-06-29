"""
Deduplication for list-returning secondary APIs (parents, education,
employment, training, minor).

Confirmed with Echan (2026-06-24):
- A shared pooling ID does NOT mean records are duplicates (e.g. same
  edu_pool_id can have a HIGH SCHOOL record and a COLLEGE record - both kept).
- Only EXACT full-record matches are duplicates (observed: same fam_pooling
  group returning the identical FATHER record 6 times).
- None of these APIs expose a unique row ID - dedup must be by full-content
  comparison, not by ID.
"""
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def dedupe_records(records: list[T]) -> list[T]:
    """Remove exact duplicate records, preserving first-seen order.

    Two records are duplicates only if ALL fields match exactly (after
    Pydantic normalization has already run, so e.g. "" and None are
    already unified before this function sees them).
    """
    seen: set[tuple] = set()
    result: list[T] = []
    for record in records:
        # model_dump() + sorted items -> hashable, order-independent fingerprint
        fingerprint = tuple(sorted(record.model_dump().items()))
        if fingerprint not in seen:
            seen.add(fingerprint)
            result.append(record)
    return result