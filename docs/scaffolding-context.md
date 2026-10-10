# Scaffolding context — rmread

How the general `scaffolding-codebases` skill applies when scaffolding
**genealogy-domain** tools in this repository. Read that skill first
for layout, naming, and the approval-gate rule; this file documents
the *extra* conventions and lessons specific to rmread.

## Synthetic-data conventions

Genealogy test fixtures can leak real people's names into citations,
research notes, or screenshots by mistake. The general rule
("obviously fake") is not strong enough here — `Zoe PlaceholderSurnameThree` is
plausible enough to be quoted in a research note by a tired
researcher at 1am.

The conventions used in this project's fixtures:

| Field | Convention | Example |
|---|---|---|
| Surname | Six-of-a-letter | `AAAAAA`, `BBBBBB`, `O'CCCC` |
| Given name | Recognisable placeholder, not a real-sounding name | `Zoe`, `Yara`, `Xerxes`, `Wren` |
| Place | Tagged fake | `FFakePlace-1`, `Fakeland` |
| Unique ID | `fp-` prefix on UUID | `fp-1`, `fp-uuid-...` |
| Email | `example.invalid` | `test@example.invalid` |
| UUID pattern | `FAKE-UUID-DEADBEEF` | |
| Phone | Reserved ITU range | `+1 555-0100` |

**Why this combination:** a reader scanning `AAAAAA / Xerxes /
FFakePlace-1 / fp-1` cannot mistake it for a research-grade record of
any real person. `Zoe / Wren / PlaceholderSurnameTwo / PlaceholderPlace` *is* mistakable.

If a test only needs a name (no demographic specificity), the
placeholder surname alone is enough — skip the plausible-sounding
given name entirely.

For real-data testing the user must explicitly consent; create
`tests/fixtures/` and document the source. Default is synthetic.

## RootsMagic SQLite column recon

Before any code that touches `*.rmtree` runs in production, the column
names of every table the adapter reads must be verified against a real
RM database. The documented schema uses generic names (`ID`, `Name`,
`BlobData`) — **the real RM 11.0 schema does not.** Verified against
the dev `SampleTree.rmtree`:

- `ConfigTable` columns are `RecID`, `RecType`, `Title`, `DataRec`, `UTCModDate`.
  Root row: `RecID=1, RecType=1, Title=''`. Do not guess generic names.
- `EventTable.OwnerType` selects the owner: `0` = Person, `1` = Family,
  `2` = Source.
- Integer codes like `EventType=1` map to names via `FactTypeTable`;
  unknown codes are normal (user-added custom facts). Fall back to
  `"Unknown(<int>)"` rather than crashing.

## Read-only SQLite belt-and-braces

Opening a `.rmtree` file for reading uses three layers, any one of
which is sufficient:

1. SQLite URI with `mode=ro`.
2. `PRAGMA query_only = ON` after opening — refuses writes even if the
   URI flag is dropped.
3. `try/except sqlite3.DatabaseError` around the `connect()` call —
   a non-SQLite file opens cleanly but raises on the first query, and
   that error must be translated to the same exception class
   (`SchemaError`) so callers do not see raw `sqlite3` errors.

The third matters because tests for "garbage file" and "real database"
share the same code path — only the translation differs.

## `*.rmtree` gitignore

`.gitignore` excludes `*.rmtree` and `*.rmgc` at the repo root. Real
RootsMagic databases contain living-people records and are never
committed. The library's tests run against synthetic in-memory SQLite;
no real file should be opened from CI.

## Parents vs co-parents

`load_parents(pid)` in `tools/rmread/src/rmread/family.py` returns the
person's *parents*, not the partners-in-couple-of. The wrong
implementation (which we shipped and caught in tests) was
`FamilyTable WHERE FatherID = ? OR MotherID = ?` — this returns the
co-parents across every family the person participated in, which is
not what *parents* means in genealogy.

The correct walk is `ChildTable → FamilyTable.FatherID/MotherID`,
returning the FatherID/MotherID of every family where `person_id` is
a `ChildID`. Multiple parent families (adoption, multiple marriages)
return more than two ParentRefs; we expose them all and let callers
disambiguate using the `family_id`.
