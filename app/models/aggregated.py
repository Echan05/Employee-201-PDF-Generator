"""
The unified Employee 201 data model.

This is the ONLY model the Jinja template and PDF generator should ever
consume. It is produced exclusively by app.services.aggregator.

Design decision (confirmed with Echan, 2026-06-24):
- If a secondary API fails/times out, we continue with partial data.
- Failure vs. genuinely-empty-section are tracked separately in `status`/
  `error_detail` for SERVER-SIDE LOGGING ONLY. The template does not branch
  on status - a failed section and an empty section render identically
  (just an empty section in the PDF). status/error_detail exist purely so
  we have visibility into how often these APIs fail in production.
"""
from __future__ import annotations

from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

from app.models.education import EducationRecord
from app.models.employment import EmploymentHistoryRecord
from app.models.minor import MinorRecord
from app.models.parent import ParentRecord
from app.models.primary import PrimaryEmployeeRecord
from app.models.training import TrainingRecord

T = TypeVar("T", bound=BaseModel)

SectionStatus = Literal["ok", "failed", "timeout"]


class SectionResult(BaseModel, Generic[T]):
    data: list[T] = []
    status: SectionStatus = "ok"
    error_detail: Optional[str] = None


class Employee201Data(BaseModel):
    primary: PrimaryEmployeeRecord
    parents: SectionResult[ParentRecord]
    education: SectionResult[EducationRecord]
    employment: SectionResult[EmploymentHistoryRecord]
    training: SectionResult[TrainingRecord]
    minors: SectionResult[MinorRecord]