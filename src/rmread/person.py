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
WHERE primaryName.Surname LIKE ? COLLATE NOCASE
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
    """Return all Person records whose primary surname matches ``surname``.

    Matching is case-insensitive (``COLLATE NOCASE``) and substring by
    default — pass an exact surname or anchor with ``%`` if you need
    something tighter.

    Parameters
    ----------
    con
        Open sqlite3 connection (e.g. the one owned by an
        :class:`rmread.RMDatabase`).
    surname
        Pattern matched against ``NameTable.Surname`` for the primary
        (``NameType=0``) name row. Required.
    given
        Optional case-insensitive substring filter on ``Given``.
    limit
        Cap on returned rows. Useful for common surnames (``PlaceholderSurnameTwo``).
    """
    if not surname or not surname.strip():
        raise ValueError("surname must be a non-empty string")

    like = surname.strip()
    if "%" not in like and "_" not in like:
        like = f"%{like}%"

    sql = _SURNAME_SEARCH_SQL
    params: tuple = (like,)
    if given is not None:
        given = given.strip()
        if given:
            sql = sql.replace(
                "WHERE primaryName.Surname LIKE ? COLLATE NOCASE",
                "WHERE primaryName.Surname LIKE ? COLLATE NOCASE "
                "AND primaryName.Given LIKE ? COLLATE NOCASE",
            )
            params = params + (f"%{given}%",)
    if limit is not None:
        sql += "\nLIMIT ?"
        params = params + (int(limit),)

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
