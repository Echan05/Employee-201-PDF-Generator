"""
Model for: GET api_hr_201_06_minor.php?minor_pooling={rm_tran_no}

Returns a LIST of records. This is the endpoint where we directly observed
the "0000-00-00" null-date pattern (minor_exp_date) and a real image URL
with a filename (minor_image), confirming the image-URL normalizer's
"no filename = no image" rule against a positive case.

OPEN QUESTION (not yet resolved with Echan): minor_remarks sample value
was "." (a single period) - unclear if this means "no remarks" in this
legacy system, or is a real value. NOT normalized to None for now -
left as-is until confirmed.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator, field_validator
from typing_extensions import Annotated

from app.models.normalizers import (
    blank_str_to_none,
    image_url_to_none_if_no_filename,
    null_date_to_none,
)

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]


class MinorRecord(BaseModel):
    minor_pooling: int
    minor_reqs: NoneIfBlank = None          # e.g. "Certificate, Birth"
    minor_iss_date: NoneIfBlank = None
    minor_exp_date: NoneIfBlank = None
    minor_remarks: NoneIfBlank = None        # NOT auto-converted from "." - see module docstring
    minor_image: NoneIfBlank = None
    minor_controlno: NoneIfBlank = None

    @field_validator("minor_iss_date", "minor_exp_date", mode="before")
    @classmethod
    def normalize_null_date(cls, v):
        return null_date_to_none(blank_str_to_none(v))

    @field_validator("minor_image", mode="before")
    @classmethod
    def normalize_image(cls, v):
        return image_url_to_none_if_no_filename(v)