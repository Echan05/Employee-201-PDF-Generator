"""
FastAPI router for the Employee 201 File PDF endpoint.

GET /employee-201?erms_id=X

Wires together pieces that already existed in isolation:
    aggregator.aggregate_employee_201()
        -> template_context.build_template_context()
        -> Jinja2 render of app/templates/employee_201.html
        -> WeasyPrint HTML -> PDF bytes
        -> contract_merge.append_signed_contract_if_present()
        -> security_docs_merge.append_security_docs_if_present()   [NEW]
        -> HTTP response with Content-Disposition attachment

Error mapping (per PROJECT_HANDOFF.md section 9.3):
    InvalidErmsId          -> 400 Bad Request  (erms_id=0, structurally invalid input)
    PrimaryRecordNotFound   -> 404 Not Found    (valid-looking erms_id, no matching record)
    anything else (render/PDF failure) -> 500, logged with full traceback

Page order in the final PDF, confirmed this session:
    main template pages (page 1 + page2 document images)
    -> signed contract pages (Section 7F)
    -> security license / DDO pages (NEW - must come after the contract,
       hence the separate WeasyPrint pass + pikepdf merge in
       security_docs_merge.py rather than being part of the main template)
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.services.aggregator import (
    InvalidErmsId,
    PrimaryRecordNotFound,
    aggregate_employee_201,
)
from app.services.contract_merge import append_signed_contract_if_present
from app.services.image_layout import fetch_and_classify_images, group_into_pages
from app.services.security_docs_merge import append_security_docs_if_present
from app.services.template_context import build_template_context

logger = logging.getLogger(__name__)

router = APIRouter()

# Templates dir is app/templates/ - this file lives at app/routers/, so go
# up one level then into templates/.
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Static preview shell (plain HTML/JS, no Jinja needed - erms_id is read
# client-side from the URL query string). Separate from TEMPLATES_DIR since
# this isn't PDF content, it's the browser-facing wrapper page.
PREVIEW_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "employee_201_preview.html"

# autoescape=False to match how dev_preview/render_preview.py has been
# rendering the template during development (per Section 7 of the handoff,
# the template was visually confirmed against that rendering path - turning
# autoescape on here would risk divergence from what Echan already verified
# in the browser/PDF). CONFIRM against render_preview.py's actual Environment
# setup before this ships - if that file uses autoescape=True, flip this.
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
)

# Characters not allowed (or risky) in filenames across Windows/Mac/Linux
# and in a Content-Disposition header value: \ / : * ? " < > | plus control chars.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _build_download_filename(primary) -> str:
    """Build '{LASTNAME}, {FIRSTNAME} {MIDDLENAME} - 201.pdf'.

    Middle name is Optional on the primary record (per Section 7 of the
    handoff, several fields normalize to None) - if absent, we omit it
    rather than printing a literal 'None' into the filename.
    """
    last = (primary.rm_lastname or "").strip()
    first = (primary.rm_first_name or "").strip()
    middle = (primary.rm_middle_name or "").strip()

    name_part = f"{first} {middle}".strip() if middle else first
    raw_filename = f"{last}, {name_part} - 201.pdf"

    return _UNSAFE_FILENAME_CHARS.sub("", raw_filename)


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition header with both a plain ASCII fallback
    and an RFC 5987 UTF-8 filename* param, for names containing accented
    characters (not uncommon in PH names) or the comma in our format."""
    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii") or "employee-201.pdf"
    utf8_quoted = quote(filename)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{utf8_quoted}'


async def _to_data_uri(url: str) -> str | None:
    """Fetch one remote image URL and return a base64 data URI.

    Returns None on any fetch/HTTP error so header rendering can degrade
    gracefully without failing the whole PDF generation.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=20.0)
            resp.raise_for_status()
            content = resp.content
            content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch header logo %s: %s", url, exc)
        return None

    if not content:
        logger.warning("Header logo URL returned empty response body: %s", url)
        return None

    mime_type = content_type if content_type.startswith("image/") else (mimetypes.guess_type(url)[0] or "image/png")
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


@router.get("/employee-201/view", response_class=HTMLResponse)
async def get_employee_201_preview_page():
    """Serves the static preview page shell. The page itself fetches the
    actual PDF client-side from GET /employee-201?erms_id=X (the endpoint
    above) - this route just returns the HTML/CSS/JS wrapper, nothing
    employee-specific happens server-side here."""
    html = PREVIEW_HTML_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/employee-201")
async def get_employee_201_pdf(
    erms_id: int = Query(..., description="Employee erms_id from the legacy HR system"),
):
    try:
        data = await aggregate_employee_201(erms_id)
    except InvalidErmsId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PrimaryRecordNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        context = build_template_context(data)

        # Convert logo URL to an embedded data URI so PDF rendering is not
        # dependent on an additional remote fetch at WeasyPrint render time.
        # If unavailable/unreachable, render without logo (no hard failure).
        header_logo_url = context.get("header_logo_url")
        if header_logo_url:
            context["header_logo_url"] = await _to_data_uri(header_logo_url)

        # page2_images is the raw ordered URL list from template_context.py -
        # consumed here (not passed to the template directly) since fetching
        # and measuring orientation requires async I/O that template_context.py
        # deliberately doesn't do (kept pure/sync).
        page2_image_urls = context.pop("page2_images", [])
        classified_images = await fetch_and_classify_images(page2_image_urls)
        context["image_pages"] = group_into_pages(classified_images)

        template = jinja_env.get_template("employee_201.html")
        html_string = template.render(**context)
        pdf_bytes = HTML(string=html_string).write_pdf()

        # Append the employee's signed contract (fetched from
        # primary.signed_contract) as extra pages at the end of the PDF.
        # Fails silently - returns pdf_bytes unchanged - if the URL is
        # missing, unreachable, or not a valid PDF. Same "skip silently"
        # policy as page2 images (Section 7B of the handoff).
        pdf_bytes = await append_signed_contract_if_present(
            pdf_bytes, data.primary.signed_contract
        )

        # Append Security License / DDO pages, in that order, AFTER the
        # signed contract - confirmed placement this session. Each group
        # (License, DDO) is judged independently inside
        # append_security_docs_if_present and skipped silently if its
        # image field is blank/missing. [NEW this session]
        pdf_bytes = await append_security_docs_if_present(pdf_bytes, data.primary)
    except Exception as exc:  # noqa: BLE001 - last line of defense, must not leak a raw 500 with no context
        logger.exception("Failed to render/generate PDF for erms_id=%s", erms_id)
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from exc

    filename = _build_download_filename(data.primary)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _content_disposition(filename),
            # ASCII-safe, JS does decodeURIComponent(). Raw filename can
            # contain non-Latin1 characters (e.g. accented PH surnames)
            # which would crash if put directly into a header value.
            "X-Filename": quote(filename),
        },
    )