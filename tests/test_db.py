"""Tests for rmread.db and rmread.person.

All data is **synthetic** — fake names invented for tests ("AAAAAA",
"BBBBBB", "O'CCCC", "Zoe", "Yara", etc.), not real people. No real
.rmtree is opened.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from rmread import RMDatabase, SchemaError, open_database
from rmread.person import SEX_FEMALE, SEX_MALE


# --- synthetic RM schema scaffolding ----------------------------------

# A dummy ConfigTable blob shaped like a real one. Version 11000 = RM 11.
_RM_BLOB_VERSION_11 = (
    b'<Root><Version>11000</Version><STVersion>700</STVersion>'
    b'<UniqueID>FAKE-UUID-DEADBEEF</UniqueID>'
    b'<RootPerson>1</RootPerson>'
    b'</Root>'
)


def _bootstrap_schema(cur: sqlite3.Cursor) -> None:
    """Create the minimum RootsMagic schema we read from.

    Column names mirror real RM (``RecID``, ``RecType``, ``Title``,
    ``DataRec``), not the generic identifiers you'd expect.
    """
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
    """)
    cur.execute(
        "INSERT INTO ConfigTable (RecID, RecType, Title, DataRec) VALUES (1, 1, '', ?)",
        (_RM_BLOB_VERSION_11,),
    )


# Five synthetic persons across three fake surnames, including a tricky
# apostrophe-bearing name.
_FAKE_PEOPLE = [
    # (pid, uid, sex, living, private, surname, given, nickname)
    (1, "fp-1", 1, True,  False, "AAAAAA", "Zoe",     ""),
    (2, "fp-2", 1, False, False, "AAAAAA", "Yara",    ""),
    (3, "fp-3", 2, True,  False, "BBBBBB", "Xerxes",  ""),
    (4, "fp-4", 0, True,  False, "O'CCCC", "Wren",    ""),
    (5, "fp-5", 1, True,  False, "AAAAAA", "Victor",  "Vic"),
]


def _seed_person(cur, *, pid, uid, sex, living, private,
                 surname, given, nick=""):
    cur.execute(
        "INSERT INTO PersonTable "
        "(PersonID, UniqueID, Sex, Living, IsPrivate) VALUES (?, ?, ?, ?, ?)",
        (pid, uid, sex, int(living), int(private)),
    )
    sentence = f"{given} {surname}".strip()
    cur.execute(
        "INSERT INTO NameTable "
        "(NameID, OwnerID, Surname, Given, Nickname, NameType, IsPrimary, "
        " Sentence, BirthYear) "
        "VALUES (?, ?, ?, ?, ?, 0, 1, ?, NULL)",
        (pid * 10, pid, surname, given, nick, sentence),
    )


