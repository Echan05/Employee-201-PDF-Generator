"""
Model for: GET api_hr_201_02_parents.php?fam_pooling={rm_tran_no}

Returns a LIST of records. Multiple records may share the same fam_pooling
value - this is normal (father + mother + guardian are separate records).

Confirmed with Echan (2026-06-24): records can also be EXACT duplicates
within the same fam_pooling group (e.g. same father record repeated 6x).
Exact duplicates must be collapsed to one; non-identical records with the
same fam_pooling must all be kept (see app/services/dedup.py).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator
from typing_extensions import Annotated

from app.models.normalizers import blank_str_to_none

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]


class ParentRecord(BaseModel):
    fam_pooling: int
    fam_rela: NoneIfBlank = None      # e.g. "FATHER", "MOTHER", "GUARDIAN"
    fam_name: NoneIfBlank = None
    fam_age: NoneIfBlank = None       # kept as string - sample shows "59", "50" as strings not ints
    fam_ocu: NoneIfBlank = None       # occupation