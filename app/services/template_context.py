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


def _first_by_relation(parents: list, relation_keyword: str):
    """Return the first ParentRecord whose fam_rela contains relation_keyword
    (case-insensitive), or None if no match."""
    for p in parents:
        if p.fam_rela and relation_keyword in p.fam_rela.upper():
            return p
    return None


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
    }