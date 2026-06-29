"""
Model for: GET api_hr_201_01_main.php?erms_id={erms_id}

Confirmed sample (Echan, 2026-06-24):
{
    "rm_tran_no": 53383,
    "erms_id": 23376492,
    "rm_lastname": "CADORNA",
    ...
}
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, BeforeValidator, field_validator
from typing_extensions import Annotated

from app.models.normalizers import (
    blank_str_to_none,
    zero_to_none,
)

NoneIfBlank = Annotated[Optional[str], BeforeValidator(blank_str_to_none)]
NoneIfZero = Annotated[Optional[int], BeforeValidator(zero_to_none)]


class PrimaryEmployeeRecord(BaseModel):
    rm_tran_no: int
    erms_id: int

    # Identity
    rm_lastname: str
    rm_first_name: str
    rm_middle_name: NoneIfBlank = None
    rm_other_name: NoneIfBlank = None

    # Contact
    rm_email_address: NoneIfBlank = None
    rm_contact_no: NoneIfBlank = None

    # Personal
    rm_gender: NoneIfBlank = None
    rm_civiil_status: NoneIfBlank = None  # NOTE: typo "civiil" is in the live API field name, kept as-is
    rm_religion: NoneIfBlank = None
    rm_height: NoneIfBlank = None
    rm_weight: NoneIfBlank = None

    # Government IDs
    rm_sss_no: NoneIfBlank = None
    rm_pagibig_no: NoneIfBlank = None
    rm_phhealth: NoneIfBlank = None
    rm_tin: NoneIfBlank = None

    # Emergency contact
    rm_incase_contact: NoneIfBlank = None
    rm_incase_rela: NoneIfBlank = None
    rm_incase_add: NoneIfBlank = None
    rm_incace_contactno: NoneIfBlank = None  # NOTE: typo "incace" is in the live API field name, kept as-is

    # Employment
    contract_sdate: NoneIfBlank = None  # TODO: confirm date format / 0000-00-00 handling once seen in real data

    # Current address
    cur_street: NoneIfBlank = None
    cur_subd: NoneIfBlank = None
    cur_town: NoneIfBlank = None
    cur_prov: NoneIfBlank = None
    cur_zip: NoneIfZero = None

    # Provincial address
    prov_street: NoneIfBlank = None
    prov_subd: NoneIfBlank = None
    prov_town: NoneIfBlank = None
    prov_prov: NoneIfBlank = None
    prov_zip: NoneIfZero = None

    # Document images (URLs)
    gcash_image: NoneIfBlank = None
    sss_image: NoneIfBlank = None
    drug_test_image: NoneIfBlank = None
    valid_id_image: NoneIfBlank = None
    valid_id_image_rear: NoneIfBlank = None
    heath_card_image: NoneIfBlank = None  # NOTE: typo "heath" is in the live API field name, kept as-is
    hcb_image: NoneIfBlank = None
    ph_image: NoneIfBlank = None
    nbi_image: NoneIfBlank = None
    ub_image: NoneIfBlank = None

    @field_validator(
        "gcash_image", "sss_image", "drug_test_image", "valid_id_image",
        "valid_id_image_rear", "heath_card_image", "hcb_image", "ph_image",
        "nbi_image", "ub_image",
        mode="before",
    )
    @classmethod
    def normalize_image_url(cls, v):
        from app.models.normalizers import image_url_to_none_if_no_filename
        return image_url_to_none_if_no_filename(v)