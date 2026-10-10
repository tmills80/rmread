"""Output renderers for rmread query results."""

from __future__ import annotations

import json
from collections.abc import Iterable

from .person import Person


def _person_to_dict(p: Person) -> dict:
    """Plain-dict projection of a Person for JSON output."""
    return {
        "person_id": p.person_id,
        "unique_id": p.unique_id,
        "sex": p.sex,
        "living": p.living,
        "is_private": p.is_private,
        "primary_name": {
            "surname": p.primary_name.surname,
            "given": p.primary_name.given,
            "prefix": p.primary_name.prefix,
            "suffix": p.primary_name.suffix,
            "nickname": p.primary_name.nickname,
            "name_type": p.primary_name.name_type,
            "is_primary": p.primary_name.is_primary,
            "birth_year": p.primary_name.birth_year,
            "death_year": p.primary_name.death_year,
            "sentence": p.primary_name.sentence,
        },
    }


def to_json(
    persons: Iterable[Person],
    *,
    source_path: str,
    db_version: int,
    indent: int | None = 2,
) -> str:
    """Render a list of Person results as JSON.

    ``source_path`` and ``db_version`` are stamped into the envelope so an
    output file is self-describing.
    """
    if isinstance(persons, list):
        results = persons
        count = len(persons)
    else:
        results = list(persons)
        count = len(results)
    return json.dumps(
        {
            "envelope": {
                "tool": "rmread",
                "source_database": source_path,
                "db_version": db_version,
                "count": count,
            },
            "results": [_person_to_dict(p) for p in results],
        },
        indent=indent,
        ensure_ascii=False,
    )


def to_text(persons: Iterable[Person]) -> str:
    """Render a Person list as a fixed-column text table."""
    rows = list(persons)
    if not rows:
        return "(no matches)"

    headers = ("ID", "Surname", "Given", "Sex", "B.Year", "D.Year", "Private")
    widths = (8, 18, 28, 5, 7, 7, 5)

    def cell(v, w):
        s = "" if v is None else str(v)
        if len(s) > w:
            s = s[: w - 1] + "…"
        return s.ljust(w)

    sex_letter = {0: "?", 1: "M", 2: "F"}
    lines = ["  ".join(cell(h, w) for h, w in zip(headers, widths))]
    lines.append("  ".join("-" * w for w in widths))
    for p in rows:
        lines.append("  ".join([
            cell(p.person_id, widths[0]),
            cell(p.primary_name.surname, widths[1]),
            cell(p.primary_name.given, widths[2]),
            cell(sex_letter.get(p.sex, "?"), widths[3]),
            cell(p.primary_name.birth_year, widths[4]),
            cell(p.primary_name.death_year, widths[5]),
            cell("yes" if p.is_private else "", widths[6]),
        ]))
    return "\n".join(lines)
