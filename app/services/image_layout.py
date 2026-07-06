"""
Fetches page-2 document images once, corrects orientation, measures their
real pixel dimensions to classify orientation (portrait vs landscape), and
groups them into a list of "pages" for the PDF.

Confirmed with Echan, 2026-07-02:
  - Regrouped by orientation, NOT interleaved in original field order:
    all portrait images come first (one per page), then all landscape
    images after (paired two per page).
  - Odd landscape image out gets its own solo page.
  - Every image gets a visible label (see PRIMARY_IMAGE_LABELS in
    template_context.py).

ORIENTATION CORRECTION - EXIF transpose only (PIL.ImageOps.exif_transpose).
Fixes images where the camera recorded rotation metadata but didn't
physically rotate pixel data. Free, fast, no downside - already-correct
images are unaffected (their EXIF tag is "normal" or absent).

A face-detection-based second layer (OpenCV Haar Cascade) was tried and
REMOVED, 2026-07-xx (confirmed with Echan): it correctly fixed images with
no EXIF data but a visible, correctly-oriented face (e.g. the PhilHealth
card, the NBI clearance), but a single false-positive face detection on
noisy non-face content (X-ray film grain, dense lab-report text, scan
artifacts) was enough to wrongly rotate images that were already correct
and never had a real face in them at all. Tried tightening the detector
(require an unambiguous single-angle match, scale minSize to image
dimensions) but Echan judged the tradeoff not worth it - better to
occasionally miss a real 180-degree/no-EXIF rotation than risk actively
breaking a document that was already fine. Do not re-add face-detection
orientation correction without re-confirming this decision with Echan -
this was a deliberate, tested rejection, not an oversight.

KNOWN LIMIT after this revert: an image with a genuine rotation and NO
EXIF orientation tag (e.g. a flat scan with no camera metadata) will NOT
be auto-corrected. This is an accepted, explicit tradeoff, not a bug.

Images are embedded as base64 data URIs rather than left as external URLs
so WeasyPrint does not need to re-fetch them a second time during PDF
render - we already downloaded the bytes here to correct/measure them, so
we reuse the same (now-corrected) bytes for embedding.

A failed/unreachable image URL, or one that fails to decode, must not
crash the whole PDF - dropped silently (with a server-side log) rather
than raised, consistent with the project's existing partial-failure
tolerance for secondary API sections.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from dataclasses import dataclass
from io import BytesIO

import httpx
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


@dataclass
class PageImage:
    data_uri: str
    orientation: str  # "portrait" or "landscape"
    label: str


async def _fetch_and_measure(client: httpx.AsyncClient, url: str, label: str) -> PageImage | None:
    """Fetch one image, correct orientation via EXIF, determine
    orientation from its real post-correction pixel dimensions, and
    build a base64 data URI from the corrected bytes."""
    try:
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        content = resp.content
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch page-2 image %s: %s", url, exc)
        return None

    try:
        with Image.open(BytesIO(content)) as raw_img:
            img_format = raw_img.format or "JPEG"
            corrected_img = ImageOps.exif_transpose(raw_img)
            width, height = corrected_img.size

            buffer = BytesIO()
            corrected_img.save(buffer, format=img_format)
            corrected_bytes = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - a corrupt/unsupported image must not crash the whole request
        logger.warning("Failed to read/correct orientation for page-2 image %s: %s", url, exc)
        return None

    orientation = "landscape" if width > height else "portrait"

    mime_type = mimetypes.guess_type(url)[0] or f"image/{img_format.lower()}"
    encoded = base64.b64encode(corrected_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{encoded}"

    return PageImage(data_uri=data_uri, orientation=orientation, label=label)


async def fetch_and_classify_images(image_url_label_pairs: list[tuple[str, str]]) -> list[PageImage]:
    """Fetch all given (url, label) pairs concurrently. Returns only the
    ones that succeeded, each tagged with measured orientation and its
    label. Failures are dropped (logged), not raised."""
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_and_measure(client, url, label) for url, label in image_url_label_pairs]
        )
    return [r for r in results if r is not None]


def group_into_pages(images: list[PageImage]) -> list[list[PageImage]]:
    """Regroup by orientation (confirmed with Echan: all portraits first,
    then all landscapes after - NOT interleaved in original order).
    Portraits: one per page. Landscapes: paired two per page, last odd one
    solo. Returns a list of "pages", each page being a list of 1 or 2
    PageImage objects for the template to render."""
    portraits = [img for img in images if img.orientation == "portrait"]
    landscapes = [img for img in images if img.orientation == "landscape"]

    pages: list[list[PageImage]] = [[p] for p in portraits]

    for i in range(0, len(landscapes), 2):
        pair = landscapes[i:i + 2]  # last iteration may be length 1 - solo page, per Echan
        pages.append(pair)

    return pages