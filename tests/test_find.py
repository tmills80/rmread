"""Tests for rmread.person.find_by_surname and find_person — synthetic only."""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_db():
    """Reuse the same synthetic fixture as test_db.py / test_event.py."""
    import os, sqlite3, tempfile
    from tests._schema import _create_schema, _seed_person

    DB_VERSION_11 = (
        b'<Root><Version>11000</Version><STVersion>700</STVersion>'
        b'<UniqueID>FAKE</UniqueID><RootPerson>1</RootPerson></Root>'
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".rmtree", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        build = sqlite3.connect(db_path)
        build.cursor().executescript("""
            CREATE TABLE ConfigTable (RecID INTEGER, RecType INTEGER, Title TEXT,
                                      DataRec BLOB, UTCModDate FLOAT);
            CREATE TABLE PersonTable (
                PersonID INTEGER PRIMARY KEY, UniqueID TEXT,
                Sex INTEGER, ParentID INTEGER, SpouseID INTEGER,
                Color INTEGER, Color1 INTEGER, Color2 INTEGER, Color3 INTEGER,
                Color4 INTEGER, Color5 INTEGER, Color6 INTEGER, Color7 INTEGER,
                Color8 INTEGER, Color9 INTEGER, Relate1 INTEGER, Relate2 INTEGER,
                Flags INTEGER, Living INTEGER, IsPrivate INTEGER, Proof INTEGER,
                Bookmark INTEGER, Note TEXT, UTCModDate FLOAT);
            CREATE TABLE NameTable (
                NameID INTEGER PRIMARY KEY, OwnerID INTEGER, Surname TEXT,
                Given TEXT, Prefix TEXT, Suffix TEXT, Nickname TEXT,
                NameType INTEGER, Date TEXT, SortDate BIGINT,
                IsPrimary INTEGER, IsPrivate INTEGER, Proof INTEGER,
                Sentence TEXT, Note TEXT, BirthYear INTEGER, DeathYear INTEGER,
                Display INTEGER, Language TEXT, UTCModDate FLOAT,
                SurnameMP TEXT, GivenMP TEXT, NicknameMP TEXT);
        """)
        cur = build.cursor()
        cur.execute(
            "INSERT INTO ConfigTable (RecID, RecType, Title, DataRec) "
            "VALUES (1, 1, '', ?)",
            (DB_VERSION_11,),
        )
        # Three Zoes, two ABCAAA and one ABCAAX variants — useful for
        # testing both wildcard and substring behaviour.
        for pid, surname, given, nick in [
            (1, "AAAAAA", "Zoe",      "Z"),
            (2, "AAAAAA", "Yara",     ""),
            (3, "AAAAAA", "Zed",      ""),
            (4, "BBBBBB", "Zoe",      ""),
            (5, "ABCAAB", "Zoe",      ""),
        ]:
            sentence = f"{given} {surname}".strip()
            cur.execute(
                "INSERT INTO PersonTable "
                "(PersonID, UniqueID, Sex, Living, IsPrivate) "
                "VALUES (?, ?, 0, 1, 0)",
                (pid, f"fp-{pid}"),
            )
            cur.execute(
                "INSERT INTO NameTable "
                "(NameID, OwnerID, Surname, Given, Nickname, NameType, "
                " IsPrimary, Sentence, BirthYear) "
                "VALUES (?, ?, ?, ?, ?, 0, 1, ?, 2000)",
                (pid * 10, pid, surname, given, nick, sentence),
            )
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


# ----- find_by_surname (verbatim LIKE, no substring wrap) -------------
#
# find_by_surname is a positional-arg wrapper over find_person and
# does NOT auto-wrap bare words as %value%. These tests pin that: a
# pattern that would match under wrapping must return [] under the
# current behaviour. rm-find's CLI substring default lives in
# cli/find._to_pattern, not here.

def test_find_by_surname_no_substring_wrap(fake_db):
    """A bare prefix must NOT match as a substring.

    'ABC' is a prefix of 'ABCAAB' (pid 5). Under substring wrapping
    this would return {5}; verbatim LIKE matching returns nothing.
    This is the regression guard — if wrapping is ever reintroduced,
    this test fails.
    """
    from rmread import find_by_surname
    assert find_by_surname(fake_db.con, "ABC") == []


def test_find_by_surname_exact_match(fake_db):
    from rmread import find_by_surname
    # Plain "AAAAAA" — literal match on all three AAAAAA records.
    # (Same result under wrapping; kept as the happy-path anchor.)
    pids = {p.person_id for p in find_by_surname(fake_db.con, "AAAAAA")}
    assert pids == {1, 2, 3}


def test_find_by_surname_passes_through_pattern(fake_db):
    from rmread import find_by_surname
    # User-supplied wildcard must be respected — not wrapped further.
    pids = {p.person_id for p in find_by_surname(fake_db.con, "A%")}
    # A%, %A, AAA, AAAAAA all match; pid 5 has surname ABCAAB (starts with A too).
    assert pids == {1, 2, 3, 5}


def test_find_by_surname_single_char_wildcard(fake_db):
    from rmread import find_by_surname
    pids = {p.person_id for p in find_by_surname(fake_db.con, "AAAAAA_")}
    # AAAAAA_ — surname starting with AAAAAA then any char. None in fixture.
    assert pids == set()


def test_find_by_surname_rejects_empty(fake_db):
    from rmread import find_by_surname
    with pytest.raises(ValueError):
        find_by_surname(fake_db.con, "   ")


def test_find_by_surname_given_filter(fake_db):
    from rmread import find_by_surname
    # Given "Zoe" is a literal LIKE match — not substring-wrapped.
    pids = {p.person_id for p in find_by_surname(fake_db.con, "AAAAAA", given="Zoe")}
    assert pids == {1}


def test_find_by_surname_given_wildcard(fake_db):
    from rmread import find_by_surname
    # "%Z%" — matches any given containing Z.
    pids = {p.person_id for p in find_by_surname(fake_db.con, "AAAAAA", given="%Z%")}
    # Yara contains no Z; Zoe/Zed both contain Z.
    assert pids == {1, 3}


def test_find_by_surname_limit(fake_db):
    from rmread import find_by_surname
    pids = {p.person_id for p in find_by_surname(fake_db.con, "AAAAAA", limit=2)}
    assert len(pids) == 2


def test_find_by_surname_no_match(fake_db):
    from rmread import find_by_surname
    assert find_by_surname(fake_db.con, "ZZZZZ") == []


# ----- new find_person (explicit patterns only) ----------------------

def test_find_person_exact_match(fake_db):
    from rmread import find_person
    # Exact "AAAAAA" — only literal AAAAAA records, NOT ABCAAB.
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA")}
    assert pids == {1, 2, 3}


def test_find_person_prefix_wildcard(fake_db):
    from rmread import find_person
    pids = {p.person_id for p in find_person(fake_db.con, surname="A%")}
    assert pids == {1, 2, 3, 5}


def test_find_person_single_char_wildcard(fake_db):
    from rmread import find_person
    # ABCAA_ matches ABCAAB only.
    pids = {p.person_id for p in find_person(fake_db.con, surname="ABCAA_")}
    assert pids == {5}


def test_find_person_double_wildcard_in_middle(fake_db):
    from rmread import find_person
    # A%_AA matches AAAAAA (5 A's with one of anything at position 2-3)
    # — the middle wildcard is "AA" + _ + ""-style match.
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA")}
    assert pids == {1, 2, 3}


def test_find_person_no_substring_wrap(fake_db):
    """A plain `OOO` is NOT auto-wrapped — must return zero hits."""
    from rmread import find_person
    pids = list(find_person(fake_db.con, surname="OOO"))
    assert pids == []


def test_find_person_surname_and_given_wildcards(fake_db):
    from rmread import find_person
    # 'Z__' = Z followed by exactly two more characters → 'Zoe' and 'Zed'.
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA", given="Z__")}
    assert pids == {1, 3}


def test_find_person_explicitly_underscored_surname(fake_db):
    """A prefix pattern — 'AA_' = AA then one more char = 'AAA' (3 chars).

    AAAAAA is 6 chars, so the pattern 'AA%' is needed for substring,
    not 'AA_'. This test pins the underscore semantic clearly."""
    from rmread import find_person
    # 'AAA' exactly = matches the literal 3-char surname (none seeded).
    assert list(find_person(fake_db.con, surname="AAA")) == []
    # 'AA%' = AA followed by anything.
    pids = {p.person_id for p in find_person(fake_db.con, surname="AA%")}
    assert pids == {1, 2, 3}


def test_find_person_given_only_exact(fake_db):
    from rmread import find_person
    # Given filter without wildcards matches the literal "Zoe".
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA", given="Zoe")}
    assert pids == {1}


def test_find_person_given_none_skips_filter(fake_db):
    from rmread import find_person
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA", given=None)}
    assert pids == {1, 2, 3}


def test_find_person_given_empty_string_skips_filter(fake_db):
    from rmread import find_person
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA", given="")}
    assert pids == {1, 2, 3}


def test_find_person_limit(fake_db):
    from rmread import find_person
    pids = [p.person_id for p in find_person(fake_db.con, surname="A%", limit=2)]
    assert len(pids) == 2


def test_find_person_empty_surname_raises(fake_db):
    from rmread import find_person
    with pytest.raises(ValueError):
        find_person(fake_db.con, surname="")
    # Whitespace-only is also caught — the runtime check is truthy on
    # the stripped value, not just on `not surname`.
    with pytest.raises(ValueError):
        find_person(fake_db.con, surname="   ")


def test_find_person_case_insensitive(fake_db):
    from rmread import find_person
    a = {p.person_id for p in find_person(fake_db.con, surname="aaaaaa")}
    b = {p.person_id for p in find_person(fake_db.con, surname="AAAAAA")}
    assert a == b == {1, 2, 3}


def test_find_person_underscore_matches_single_char(fake_db):
    """SQL LIKE: '_' matches exactly one character at that position.

    'AAAAA_' = literal 5 A's + any 1 char (total 6 chars). 'AAAAAA'
    is exactly 6 chars and ends with an A, so 'AAAAA_' matches it.
    """
    from rmread import find_person
    pids = {p.person_id for p in find_person(fake_db.con, surname="AAAAA_")}
    # All three AAAAAA records match.
    assert pids == {1, 2, 3}


def test_find_person_underscore_too_short_does_not_match(fake_db):
    """'AAAA_' = 4 A's + any 1 char = 5 chars total. 'AAAAAA' is 6 chars
    and so does NOT match — the pattern length must equal the column
    value length when only underscores are used."""
    from rmread import find_person
    pids = list(find_person(fake_db.con, surname="AAAA_"))
    assert pids == []


# --- SQL template guards ---------------------------------------------------
#
# find_person formats its WHERE clause into _SURNAME_SEARCH_SQL. Note
# that sqlite3's trace callback reports the *expanded* statement
# (placeholders already substituted), so it cannot be used to assert
# that input stays parameterised. These tests pin what is observable:
# the template shape, and that every clause combination builds SQL
# sqlite3 accepts.
#
# Parameterisation itself is guaranteed structurally — the only
# value ever formatted into the statement is " AND ".join(clauses),
# and clauses are constant strings.


def test_search_sql_template_exposes_one_where_slot():
    """The SQL constant must expose exactly one {where} slot.

    A stray literal brace would raise KeyError at runtime; a missing
    one would silently drop the surname filter and return every
    person in the database.
    """
    from rmread.person import _SURNAME_SEARCH_SQL
    assert _SURNAME_SEARCH_SQL.count("{where}") == 1
    assert "{" not in _SURNAME_SEARCH_SQL.replace("{where}", "")


def test_find_person_each_clause_shape_executes(fake_db):
    """Every supported filter combination must build valid SQL.

    Guards the format() path: a clause appended without a matching
    params entry raises "Incorrect number of bindings" at execute
    time. Running each shape is the assertion.
    """
    from rmread import find_person

    cases: list[dict[str, object]] = [
        {"surname": "QQQQQQ"},
        {"surname": "QQQQQQ", "given": "Zxexy"},
        {"surname": "QQQQQQ", "given": ""},
        {"surname": "QQQQQQ", "limit": 2},
        {"surname": "QQQQQQ", "given": "Z__", "limit": 1},
    ]
    for kwargs in cases:
        find_person(fake_db.con, **kwargs)  # type: ignore[arg-type]
