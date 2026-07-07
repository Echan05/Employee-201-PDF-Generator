"""
app/services/contract_merge.py

Fetches an employee's signed contract PDF (from the `signed_contract` URL
field on the primary API record) and appends its pages to the end of an
already-rendered Employee 201 PDF.

Design notes (read before modifying):

- Failure policy is "skip silently, PDF just ends without it" — confirmed
  with Echan, same policy as the page2 document images (Section 7B of the
  handoff). This module NEVER raises out to the router for a missing or
  broken contract file. A missing/failed contract must not break the whole
  201 PDF response.
- Merge library is pikepdf (wraps qpdf), chosen over pypdf specifically for
  robustness against malformed/scanned PDFs coming out of a legacy system —
  confirmed with Echan. pikepdf's wheels bundle libqpdf statically on
  Windows/macOS/most Linux, so `pip install pikepdf` should be sufficient;
  if it isn't on Echan's machine, that's a real install blocker to report
  back, not something to silently work around here.
- This module does NOT know about `Employee201Data`/`PrimaryEmployeeRecord`
  models — it takes a plain `signed_contract_url: str | None` so it stays
  decoupled from the aggregator/model layer. The router is responsible for
  pulling that value off `data.primary.signed_contract`.
"""

from __future__ import annotations

import io
import logging

import httpx
import pikepdf

logger = logging.getLogger(__name__)

# Same timeout convention as the rest of this project's outbound legacy-API
# calls — kept as a module-level constant so it's one place to tune, not
# scattered across call sites.
FETCH_TIMEOUT_SECONDS = 15.0


async def fetch_signed_contract(signed_contract_url: str | None) -> bytes | None:
    """
    Fetch the raw bytes of the signed contract PDF from its URL.

    Returns None (never raises) if:
      - signed_contract_url is None/empty (employee has no contract on file)
      - the HTTP request fails outright (network error, timeout)
      - the server responds with a non-2xx status
      - the response body isn't a well-formed PDF at all (checked later,
        during the actual merge step in append_contract_pages — this
        function only handles the network layer)

    This mirrors the existing image-fetch failure policy in
    app/services/image_layout.py: log server-side, return nothing, let the
    caller decide what "nothing" means for the response.
    """
    if not signed_contract_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(signed_contract_url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        logger.warning(
            "Signed contract fetch failed for url=%s: %s", signed_contract_url, exc
        )
        return None


def append_contract_pages(base_pdf_bytes: bytes, contract_pdf_bytes: bytes) -> bytes:
    """
    Append every page of contract_pdf_bytes to the end of base_pdf_bytes.

    Returns the merged PDF as bytes. If contract_pdf_bytes is not a valid,
    openable PDF (corrupt file, HTML error page returned instead of a PDF,
    etc.), logs a warning and returns base_pdf_bytes UNCHANGED — this is the
    "skip silently" behavior applied to the merge step itself, not just the
    fetch step. A broken contract file must never take down an otherwise
    good 201 PDF.
    """
    try:
        with pikepdf.open(io.BytesIO(base_pdf_bytes)) as base_pdf:
            with pikepdf.open(io.BytesIO(contract_pdf_bytes)) as contract_pdf:
                base_pdf.pages.extend(contract_pdf.pages)

            output_buffer = io.BytesIO()
            base_pdf.save(output_buffer)
            return output_buffer.getvalue()
    except pikepdf.PdfError as exc:
        logger.warning("Signed contract PDF could not be merged, skipping: %s", exc)
        return base_pdf_bytes


async def append_signed_contract_if_present(
    pdf_bytes: bytes, signed_contract_url: str | None
) -> bytes:
    """
    Single entry point for the router: fetch + merge in one call.

    Always returns a usable PDF's bytes — either the original pdf_bytes
    with the contract appended, or pdf_bytes completely unchanged if
    anything along the way (missing URL, fetch failure, corrupt PDF) didn't
    work out. Never raises.

    Router usage (once app/routers/employee201.py is updated):

        pdf_bytes = await append_signed_contract_if_present(
            pdf_bytes, data.primary.signed_contract
        )
    """
    contract_bytes = await fetch_signed_contract(signed_contract_url)
    if contract_bytes is None:
        return pdf_bytes

    return append_contract_pages(pdf_bytes, contract_bytes)