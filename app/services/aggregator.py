"""
Aggregation service for the Employee 201 File.

Call sequence (confirmed with Echan, 2026-06-24):
  1. AWAIT primary record fetch using erms_id -> extract rm_tran_no.
     This is a hard sequential dependency - the 5 secondary calls cannot
     fire until rm_tran_no is known. If this call fails, we cannot
     proceed at all (no PDF without the primary record).
  2. Once rm_tran_no is known, fire all 5 secondary calls CONCURRENTLY -
     they don't depend on each other, only on step 1's result. The
     company-directory lookup (added 2026-07-06) also fires here,
     concurrently with the 5 secondary calls - it only depends on
     primary.company_name_con, already known at this point, not on
     rm_tran_no.
  3. Each secondary call is individually fault-tolerant (continue with
     partial data per Echan's decision) - one API failing must not
     cancel the others or fail the whole request.
  4. Dedup is applied per-section using app.services.dedup.dedupe_records.

TODO before production: confirm the actual base URL / auth scheme.
Currently assumes no auth header is required (matches what Echan has
shown so far - plain GET with query params, no token visible).
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.services.table_cache import get_cached_table
from app.models.aggregated import Employee201Data, SectionResult
from app.models.company import CompanyRecord
from app.models.education import EducationRecord
from app.models.employment import EmploymentHistoryRecord
from app.models.minor import MinorRecord
from app.models.parent import ParentRecord
from app.models.primary import PrimaryEmployeeRecord
from app.models.training import TrainingRecord
from app.services.dedup import dedupe_records

logger = logging.getLogger(__name__)


def _required_env(name: str) -> str:
    """Read a required environment variable, failing loudly and clearly
    at startup rather than with a bare KeyError buried in a stack trace
    the first time something tries to use it."""
    try:
        return os.environ[name]
    except KeyError as exc:
        raise RuntimeError(
            f"{name} is not set. Add it to your .env file - see .env.example for the full template."
        ) from exc


BASE_URL = "https://cmiitdept.com/hr"
ENDPOINT_PRIMARY = "api_hr_201_01_main.php"
ENDPOINT_PARENTS = "api_hr_201_02_parents.php"
ENDPOINT_EDUCATION = "api_hr_201_03_educ.php"
ENDPOINT_EMPLOYMENT = "api_hr_201_04_employment.php"
ENDPOINT_TRAINING = "api_hr_201_05_traning.php"
ENDPOINT_MINOR = "api_hr_201_06_minor.php"
COMPANY_ENDPOINT = "api_company.php"

# (endpoint path, query param name, response model, friendly name for logging)
SECONDARY_ENDPOINTS = [
    (ENDPOINT_PARENTS, "fam_pooling", ParentRecord, "parents"),
    (ENDPOINT_EDUCATION, "edu_pool_id", EducationRecord, "education"),
    (ENDPOINT_EMPLOYMENT, "history_pooling", EmploymentHistoryRecord, "employment"),
    (ENDPOINT_TRAINING, "training_pooling_no", TrainingRecord, "training"),
    (ENDPOINT_MINOR, "minor_pooling", MinorRecord, "minors"),
]


class PrimaryRecordNotFound(Exception):
    """Raised when the primary employee record cannot be fetched - this is fatal,
    there is no PDF without it."""


class InvalidErmsId(Exception):
    """Raised when erms_id is 0 (employee not yet processed) or otherwise
    structurally invalid - this is a bad request, not a missing record."""


async def fetch_primary_record(client: httpx.AsyncClient, erms_id: int) -> PrimaryEmployeeRecord:
    """Fetch the primary employee record matching erms_id.

    CONFIRMED (Echan, 2026-06-25): api_hr_201_01_main.php does NOT filter
    by the erms_id query param - it always returns the full table
    (~23,236 records as of this writing) wrapped in an envelope:
        {"status": "success", "total": <int>, "data": [ {...}, ... ]}

    There is no server-side filtering available (undocumented legacy API,
    confirmed no alternate filter param exists). We fetch the full table
    and filter client-side. erms_id is confirmed unique across processed
    employees, so first match is safe - no duplicate-handling needed.

    erms_id == 0 marks an employee not yet processed by HR and must be
    rejected before searching (these records are real but exist purely as
    incomplete placeholders - 0 is not a valid lookup key for any employee).
    """
    if erms_id == 0:
        raise InvalidErmsId("erms_id=0 indicates an employee that has not been processed yet; cannot generate 201 file.")

    async def _fetch_raw() -> dict:
        url = f"{BASE_URL}/{ENDPOINT_PRIMARY}"
        resp = await client.get(url, timeout=30.0)  # no point passing erms_id - server ignores it; longer timeout for full-table fetch
        resp.raise_for_status()
        return resp.json()

    try:
        envelope = await get_cached_table(ENDPOINT_PRIMARY, _fetch_raw)
    except (httpx.HTTPError, ValueError) as exc:
        raise PrimaryRecordNotFound(f"Failed to fetch primary employee table: {exc}") from exc

    records = envelope.get("data", [])
    if not isinstance(records, list):
        raise PrimaryRecordNotFound(f"Unexpected response shape from primary API: 'data' is not a list")

    match = next((r for r in records if r.get("erms_id") == erms_id), None)
    if match is None:
        raise PrimaryRecordNotFound(f"No employee found with erms_id={erms_id}")

    return PrimaryEmployeeRecord(**match)


async def fetch_section(
    client: httpx.AsyncClient,
    endpoint: str,
    param_name: str,
    rm_tran_no: int,
    model_cls,
    section_name: str,
) -> SectionResult:
    """Fetch and filter one secondary section for a single employee.

    CONFIRMED (Echan, 2026-06-25): ALL 5 secondary endpoints share the same
    bug as the primary endpoint - they ignore their filter query param
    entirely and always return the full table (e.g. parents.php returned
    1127 records identically whether fam_pooling=53383 or fam_pooling=999999999).

    We fetch the full table and filter client-side by matching param_name
    against rm_tran_no, BEFORE deduping - dedup must only ever compare
    records within the same employee's filtered subset, never across the
    full unfiltered table.
    """
    async def _fetch_raw() -> dict:
        url = f"{BASE_URL}/{endpoint}"
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    try:
        envelope = await get_cached_table(endpoint, _fetch_raw)
    except httpx.TimeoutException as exc:
        logger.warning("Section '%s' timed out for rm_tran_no=%s: %s", section_name, rm_tran_no, exc)
        return SectionResult(data=[], status="timeout", error_detail=str(exc))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Section '%s' failed for rm_tran_no=%s: %s", section_name, rm_tran_no, exc)
        return SectionResult(data=[], status="failed", error_detail=str(exc))

    all_records = envelope.get("data", []) if isinstance(envelope, dict) else envelope
    if not isinstance(all_records, list):
        logger.warning("Section '%s' unexpected response shape for rm_tran_no=%s", section_name, rm_tran_no)
        return SectionResult(data=[], status="failed", error_detail="'data' is not a list")

    matching_raw = [r for r in all_records if r.get(param_name) == rm_tran_no]

    try:
        records = [model_cls(**item) for item in matching_raw]
    except Exception as exc:  # noqa: BLE001 - validation errors must not crash the whole request
        logger.warning("Section '%s' returned unparseable data for rm_tran_no=%s: %s", section_name, rm_tran_no, exc)
        return SectionResult(data=[], status="failed", error_detail=str(exc))

    deduped = dedupe_records(records)
    if len(deduped) < len(records):
        logger.info(
            "Section '%s' for rm_tran_no=%s: removed %d exact duplicate(s) (%d -> %d)",
            section_name, rm_tran_no, len(records) - len(deduped), len(records), len(deduped),
        )

    return SectionResult(data=deduped, status="ok")


async def fetch_company_directory(client: httpx.AsyncClient) -> list[CompanyRecord]:
    """Fetch the full company directory (18 rows as of 2026-07-06, real
    payload confirmed).

    ASSUMED, NOT YET DIRECTLY TESTED: that api_company.php shares the same
    "ignores its query params, always returns the full table" behavior as
    the other 6 endpoints (Section 4 of the handoff doc). Harmless if the
    assumption is wrong either way - the table is tiny, so a full fetch +
    client-side match costs nothing extra. Uses the same table_cache as
    everything else, per Echan's confirmation to reuse that pattern here.
    """
    async def _fetch_raw() -> dict:
        url = f"{BASE_URL}/{COMPANY_ENDPOINT}"
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    try:
        envelope = await get_cached_table(COMPANY_ENDPOINT, _fetch_raw)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Company directory fetch failed: %s", exc)
        return []

    records = envelope.get("data", []) if isinstance(envelope, dict) else envelope
    if not isinstance(records, list):
        logger.warning("Company directory: unexpected response shape, 'data' is not a list")
        return []

    try:
        return [CompanyRecord(**row) for row in records]
    except Exception as exc:  # noqa: BLE001 - a bad row here must not break the whole PDF
        logger.warning("Company directory returned unparseable data: %s", exc)
        return []


def match_company(company_name_con: str | None, directory: list[CompanyRecord]) -> CompanyRecord | None:
    """Match primary.company_name_con against company_name_con_x.

    Case/whitespace-insensitive compare - cheap insurance against minor
    formatting drift, NOT yet confirmed necessary (a real sample of
    primary.company_name_con hasn't been checked against this match logic
    yet - worth a real test the first time this runs against live data).

    First match wins if company_name_con_x has duplicates. Known real case:
    "MEGATEKTON MANUFACTURING CORP. (MET)" and "... (SEE)" both reduce to
    company_name_con_x == "MEGATEKTON MANUFACTURING CORP." - harmless for
    this feature since both rows share the same `company` and
    `company_id_logo` values (they only diverge on signatory/header, which
    this feature doesn't use). Re-check this if signatory/header ever get
    pulled in later.
    """
    if not company_name_con:
        return None
    target = company_name_con.strip().upper()
    for row in directory:
        if row.company_name_con_x and row.company_name_con_x.strip().upper() == target:
            return row
    return None


async def aggregate_employee_201(erms_id: int) -> Employee201Data:
    async with httpx.AsyncClient() as client:
        # Step 1: primary record is a hard sequential dependency - must complete
        # before we know rm_tran_no for the 5 secondary calls.
        primary = await fetch_primary_record(client, erms_id)
        rm_tran_no = primary.rm_tran_no

        # Step 2: fire all 5 secondary calls concurrently, plus the company
        # directory lookup (only needs primary.company_name_con, already known).
        # return_exceptions is NOT needed for the secondary calls because
        # fetch_section already catches its own errors internally and always
        # returns a SectionResult, never raises. fetch_company_directory follows
        # the same never-raises contract, returning [] on failure.
        section_results, company_directory = await asyncio.gather(
            asyncio.gather(
                *[
                    fetch_section(client, endpoint, param_name, rm_tran_no, model_cls, name)
                    for endpoint, param_name, model_cls, name in SECONDARY_ENDPOINTS
                ]
            ),
            fetch_company_directory(client),
        )

        sections = dict(zip([name for _, _, _, name in SECONDARY_ENDPOINTS], section_results))
        company_match = match_company(primary.company_name_con, company_directory)

        return Employee201Data(
            primary=primary,
            parents=sections["parents"],
            education=sections["education"],
            employment=sections["employment"],
            training=sections["training"],
            minors=sections["minors"],
            company_match=company_match,  # requires this field added to Employee201Data - see chat note
        )