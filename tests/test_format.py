"""Tests for format.py — text table and JSON envelope.

All input data is **synthetic** — fake names invented for tests. No real
.rmtree is opened.
"""

from __future__ import annotations

import json

import pytest

from rmread.event import Event
from rmread.family import ChildRef, ParentRef, SpouseLink
from rmread.format import (
    DUMP_SCHEMA_VERSION,
    FIND_SCHEMA_VERSION,
    dump_payload,
    to_json,
    to_text,
)
from rmread.person import Name, Person, PersonDump


@pytest.fixture
def two_people():
    n1 = Name(
        name_id=1, surname="AAAAAA", given="Zoe",
        prefix="", suffix="", nickname="Z",
        name_type=0, is_primary=True,
        birth_year=1980, death_year=None,
        sentence="Zoe AAAAAA",
    )
    n2 = Name(
        name_id=2, surname="AAAAAA", given="Yara",
        prefix="", suffix="", nickname="",
        name_type=0, is_primary=True,
        birth_year=1905, death_year=1972,
        sentence="Yara AAAAAA",
    )
    return [
        Person(
            person_id=1, unique_id="fp-1", sex=1,
            living=True, is_private=False,
            primary_name=n1,
        ),
        Person(
            person_id=2, unique_id="fp-2", sex=1,
            living=False, is_private=False,
            primary_name=n2,
        ),
    ]


@pytest.fixture
def person_dump():
    """A person with one event, one parent, one spouse and one child."""
    return PersonDump(
        person=Person(
            person_id=7, unique_id="fp-7", sex=1,
            living=False, is_private=False,
            primary_name=Name(
                name_id=70, surname="AAAAAA", given="Placeholder Given",
                prefix="", suffix="", nickname="",
                name_type=0, is_primary=True,
                birth_year=1880, death_year=1945,
                sentence="Placeholder Given AAAAAA",
            ),
        ),
        events=(
            Event(
                event_id=1, event_type=1, event_type_name="Birth",
                date="1 JAN 1880", sort_date=1, place="PlaceholderPlace",
                is_primary=True, sentence="Birth: 1 JAN 1880",
                details="", note="",
            ),
        ),
        parents=(
            ParentRef(
                family_id=1, parent_id=8,
                parent_name="Placeholder Father AAAAAA", role="father",
            ),
        ),
        spouses=(
            SpouseLink(
                family_id=2, spouse_id=9,
                spouse_name="Placeholder Spouse AAAAAA",
                role="spouse_of_father",
            ),
        ),
        children=(
            ChildRef(
                child_id=10, child_name="Placeholder Child AAAAAA",
                rel_father=1, rel_mother=0, child_order=1,
            ),
        ),
    )


def test_to_text_includes_both_names(two_people):
    out = to_text(two_people)
    assert "Zoe" in out
    assert "Yara" in out
    assert "AAAAAA" in out
    assert "1980" in out
    assert "1972" in out


def test_to_text_truncates_long_given():
    p = Person(
        person_id=99, unique_id="fp-z", sex=2,
        living=True, is_private=False,
        primary_name=Name(
            name_id=1,
            surname="LONG-LONG-LONG",
            given="ANameMuchLongerThanTheGivenColumnWidth",
            prefix="", suffix="", nickname="",
            name_type=0, is_primary=True,
            birth_year=None, death_year=None,
            sentence="",
        ),
    )
    out = to_text([p])
    assert "\u2026" in out


def test_to_text_empty_message():
    assert to_text([]) == "(no matches)"


def test_to_json_envelope_and_results(two_people):
    raw = to_json(two_people, source_path="/tmp/fake.rmtree", db_version=11000)
    obj = json.loads(raw)
    assert obj["envelope"]["tool"] == "rmread"
    assert obj["envelope"]["source_database"] == "/tmp/fake.rmtree"
    assert obj["envelope"]["db_version"] == 11000
    assert obj["envelope"]["count"] == 2
    assert len(obj["results"]) == 2
    assert obj["results"][0]["primary_name"]["surname"] == "AAAAAA"


def test_to_json_envelope_carries_the_schema_version(two_people):
    """The envelope says which shape the payload under it has."""
    obj = json.loads(
        to_json(two_people, source_path="/tmp/fake.rmtree", db_version=11000)
    )
    assert obj["envelope"]["schema_version"] == FIND_SCHEMA_VERSION


def test_to_json_round_trip_is_unicode_safe():
    p = Person(
        person_id=1, unique_id="u", sex=0,
        living=False, is_private=False,
        primary_name=Name(
            name_id=1, surname="O'CCCC", given="Wren",
            prefix="", suffix="", nickname="",
            name_type=0, is_primary=True,
            birth_year=None, death_year=None,
            sentence="Wren O'CCCC",
        ),
    )
    obj = json.loads(to_json([p], source_path="x", db_version=11000))
    assert obj["results"][0]["primary_name"]["surname"] == "O'CCCC"


def test_to_json_handles_generator_input():
    def gen():
        yield Person(
            person_id=1, unique_id="u", sex=0,
            living=False, is_private=False,
            primary_name=Name(
                name_id=1, surname="X", given="Y",
                prefix="", suffix="", nickname="",
                name_type=0, is_primary=True,
                birth_year=None, death_year=None,
                sentence="X Y",
            ),
        )
    obj = json.loads(to_json(gen(), source_path="x", db_version=11000))
    assert obj["envelope"]["count"] == 1


def test_dump_payload_envelope_carries_the_schema_version(person_dump):
    """The rm-dump payload is versioned too — it is a different shape."""
    payload = dump_payload(
        person_dump, source_path="/tmp/fake.rmtree", db_version=11000,
        person_id=7,
    )
    assert payload["envelope"]["schema_version"] == DUMP_SCHEMA_VERSION
    assert payload["envelope"]["tool"] == "rmread"
    assert payload["envelope"]["source_database"] == "/tmp/fake.rmtree"
    assert payload["envelope"]["db_version"] == 11000
    assert payload["envelope"]["person_id"] == 7


def test_dump_payload_carries_the_whole_result(person_dump):
    """Every section rm-dump emits is present, spouses and children included."""
    payload = dump_payload(
        person_dump, source_path="/tmp/fake.rmtree", db_version=11000,
        person_id=7,
    )
    result = payload["result"]
    assert result["person"]["display_name"] == "Placeholder Given AAAAAA"
    assert result["events"][0]["event_type_name"] == "Birth"
    assert result["parents"][0]["parent_id"] == 8
    assert result["spouses"][0]["spouse_id"] == 9
    assert result["spouses"][0]["spouse_name"] == "Placeholder Spouse AAAAAA"
    assert result["children"][0]["child_id"] == 10
    assert result["children"][0]["child_name"] == "Placeholder Child AAAAAA"
