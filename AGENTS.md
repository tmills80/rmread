# AGENTS.md — rmread

## What this is

**rmread** is the read-only RootsMagic reader: a Python library plus two
CLI commands (`rm-find`, `rm-dump`) that read `.rmtree` SQLite
databases without modifying them. Standard library only.

This repository used to live inside the `genealogy_tools` workspace, at
`tools/rmread/`. It now stands alone. The house style below is
inherited from that workspace and is unchanged; only the *Layout* and
the *Sibling repository* sections are specific to this project.

Everything here should be **evidence-grade** — the kind of code that
gets cited in a research note, run against real records, and audited
later when a conclusion is challenged.

Optimise for: **correctness, traceability, reproducibility of evidence,
and clean hand-off to other researchers**. Optimise against: clever
abstractions, clever frameworks, "scale," premature packaging.

## Sibling repository

`rm2gramps` is a **separate repository** and a downstream consumer: it
imports `rmread.open_database`, `rmread.linktables`, and
`rmread.rmtext` at runtime.

`docs/rm11-schema.md` in this repository is the **single source of
truth** for RM 11 column names, FactType IDs, and link-table
semantics. Do not copy parts of it into another repository; link to it.

The two are expected to sit side by side:

```
~/projects/
├── rmread/       ← this repository
└── rm2gramps/
```

`rmread` is not on PyPI, so `rm2gramps` resolves it through a
`[tool.uv.sources]` path dependency in its own `pyproject.toml`.

## House style

- **Plain Python 3.12+**, standard library first. Reach for a
  third-party package only when the standard library genuinely cannot do
  the job.
- **One script per concern.** Don't build a framework until four scripts
  need the same code — then factor it, not before.
- **Files are evidence.** Every output that names a person, date, or
  place must carry a source citation (archive, series, volume,
  folio/image, reference) next to the claim, not as a footnote. See
  [`references/evidence-discipline.md`](references/evidence-discipline.md)
  for what that means in practice.
- **No silent failure.** If a script produces no result, say so. If it
  picks between multiple plausible interpretations, surface them —
  never paper over.

## Conventions for code

- Type hints on public function signatures. Narrow types beat broad
  ones.
- Functions take **paths and parameters explicitly**; no implicit
  globals, no hidden state.
- CLI entry points use `argparse` with `--help` that documents every
  flag.
- Errors raise with context. `raise ValueError(f"line {lineno}: …")`,
  not bare `raise ValueError`.
- Tests live next to the code they test, named `test_*.py`.

## Conventions for evidence handling

For anything that touches a record, read the evidence-discipline
reference and follow it. The short version:

1. **Name the copy** (local register / GRO register / certified
   certificate).
2. **Cite inline**, not at the end.
3. **Treat GEDCOM as hypothesis**, not kinship.
4. **Provenance over polish** — the source line goes next to the claim.

Full rules: [`references/evidence-discipline.md`](references/evidence-discipline.md).

## Don't

- Don't add a `requirements.txt` for a one-file script.
- Don't reach for pandas / numpy / a database to join two CSV-shaped
  lists.
- Don't write a class when a function with module-level constants will
  do.
- Don't commit raw personal data, living-people records, or anything
  under UK GDPR / PIPL constraints. Anonymise or hash before committing.
- Don't rewrite history — `git rebase` is fine locally, but the public
  branch is append-only.

## Architecture

Standard library only — `sqlite3`, `dataclasses`, `argparse`.

- `db.py` — opens a `.rmtree` as SQLite with three independent
  read-only layers (URI `mode=ro`, `PRAGMA query_only`,
  `sqlite3.DatabaseError` → `SchemaError` translation). Schema
  validation is **not** a table check: it parses the `ConfigTable`
  root blob (`RecID=1, RecType=1, Title=''`) and reads
  `Version`/`STVersion`/`RootPerson` out of its XML. RM < 7 is
  rejected. Every failure funnels into `SchemaError` — never a bare
  `ValueError`.
- Registers a Python `RMNOCASE` collation (NFKD → strip combining
  marks → `casefold`). RM declares many TEXT columns `COLLATE
  RMNOCASE`; Python's `sqlite3` does not ship it, so even a read-only
  `SELECT` dies without it.
- `linktables.py` — the `*LinkTable` walkers. **One global OwnerType
  enum shared by all three tables**: `0=Person 1=Family 2=Event 3=Source
  4=Citation`. It was derived by cardinality disambiguation against a
  real database, not guessed. Unknown OwnerTypes (7, 19 occur in the
  wild) are dropped with one warning, never fatal.
  `walk_citation_links` deliberately does **not** dedupe repeated
  `(owner, citation)` rows.
- `rmtext.py` — the RootsMagic markup dialect, shared with `rm2gramps`
  and `rmcite`. `tokenize()` returns text/style/link/break/tag chunks;
  unknown tags come back with their **exact source text** and entities
  are never decoded (RM stores note text raw). `plain_text()` resolves
  to text plus half-open `[start, end)` style ranges, and normalises
  CRLF→LF **before** measuring offsets — XML parsers normalise line
  endings, so offsets computed on raw text would be wrong after the
  first line break.
- `format.py` — `to_json` (rm-find), `dump_payload` (rm-dump, returns a
  dict so consumers compare shapes without parsing), `to_text` (rm-find
  table). The rm-dump *text* renderer lives in the CLI, not here.

### Two traps that are easy to reintroduce

- **Parents vs co-parents.** `load_parents` walks `ChildTable →
  FamilyTable.FatherID/MotherID`, never `FamilyTable WHERE FatherID=? OR
  MotherID=?` (which returns co-parents from every family the person
  touched). It can legitimately return more than two parents;
  disambiguate by `family_id`.
- **Fact-type IDs.** `DEFAULT_EVENT_TYPES` was historically wrong (the
  *names* were right, the SQL filter was not). Take IDs from `SELECT
  FactTypeID, Name FROM FactTypeTable` against a real `.rmtree`, never
  from memory or a comment. `tests/test_event_default_ids.py` pins it.

## Layout

```
AGENTS.md                                  ← you are here
CLAUDE.md                                  ← Claude Code entry point
LICENSE                                    ← MIT
README.org                                 ← user-facing notes
DEVELOPMENT.org                            ← working notes
pyproject.toml                             ← package metadata
uv.lock                                    ← pinned resolution
references/evidence-discipline.md           ← sourcing rules
docs/rm11-schema.md                        ← the RM 11 schema reference
docs/scaffolding-context.md                ← project-local guidance
src/rmread/                                ← library code on src-layout
src/rmread/cli/                            ← CLI entry points
tests/                                     ← tests next to the code
```

`docs/rm11-schema.md` is load-bearing: it is cited from `db.py` and
`linktables.py`, and from the sibling `rm2gramps` repository. Keep it
current.

Real research data (`.rmtree` databases) lives outside the repository and
is gitignored.

## When you are unsure

Ask. One short question beats guessing and rewriting.
