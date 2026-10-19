"""Person and Name dataclasses + surname search.

In RootsMagic, a Person can have many ``NameTable`` rows (birth, married,
alias, immigration, etc.). ``NameType=0`` is the birth / primary name and
is what most queries want.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Name:
    """A single name record attached to a Person."""

    name_id: int
    surname: str
    given: str
    prefix: str
    suffix: str
    nickname: str
    name_type: int          # 0 = birth/primary, 1 = married, etc.
    is_primary: bool
    birth_year: int | None
    death_year: int | None
    sentence: str           # pre-formatted full name as RM stores it


@dataclass(frozen=True)
class Person:
    """A PersonTable row joined with their primary NameTable row."""

    person_id: int
    unique_id: str
    sex: int                # 0 = unknown, 1 = male, 2 = female (RM convention)
    living: bool
    is_private: bool
    primary_name: Name
    alt_names: tuple[Name, ...] = field(default_factory=tuple)

    @property
    def display_name(self) -> str:
        if self.primary_name.sentence:
            return self.primary_name.sentence
        parts = [self.primary_name.prefix, self.primary_name.given,
                 self.primary_name.surname, self.primary_name.suffix]
        return " ".join(p for p in parts if p)


SEX_UNKNOWN = 0
SEX_MALE = 1
SEX_FEMALE = 2


_SURNAME_SEARCH_SQL = """
SELECT
    pt.PersonID,
    pt.UniqueID,
    pt.Sex,
    pt.Living,
    pt.IsPrivate,
    primaryName.NameID,
    primaryName.Surname,
    primaryName.Given,
    primaryName.Prefix,
    primaryName.Suffix,
    primaryName.Nickname,
    primaryName.NameType,
    primaryName.IsPrimary,
    primaryName.BirthYear,
    primaryName.DeathYear,
    primaryName.Sentence
FROM PersonTable pt
JOIN NameTable primaryName
    ON primaryName.OwnerID = pt.PersonID
   AND primaryName.NameType = 0
WHERE {where}
ORDER BY primaryName.Surname COLLATE NOCASE,
         primaryName.Given COLLATE NOCASE,
         pt.PersonID
