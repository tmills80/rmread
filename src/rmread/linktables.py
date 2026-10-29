"""``*LinkTable`` walkers for RootsMagic.

RM groups fact-rows (citations, media items, addresses) to their
owners through three link tables:

    CitationLinkTable   citation -> person / family / source / event
    MediaLinkTable      media item -> person / source / citation / event
    AddressLinkTable    address -> source (and other kinds)

All three use **one global OwnerType enum**:

    0 = Person   1 = Family   2 = Event   3 = Source   4 = Citation

Verified against SampleTree.rmtree (RM 11.0) by counting distinct
OwnerIDs per bucket and using referential-integrity cardinality
disambiguation. Bucket sizes large enough to refute on cardinality:

    CitationLink OT=2: 488 ids    -> only EventTable has 488+ rows
    MediaLink    OT=3:  67 ids    -> only SourceTable is 100%-contained
    MediaLink    OT=4:  73 ids    -> only CitationTable is 100%-contained

AddressLinkTable has only OwnerType=3 (Source) in SampleTree; its
13 distinct OwnerIDs are all in SourceTable, with significant
CitationTable overlap by ID coincidence. Single-source confirmation
only — Plowman has zero AddressLink rows.

OwnerTypes 7 and 19 appear in CitationLinkTable, outside the 0–4
enum. Both point at **people** — they are RM's person-level citations
(the person's own Sources tab), as opposed to owner type 0's
fact-level person citation. They are folded into the ``Person``
bucket; see ``CITATION_PERSON_OWNER_TYPES`` for the evidence.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from typing import TypedDict

_log = logging.getLogger(__name__)


# Global OwnerType enum shared across every *LinkTable.
OWNER_TYPE_TO_KEY: dict[int, str] = {
    0: "Person",
    1: "Family",
    2: "Event",
    3: "Source",
    4: "Citation",
}

#: Owner types that ``CitationLinkTable`` uses for a citation attached
#: at the **person** level, outside the 0–4 global enum.
#:
#: RM 11 stores two kinds of citation against a person: one on the
#: person as a whole (the Sources tab / the name) and one on each of
#: the person's facts. Both land in ``CitationLinkTable``, but only
#: the fact-level one uses the global enum's ``0`` (Person).
#:
#: Verified against ``SampleTree.rmtree`` (RM 11.0) — 33 rows:
#:
#: | OwnerType | rows | distinct owners |
#: |---|---|---|
#: | 7  | 24 | 18 |
#: | 19 |  9 |  6 |
#:
#: Every one of those 24 / 9 owner ids resolves to a person, and in
#: 20 of the 24 type-7 rows the citation's source is *also* cited by
#: that same person's own facts — the signature of a citation copied
#: up from a fact to the person.
#:
#: They are folded into the ``Person`` bucket rather than dropped:
#: dropping them lost 33 citations' worth of attribution, and 4
#: citations in SampleTree were reachable *only* through them (they
#: had no owner at all in the export).
#:
#: Scoped to the citation table on purpose. The media and address
#: link tables in SampleTree use only owner types 0–4, and this says
#: nothing about how RM uses 7 / 19 there.
CITATION_PERSON_OWNER_TYPES: frozenset[int] = frozenset({7, 19})


class CitationLinks(TypedDict):
    Person: dict[int, tuple[int, ...]]
    Family: dict[int, tuple[int, ...]]
    Event: dict[int, tuple[int, ...]]
    Source: dict[int, tuple[int, ...]]
    Citation: dict[int, tuple[int, ...]]


class MediaLinks(TypedDict, total=False):
    # Each map is {owner_id: (child_id, ...)}. Every emitted entry
    # already has the owner-type string resolved; the caller does not
    # need to know the OwnerType integer for downstream use.
    Person: dict[int, tuple[int, ...]]
    Family: dict[int, tuple[int, ...]]
    Event: dict[int, tuple[int, ...]]
    Source: dict[int, tuple[int, ...]]
    Citation: dict[int, tuple[int, ...]]


class AddressLinks(TypedDict):
    Source: dict[int, tuple[int, ...]]


# Sentinel for "any owner type" — used in narrow-by-foreign-key paths
# where the OwnerType discrimination is a downstream concern.
_ALL_BUCKETS = ("Person", "Family", "Event", "Source", "Citation")


def walk_citation_links(
    con: sqlite3.Connection,
    *,
    person_ids: Iterable[int] | None = None,
    family_ids: Iterable[int] | None = None,
) -> CitationLinks:
    """Walk CitationLinkTable and return ``{OwnerType: {OwnerID: (CitationID, ...)}}``.

    Unknown OwnerType values are warned once per distinct value and
    dropped. Buckets beyond the global enum (0–4) are skipped without
    crashing.

    Two owner types outside the global enum are known and are folded
    into the ``Person`` bucket — see
    :data:`CITATION_PERSON_OWNER_TYPES`.

    Parameters
    ----------
    con
        Open ``sqlite3.Connection`` to the .rmtree database.
    person_ids
        Optional PersonID subset. When supplied, ``Person`` rows
        are filtered to those whose ``OwnerID`` is in the set.
    family_ids
        Optional FamilyID subset, applied to the ``Family`` bucket
        the same way. Without it a ``person_ids`` export leaks
        every citation attached to any family in the tree.
    """
    out: CitationLinks = {
        "Person": {}, "Family": {}, "Event": {},
        "Source": {}, "Citation": {},
    }

    rows = con.execute(
        """
        SELECT CitationID, OwnerType, OwnerID
        FROM CitationLinkTable
        ORDER BY OwnerType, OwnerID, SortOrder, CitationID
        """
    ).fetchall()

    bucket_filters: dict[str, set[int] | None] = {
        "Person": None if person_ids is None else set(person_ids),
        "Family": None if family_ids is None else set(family_ids),
        "Event": None,
        "Source": None,
        "Citation": None,
    }

    seen_unknown: set[int] = set()
    skipped_count = 0
    for r in rows:
        otype = r["OwnerType"]
        kind = OWNER_TYPE_TO_KEY.get(otype)
        if kind is None and otype in CITATION_PERSON_OWNER_TYPES:
            kind = "Person"
        if kind is None:
            if otype not in seen_unknown:
                _log.warning(
                    "unknown citation OwnerType=%d (%d rows skipped so far); "
                    "see docs/rm11-schema.md § 'CitationLinkTable'",
                    otype, skipped_count,
                )
                seen_unknown.add(otype)
            skipped_count += 1
            continue

        oid = r["OwnerID"]
        cid = r["CitationID"]

        allowed = bucket_filters[kind]
        if allowed is not None and oid not in allowed:
            continue

        out[kind][oid] = out[kind].get(oid, ()) + (cid,)

    return out


def walk_media_links(
    con: sqlite3.Connection,
    *,
    owner_types: Iterable[int] | None = None,
) -> list[tuple[str, int, int]]:
    """Walk MediaLinkTable and return rows of ``(owner_kind, owner_id, media_id)``.

    Each row's owner_kind is the resolved enum value
    (``"Person"``, ``"Event"``, ``"Source"``, ``"Citation"`` — or
    ``"Family"`` if SampleTree ever grows one). Unknown OwnerTypes
    are dropped with a single warning.

    Parameters
    ----------
    con
        Open ``sqlite3.Connection`` to the .rmtree database.
    owner_types
        Optional subset of OwnerType integers. When supplied, only
        rows with those OwnerTypes are returned; ``None`` returns
        every row whose OwnerType is in the known enum.
    """
    allowed_types = (
        None if owner_types is None else set(owner_types)
    )

    rows = con.execute(
        """
        SELECT MediaID, OwnerType, OwnerID
        FROM MediaLinkTable
        """
    ).fetchall()

    out: list[tuple[str, int, int]] = []
    seen_unknown: set[int] = set()
    skipped_count = 0
    for r in rows:
        otype = r["OwnerType"]
        if allowed_types is not None and otype not in allowed_types:
            continue
        kind = OWNER_TYPE_TO_KEY.get(otype)
        if kind is None:
            if otype not in seen_unknown:
                _log.warning(
                    "unknown media OwnerType=%d (%d rows skipped so far); "
                    "see docs/rm11-schema.md § "
                    "'MultimediaTable + MediaLinkTable'",
                    otype, skipped_count,
                )
                seen_unknown.add(otype)
            skipped_count += 1
            continue
        out.append((kind, r["OwnerID"], r["MediaID"]))
    return out


def walk_address_links(
    con: sqlite3.Connection,
) -> list[tuple[str, int, int]]:
    """Walk AddressLinkTable and return rows of ``(owner_kind, owner_id, address_id)``.

    In SampleTree the only OwnerType in AddressLinkTable is 3
    (Source). The walker enforces the global enum and drops
    unexpected values with a warning.

    Parameters
    ----------
    con
        Open ``sqlite3.Connection`` to the .rmtree database.
    """
    rows = con.execute(
        """
        SELECT AddressID, OwnerType, OwnerID
        FROM AddressLinkTable
        """
    ).fetchall()

    out: list[tuple[str, int, int]] = []
    seen_unknown: set[int] = set()
    skipped_count = 0
    for r in rows:
        otype = r["OwnerType"]
        kind = OWNER_TYPE_TO_KEY.get(otype)
        if kind is None:
            if otype not in seen_unknown:
                _log.warning(
                    "unknown address OwnerType=%d (%d rows skipped so far); "
                    "see docs/rm11-schema.md § "
                    "'AddressTable + AddressLinkTable'",
                    otype, skipped_count,
                )
                seen_unknown.add(otype)
            skipped_count += 1
            continue
        out.append((kind, r["OwnerID"], r["AddressID"]))
    return out


def media_owner_map(
    con: sqlite3.Connection,
) -> dict[tuple[int, int], list[int]]:
    """MediaLink rows as ``{(OwnerType, OwnerID): [MediaID, ...]}``.

    Returned keys are integer OwnerTypes — the same shape the
    callers using ``mediaref`` per-owner lookups already consume.
    Rows whose OwnerType is outside the known enum are dropped
    with a warning.

    This is a separate walk from ``walk_media_links``: the walker
    returns resolved owner-kind strings for callers that want
    business-level filtering, this builder returns integer keys
    for callers that map directly by OwnerType.
    """
    out: dict[tuple[int, int], list[int]] = {}
    seen_unknown: set[int] = set()
    skipped_count = 0
    for r in con.execute(
        "SELECT MediaID, OwnerType, OwnerID FROM MediaLinkTable"
    ):
        otype = r["OwnerType"]
        if otype not in OWNER_TYPE_TO_KEY:
            if otype not in seen_unknown:
                _log.warning(
                    "unknown media OwnerType=%d (%d rows skipped so far); "
                    "see docs/rm11-schema.md § "
                    "'MultimediaTable + MediaLinkTable'",
                    otype, skipped_count,
                )
                seen_unknown.add(otype)
            skipped_count += 1
            continue
        out.setdefault((otype, r["OwnerID"]), []).append(r["MediaID"])
    return out


def address_owner_map(
    con: sqlite3.Connection,
) -> dict[int, list[int]]:
    """AddressLink rows as ``{OwnerID: [AddressID, ...]}``.

    Returns the raw integer mapping — caller picks the kind. OwnerTypes
    outside the known enum are dropped with a warning.
    """
    out: dict[int, list[int]] = {}
    seen_unknown: set[int] = set()
    skipped_count = 0
    for r in con.execute(
        "SELECT AddressID, OwnerType, OwnerID FROM AddressLinkTable"
    ):
        otype = r["OwnerType"]
        if otype not in OWNER_TYPE_TO_KEY:
            if otype not in seen_unknown:
                _log.warning(
                    "unknown address OwnerType=%d (%d rows skipped so far); "
                    "see docs/rm11-schema.md § "
                    "'AddressTable + AddressLinkTable'",
                    otype, skipped_count,
                )
                seen_unknown.add(otype)
            skipped_count += 1
            continue
        out.setdefault(r["OwnerID"], []).append(r["AddressID"])
    return out
