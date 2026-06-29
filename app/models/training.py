"""
Model for: GET api_hr_201_05_traning.php?training_pooling_no={rm_tran_no}

Note: the live endpoint filename is "traning.php" (typo, missing "i") -
kept as documented since this is the real URL, not a typo to fix.

Returns a LIST of records, one per training/seminar attended.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator, field_validator
from typing_extensions import Annotated

from app.models.normalizers import blank_str_to_none, null_date_to_none

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]


class TrainingRecord(BaseModel):
    training_pooling_no: int
    traning_school: NoneIfBlank = None     # NOTE: typo "traning" is in the live API field name, kept as-is
    training_course: NoneIfBlank = None
    training_sdate: NoneIfBlank = None
    training_edate: NoneIfBlank = None

    @field_validator("training_sdate", "training_edate", mode="before")
    @classmethod
    def normalize_null_date(cls, v):
        return null_date_to_none(blank_str_to_none(v))