@pytest.fixture
def fake_db():
    """Read-only RMDatabase backed by synthetic data only."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".rmtree", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        build = sqlite3.connect(db_path)
        _bootstrap_schema(build.cursor())
        for row in _FAKE_PEOPLE:
            _seed_person(build, pid=row[0], uid=row[1], sex=row[2],
                         living=row[3], private=row[4],
                         surname=row[5], given=row[6], nick=row[7])
        # Add an alt-name row (NameType=1) for person 1 to exercise
        # load_alt_names().
        build.cursor().execute(
            "INSERT INTO NameTable "
            "(NameID, OwnerID, Surname, Given, Nickname, NameType, IsPrimary, "
            " Sentence, BirthYear) "
            "VALUES (?, ?, ?, ?, ?, 1, 0, ?, NULL)",
            (11, 1, "MARRIED-NAME", "Zoe", "", "Zoe MARRIED-NAME"),
        )
        build.commit()
        build.close()
        # Slight pause for SQLite to flush WAL; remove any -wal sidecar so
        # the read-only opener doesn't see a half-finished transaction.
        for sidecar in (db_path + "-wal", db_path + "-shm"):
            if os.path.exists(sidecar):
                os.unlink(sidecar)
        db = open_database(db_path)
        yield db
        db.close()
    finally:
        for ext in ("", "-wal", "-shm", "-journal"):
            p = db_path + ext
            if os.path.exists(p):
                os.unlink(p)


# --- behaviour tests --------------------------------------------------

def test_db_opens_in_read_only_mode(fake_db):
    assert fake_db.version == 11000
    with pytest.raises(sqlite3.OperationalError):
        fake_db.con.execute("CREATE TABLE should_not_exist (id INTEGER)")


def test_db_close_releases_connection(fake_db):
    fake_db.close()
    with pytest.raises(sqlite3.ProgrammingError):
        fake_db.con.execute("SELECT 1")


def test_schema_error_on_garbage_file(tmp_path):
    bad = tmp_path / "garbage.rmtree"
    bad.write_bytes(b"not a sqlite file")
    with pytest.raises(SchemaError):
        open_database(bad)


def test_schema_error_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_database(tmp_path / "nope.rmtree")


def _open_with_root_blob(tmp_path, blob: bytes):
    """Build a minimal RM DB whose ConfigTable root row is ``blob``.

    Returns the path. Used to pin how malformed root values surface.
    """
    path = tmp_path / "badroot.rmtree"
    build = sqlite3.connect(path)
    _bootstrap_schema(build.cursor())
    build.cursor().execute("DELETE FROM ConfigTable")
    build.cursor().execute(
        "INSERT INTO ConfigTable (RecID, RecType, Title, DataRec) "
        "VALUES (1, 1, '', ?)", (blob,),
    )
    build.commit()
    build.close()
    for ext in ("-wal", "-shm", "-journal"):
        p = str(path) + ext
        if os.path.exists(p):
            os.unlink(p)
    return path


def test_schema_error_on_non_integer_root_person(tmp_path):
    """A malformed RootPerson raises SchemaError, not a bare ValueError.

    Callers are documented to catch SchemaError; a leaking ValueError
    would escape that contract. Every integer parse in the root blob
    must be guarded.
    """
    path = _open_with_root_blob(
        tmp_path,
        b'<Root><Version>11000</Version><STVersion>700</STVersion>'
        b'<UniqueID>FAKE-UUID</UniqueID>'
        b'<RootPerson>NOT-AN-INT</RootPerson></Root>',
    )
    with pytest.raises(SchemaError) as exc:
        open_database(path)
    assert "RootPerson" in str(exc.value)


def test_schema_error_on_non_integer_version(tmp_path):
    """Same guard applies to <Version> — the sibling parse."""
    path = _open_with_root_blob(
        tmp_path,
        b'<Root><Version>NOT-AN-INT</Version><STVersion>700</STVersion>'
        b'<UniqueID>FAKE-UUID</UniqueID><RootPerson>1</RootPerson></Root>',
    )
    with pytest.raises(SchemaError) as exc:
        open_database(path)
    assert "version" in str(exc.value)


def test_schema_error_on_missing_root_person_element(tmp_path):
    """A root blob with no <RootPerson> at all is still SchemaError."""
    path = _open_with_root_blob(
        tmp_path,
        b'<Root><Version>11000</Version><STVersion>700</STVersion>'
        b'<UniqueID>FAKE-UUID</UniqueID></Root>',
    )
    with pytest.raises(SchemaError) as exc:
        open_database(path)
    assert "RootPerson" in str(exc.value)


def test_find_by_surname_returns_seeded_records(fake_db):
    from rmread import find_by_surname
    people = find_by_surname(fake_db.con, "AAAAAA")
    assert {p.person_id for p in people} == {1, 2, 5}
    assert {p.primary_name.given for p in people} == {"Zoe", "Yara", "Victor"}


def test_find_by_surname_is_case_insensitive(fake_db):
    from rmread import find_by_surname
    a = find_by_surname(fake_db.con, "aaaaaa")
    b = find_by_surname(fake_db.con, "AAAAAA")
    c = find_by_surname(fake_db.con, "AaAaAa")
    assert {p.person_id for p in a} == {p.person_id for p in b} == {p.person_id for p in c}


def test_find_by_surname_handles_apostrophe(fake_db):
    from rmread import find_by_surname
    people = find_by_surname(fake_db.con, "O'CCCC")
    assert len(people) == 1
    assert people[0].primary_name.given == "Wren"


def test_find_by_surname_with_given_filter(fake_db):
    from rmread import find_by_surname
    people = find_by_surname(fake_db.con, "AAAAAA", given="Yara")
    assert len(people) == 1
    assert people[0].person_id == 2


def test_find_by_surname_limit(fake_db):
    from rmread import find_by_surname
    capped = find_by_surname(fake_db.con, "AAAAAA", limit=2)
    assert len(capped) == 2


def test_find_by_surname_empty_raises(fake_db):
    from rmread import find_by_surname
    with pytest.raises(ValueError):
        find_by_surname(fake_db.con, "   ")


def test_find_by_surname_no_match(fake_db):
    from rmread import find_by_surname
    assert find_by_surname(fake_db.con, "ZZZZZ_NOPE") == []


def test_person_dataclass_fields(fake_db):
    from rmread import find_by_surname
    p = find_by_surname(fake_db.con, "AAAAAA")[0]
    assert hasattr(p, "person_id")
    assert hasattr(p, "unique_id")
    assert hasattr(p, "primary_name")
    assert hasattr(p, "display_name")
    assert p.sex in (0, 1, 2)


def test_load_alt_names_returns_only_non_primary(fake_db):
    from rmread import load_alt_names
    alts = load_alt_names(fake_db.con, 1)
    assert len(alts) == 1
    assert alts[0].name_type == 1
    assert alts[0].surname == "MARRIED-NAME"


def test_load_alt_names_empty_for_person_with_only_primary(fake_db):
    from rmread import load_alt_names
    assert load_alt_names(fake_db.con, 3) == ()


def test_sex_encoding_constants():
    assert SEX_MALE == 1
    assert SEX_FEMALE == 2
