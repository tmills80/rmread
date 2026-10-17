"""Regression guard for ``rmread.event.DEFAULT_EVENT_TYPES``.

The default tuple is referenced as integer IDs in
``EventTable.EventType IN (...)``. Those IDs must be the ones
RootsMagic actually uses for the named civil facts — verified
against ``SampleTree.rmtree`` (RM 11.0); see
``docs/rm11-schema.md`` §"Verified RM 11 IDs for the names
`rmread` cares about" for the source table.

If a future change introduces a drift between the default
tuple and the names in ``FactTypeTable``, this test goes red
before the broken defaults ship. The expected ID for each
name is recomputed by reading ``FactTypeTable`` from a
synthetic in-memory DB, so a rename in the canonical fact-name
set is caught here too.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest


# The names rmread.event.DEFAULT_EVENT_TYPES is supposed to map.
# If the canonical set changes (e.g. RM adds "Burial (cremated)"),
# update both this dict and ``DEFAULT_EVENT_TYPES``.
EXPECTED_FACT_NAMES_BY_MEANING: dict[str, str] = {
    "Birth": "Birth",
    "Death": "Death",
    "Burial": "Burial",
    "Christening": "Christen",
    "Baptism": "Baptism",
    "Cremation": "Cremation",
    "Occupation": "Occupation",
    "Census": "Census",
    "Probate": "Probate",
    "Will": "Will",
    "Residence": "Residence",
}


# Build a synthetic FactTypeTable that pins each canonical name
# to the verified RM 11.0 integer ID. The mapping is taken from
# the SampleTree.rmtree introspection captured in
# ``docs/rm11-schema.md``.
VERIFIED_RM11_FACT_IDS: dict[str, tuple[int, str]] = {
    # rmread-meaning : (FactTypeID, FactTypeTable.Name)
    "Birth":        (1,   "Birth"),
    "Death":        (2,   "Death"),
    "Burial":       (4,   "Burial"),
    "Christening":  (3,   "Christen"),
    "Baptism":      (7,   "Baptism"),
    "Cremation":    (5,   "Cremation"),
    "Occupation":   (26,  "Occupation"),
    "Census":       (18,  "Census"),
    "Probate":      (19,  "Probate"),
    "Will":         (20,  "Will"),
    "Residence":    (29,  "Residence"),
}


@pytest.fixture
def rm11_style_fact_table():
    """In-memory SQLite with a FactTypeTable shaped like RM 11.0.

    The table mirrors exactly the rows that exist in
    ``SampleTree.rmtree`` for the 11 fact names rmread maps.
    """
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE FactTypeTable "
        "(FactTypeID INTEGER PRIMARY KEY, Name TEXT)"
    )
    for _meaning, (ft_id, ft_name) in VERIFIED_RM11_FACT_IDS.items():
        db.execute(
            "INSERT INTO FactTypeTable (FactTypeID, Name) VALUES (?, ?)",
            (ft_id, ft_name),
        )
    yield db
    db.close()


def _resolve_expected_ids(ft_con, names_by_meaning):
    """Look up the FactTypeID for each canonical name from a
    FactTypeTable-shaped DB and return ``{meaning: id}``.

    The fixture only seeds the 11 rows we care about, so a
    rename of a canonical name in RM (e.g. "Christen" →
    "Christening") turns this into a fetch error and the test
    fails with a clear message.
    """
    out = {}
    for meaning, name in names_by_meaning.items():
        row = ft_con.execute(
            "SELECT FactTypeID FROM FactTypeTable WHERE Name = ?", (name,)
        ).fetchone()
        if row is None:
            raise AssertionError(
                f"canonical fact-name {name!r} (for {meaning!r}) not "
                f"present in the FactTypeTable fixture — has RM renamed it?"
            )
        out[meaning] = row[0]
    return out


def test_default_event_types_match_verified_rm11_ids(rm11_style_fact_table):
    """Every ID in DEFAULT_EVENT_TYPES is the integer RootsMagic
    11.0 uses for the named civil fact."""
    from rmread import DEFAULT_EVENT_TYPES

    expected_by_meaning = _resolve_expected_ids(
        rm11_style_fact_table, EXPECTED_FACT_NAMES_BY_MEANING
    )
    expected = set(expected_by_meaning.values())

    missing = expected - set(DEFAULT_EVENT_TYPES)
    unexpected = set(DEFAULT_EVENT_TYPES) - expected

    assert not missing and not unexpected, (
        "DEFAULT_EVENT_TYPES does not match verified RM 11 fact IDs.\n"
        f"  Missing from DEFAULT_EVENT_TYPES: {sorted(missing)}\n"
        f"  Unexpected in DEFAULT_EVENT_TYPES: {sorted(unexpected)}\n"
        f"  Expected mapping (name → FactTypeID):\n"
        + "\n".join(
            f"    {m!r} ({n}): {i}"
            for m, (i, n) in sorted(
                VERIFIED_RM11_FACT_IDS.items(),
                key=lambda kv: (kv[1][0], kv[0]),
            )
        )
    )


def test_default_event_types_has_no_duplicate_ids(rm11_style_fact_table):
    """DEFAULT_EVENT_TYPES is a tuple of distinct IDs — a duplicate
    would silently widen the filter without raising."""
    from rmread import DEFAULT_EVENT_TYPES

    assert len(DEFAULT_EVENT_TYPES) == len(set(DEFAULT_EVENT_TYPES)), (
        f"DEFAULT_EVENT_TYPES contains duplicates: {DEFAULT_EVENT_TYPES}"
    )


def test_default_event_types_covers_eleven_civil_facts(rm11_style_fact_table):
    """The default set is the eleven-name civil-facts set a person
    dump usually wants; if this drifts, callers depending on the
    set size know."""
    from rmread import DEFAULT_EVENT_TYPES

    # Reasonably stable contract: 11 civil facts (matches the size
    # of the verified mapping). If a future change adds a fact to
    # this set (or removes one), update this assertion with a
    # matching change to EXPECTED_FACT_NAMES_BY_MEANING.
    assert len(DEFAULT_EVENT_TYPES) == len(EXPECTED_FACT_NAMES_BY_MEANING)
