"""
app/services/hcb_pages.py

Renders the Health Card Benefits (HCB) image as its own small PDF so the
router can place it BEFORE the main 201 pages (page order confirmed with
Echan, 2026-10-16: contract -> HCB -> main page 1 -> remaining document
images -> security license / DDO).

Why a separate render: the main template (employee_201.html) always
renders page 1 first, so HCB cannot be moved ahead of it from inside that
template. Same approach as security_docs_merge.py - a small independent
template + WeasyPrint pass, merged with pikepdf by the router.

Failure policy: "skip silently", same as the contract and the other
document images. A missing URL, failed fetch, undecodable image or render
error returns None and never raises.

NOTE: app/templates/hcb_page.html takes its page geometry, frame and
image-page markup from the shared partials _page_base.css and
_image_pages.html (also used by employee_201.html), so the HCB page always
looks identical to the other image pages. Change image-page styling in
those partials, not here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.services.image_layout import fetch_and_classify_images, group_into_pages

logger = logging.getLogger(__name__)

HCB_LABEL = "Health Card Benefits"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
)


async def render_hcb_pdf_if_present(primary) -> bytes | None:
    """Return a PDF (as bytes) containing the HCB page, or None if the
    employee has no HCB image or it could not be fetched/rendered.

    `primary` is the aggregated PrimaryEmployeeRecord (reads .hcb_image).
    """
    hcb_url = primary.hcb_image
    if not hcb_url:
        return None

    # fetch_and_classify_images already logs and drops failed/corrupt images.
    classified = await fetch_and_classify_images([(hcb_url, HCB_LABEL)])
    if not classified:
        return None

    try:
        template = _jinja_env.get_template("hcb_page.html")
        html_string = template.render(image_pages=group_into_pages(classified))
        return HTML(string=html_string).write_pdf()
    except Exception:  # noqa: BLE001 - a broken HCB page must not take down the whole 201 PDF
        logger.exception("Failed to render Health Card Benefits page, skipping")
        return None