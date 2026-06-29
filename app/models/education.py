"""
Model for: GET api_hr_201_03_educ.php?edu_pool_id={rm_tran_no}

Returns a LIST of records. Multiple records share the same edu_pool_id
by design (elementary/high school/college/grad studies are all separate
records under one employee). Confirmed (Echan, 2026-06-24): records with
the same edu_pool_id but different field content (school/course/year) are
ALL valid and must be kept - only exact full-content duplicates collapse.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator
from typing_extensions import Annotated

from app.models.normalizers import blank_str_to_none

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]


class EducationRecord(BaseModel):
    edu_pool_id: int
    edu_type: NoneIfBlank = None      # e.g. "A. HIGH SCHOOL"
    edu_school: NoneIfBlank = None
    edu_course: NoneIfBlank = None
    edu_year: NoneIfBlank = None      # kept as string range e.g. "2015-2017", not a date type
    