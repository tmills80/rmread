# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

## What this is

`rmread` is the read-only RootsMagic reader: a Python library plus two
CLI commands (`rm-find`, `rm-dump`) that read `.rmtree` SQLite
databases without modifying them. Standard library only.

`AGENTS.md` is the authority on house style; this file records the
architecture and the commands. Read `AGENTS.md` before changing
anything — it is short and it binds.

## Commands

`uv` drives everything.

```sh
uv sync --all-extras      # setup
uv run pytest tests/ -q   # run (127 tests)
```

`SampleTree.rmtree` (RM 11, 4.6 MB) sits at the repository root and is
gitignored. Tests needing it **skip** rather than fail when it is
absent; point `RM_SAMPLE_TREE` at another file to override the
auto-detection.

CLIs: `uv run rm-find --help`, `uv run rm-dump --help`.

## Consumers

`rm2gramps` is a **separate repository** and a hard runtime consumer: it
imports `rmread.open_database`, `rmread.linktables`, and
`rmread.rmtext`. `rm2gramps` resolves this package from a sibling
checkout via `[tool.uv.sources]` because `rmread` is not on PyPI.

Changes to `rmread`'s public surface — `__init__.py`'s `__all__`,
`linktables`, `rmtext`, the `open_database` signature — are a
cross-repository contract. `linktables` is not in `__all__` but is
imported directly downstream; treat it as public.

## Architecture

Standard library only — `sqlite3`, `dataclasses`, `argparse`.

- `db.py` — opens a `.rmtree` as SQLite with three independent read-only
  layers (URI `mode=ro`, `PRAGMA query_only`, `sqlite3.DatabaseError` →
  `SchemaError` translation). Schema validation is **not** a table check:
  it parses the `ConfigTable` root blob (`RecID=1, RecType=1, Title=''`)
  and reads `Version`/`STVersion`/`RootPerson` out of its XML. RM < 7 is
  rejected. Every failure funnels into `SchemaError` — never a bare
  `ValueError`.
- Registers a Python `RMNOCASE` collation (NFKD → strip combining marks
  → `casefold`). RM declares many TEXT columns `COLLATE RMNOCASE`;
  Python's `sqlite3` does not ship it, so even a read-only `SELECT` dies
  without it.
- `linktables.py` — the `*LinkTable` walkers. **One global OwnerType enum
  shared by all three tables**: `0=Person 1=Family 2=Event 3=Source
  4=Citation`. It was derived by cardinality disambiguation against a
  real database, not guessed. Unknown OwnerTypes (7, 19 occur in the
  wild) are dropped with one warning, never fatal.
  `walk_citation_links` deliberately does **not** dedupe repeated
  `(owner, citation)` rows.
- `rmtext.py` — the RootsMagic markup dialect, shared with `rm2gramps`
  and `rmcite`. `tokenize()` returns text/style/link/break/tag chunks;
  unknown tags come back with their **exact source text** and entities
  are never decoded (RM stores note text raw). `plain_text()` resolves to
  text plus half-open `[start, end)` style ranges, and normalises
  CRLF→LF **before** measuring offsets — XML parsers normalise line
  endings, so offsets computed on raw text would be wrong after the
  first line break.
- `format.py` — `to_json` (rm-find), `dump_payload` (rm-dump, returns a
  dict so consumers compare shapes without parsing), `to_text` (rm-find
  table). The rm-dump *text* renderer lives in the CLI, not here.

Two traps in this package that are easy to reintroduce:

- **Parents vs co-parents.** `load_parents` walks `ChildTable →
  FamilyTable.FatherID/MotherID`, never `FamilyTable WHERE FatherID=? OR
  MotherID=?` (which returns co-parents from every family the person
  touched). It can legitimately return more than two parents; disambiguate
  by `family_id`.
- **Fact-type IDs.** `DEFAULT_EVENT_TYPES` was historically wrong (the
  *names* were right, the SQL filter was not). Take IDs from
  `SELECT FactTypeID, Name FROM FactTypeTable` against a real `.rmtree`,
  never from memory or a comment. `tests/test_event_default_ids.py` pins
  it.

## Evidence and privacy rules

These are not stylistic; the repo's outputs are meant to be cited.

- **Name the copy.** Before analysing an England & Wales vital record
  (registered after 1 July 1837) you must know whether you hold the
  local register copy, the GRO register copy, or a certified copy
  certificate. Handwriting and informant-signature analysis is only
  meaningful on the local register copy. Scripts touching vital records
  take a `--copy-type` flag; the default is *unknown* and must **refuse**
  to run record-graphy tests rather than silently pass. The output header
  states the copy type it ran against.
- **Cite inline, never as a trailing footnote.** Minimum shape:
  `Staines, Thomas, b. 1840 Q4, Aston. [GRO index, vol. XVI, p. 211]`. A
  claim with no citation is a draft, not a finding.
- **GEDCOM is a hypothesis, not kinship.** Authoritative on what it
  claims to exist; suspect on what it implies. Never infer kinship from
  a shared surname or shared parish.
- **Provenance over polish.** The source line goes next to the claim so
  another researcher can check it without going through you.
- **Never commit** records of anyone born after 1906 whose death is not
  registered, full dates for living people, or anything under a
  `RESEARCHER_PRIVATE.md` flag. Hash identifiers before writing; never
  log raw names.

Full rules: `references/evidence-discipline.md`.

## Synthetic-data conventions

Genealogy fixtures leak real names by accident. A plausible-looking
placeholder (`Zoe PlaceholderSurnameThree`) is mistakable in a research
note at 1am. The convention:

| Field | Convention | Example |
|---|---|---|
| Surname | six-or-more identical letters | `AAAAAA`, `O'CCCC` |
| Given name | recognisable placeholder | `Zoe`, `Wren`, `Xerxes` |
| Place | tagged fake | `FFakePlace-1`, `Fakeland` |
| Unique ID | `fp-` / `FAKE-UUID-` prefix | `fp-1` |
| Email | `.invalid` TLD | `test@example.invalid` |
| Phone | ITU reserved range | `+1 555-0100` |

If a test only needs a name, use the placeholder surname alone — skip
the plausible given name.

## Where the facts live

- `README.org` — current CLI docs.
- `DEVELOPMENT.org` — working notes.
- `docs/rm11-schema.md` — RM column names, fact-type IDs, link-table
  semantics. The single source for the schema, and cited from `db.py`
  and `linktables.py` as well as from the sibling `rm2gramps` repository.
- `docs/scaffolding-context.md` — per-tool house conventions
  (read-only belt-and-braces, fake-data naming, the fake-data
  override).
- `references/evidence-discipline.md` — the sourcing rules.
