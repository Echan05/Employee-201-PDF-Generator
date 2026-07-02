from __future__ import annotations

from app.models.aggregated import Employee201Data

# Reference form's 4 education row labels, in display order.
# Confirmed real values: "A.  HIGH SCHOOL", "B. COLLEGE", "C. VOCATIONAL",
# "D. POST GRADUATE" - matched by leading letter, not exact string, since
# spacing is inconsistent in the source data (e.g. "A.  HIGH SCHOOL" has
# two spaces after the period in some records).
EDUCATION_LEVELS = [
    ("ELEMENTARY", "E"),  # UNVERIFIED - never seen in real data, guessed prefix
    ("HIGH SCHOOL", "A"),
    ("COLLEGE", "B"),
    ("VOC. COURSE", "C"),
]

# Order for page 2's image display. minor_image(s) always come first
# (per Echan), then the primary record's own images in this fixed order.
# "Skip if missing" is enforced by _collect_page2_images below, not here -
# this list is just field names, existence-checked at collection time.
# Labels confirmed with Echan, 2026-07-02 - shown as a caption above each
# image in the PDF. Dict preserves the same fixed display order as before
# (Python dicts keep insertion order), so PRIMARY_IMAGE_FIELDS below is
# just this dict's keys - no separate list to keep in sync anymore.
PRIMARY_IMAGE_LABELS = {
    "gcash_image": "GCash Account",
    "sss_image": "SSS",
    "drug_test_image": "Drug Test",
    "valid_id_image": "Valid ID FRONT",
    "valid_id_image_rear": "Valid ID BACK",
    "heath_card_image": "Health Card",
    "hcb_image": "Health Card Benefits",
    "pag_image": "Pag-IBIG",
    "ph_image": "PhilHealth",
    "nbi_image": "NBI Clearance",
    "ub_image": "Union Bank Account",
}
PRIMARY_IMAGE_FIELDS = list(PRIMARY_IMAGE_LABELS.keys())


def _first_by_relation(parents: list, relation_keyword: str):
    """Return the first ParentRecord whose fam_rela contains relation_keyword
    (case-insensitive), or None if no match."""
    for p in parents:
        if p.fam_rela and relation_keyword in p.fam_rela.upper():
            return p
    return None

def _collect_page2_images(data) -> list[tuple[str, str]]:
    """Ordered list of (url, label) pairs for page 2: all minor_image(s)
    first (a minor SectionResult can contain more than one record, each
    labeled with its own minor_reqs value - e.g. "Certificate, Birth" -
    since minor documents aren't a fixed single type), then the primary
    record's 11 document images labeled per PRIMARY_IMAGE_LABELS. Missing
    images (None, already normalized upstream by the Pydantic validators)
    are simply not appended - this is what makes the later images flow up
    and fill the gap in the layout, rather than leaving a reserved blank
    slot."""
    images = []

    for minor in data.minors.data:
        if minor.minor_image:
            label = minor.minor_reqs or "Document"
            images.append((minor.minor_image, label))

    primary = data.primary
    for field_name in PRIMARY_IMAGE_FIELDS:
        url = getattr(primary, field_name)
        if url:
            images.append((url, PRIMARY_IMAGE_LABELS[field_name]))

    return images

def _group_education_by_level(education: list) -> list[tuple[str, list]]:
    """Group EducationRecord entries by their level label, preserving the
    reference form's row order. Levels with zero matching records are
    skipped entirely (filtered here, not in the template)."""
    grouped = []
    for label, prefix in EDUCATION_LEVELS:
        matches = [e for e in education if e.edu_type and e.edu_type.strip().upper().startswith(prefix)]
        if matches:
            grouped.append((label, matches))
    return grouped


def build_template_context(data: Employee201Data) -> dict:
    parents = data.parents.data

    return {
        "primary": data.primary,
        "parents": parents,
        "father": _first_by_relation(parents, "FATHER"),
        "mother": _first_by_relation(parents, "MOTHER"),
        "spouse": _first_by_relation(parents, "SPOUSE"),
        "education_grouped": _group_education_by_level(data.education.data),
        "training": data.training.data,
        "employment": data.employment.data,
        "minors": data.minors.data,
        "page2_images": _collect_page2_images(data),
    }