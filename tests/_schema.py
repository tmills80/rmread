"""Shared synthetic-RM schema builder used by the person-dump tests.

Builds a fully-populated in-memory SQLite database that satisfies every
read the person-dump code paths perform, then writes it to a temp file
and opens it via :func:`rmread.open_database` so the suite exercises
the real read-only connection path (mode=ro + PRAGMA query_only).

Person tree in the default fixture::

        pid 1 (M) ----- pid 2 (F)            single-parent family with pid 3
             |
             +--- pid 4 (F) [spouse of pid 1]
                       |
                       +--- pid 5 (F)
                       +--- pid 6 (M)

Plus one lone PersonID that exists but has no NameTable row (orphan).

No real .rmtree is opened.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterator

import pytest


# Fact names corresponding to the synthetic EventType ints below.
_FACT_NAMES = {
    1: "Birth",
    2: "Death",
    17: "Occupation",
    33: "Residence",
}


def _create_schema(cur: sqlite3.Cursor) -> None:
    cur.executescript("""
        CREATE TABLE ConfigTable (
            RecID INTEGER, RecType INTEGER, Title TEXT,
            DataRec BLOB, UTCModDate FLOAT
        );
        CREATE TABLE PersonTable (
            PersonID INTEGER PRIMARY KEY,
            UniqueID TEXT, Sex INTEGER, ParentID INTEGER, SpouseID INTEGER,
            Color INTEGER, Color1 INTEGER, Color2 INTEGER, Color3 INTEGER,
            Color4 INTEGER, Color5 INTEGER, Color6 INTEGER, Color7 INTEGER,
            Color8 INTEGER, Color9 INTEGER, Relate1 INTEGER, Relate2 INTEGER,
            Flags INTEGER, Living INTEGER, IsPrivate INTEGER, Proof INTEGER,
            Bookmark INTEGER, Note TEXT, UTCModDate FLOAT
        );
        CREATE TABLE NameTable (
            NameID INTEGER PRIMARY KEY,
            OwnerID INTEGER, Surname TEXT, Given TEXT, Prefix TEXT, Suffix TEXT,
            Nickname TEXT, NameType INTEGER, Date TEXT, SortDate BIGINT,
            IsPrimary INTEGER, IsPrivate INTEGER, Proof INTEGER, Sentence TEXT,
            Note TEXT, BirthYear INTEGER, DeathYear INTEGER, Display INTEGER,
            Language TEXT, UTCModDate FLOAT,
            SurnameMP TEXT, GivenMP TEXT, NicknameMP TEXT
        );
        CREATE TABLE FamilyTable (
            FamilyID INTEGER PRIMARY KEY,
            FatherID INTEGER, MotherID INTEGER, ChildID INTEGER,
            HusbOrder INTEGER, WifeOrder INTEGER, IsPrivate INTEGER, Proof INTEGER,
            SpouseLabel INTEGER, FatherLabel INTEGER, MotherLabel INTEGER,
            SpouseLabelStr TEXT, FatherLabelStr TEXT, MotherLabelStr TEXT,
            Note TEXT, UTCModDate FLOAT
        );
        CREATE TABLE ChildTable (
            RecID INTEGER PRIMARY KEY,
            ChildID INTEGER, FamilyID INTEGER,
            RelFather INTEGER, RelMother INTEGER, ChildOrder INTEGER,
            IsPrivate INTEGER, ProofFather INTEGER, ProofMother INTEGER,
            Note TEXT, UTCModDate FLOAT
        );
        CREATE TABLE EventTable (
            EventID INTEGER PRIMARY KEY,
            EventType INTEGER, OwnerType INTEGER, OwnerID INTEGER,
            FamilyID INTEGER, PlaceID INTEGER, SiteID INTEGER,
            Date TEXT, SortDate BIGINT, IsPrimary INTEGER, IsPrivate INTEGER,
            Proof INTEGER, Status INTEGER, Sentence TEXT, Details TEXT, Note TEXT,
            UTCModDate FLOAT
        );
        CREATE TABLE PlaceTable (
            PlaceID INTEGER PRIMARY KEY, Name TEXT
        );
        CREATE TABLE FactTypeTable (
            FactTypeID INTEGER PRIMARY KEY, Name TEXT
        );
    """)
    cur.execute(
        "INSERT INTO ConfigTable (RecID, RecType, Title, DataRec) "
        "VALUES (1, 1, '', ?)",
        (b'<Root><Version>11000</Version><STVersion>700</STVersion>'
         b'<UniqueID>FAKE-UUID</UniqueID><RootPerson>1</RootPerson></Root>',),
    )
    for ft_id, ft_name in _FACT_NAMES.items():
        cur.execute(
            "INSERT INTO FactTypeTable (FactTypeID, Name) VALUES (?, ?)",
            (ft_id, ft_name),
        )


def _seed_person(cur, *, pid, uid, sex, living, surname, given, nick=""):
    cur.execute(
        "INSERT INTO PersonTable "
        "(PersonID, UniqueID, Sex, Living, IsPrivate) VALUES (?, ?, ?, ?, 0)",
        (pid, uid, sex, int(living)),
    )
    if surname or given:
        sentence = f"{given} {surname}".strip()
        cur.execute(
            "INSERT INTO NameTable "
            "(NameID, OwnerID, Surname, Given, Nickname, NameType, IsPrimary, "
            " Sentence, BirthYear, DeathYear) "
            "VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?)",
            (pid * 10, pid, surname, given, nick, sentence,
             1900 + pid, 1980 if pid % 2 == 0 else None),
        )


def _seed_event(cur, *, eid, event_type, owner_id, date, sort_date,
                place_text=None, primary=1, sentence="", details=""):
    place_id = None
    if place_text is not None:
        cur.execute("INSERT INTO PlaceTable (Name) VALUES (?)", (place_text,))
        place_id = cur.lastrowid
    cur.execute(
        "INSERT INTO EventTable "
        "(EventID, EventType, OwnerType, OwnerID, PlaceID, Date, SortDate, "
        " IsPrimary, Sentence, Details) "
        "VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?)",
        (eid, event_type, owner_id, place_id, date, sort_date,
         primary, sentence, details),
    )


def _seed_family(cur, *, fid, father_id=0, mother_id=0):
    cur.execute(
        "INSERT INTO FamilyTable "
        "(FamilyID, FatherID, MotherID, ChildID) VALUES (?, ?, ?, 0)",
        (fid, father_id, mother_id),
    )


def _seed_child(cur, *, rid, family_id, child_id, order, rel_father=0, rel_mother=0):
    cur.execute(
        "INSERT INTO ChildTable "
        "(RecID, ChildID, FamilyID, RelFather, RelMother, ChildOrder) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (rid, child_id, family_id, rel_father, rel_mother, order),
    )


def _populate_default(cur) -> None:
    """Six-person synthetic tree described in module docstring."""
    _seed_person(cur, pid=1, uid="fp-1", sex=1, living=False,
                 surname="AAAAAA", given="Zed",   nick="Z")
    _seed_person(cur, pid=2, uid="fp-2", sex=2, living=False,
                 surname="AAAAAA", given="Yara")
    _seed_person(cur, pid=3, uid="fp-3", sex=2, living=True,
                 surname="UNKNOWN-MOM",  given="Uma")
    _seed_person(cur, pid=4, uid="fp-4", sex=2, living=True,
                 surname="BBBBB", given="Wren")
    _seed_person(cur, pid=5, uid="fp-5", sex=2, living=True,
                 surname="BBBBB", given="Vivi")
    _seed_person(cur, pid=6, uid="fp-6", sex=1, living=True,
                 surname="BBBBB", given="Umar")
    # PersonID 7: orphan (exists in PersonTable but no NameTable row).
    cur.execute(
        "INSERT INTO PersonTable "
        "(PersonID, UniqueID, Sex, Living, IsPrivate) "
        "VALUES (7, 'fp-7', 0, 1, 0)",
    )

    # Family 1: pid 1 + pid 2 → no children (set up first so pid 1 is a parent)
    _seed_family(cur, fid=1, father_id=1, mother_id=2)
    # pid 1 is also linked (as father) to a one-parent family with pid 3:
    _seed_family(cur, fid=2, father_id=1, mother_id=3)

    # Family 3: pid 1 + pid 4 → children 5, 6
    _seed_family(cur, fid=3, father_id=1, mother_id=4)
    _seed_child(cur, rid=1, family_id=3, child_id=5, order=1, rel_father=1, rel_mother=1)
    _seed_child(cur, rid=2, family_id=3, child_id=6, order=2, rel_father=1, rel_mother=1)

    # Events: pid 1 — birth, death, occupation.
    _seed_event(cur, eid=1, event_type=1, owner_id=1,
                date="1 JAN 1901", sort_date=1, primary=1,
                sentence="BIRTH 1 JAN 1901",
                place_text="FFakePlace-1")
    _seed_event(cur, eid=2, event_type=17, owner_id=1,
                date="BET 1925 AND 1930", sort_date=2,
                sentence="OCCUPATION 1925-1930",
                details="ZZ-fake-detail")
    # No-death event sort_date=0 (unparsed) to exercise the unparsed branch.
    _seed_event(cur, eid=3, event_type=2, owner_id=1,
                date="AFTER 1980", sort_date=0,
                sentence="DEATH AFTER 1980")

    # A custom event type (999) for pid 1 that isn't in FactTypeTable —
    # exercises the "Unknown(<int>)" fallback path.
    _seed_event(cur, eid=4, event_type=999, owner_id=1,
                date="1 FEB 1950", sort_date=3,
                sentence="custom fact")


@pytest.fixture
def full_db() -> Iterator:
    """Synthetic read-only RMDatabase with full person-dump fixtures."""
    tmp = tempfile.NamedTemporaryFile(suffix=".rmtree", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        build = sqlite3.connect(db_path)
        _create_schema(build.cursor())
        _populate_default(build.cursor())
        build.commit()
        build.close()
        for sidecar in (db_path + "-wal", db_path + "-shm"):
            if os.path.exists(sidecar):
                os.unlink(sidecar)

        from rmread import open_database
        db = open_database(db_path)
        yield db
        db.close()
    finally:
        for ext in ("", "-wal", "-shm", "-journal"):
            p = db_path + ext
            if os.path.exists(p):
                os.unlink(p)