"""


def find_by_surname(
    con: sqlite3.Connection,
    surname: str,
    *,
    given: str | None = None,
    limit: int | None = None,
) -> list[Person]:
    """Search the primary surname. **No substring wrapping.**

    ``surname`` (and ``given``) are SQL LIKE patterns passed through
    verbatim, exactly as in :func:`find_person`: ``"AAAAAA"`` matches
    only the literal surname, ``"AAAA%"`` matches prefixes,
    ``"%AAAA%"`` matches anywhere. A bare word is *not* auto-wrapped —
    use the wildcards explicitly.

    This is a positional-argument wrapper kept for callers written
    against the earlier API. ``find_by_surname(con, "Smith")`` and
    ``find_person(con, surname="Smith")`` are equivalent.

    Note: the =rm-find= CLI *does* wrap a bare word as ``%value%``
    before calling in (see ``rmread.cli.find._to_pattern``), so the
    CLI's default substring behaviour is not inherited from here.
    """
    if not surname or not surname.strip():
        raise ValueError("surname must be a non-empty string")
    return find_person(
        con, surname=surname, given=given, limit=limit,
    )


def find_person(
    con: sqlite3.Connection,
    *,
    surname: str,
    given: str | None = None,
    limit: int | None = None,
) -> list[Person]:
    """Person search with **explicit** LIKE patterns on surname and given.

    Both ``surname`` and ``given`` are passed verbatim as SQL LIKE
    patterns. That means:

    - ``find_person(con, surname="PlaceholderSurname")`` matches only the literal
      string ``PlaceholderSurname`` (case-insensitively).
    - ``find_person(con, surname="%PlaceholderSurname%")`` matches anything containing
      ``PlaceholderSurname``.
    - ``find_person(con, surname="PlaceholderSurname%")`` matches names *starting*
      with ``PlaceholderSurname``.
    - ``find_person(con, surname="M_lls")`` matches ``PlaceholderSurname``, ``Mulls``,
      ``M@lls``, etc. (single-char wildcard).
    - ``find_person(con, surname="PlaceholderSurname", given="Ann_")`` matches
      ``PlaceholderSurname`` + ``Anna`` / ``Anne`` / ``Anny`` etc.

    For the legacy substring behaviour (auto-wrap with ``%…%``) see
    :func:`find_by_surname`.

    Parameters
    ----------
    con
        Open sqlite3 connection.
    surname
        Required SQL LIKE pattern matched against the primary
        (``NameType=0``) ``NameTable.Surname`` field.
    given
        Optional SQL LIKE pattern matched against the primary
        ``Given`` field. ``None`` or empty string disables the filter.
    limit
        Cap on returned rows.
    """
    if surname is None:
        raise ValueError("surname must be a non-empty string")
    surname_pat = str(surname).strip()
    if not surname_pat:
        raise ValueError("surname must be a non-empty string")

    clauses = ["primaryName.Surname LIKE ? COLLATE NOCASE"]
    params: list = [surname_pat]
    if given is not None:
        given_pat = str(given).strip()
        if given_pat:
            clauses.append("primaryName.Given LIKE ? COLLATE NOCASE")
            params.append(given_pat)

    sql = _SURNAME_SEARCH_SQL.format(where=" AND ".join(clauses))
    if limit is not None:
        sql += "\nLIMIT ?"
        params.append(int(limit))

    rows = con.execute(sql, params).fetchall()

    out: list[Person] = []
    for r in rows:
        primary = Name(
            name_id=r["NameID"],
            surname=r["Surname"] or "",
            given=r["Given"] or "",
            prefix=r["Prefix"] or "",
            suffix=r["Suffix"] or "",
            nickname=r["Nickname"] or "",
            name_type=r["NameType"],
            is_primary=bool(r["IsPrimary"]),
            birth_year=r["BirthYear"] if r["BirthYear"] else None,
            death_year=r["DeathYear"] if r["DeathYear"] else None,
            sentence=r["Sentence"] or "",
        )
        out.append(Person(
            person_id=r["PersonID"],
            unique_id=r["UniqueID"] or "",
            sex=r["Sex"],
            living=bool(r["Living"]),
            is_private=bool(r["IsPrivate"]),
            primary_name=primary,
        ))
    return out


def load_alt_names(
    con: sqlite3.Connection, person_id: int
) -> tuple[Name, ...]:
    """Load non-primary name rows for a Person (married, alias, etc.)."""
    rows = con.execute(
        """
        SELECT NameID, Surname, Given, Prefix, Suffix, Nickname,
               NameType, IsPrimary, BirthYear, DeathYear, Sentence
        FROM NameTable
        WHERE OwnerID = ?
          AND NameType <> 0
        ORDER BY NameType, SortDate
        """,
        (person_id,),
    ).fetchall()
    return tuple(
        Name(
            name_id=r["NameID"],
            surname=r["Surname"] or "",
            given=r["Given"] or "",
            prefix=r["Prefix"] or "",
            suffix=r["Suffix"] or "",
            nickname=r["Nickname"] or "",
            name_type=r["NameType"],
            is_primary=bool(r["IsPrimary"]),
            birth_year=r["BirthYear"] if r["BirthYear"] else None,
            death_year=r["DeathYear"] if r["DeathYear"] else None,
            sentence=r["Sentence"] or "",
        )
        for r in rows
    )


# --- person dump ------------------------------------------------------

@dataclass(frozen=True)
class PersonDump:
    """Everything we know about a Person: identity + events + family links."""

    person: Person
    events: tuple["Event", ...] = field(default_factory=tuple)
    parents: tuple["ParentRef", ...] = field(default_factory=tuple)
    spouses: tuple["SpouseLink", ...] = field(default_factory=tuple)
    children: tuple["ChildRef", ...] = field(default_factory=tuple)


def get_person(
    con: sqlite3.Connection, person_id: int
) -> Person | None:
    """Load a single Person by PersonID. Returns None if not found."""
    row = con.execute(
        """
        SELECT PersonID, UniqueID, Sex, Living, IsPrivate
        FROM PersonTable
        WHERE PersonID = ?
        """,
        (person_id,),
    ).fetchone()
    if row is None:
        return None
    name_row = con.execute(
        """
        SELECT NameID, Surname, Given, Prefix, Suffix, Nickname,
               NameType, IsPrimary, BirthYear, DeathYear, Sentence
        FROM NameTable
        WHERE OwnerID = ? AND NameType = 0
        """,
        (person_id,),
    ).fetchone()
    if name_row is None:
        # Person exists but no primary name — return a stub with empty Name.
        # This is rare but RM allows it (e.g. imported records that haven't
        # been reconciled yet).
        primary = Name(
            name_id=0, surname="", given="", prefix="", suffix="",
            nickname="", name_type=0, is_primary=True,
            birth_year=None, death_year=None, sentence="",
        )
    else:
        primary = Name(
            name_id=name_row["NameID"],
            surname=name_row["Surname"] or "",
            given=name_row["Given"] or "",
            prefix=name_row["Prefix"] or "",
            suffix=name_row["Suffix"] or "",
            nickname=name_row["Nickname"] or "",
            name_type=name_row["NameType"],
            is_primary=bool(name_row["IsPrimary"]),
            birth_year=name_row["BirthYear"] if name_row["BirthYear"] else None,
            death_year=name_row["DeathYear"] if name_row["DeathYear"] else None,
            sentence=name_row["Sentence"] or "",
        )
    return Person(
        person_id=row["PersonID"],
        unique_id=row["UniqueID"] or "",
        sex=row["Sex"],
        living=bool(row["Living"]),
        is_private=bool(row["IsPrivate"]),
        primary_name=primary,
    )


def dump_person(
    con: sqlite3.Connection,
    person_id: int,
    *,
    include_events: bool = True,
    include_family: bool = True,
) -> PersonDump | None:
    """Compose a full PersonDump for ``person_id`` — identity, events, family.

    Returns None if no such PersonID exists. Either family or events can be
    suppressed via the corresponding flag — useful for narrow lookups.
    """
    # Lazy imports to avoid an import cycle (event.py / family.py don't
    # import person.py, but module-load order in editable installs can be
    # subtle).
    from .event import load_events
    from .family import load_children, load_parents, load_spouses

    person = get_person(con, person_id)
    if person is None:
        return None
    events = tuple(load_events(con, person_id)) if include_events else ()
    parents: tuple = ()
    spouses: tuple = ()
    children: tuple = ()
    if include_family:
        parents = tuple(load_parents(con, person_id))
        spouses = tuple(load_spouses(con, person_id))
        children = tuple(load_children(con, person_id))
    return PersonDump(
        person=person,
        events=events,
        parents=parents,
        spouses=spouses,
        children=children,
    )

