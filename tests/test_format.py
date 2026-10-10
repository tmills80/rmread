"""Tests for format.py — text table and JSON envelope.

All input data is **synthetic** — fake names invented for tests. No real
.rmtree is opened.
"""

from __future__ import annotations

import json

import pytest

from rmread.format import to_json, to_text
from rmread.person import Name, Person


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
    assert "…" in out


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
                sentence="Y X",
            ),
        )
    obj = json.loads(to_json(gen(), source_path="x", db_version=11000))
    assert obj["envelope"]["count"] == 1
