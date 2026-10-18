"""Database access for RootsMagic (.rmtree) SQLite files.

Read-only. Opens via the SQLite URI ``mode=ro`` so a stray write raises
rather than silently corrupting research data.
"""

from __future__ import annotations

import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class SchemaError(Exception):
    """Raised when the database does not look like a RootsMagic file."""


def _rmnocase(value, _name=None):
    """RMNOCASE collation function: case-fold + Unicode-diacritic-strip.

    SQLite passes the column value as ``value`` and the collation name
    as ``_name``; the latter is ignored (Python's sqlite3 expects the
    callback shape ``(str, str) -> int``).
    """
    if value is None:
        return None
    nfkd = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True)
class RootInfo:
    """Top-level metadata pulled from ConfigTable row id=1."""

    version: int          # e.g. 11000 for RootsMagic 11
    st_version: int       # Source Template version
    unique_id: str
    root_person_id: int
    preparer_email: str | None


def _read_root_info(con: sqlite3.Connection) -> RootInfo:
    """Parse the RM root blob out of the first ConfigTable row.

    Column names are ``RecID``, ``RecType``, ``Title``, ``DataRec`` —
    not the generic ``ID``/``Section``/``Name``/``BlobData`` you'd
    expect. Verified against an RM 11.0 sample database. The root row
    is ``RecID=1, RecType=1, Title=''``.
    """
    cur = con.execute(
        "SELECT DataRec FROM ConfigTable "
        "WHERE RecID=1 AND RecType=1 AND Title=''"
    )
    row = cur.fetchone()
    if row is None:
        raise SchemaError("ConfigTable root row not found — not a RootsMagic database.")
    try:
        root = ET.fromstring(row[0])
    except ET.ParseError as e:
        raise SchemaError(f"ConfigTable root blob is not valid XML: {e}") from e

    def text(tag: str) -> str | None:
        el = root.find(tag)
        return el.text if (el is not None and el.text is not None) else None

    try:
        version = int(text("Version") or "0")
        st_version = int(text("STVersion") or "0")
    except ValueError as e:
        raise SchemaError(f"non-integer version in ConfigTable: {e}") from e

    root_pid = text("RootPerson")
    if root_pid is None:
        raise SchemaError("ConfigTable root has no <RootPerson>.")

    return RootInfo(
        version=version,
        st_version=st_version,
        unique_id=text("UniqueID") or "",
        root_person_id=int(root_pid),
        preparer_email=text("PreparerEmail"),
    )


# RootsMagic versions we know how to query. RM 7 introduced the schema we
# target; anything below 7 will be rejected. Newer versions keep the same
# NameTable / PersonTable / EventTable shape we read from.
_MIN_SUPPORTED_VERSION = 7000


class RMDatabase:
    """A read-only connection to a RootsMagic SQLite database.

    Always opens ``mode=ro``. Use as a context manager:

        with RMDatabase("/path/to/Tree.rmtree") as db:
            for p in db.find_surname("PlaceholderSurname"):
                ...
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"RootsMagic file not found: {self.path}")
        uri = f"file:{self.path}?mode=ro"
        try:
            self._con = sqlite3.connect(
                uri, uri=True, isolation_level=None
            )
        except sqlite3.DatabaseError as e:
            raise SchemaError(f"{self.path} is not a valid SQLite database: {e}") from e
        # Register RM's RMNOCASE collation before any user query. Many
        # RM TEXT columns (NameTable.Surname, PlaceTable.Name,
        # AddressTable.Name, CitationTable.CitationName, …) are
        # declared COLLATE RMNOCASE — a case-fold + diacritic-strip
        # collation that Python's sqlite3 doesn't ship. Without this
        # registration, even read-only queries against those tables
        # raise ``no such collation sequence: RMNOCASE``. See
        # ``tools/rmread/docs/rm11-schema.md`` § "The ``RMNOCASE``
        # collation" for the original bug report.
        self._con.create_collation("RMNOCASE", _rmnocase)
        # Defensive: refuse to run any write even if mode=ro is dropped.
        # A "not a database" file opens cleanly but raises on first query —
        # _read_root_info will then raise OperationalError, which we map
        # below. If even PRAGMA fails we still end up with a SchemaError.
        try:
            self._con.execute("PRAGMA query_only = ON")
        except sqlite3.DatabaseError as e:
            self._con.close()
            raise SchemaError(f"{self.path} is not a valid SQLite database: {e}") from e
        self._con.row_factory = sqlite3.Row

        try:
            self.root = _read_root_info(self._con)
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            self._con.close()
            raise SchemaError(
                f"could not read ConfigTable from {self.path}: {e}"
            ) from e

        if self.root.version < _MIN_SUPPORTED_VERSION:
            self._con.close()
            raise SchemaError(
                f"RootsMagic version {self.root.version} is below the "
                f"supported minimum ({_MIN_SUPPORTED_VERSION}). "
                f"This library targets RM 7+ schema."
            )

    @property
    def version(self) -> int:
        """RootsMagic version number (e.g. 11000 = RM 11)."""
        return self.root.version

    @property
    def con(self) -> sqlite3.Connection:
        """Underlying sqlite3 connection. Prefer dedicated query functions in
        :mod:`rmread.person` so SQL stays in one place."""
        return self._con

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "RMDatabase":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_database(path: str | Path) -> RMDatabase:
    """Open a RootsMagic file in read-only mode."""
    return RMDatabase(path)
