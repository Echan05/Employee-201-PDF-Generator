"""
app/services/security_docs_merge.py

Renders and appends the Security License and Duty Detail Order (DDO) pages
to an already-fully-merged Employee 201 PDF (main template pages + page2
document images + signed contract, in that order - see
app/routers/employee201.py for the exact pipeline order).

Design notes (mirrors app/services/contract_merge.py's conventions):

- Failure/absence policy: "skip silently." Each of the two groups (Security
  License, DDO) is judged independently - if `sg_license` is blank/missing,
  the License page (and its associated seculic_* text fields) is omitted
  entirely, not left as a blank page. Same for `ddo` and `secu_ddo_date`.
  This mirrors the existing rule for page2 document images (Section 7B)
  and the signed contract (Section 7F): missing data means "don't render
  that page," never an error surfaced to the requester.
- No EXIF orientation correction on these two images - confirmed with
  Echan as an explicit simplification vs. the page2 image pipeline
  (image_layout.py). If a security license or DDO photo comes in sideways,
  it renders sideways; nothing corrects it. Revisit only if this is
  reported as a real problem in practice.
- Rendered as its OWN small Jinja2 template + WeasyPrint pass
  (security_docs.html), independent of app/templates/employee_201.html,
  because these pages must land AFTER the signed contract in the final
  PDF - the contract is appended via a raw pikepdf byte-merge that happens
  entirely outside the main WeasyPrint render (see contract_merge.py), so
  there is no way to get "after the contract" by adding these pages inside
  the main template. Instead: render this fragment on its own, then
  pikepdf-merge it onto pdf_bytes AFTER append_signed_contract_if_present
  has already run - confirmed with Echan as the intended page order.
- Plain httpx GET per image, same FETCH_TIMEOUT_SECONDS convention as
  contract_merge.py. A failed fetch for one image does not affect the
  other group - each is fetched and judged independently.
- Takes the aggregated `primary` record directly (reads .sg_license,
  .ddo, .seculic_no, etc. off it) rather than unpacking six separate
  arguments at the call site.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

import httpx
import pikepdf
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 15.0

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
)


async def _fetch_image_data_uri(url: str | None) -> str | None:
    """Fetch one remote image and return it as a base64 data URI.

    Returns None (never raises) for a missing URL, network failure, or
    non-2xx response - same failure policy as the rest of this project's
    image fetches. No EXIF correction here (see module docstring).
    """
    if not url:
        return None

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
            content_type = (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
    except httpx.HTTPError as exc:
        logger.warning("Security doc image fetch failed for url=%s: %s", url, exc)
        return None

    if not content:
        logger.warning("Security doc image URL returned empty response body: %s", url)
        return None

    mime_type = content_type if content_type.startswith("image/") else "image/jpeg"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_security_docs_pdf(context: dict) -> bytes:
    """Render security_docs.html with the given context through WeasyPrint,
    returning raw PDF bytes for the pikepdf merge step to append."""
    template = _jinja_env.get_template("security_docs.html")
    html_string = template.render(**context)
    return HTML(string=html_string).write_pdf()


def _append_pdf_bytes(base_pdf_bytes: bytes, extra_pdf_bytes: bytes) -> bytes:
    """Append every page of extra_pdf_bytes onto base_pdf_bytes.

    Same pikepdf pattern as contract_merge.append_contract_pages. If
    extra_pdf_bytes somehow isn't a valid PDF (shouldn't happen since we
    just rendered it ourselves via WeasyPrint, but handled defensively the
    same way contract_merge.py treats an externally-sourced PDF), logs and
    returns base_pdf_bytes unchanged rather than raising.
    """
    try:
        with pikepdf.open(io.BytesIO(base_pdf_bytes)) as base_pdf:
            with pikepdf.open(io.BytesIO(extra_pdf_bytes)) as extra_pdf:
                base_pdf.pages.extend(extra_pdf.pages)

            output_buffer = io.BytesIO()
            base_pdf.save(output_buffer)
            return output_buffer.getvalue()
    except pikepdf.PdfError as exc:
        logger.warning("Security docs pages could not be merged, skipping: %s", exc)
        return base_pdf_bytes


async def append_security_docs_if_present(pdf_bytes: bytes, primary) -> bytes:
    """
    Single entry point for the router - mirrors
    contract_merge.append_signed_contract_if_present's shape.

    Fetches sg_license and ddo images independently (one missing does not
    affect the other), renders whichever page(s) have a valid image via
    security_docs.html, and pikepdf-merges that onto pdf_bytes. MUST be
    called after append_signed_contract_if_present so these pages land
    after the contract, per the confirmed page order.

    `primary` is the aggregated PrimaryEmployeeRecord (or anything with
    the same attribute names).

    Always returns usable PDF bytes. Never raises. If both images are
    missing/blank, pdf_bytes is returned completely unchanged with no
    WeasyPrint render attempted at all (cheap no-op path).
    """
    license_data_uri = await _fetch_image_data_uri(primary.sg_license)
    ddo_data_uri = await _fetch_image_data_uri(primary.ddo)

    if license_data_uri is None and ddo_data_uri is None:
        return pdf_bytes

    context = {
        "show_license_page": license_data_uri is not None,
        "license_image": license_data_uri,
        "seculic_no": primary.seculic_no,
        "seculic_iss_date": primary.seculic_iss_date,
        "seculic_exp_date": primary.seculic_exp_date,
        "show_ddo_page": ddo_data_uri is not None,
        "ddo_image": ddo_data_uri,
        "secu_ddo_date": primary.secu_ddo_date,
    }

    security_docs_pdf_bytes = _render_security_docs_pdf(context)
    return _append_pdf_bytes(pdf_bytes, security_docs_pdf_bytes)