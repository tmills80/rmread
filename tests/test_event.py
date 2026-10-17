"""Tests for rmread.event — synthetic in-memory only."""

from __future__ import annotations

from ._schema import full_db


def test_load_events_returns_seeded_facts(full_db):
    from rmread import load_events
    events = load_events(full_db.con, 1)
    types = {(e.event_type, e.event_type_name) for e in events}
    # DEFAULT_EVENT_TYPES excludes 999, so only the registered types
    # appear. The Unknown(999) fallback path is covered by
    # test_load_events_can_explicitly_include_custom below.
    assert (1, "Birth") in types
    assert (26, "Occupation") in types
    assert (2, "Death") in types
    assert (999, "Unknown(999)") not in types


def test_load_events_resolves_unknown_fact_type_for_custom(full_db):
    """event_type=999 has no FactTypeTable row — must fall back to
    ``Unknown(999)`` rather than crash."""
    from rmread import load_events
    events = load_events(full_db.con, 1, event_types=(1, 2, 26, 4, 999))
    custom = next(e for e in events if e.event_type == 999)
    assert custom.event_type_name == "Unknown(999)"


def test_load_events_filters_to_default_types(full_db):
    """Event 4 is event_type=999 (custom) — DEFAULT_EVENT_TYPES does not
    include 999, so it should be filtered out from the default view."""
    from rmread import DEFAULT_EVENT_TYPES, load_events
    assert 999 not in DEFAULT_EVENT_TYPES
    events = load_events(full_db.con, 1)
    assert 999 not in {e.event_type for e in events}


def test_load_events_can_explicitly_include_custom(full_db):
    from rmread import load_events
    events = load_events(full_db.con, 1, event_types=(1, 2, 26, 4, 999))
    assert 999 in {e.event_type for e in events}


def test_load_events_sorts_by_sort_date(full_db):
    from rmread import load_events
    events = load_events(full_db.con, 1)
    # Default filter excludes 999, so the order is: eid1(Birth, sd=1),
    # eid2(Occupation, sd=2), eid3(Death, sd=0). SortDate=0 sinks to end.
    assert [e.event_type for e in events] == [1, 26, 2]


def test_load_events_returns_empty_for_no_events(full_db):
    from rmread import load_events
    assert load_events(full_db.con, 4) == []


def test_load_events_resolves_place_name(full_db):
    from rmread import load_events
    events = load_events(full_db.con, 1)
    birth = next(e for e in events if e.event_type == 1)
    assert birth.place == "FFakePlace-1"


def test_load_events_empty_event_types_returns_empty(full_db):
    from rmread import load_events
    assert load_events(full_db.con, 1, event_types=()) == []
