"""Output renderers for rmread query results.

Two JSON shapes leave rmread, and they are *different shapes*, so they
carry *different* schema versions:

* ``rm-find --format json`` — ``{"envelope": ..., "results": [...]}``,
  rendered by :func:`to_json`.
* ``rm-dump --format json`` — ``{"envelope": ..., "result": {...}}``,
  rendered by :func:`dump_payload`.

The envelope's ``schema_version`` says which shape the payload under it
has. A consumer that does not recognise the version must refuse the
payload rather than guess at it: a note that silently drops half a
payload is worse than no note.

``rmcite`` consumes the ``rm-dump`` shape and pins
``DUMP_SCHEMA_VERSION``; see the rmcite package's ``contract.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .person import Person, PersonDump

#: Schema version of the ``rm-find --format json`` payload shape.
FIND_SCHEMA_VERSION = 1

#: Schema version of the ``rm-dump --format json`` payload shape.
DUMP_SCHEMA_VERSION = 1


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
    output file is self-describing. ``schema_version`` says which shape
    the payload under the envelope has.
    """
    results = list(persons)
    return json.dumps(
        {
            "envelope": {
                "tool": "rmread",
                "schema_version": FIND_SCHEMA_VERSION,
                "source_database": source_path,
                "db_version": db_version,
                "count": len(results),
            },
            "results": [_person_to_dict(p) for p in results],
        },
        indent=indent,
        ensure_ascii=False,
    )


def dump_payload(
    dump: PersonDump,
    *,
    source_path: str,
    db_version: int,
    person_id: int,
) -> dict:
    """Render a PersonDump as the ``rm-dump --format json`` payload.

    Returns the payload as a dict (not a JSON string) so that a consumer
    can compare its shape against the fixture it was written for without
    parsing it first.
    """
    p = dump.person
    return {
        "envelope": {
            "tool": "rmread",
            "schema_version": DUMP_SCHEMA_VERSION,
            "source_database": source_path,
            "db_version": db_version,
            "person_id": person_id,
        },
        "result": {
            "person": {
                "person_id": p.person_id,
                "unique_id": p.unique_id,
                "sex": p.sex,
                "living": p.living,
                "is_private": p.is_private,
                "display_name": p.display_name,
                "primary_name": {
                    "surname": p.primary_name.surname,
                    "given": p.primary_name.given,
                    "prefix": p.primary_name.prefix,
                    "suffix": p.primary_name.suffix,
                    "nickname": p.primary_name.nickname,
                    "birth_year": p.primary_name.birth_year,
                    "death_year": p.primary_name.death_year,
                    "sentence": p.primary_name.sentence,
                },
            },
            "events": [
                {
                    "event_id": ev.event_id,
                    "event_type": ev.event_type,
                    "event_type_name": ev.event_type_name,
                    "date": ev.date,
                    "sort_date": ev.sort_date,
                    "place": ev.place,
                    "is_primary": ev.is_primary,
                    "sentence": ev.sentence,
                    "details": ev.details,
                    "note": ev.note,
                }
                for ev in dump.events
            ],
            "parents": [
                {
                    "family_id": par.family_id,
                    "parent_id": par.parent_id,
                    "parent_name": par.parent_name,
                    "role": par.role,
                }
                for par in dump.parents
            ],
            "spouses": [
                {
                    "family_id": sp.family_id,
                    "spouse_id": sp.spouse_id,
                    "spouse_name": sp.spouse_name,
                    "role": sp.role,
                }
                for sp in dump.spouses
            ],
            "children": [
                {
                    "child_id": ch.child_id,
                    "child_name": ch.child_name,
                    "rel_father": ch.rel_father,
                    "rel_mother": ch.rel_mother,
                    "child_order": ch.child_order,
                }
                for ch in dump.children
            ],
        },
    }


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
            s = s[: w - 1] + "\u2026"
        return s.ljust(w)

    sex_letter = {0: "?", 1: "M", 2: "F"}
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths))]
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
