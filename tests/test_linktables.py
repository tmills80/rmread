"""Tests for rmread.linktables — the three RM `*LinkTable` walkers.

Each `*LinkTable` (CitationLinkTable, MediaLinkTable,
AddressLinkTable) groups `(OwnerType, OwnerID)` pairs so a fact
(citation / media item / address) can attach to several owners
across the schema. RM uses one global OwnerType enum across all
three tables:

    0 = Person   1 = Family   2 = Event   3 = Source   4 = Citation

This module owns that vocabulary and the three row → ``(type,
key)`` walkers that consume it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rmread import open_database

SAMPLE_TREE = Path("/home/tristan/genealogy_tools/SampleTree.rmtree")

CITE_TABLE = "CitationLinkTable"
MEDIA_TABLE = "MediaLinkTable"
ADDRESS_TABLE = "AddressLinkTable"


def _bucket_ids(con, table: str, owner_type: int) -> set[int]:
    return {
        r[0] for r in con.execute(
            f"SELECT DISTINCT OwnerID FROM {table} WHERE OwnerType = ?",
            (owner_type,),
        )
    }


# --- exports -------------------------------------------------------------


def test_module_exposes_walkers() -> None:
    """All three walkers and the enum are importable from rmread."""
    from rmread import linktables  # noqa: F401

    for name in ("OWNER_TYPE_TO_KEY", "walk_citation_links",
                 "walk_media_links", "walk_address_links",
                 "CitationLinks", "MediaLinks", "AddressLinks"):
        assert hasattr(linktables, name), f"linktables.{name} missing"


def test_owner_type_enum_documents_correct_mapping() -> None:
    """The shared enum is 0/1/2/3/4 — Person/Family/Event/Source/Citation."""
    from rmread.linktables import OWNER_TYPE_TO_KEY

    assert OWNER_TYPE_TO_KEY == {
        0: "Person", 1: "Family", 2: "Event",
        3: "Source", 4: "Citation",
    }


# --- CitationLinkTable walker --------------------------------------------


def test_citation_link_walker_returns_five_buckets() -> None:
    from rmread.linktables import walk_citation_links

    db = open_database(SAMPLE_TREE)
    try:
        result = walk_citation_links(db.con)
    finally:
        db.close()

    assert set(result) == {"Person", "Family", "Event", "Source", "Citation"}
    for bucket in result.values():
        assert isinstance(bucket, dict)


def test_citation_link_event_bucket_is_not_empty() -> None:
    """SampleTree has 488 distinct CitationLinkTable OwnerType=2 owners.

    OwnerType=2 = Event in the global enum. This is the largest bucket
    in SampleTree and the one that pinned the enum refutation —
    without it, the test does not exercise the bucket that broke
    the old rm2gramps mapper. We compare bucket size by counting
    walk-derived ids, not assertion against the link-table row
    count, because one Event can carry many of the same CitationIDs.
    """
    from rmread.linktables import walk_citation_links

    db = open_database(SAMPLE_TREE)
    try:
        con = db.con
        result = walk_citation_links(con)
        db_owner_ids = _bucket_ids(con, CITE_TABLE, 2)
    finally:
        db.close()

    assert len(db_owner_ids) > 100, "SampleTree should have many Event citations"
    walker_owner_ids = set(result["Event"])
    assert walker_owner_ids == db_owner_ids, (
        f"walker saw {len(walker_owner_ids - db_owner_ids)} extra "
        f"and {len(db_owner_ids - walker_owner_ids)} missing Event owner ids"
    )


def test_citation_link_walker_respects_family_subset() -> None:
    from rmread.linktables import walk_citation_links

    db = open_database(SAMPLE_TREE)
    try:
        con = db.con
        # Pull a few families that actually own citations, then ask
        # the walker to narrow to only those.
        rows = con.execute(
            "SELECT OwnerID FROM CitationLinkTable "
            "WHERE OwnerType = 1 LIMIT 5"
        ).fetchall()
        family_subset = {r[0] for r in rows}
        if not family_subset:
            pytest.skip("no Family citations in sample")
        full = walk_citation_links(con)
        subset = walk_citation_links(
            con, family_ids=family_subset,
        )
    finally:
        db.close()

    full_owner_ids = set(full["Family"])
    assert full_owner_ids, "Family bucket should be populated"
    # Narrowed walker must only include the requested owners.
    assert set(subset["Family"]).issubset(family_subset)
    # Bucket contents for the same owner must match.
    for owner in full_owner_ids.intersection(family_subset):
        assert full["Family"][owner] == subset["Family"][owner]


# --- MediaLinkTable walker -----------------------------------------------


def test_media_link_walker_returns_resolved_owner_handles() -> None:
    """Each row becomes (OWNER_TYPE_TO_KEY[ot], owner_id, child_id)."""
    from rmread.linktables import walk_media_links

    db = open_database(SAMPLE_TREE)
    try:
        rows = walk_media_links(db.con)
    finally:
        db.close()

    assert rows, "SampleTree should have MediaLinks"
    kinds = {r[0] for r in rows}
    assert kinds.issubset({"Person", "Family", "Event", "Source", "Citation"})


# --- AddressLinkTable walker ---------------------------------------------


def test_address_link_walker_handles_only_owner_type_3() -> None:
    """AddressLinkTable in SampleTree only carries OwnerType=3, which
    is Source in the global enum.
    """
    from rmread.linktables import walk_address_links

    db = open_database(SAMPLE_TREE)
    try:
        result = walk_address_links(db.con)
    finally:
        db.close()

    # All returned owners are SourceIDs.
    assert all(r[0] == "Source" for r in result), (
        "AddressLinkTable should map only to Source in the global enum"
    )


def test_address_link_walker_full_containment_in_source_table() -> None:
    """Every returned Source-owner-id must exist in SourceTable.

    AddressLinkTable OwnerType=3 is the bucket that broke the prior
    writer (it was treated as a CitationID). The fix is here:
    walker tells the caller the owner is a Source; the caller then
    matches on SourceID.
    """
    from rmread.linktables import walk_address_links

    db = open_database(SAMPLE_TREE)
    try:
        con = db.con
        rows = walk_address_links(con)
        source_ids = {
            r[0] for r in con.execute(
                "SELECT SourceID FROM SourceTable"
            )
        }
    finally:
        db.close()

    owner_ids = {r[1] for r in rows}
    assert owner_ids, "no AddressLinks in SampleTree?"
    assert owner_ids <= source_ids, (
        f"{len(owner_ids - source_ids)} of {len(owner_ids)} AddressLink "
        f"owner_ids are not SourceIDs"
    )


# --- provenance ------------------------------------------------------------


def test_walkers_never_write() -> None:
    """Read-only: running every walker does not mutate the connection."""
    # mode=ro + PRAGMA query_only is enforced by open_database, so
    # the connection itself rejects writes. This test makes that
    # contract explicit: every walker must complete cleanly on a
    # read-only connection.
    db = open_database(SAMPLE_TREE)
    try:
        from rmread.linktables import (
            walk_address_links, walk_citation_links, walk_media_links,
        )

        con = db.con
        walk_citation_links(con)
        walk_media_links(con)
        walk_address_links(con)
        with pytest.raises(sqlite3.OperationalError):
            con.execute(
                "INSERT INTO PersonTable (PersonID) VALUES (99999)"
            )
    finally:
        db.close()


# --- integer-keyed builders ----------------------------------------------


def test_media_owner_map_keys_are_integers() -> None:
    """``media_owner_map`` returns ``{(OwnerType, OwnerID): [...]}``.

    Tests use the integer-keyed shape directly so callers like the
    Gramps export don't have to translate owner-kind strings back
    to integers.
    """
    from rmread.linktables import media_owner_map

    db = open_database(SAMPLE_TREE)
    try:
        m = media_owner_map(db.con)
    finally:
        db.close()

    assert m, "SampleTree should have MediaLinks"
    for (ot, oid), mids in m.items():
        assert isinstance(ot, int), f"OwnerType must be int, got {type(ot)}"
        assert isinstance(oid, int)
        assert all(isinstance(mid, int) for mid in mids)


def test_media_owner_map_uses_global_enum() -> None:
    """Every OwnerType key is one of the 0/2/3/4 enum values used by
    MediaLinkTable in SampleTree. The walker rejects unknown
    OwnerTypes with a warning, but those should not appear as keys.
    """
    from rmread.linktables import media_owner_map, OWNER_TYPE_TO_KEY

    db = open_database(SAMPLE_TREE)
    try:
        m = media_owner_map(db.con)
    finally:
        db.close()

    types = {ot for ot, _ in m}
    assert types <= set(OWNER_TYPE_TO_KEY), (
        f"media_owner_map produced keys outside the enum: {types}"
    )


def test_address_owner_map_is_source_keyed() -> None:
    """``address_owner_map`` returns ``{OwnerID: [AddressID, ...]}``.

    SampleTree's AddressLink has only OwnerType=3 (Source), so
    every key should be a SourceID.
    """
    from rmread.linktables import address_owner_map

    db = open_database(SAMPLE_TREE)
    try:
        con = db.con
        m = address_owner_map(con)
        source_ids = {r[0] for r in con.execute(
            "SELECT SourceID FROM SourceTable"
        )}
    finally:
        db.close()

    assert m
    assert set(m).issubset(source_ids), (
        f"address_owner_map produced non-Source keys: "
        f"{sorted(set(m) - source_ids)[:5]}"
    )

