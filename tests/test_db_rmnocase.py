"""Regression tests for rmread's sqlite3 connection setup."""

from __future__ import annotations

import sqlite3
import unicodedata
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
    ``docs/rm11-schema.md`` § "Verified-in-this-DB
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


@requires_sample_tree
def test_rmnocase_compares_correctly() -> None:
    """A name filter must match one name, not the whole table.

    The pre-fix collation returned the folded *string* rather than an
    integer, so SQLite compared every pair as equal: ``WHERE Name = ?``
    matched every row and ``COUNT(DISTINCT Name)`` returned 1. Both
    are silent wrong answers.
    """
    db = open_database(SAMPLE_TREE)
    try:
        one = db.con.execute(
            "SELECT Name FROM AddressTable WHERE Name IS NOT NULL LIMIT 1"
        ).fetchone()
        assert one is not None
        name = one[0]

        matched = db.con.execute(
            "SELECT COUNT(*) FROM AddressTable WHERE Name = ?", (name,)
        ).fetchone()[0]
        assert matched == 1, (
            f"{matched} addresses match the name {name!r} — the collation "
            f"is comparing everything as equal"
        )

        distinct = db.con.execute(
            "SELECT COUNT(DISTINCT Name) FROM AddressTable"
        ).fetchone()[0]
        total = db.con.execute(
            "SELECT COUNT(*) FROM AddressTable WHERE Name IS NOT NULL"
        ).fetchone()[0]
        assert distinct == total, (
            f"{total} address names collapse to {distinct} distinct values "
            f"under the collation"
        )
    finally:
        db.close()


@requires_sample_tree
def test_rmnocase_ignores_case_and_diacritics() -> None:
    """RM's collation folds case and strips diacritics."""
    db = open_database(SAMPLE_TREE)
    try:
        rows = db.con.execute(
            "SELECT CitationName FROM CitationTable "
            "WHERE CitationName IS NOT NULL"
        ).fetchall()
        named = [r[0] for r in rows if any(c.isalpha() for c in (r[0] or ""))]
        if not named:
            pytest.skip("no citation names with letters in this database")
        name = named[0]
        # Fold the way RM's collation folds: case-fold + strip
        # diacritics. Whitespace is *not* stripped.
        nfkd = unicodedata.normalize("NFKD", name)
        folded = "".join(
            c for c in nfkd if not unicodedata.combining(c)
        ).casefold()

        matched = db.con.execute(
            "SELECT COUNT(*) FROM CitationTable WHERE CitationName = ?",
            (folded.upper(),),
        ).fetchone()[0]
        assert matched >= 1, (
            f"case-folded name {folded!r} did not match {name!r}"
        )
    finally:
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