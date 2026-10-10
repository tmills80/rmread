"""Parents, spouses and children for a Person.

In RootsMagic, links between People live in two places:

- ``FamilyTable`` — one row per family. ``FatherID`` / ``MotherID`` are
  the parents; ``ChildID`` is a denormalised first-child pointer that we
  ignore (the authoritative child→family link is ``ChildTable``).
- ``ChildTable`` — one row per (child, family) tuple with ``ChildOrder``
  for sibling position.

This module exposes three read-only loaders and the dataclasses they
return.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ParentRef:
    """A single parent reference — comes from FamilyTable.FatherID / MotherID."""

    family_id: int
    parent_id: int
    parent_name: str                  # computed via display_name_at_row
    role: str                         # "father" or "mother"


@dataclass(frozen=True)
class SpouseLink:
    """A marriage / partnership — comes from FamilyTable rows where this
    Person appears as Father or Mother."""

    family_id: int
    spouse_id: int
    spouse_name: str
    role: str                         # "spouse_of_father" / "spouse_of_mother"


@dataclass(frozen=True)
class ChildRef:
    """A child in the family — comes from ChildTable ORDER BY ChildOrder."""

    child_id: int
    child_name: str
    rel_father: int                   # 1 = biological, 0 = not, etc. (RM-specific)
    rel_mother: int
    child_order: int


# --- internal helper --------------------------------------------------

def _display_name(con: sqlite3.Connection, person_id: int) -> str:
    """Concatenate NameTable primary-row pieces into a one-line display.

    Equivalent to ``Person.display_name`` but constructed inline so family
    lookup doesn't have to round-trip through the Person dataclass.
    """
    row = con.execute(
        """
        SELECT Given, Surname, Prefix, Suffix, Sentence
        FROM NameTable
        WHERE OwnerID = ? AND NameType = 0
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        return f"@pid{person_id}"
    sentence = row["Sentence"] or ""
    if sentence:
        return sentence
    parts = [row["Prefix"], row["Given"], row["Surname"], row["Suffix"]]
    return " ".join(p for p in parts if p) or f"@pid{person_id}"


# --- loaders ----------------------------------------------------------

def load_parents(con: sqlite3.Connection, person_id: int) -> list[ParentRef]:
    """Return the biological/legal parents of ``person_id``, if recorded.

    Walks ``ChildTable`` → ``FamilyTable`` to find families where
    ``person_id`` is a child, then returns the FatherID and/or MotherID
    of those families. Returns 0–2 records (rarely both missing for
    fully-tracked ancestors).

    Note: a single Person can have multiple parent families (adoption,
    multiple marriages), and our walk can therefore return more than
    two ParentRefs. We expose them all — downstream code can disambiguate
    using Person.event data.
    """
    rows = con.execute(
        """
        SELECT f.FamilyID, f.FatherID, f.MotherID
        FROM FamilyTable f
        JOIN ChildTable c ON c.FamilyID = f.FamilyID
        WHERE c.ChildID = ?
        ORDER BY f.FamilyID
        """,
        (person_id,),
    ).fetchall()
    out: list[ParentRef] = []
    for r in rows:
        if r["FatherID"]:
            out.append(ParentRef(
                family_id=r["FamilyID"],
                parent_id=r["FatherID"],
                parent_name=_display_name(con, r["FatherID"]),
                role="father",
            ))
        if r["MotherID"]:
            out.append(ParentRef(
                family_id=r["FamilyID"],
                parent_id=r["MotherID"],
                parent_name=_display_name(con, r["MotherID"]),
                role="mother",
            ))
    return out


def load_spouses(con: sqlite3.Connection, person_id: int) -> list[SpouseLink]:
    """Return every spouse linked to ``person_id`` via FamilyTable."""
    rows = con.execute(
        """
        SELECT FamilyID, FatherID, MotherID
        FROM FamilyTable
        WHERE FatherID = ? OR MotherID = ?
        """,
        (person_id, person_id),
    ).fetchall()
    out: list[SpouseLink] = []
    for r in rows:
        if r["FatherID"] == person_id and r["MotherID"]:
            out.append(SpouseLink(
                family_id=r["FamilyID"],
                spouse_id=r["MotherID"],
                spouse_name=_display_name(con, r["MotherID"]),
                role="spouse_of_father",
            ))
        elif r["MotherID"] == person_id and r["FatherID"]:
            out.append(SpouseLink(
                family_id=r["FamilyID"],
                spouse_id=r["FatherID"],
                spouse_name=_display_name(con, r["FatherID"]),
                role="spouse_of_mother",
            ))
        # single-parent rows produce no spouse link
    return out


def load_children(con: sqlite3.Connection, person_id: int) -> list[ChildRef]:
    """Return every child whose FamilyTable father or mother is ``person_id``.

    Sorted by ``ChildOrder`` within each family — sibling position rather
    than birth order, which is what RM uses. Birth-order sorting requires
    post-processing by event dates (see :mod:`rmread.event`).
    """
    rows = con.execute(
        """
        SELECT c.ChildID, c.FamilyID, c.RelFather, c.RelMother, c.ChildOrder,
               n.Given, n.Surname, n.Prefix, n.Suffix, n.Sentence
        FROM ChildTable c
        JOIN FamilyTable f ON f.FamilyID = c.FamilyID
        LEFT JOIN NameTable n
               ON n.OwnerID = c.ChildID AND n.NameType = 0
        WHERE f.FatherID = ? OR f.MotherID = ?
        ORDER BY c.FamilyID, c.ChildOrder
        """,
        (person_id, person_id),
    ).fetchall()
    out: list[ChildRef] = []
    for r in rows:
        sentence = r["Sentence"] or ""
        if not sentence:
            parts = [r["Prefix"], r["Given"], r["Surname"], r["Suffix"]]
            sentence = " ".join(p for p in parts if p)
        if not sentence:
            sentence = f"@pid{r['ChildID']}"
        out.append(ChildRef(
            child_id=r["ChildID"],
            child_name=sentence,
            rel_father=r["RelFather"] or 0,
            rel_mother=r["RelMother"] or 0,
            child_order=r["ChildOrder"] or 0,
        ))
    return out
