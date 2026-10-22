"""Regression tests for rmread's sqlite3 connection setup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from rmread.db import SchemaError, open_database
from ._fixture import sample_tree_path


# Path to the dev SampleTree.rmtree that ships at the repo root.
SAMPLE_TREE = sample_tree_path()



#: Skip a test that needs the sample database when it is absent.
requires_sample_tree = pytest.mark.skipif(
    SAMPLE_TREE is None,
    reason=(
        "the RootsMagic sample database is not available; set RM_SAMPLE_TREE "
        "to its path to run this test"
    ),
)

@requires_sample_tree
def test_rmnocase_registered() -> None:
    """A query against a RMNOCASE-collated column must not raise.

    ``AddressTable.Name`` is COLLATE RMNOCASE — a vanilla ``COUNT(*)``
    on the table therefore hits the collation. Pre-fix, this raises
    ``OperationalError: no such collation sequence: RMNOCASE``.

    Captured against ``SampleTree.rmtree`` (RM 11.0); see
    ``tools/rmread/docs/rm11-schema.md`` § "Verified-in-this-DB
    caveats" item 3 for the original bug report.
    """
    db = open_database(SAMPLE_TREE)
    try:
        row = db.con.execute("SELECT COUNT(*) FROM AddressTable").fetchone()
        assert row[0] >= 0
    finally:
        db.close()


@requires_sample_tree
def test_open_real_rmtree_succeeds() -> None:
    db = open_database(SAMPLE_TREE)
    db.close()


def test_open_rejects_non_rmtree(tmp_path: Path) -> None:
    bogus = tmp_path / "not_rmtree.db"
    con = sqlite3.connect(bogus)
    con.execute("CREATE TABLE foo (x INTEGER)")
    con.execute("INSERT INTO foo VALUES (1)")
    con.close()

    with pytest.raises(SchemaError):
        open_database(bogus)


@requires_sample_tree
def test_query_only_enforced() -> None:
    """Even with query_only on, a write must raise."""
    db = open_database(SAMPLE_TREE)
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.con.execute("INSERT INTO AddressTable (Name) VALUES ('x')")
    finally:
        db.close()