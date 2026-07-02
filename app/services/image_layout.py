"""
Fetches page-2 document images once, corrects their orientation, measures
their real pixel dimensions to classify orientation (portrait vs
landscape), and groups them into a list of "pages" for the PDF.

Confirmed with Echan, 2026-07-02:
  - Regrouped by orientation, NOT interleaved in original field order:
    all portrait images come first (one per page), then all landscape
    images after (paired two per page).
  - Odd landscape image out gets its own solo page.
  - Every image gets a visible label (see PRIMARY_IMAGE_LABELS in
    template_context.py).

ORIENTATION CORRECTION - two layers, in order:

1. EXIF transpose (PIL.ImageOps.exif_transpose): fixes images where the
   camera recorded an Orientation tag but didn't physically rotate pixel
   data. Free, fast, but does nothing if no EXIF tag is present.

2. Face-detection-based correction (OpenCV Haar Cascade), confirmed with
   Echan 2026-07-02 as the lightweight alternative to full OCR: tries the
   image at 0/90/180/270 degrees and keeps whichever rotation yields the
   most confident frontal-face detection. This is necessary because a
   180-degree rotation does NOT change an image's width/height at all -
   no geometry/aspect-ratio check can ever distinguish upright-landscape
   from upside-down-landscape. Only content-aware detection can.
   KNOWN LIMIT: only helps images that actually contain a visible face
   (most ID/card photos do; lab reports, X-rays, diplomas etc. do not,
   and are left untouched by this step - same as before, not a
   regression). If no face is confidently found at any of the 4 angles,
   the image is left as EXIF-transpose left it rather than guessing.

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

import cv2
import httpx
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


@dataclass
class PageImage:
    data_uri: str
    orientation: str  # "portrait" or "landscape"
    label: str


def _correct_face_orientation(pil_image: Image.Image) -> Image.Image:
    """Try the image at 0/90/180/270 degrees, return whichever rotation
    yields the most confident frontal-face detection (highest face count
    as a simple confidence proxy). Returns the ORIGINAL image unchanged
    if no face is confidently detected at any angle - guessing here would
    risk actively rotating an already-correct image, which is worse than
    leaving a genuinely-unfixable one alone."""
    best_image = pil_image
    best_count = 0

    for angle in (0, 90, 180, 270):
        candidate = pil_image.rotate(angle, expand=True)
        gray = np.array(candidate.convert("L"))
        faces = _FACE_CASCADE.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )
        if len(faces) > best_count:
            best_count = len(faces)
            best_image = candidate

    return best_image


async def _fetch_and_measure(client: httpx.AsyncClient, url: str, label: str) -> PageImage | None:
    """Fetch one image, correct orientation (EXIF, then face-detection
    fallback), determine orientation from its real post-correction pixel
    dimensions, and build a base64 data URI from the corrected bytes."""
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
            exif_corrected = ImageOps.exif_transpose(raw_img)
            fully_corrected = _correct_face_orientation(exif_corrected)
            width, height = fully_corrected.size

            buffer = BytesIO()
            fully_corrected.save(buffer, format=img_format)
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