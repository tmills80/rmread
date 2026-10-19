"""Tests for rmread.event — synthetic in-memory only."""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from ._schema import _create_schema, _seed_person, full_db


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


# --- query-count guards ---------------------------------------------------
#
# load_events used to resolve each row's fact-type name and place name
# with a per-row SELECT, so a person with N events cost N+2 queries.
# These tests pin the statement count so the regression cannot come
# back silently. Counting is done with sqlite3's trace callback, not a
# mock — the real SQL really executes.


@pytest.fixture
def many_event_db():
    """One person carrying 24 events that all share one place.

    Two distinct fact types (1 = Birth, 29 = Residence, both in
    DEFAULT_EVENT_TYPES) so the FactTypeTable lookup and the
    PlaceTable lookup are both genuinely repeated by the pre-fix code.
    """
    import os

    tmp = tempfile.NamedTemporaryFile(suffix=".rmtree", delete=False)
    tmp.close()
    try:
        build = sqlite3.connect(tmp.name)
        cur = build.cursor()
        _create_schema(cur)
        _seed_person(cur, pid=1, uid="fp-1", sex=1, living=False,
                     surname="AAAAAA", given="Zed")
        cur.execute("INSERT INTO PlaceTable (Name) VALUES ('FFakePlace-1')")
        for i in range(12):
            cur.execute(
                "INSERT INTO EventTable (EventID, EventType, OwnerType, "
                "OwnerID, PlaceID, Date, SortDate, IsPrimary) "
                "VALUES (?, ?, 0, 1, 1, '1 JAN 1901', 1, 1)",
                (100 + i, 1),
            )
            cur.execute(
                "INSERT INTO EventTable (EventID, EventType, OwnerType, "
                "OwnerID, PlaceID, Date, SortDate, IsPrimary) "
                "VALUES (?, ?, 0, 1, 1, '1 JAN 1920', 2, 0)",
                (200 + i, 29),
            )
        build.commit()
        build.close()

        from rmread import open_database
        db = open_database(tmp.name)
        yield db
        db.close()
    finally:
        for ext in ("", "-wal", "-shm", "-journal"):
            p = tmp.name + ext
            if os.path.exists(p):
                os.unlink(p)


def _count_statements(db, person_id):
    """Return (events, distinct_sql_statements, total_statements)."""
    from rmread import load_events

    seen: list[str] = []
    db.con.set_trace_callback(seen.append)
    try:
        events = load_events(db.con, person_id)
    finally:
        db.con.set_trace_callback(None)
    normalised = {" ".join(s.split()) for s in seen}
    return events, normalised, len(seen)


def test_load_events_issues_constant_number_of_queries(many_event_db):
    """24 events must not cost one lookup per row.

    The pre-fix code ran 30 statements (1 events + 1 person + 24
    FactTypeTable lookups + 24 PlaceTable lookups). Caching the fact
    types and fetching the referenced places in one query bounds it at
    a fixed handful regardless of event count.
    """
    events, statements, total = _count_statements(many_event_db, 1)

    assert len(events) == 24, "fixture should yield 24 events"
    assert total <= 8, (
        f"load_events issued {total} statements for 24 events "
        f"(N+1 lookup regression):\n  " +
        "\n  ".join(sorted(statements))
    )


def test_load_events_batches_fact_and_place_lookups(many_event_db):
    """The real invariant: lookups are batched, not per-row.

    Asserts the number of FactTypeTable/PlaceTable statements is a
    function of the schema, not of the number of result rows.
    """
    events, statements, total = _count_statements(many_event_db, 1)
    per_row_lookups = [s for s in statements
                       if "FactTypeTable" in s or "PlaceTable" in s]

    assert len(events) == 24
    assert len(per_row_lookups) <= 2, (
        "load_events must batch its FactTypeTable and PlaceTable reads "
        f"into at most two statements, saw: {per_row_lookups}"
    )
    assert total < len(events), (
        f"statement count ({total}) should be far below row count "
        f"({len(events)}) — that is the whole point of the cache"
    )
