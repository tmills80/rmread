"""Tests for PersonDump composition — synthetic in-memory only."""

from __future__ import annotations

from ._schema import full_db


def test_dump_person_returns_none_for_missing_id(full_db):
    from rmread import dump_person
    assert dump_person(full_db.con, 99999) is None


def test_dump_person_basic_identity(full_db):
    from rmread import dump_person
    dump = dump_person(full_db.con, 1)
    assert dump is not None
    assert dump.person.person_id == 1
    assert dump.person.display_name == "Zed AAAAAA"
    assert dump.person.primary_name.birth_year == 1901


def test_dump_person_composes_events(full_db):
    from rmread import dump_person
    dump = dump_person(full_db.con, 1)
    assert dump is not None
    # DEFAULT_EVENT_TYPES does not include 999, so 3 events come back.
    assert len(dump.events) == 3
    assert dump.events[0].event_type_name == "Birth"
    assert dump.events[0].place == "FFakePlace-1"


def test_dump_person_composes_family(full_db):
    from rmread import dump_person
    dump = dump_person(full_db.con, 1)
    assert dump is not None
    # pid 1 has no ChildTable rows pointing at it (it's a parent, not a
    # child), so it has no recorded parents.
    assert dump.parents == ()
    # 3 spouses (families where pid 1 is father) + 2 children (pid 5, 6).
    assert {s.spouse_id for s in dump.spouses} == {2, 3, 4}
    assert {c.child_id for c in dump.children} == {5, 6}


def test_dump_person_shows_parents_of_a_child(full_db):
    """pid 5 is a child in family 3 → its parents should appear as a
    father/mother pair."""
    from rmread import dump_person
    dump = dump_person(full_db.con, 5)
    assert dump is not None
    role_ids = {(p.role, p.parent_id) for p in dump.parents}
    assert ("father", 1) in role_ids
    assert ("mother", 4) in role_ids


def test_dump_person_no_events_flag(full_db):
    from rmread import dump_person
    dump = dump_person(full_db.con, 1, include_events=False, include_family=True)
    assert dump is not None
    assert dump.events == ()
    assert len(dump.spouses) == 3


def test_dump_person_no_family_flag(full_db):
    from rmread import dump_person
    dump = dump_person(full_db.con, 1, include_events=True, include_family=False)
    assert dump is not None
    assert dump.events != ()
    assert dump.parents == ()
    assert dump.spouses == ()
    assert dump.children == ()


def test_dump_person_orphan_returns_stub_name(full_db):
    """pid 7 exists in PersonTable but no NameTable row."""
    from rmread import dump_person
    dump = dump_person(full_db.con, 7)
    assert dump is not None
    assert dump.person.person_id == 7
    assert dump.person.display_name == ""
    assert dump.events == ()


def test_get_person_returns_none_for_missing(full_db):
    from rmread import get_person
    assert get_person(full_db.con, 99999) is None


def test_get_person_round_trip(full_db):
    from rmread import get_person
    p = get_person(full_db.con, 1)
    assert p is not None
    assert p.display_name == "Zed AAAAAA"
    assert p.living is False
    assert p.sex == 1
