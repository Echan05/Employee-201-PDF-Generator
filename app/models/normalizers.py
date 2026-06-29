"""
Shared field normalizers for the Employee 201 source APIs.

These APIs are backed by a legacy PHP/MySQL system, which leaks several
"null but not technically null" patterns into JSON:

  - empty string ""           -> no data
  - 0 (for ID-like/zip fields) -> no data, NOT a real zero
  - "0000-00-00"              -> MySQL zero-date, no data
  - image URL with no filename (trailing "/") -> no image uploaded

Confirmed with Echan (2026-06-24): all of the above normalize to None.
Rendering layer (Jinja) is responsible for displaying None as blank space.
"""
from __future__ import annotations

NULL_DATE = "0000-00-00"


def blank_str_to_none(v):
    """Empty string -> None. Leaves other values untouched for further validation."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def zero_to_none(v):
    """0 (int or numeric string) -> None, for fields where 0 is a placeholder, not a real value.

    Only fires on exact 0 / "0" - do not use on fields where 0 is a legitimate value.
    """
    if v == 0 or v == "0":
        return None
    return v


def null_date_to_none(v):
    """MySQL zero-date "0000-00-00" -> None."""
    if isinstance(v, str) and v.strip() == NULL_DATE:
        return None
    return v


def image_url_to_none_if_no_filename(v):
    """Image URL with no filename after the final "/" -> None (treated as no image uploaded)."""
    if isinstance(v, str):
        if v.strip() == "":
            return None
        if v.rstrip("/").rsplit("/", 1)[-1] == "" or v.endswith("/"):
            return None
    return v