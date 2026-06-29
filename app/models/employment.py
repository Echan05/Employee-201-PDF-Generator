"""
Model for: GET api_hr_201_04_employment.php?history_pooling={rm_tran_no}

Returns a LIST of records, one per previous employer/position.
Dates observed so far are valid (e.g. "2023-02-22") but TODO: confirm
whether history_sdate/history_edate can also hit the "0000-00-00"
null-date pattern - not yet observed in a real sample for this endpoint.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator, field_validator
from typing_extensions import Annotated

from app.models.normalizers import blank_str_to_none, null_date_to_none

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]


class EmploymentHistoryRecord(BaseModel):
    history_pooling: int
    history_company: NoneIfBlank = None
    history_position: NoneIfBlank = None
    history_sdate: NoneIfBlank = None
    history_edate: NoneIfBlank = None

    @field_validator("history_sdate", "history_edate", mode="before")
    @classmethod
    def normalize_null_date(cls, v):
        return null_date_to_none(blank_str_to_none(v))