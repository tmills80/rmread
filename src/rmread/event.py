"""Life events (births, deaths, occupations, census, etc.) for a Person.

In RootsMagic the ``EventTable`` is a generic fact store. Events are linked
to their owner via ``OwnerType`` (``0`` = Person, ``1`` = Family,
``2`` = Source); for this library we read only ``OwnerType=0``. The
``FactTypeTable`` translates the ``EventType`` int into a human-readable
name like "Birth" or "Residence".
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass


# Default event-type filter. RM has 100+ fact types; many are
# genealogist-specific tags (DNA, LDS, custom). This tuple covers the
# civil facts a person dump usually wants. The raw ``event_type`` int is
# always available on the returned ``Event`` for callers that want more.
#
# IMPORTANT: these are integer FactTypeIDs from RM's ``FactTypeTable`` —
# NOT generic placeholders. Wrong IDs land the SQL filter on the wrong
# fact rows without raising (the FactTypeTable.Name lookup will return
# a misleading name). Take the IDs from ``SELECT FactTypeID, Name FROM
# FactTypeTable`` against a real ``.rmtree``; see
# ``docs/rm11-schema.md`` §"Verified RM 11 IDs for the names `rmread`
# cares about" for the mapping captured against RM 11.0.
DEFAULT_EVENT_TYPES: tuple[int, ...] = (
    1,    # Birth
    2,    # Death
    4,    # Burial
    3,    # Christening (RM stores it as "Christen")
    7,    # Baptism
    5,    # Cremation
    26,   # Occupation
    18,   # Census
    19,   # Probate
    20,   # Will
    29,   # Residence
)


@dataclass(frozen=True)
class Event:
    """A single fact record attached to a Person."""

    event_id: int
    event_type: int
    event_type_name: str       # e.g. "Birth" — looked up from FactTypeTable
    date: str                  # raw RM date string, e.g. "12 JUN 1840"
    sort_date: int | None      # sortable surrogate (0 → unparsed)
    place: str                 # pre-formatted by RM
    is_primary: bool
    sentence: str              # RM's pre-rendered fact sentence
    details: str
    note: str


def _load_fact_type_names(con: sqlite3.Connection) -> dict[int, str]:
    """Load the whole FactTypeTable as ``{EventType: name}``.

    One query per ``load_events`` call rather than one per row. RM
    ships roughly a hundred fact types, so the whole table is small
    and cheaper to cache than to re-select per row.
    """
    rows = con.execute("SELECT FactTypeID, Name FROM FactTypeTable").fetchall()
    return {r["FactTypeID"]: (r["Name"] or "") for r in rows}


def _fact_type_name(event_type: int, names: dict[int, str]) -> str:
    """Resolve one EventType against a preloaded name map.

    Falls back to ``Unknown(<int>)`` when the type has no
    FactTypeTable row — RM lets users add custom fact types, so this
    must never crash. The fallback stays here, in the rendering
    layer, so the SQL filter stays parameter-only.
    """
    return names.get(event_type) or f"Unknown({event_type})"


def _load_place_names(
    con: sqlite3.Connection, place_ids: set[int],
) -> dict[int, str]:
    """Load ``{PlaceID: Name}`` for the referenced ids, in one query.

    Only the ids this person actually references are fetched;
    PlaceTable can hold many thousands of rows on a large tree.
    """
    if not place_ids:
        return {}
    placeholders = ",".join("?" for _ in place_ids)
    rows = con.execute(
        f"SELECT PlaceID, Name FROM PlaceTable WHERE PlaceID IN ({placeholders})",
        list(place_ids),
    ).fetchall()
    return {r["PlaceID"]: (r["Name"] or "") for r in rows}


def load_events(
    con: sqlite3.Connection,
    person_id: int,
    *,
    event_types: Sequence[int] = DEFAULT_EVENT_TYPES,
) -> list[Event]:
    """Return life events for ``person_id`` filtered to ``event_types``.

    Sorted by ``SortDate`` so order is chronological when RM has parsed
    the date; unparsed events (``SortDate=0``) sink to the end.
    """
    if not event_types:
        return []
    type_ph = ",".join("?" for _ in event_types)
    rows = con.execute(
        f"""
        SELECT EventID, EventType, PlaceID, Date, SortDate, IsPrimary,
               Sentence, Details, Note
        FROM EventTable
        WHERE OwnerType = 0
          AND OwnerID = ?
          AND EventType IN ({type_ph})
        ORDER BY
            CASE WHEN SortDate = 0 THEN 1 ELSE 0 END,
            SortDate,
            EventType
        """,
        (person_id, *event_types),
    ).fetchall()

    out: list[Event] = []
    fact_names = _load_fact_type_names(con)
    place_names = _load_place_names(
        con, {r["PlaceID"] for r in rows if r["PlaceID"]},
    )
    for r in rows:
        out.append(Event(
            event_id=r["EventID"],
            event_type=r["EventType"],
            event_type_name=_fact_type_name(r["EventType"], fact_names),
            date=r["Date"] or "",
            sort_date=r["SortDate"] or None,
            place=place_names.get(r["PlaceID"], ""),
            is_primary=bool(r["IsPrimary"]),
            sentence=r["Sentence"] or "",
            details=r["Details"] or "",
            note=r["Note"] or "",
        ))
    return out
