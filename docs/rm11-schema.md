# RM 11 SQLite schema

The exact column layout of every table in a RootsMagic 11
(`.rmtree`) SQLite database, as captured from the dev
`SampleTree.rmtree` (RM 11.0, 4.6 MB, 33 tables, 6,231 rows).
rmread's loaders are written against this schema; treat this as
the source of truth, not third-party RM documentation or
hypothesised `ID`/`Name`/`BlobData` columns.

## How this document is organised

1. [Header / version](#header--version) — `ConfigTable` root blob,
   the version integer convention.
2. [Core person / name / event tables](#core-person--name--event-tables)
   — the tables `rm-dump` reads.
3. [Family links](#family-links) — `FamilyTable`, `ChildTable`,
   parent-versus-co-parent semantics.
4. [Lookups and reference tables](#lookups-and-reference-tables)
   — `PlaceTable`, `FactTypeTable`, `RoleTable`, `TagTable`.
5. [Citation, source, multimedia, address, URL](#citation-source-multimedia-address-url)
   — the *Link* polymorphism contract.
6. [Auxiliary tables](#auxiliary-tables) — DNA, FAN, witnesses,
   tasks, health, exclusions, group, payload.
7. [Verified-in-this-DB caveats](#verified-in-this-db-caveats) —
   things this inspection caught that disagree with `rmread`'s
   current defaults.

## Header / version

### `ConfigTable`

One row per config record; `RecID` is the primary key, but the
**root row** (holding the database-level metadata) is identified
by the triple `RecID=1, RecType=1, Title=''`.

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `RecType` | INTEGER | record kind; `1` = root |
| `Title` | TEXT | `''` for the root row |
| `DataRec` | BLOB | XML payload (root row holds `<Root>…</Root>`) |
| `UTCModDate` | FLOAT | last-modified timestamp |

`SampleTree.rmtree` root blob: `Version=11000`, `STVersion=700`,
`UniqueID=<redacted — 34-char vault UUID>`, `RootPerson=1`,
blob size 16,781 bytes. rmread only parses a subset of the
keys (`Version`, `STVersion`, `UniqueID`, `RootPerson`,
`PreparerEmail`) — anything else in the root blob is preserved
bit-for-bit. The raw UUID is researcher-vault-identifying and
should not be quoted in commit artefacts; substitute it with
`SampleTree's` `<UniqueID>` element when citing the root blob.

`rmread.db._MIN_SUPPORTED_VERSION = 7000`; databases older than RM
7 are rejected.

## Core person / name / event tables

The three tables `rm-dump`, `rm-find` and the library loaders
read.

### `PersonTable`

| Column | Type | Notes |
|---|---|---|
| `PersonID` | INTEGER | PK |
| `UniqueID` | TEXT | RM's RM-UUID — survives import/export, distinct from `PersonID` |
| `Sex` | INTEGER | RM convention: **0 = unknown, 1 = male, 2 = female** |
| `ParentID`, `SpouseID` | INTEGER | denormalised pointers; do not rely on them, walk the family tables instead |
| `Color`, `Color1`…`Color9` | INTEGER | UI tint slots |
| `Relate1`, `Relate2` | INTEGER | relation-to-root flags |
| `Flags` | INTEGER | packed bitfield (RM-internal) |
| `Living` | INTEGER | 0/1 |
| `IsPrivate` | INTEGER | 0/1 |
| `Proof` | INTEGER | genealogical-proof flag |
| `Bookmark` | INTEGER | 0/1 |
| `Note` | TEXT | free-form |
| `UTCModDate` | FLOAT | |

Observed distribution in `SampleTree.rmtree`: `Sex=0` 206,
`Sex=1` 212, `Sex=2` 11 (the female-skew on a 429-person sample
is from imported spouses who never had descendants added).

### `NameTable`

A Person can have many rows here. `NameType=0` is the birth /
primary name and is what `find_by_surname` and `get_person` use.
Other values (1 = married, 2 = alias, 3 = immigrant, 4 = maiden,
etc.) are exposed by `load_alt_names` (newest-added types come
above the historical range — always look up via `NameType` int).

| Column | Type | Notes |
|---|---|---|
| `NameID` | INTEGER | PK |
| `OwnerID` | INTEGER | → `PersonTable.PersonID` |
| `Surname`, `Given`, `Prefix`, `Suffix`, `Nickname` | TEXT | all `COLLATE RMNOCASE` (case + diacritic fold) |
| `NameType` | INTEGER | `0` = birth/primary |
| `Date` | TEXT | RM raw date string (e.g. `"12 JUN 1840"`) |
| `SortDate` | BIGINT | sortable surrogate; `0` = unparsed |
| `IsPrimary` | INTEGER | 0/1; mirrors `NameType=0` in practice |
| `IsPrivate`, `Proof` | INTEGER | |
| `Sentence` | TEXT | RM's pre-rendered full-name string |
| `Note` | TEXT | |
| `BirthYear`, `DeathYear` | INTEGER | when known |
| `Display` | INTEGER | UI display flag |
| `Language` | TEXT | BCP-47-ish |
| `UTCModDate` | FLOAT | |
| `SurnameMP`, `GivenMP`, `NicknameMP` | TEXT | MP = "match-phraseable" forms used by RM's full-text index |

Indexes: `idxNameOwnerID`, `idxNamePrimary`, `idxSurname`,
`idxGiven`, `idxSurnameGiven`, plus MP twins.

`rmread` joins via `NameTable.OwnerID = PersonTable.PersonID AND
NameType = 0`. `SampleTree.rmtree`: all 438 names have
`NameType=0` (every person has exactly one primary row in this
tree).

### `EventTable`

The generic fact store. `EventType` is an integer key into
`FactTypeTable`. The same table holds events owned by Persons
(`OwnerType=0`), Families (`OwnerType=1`), and Sources
(`OwnerType=2`); `rmread` reads only `OwnerType=0`.

| Column | Type | Notes |
|---|---|---|
| `EventID` | INTEGER | PK |
| `EventType` | INTEGER | → `FactTypeTable.FactTypeID` |
| `OwnerType` | INTEGER | **`0` = Person, `1` = Family, `2` = Source** for Events |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` (`PersonID`, `FamilyID`, or `SourceID`) |
| `FamilyID` | INTEGER | optional, only when the event is attached to a family (e.g. marriage) |
| `PlaceID`, `SiteID` | INTEGER | → `PlaceTable.PlaceID` |
| `Date` | TEXT | raw RM date |
| `SortDate` | BIGINT | sortable surrogate; `0` = unparsed (events sink to the end of `load_events`) |
| `IsPrimary`, `IsPrivate`, `Proof` | INTEGER | |
| `Status` | INTEGER | RM-internal state |
| `Sentence` | TEXT | RM's pre-rendered fact sentence |
| `Details`, `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxOwnerEvent`, `idxOwnerDate`.

Observed distribution in `SampleTree.rmtree`: `OwnerType=0` 728,
`OwnerType=1` 142, `OwnerType=2` 0. **`FamilyID` was 0 in every
row of this sample** — even for Family-owned events. The `FamilyID`
column is informative rather than authoritative for the
family→events join in RM 11; the reliable walk is `OwnerType=1 AND
OwnerID=family_id`.

## Family links

### `FamilyTable`

One row per family / couple. The authoritative parent pointers
are `FatherID` and `MotherID`. `ChildID` is a denormalised
first-child stub; the real child linkage lives in `ChildTable`.

| Column | Type | Notes |
|---|---|---|
| `FamilyID` | INTEGER | PK |
| `FatherID`, `MotherID` | INTEGER | → `PersonTable.PersonID`; `0` = unknown / not recorded |
| `ChildID` | INTEGER | **denormalised first-child pointer — ignore**; use `ChildTable` |
| `HusbOrder`, `WifeOrder` | INTEGER | display order in RM UI |
| `IsPrivate`, `Proof` | INTEGER | |
| `SpouseLabel`, `FatherLabel`, `MotherLabel` | INTEGER | RM-internal label codes |
| `SpouseLabelStr`, `FatherLabelStr`, `MotherLabelStr` | TEXT | user-overridable label strings |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxFamilyFatherID`, `idxFamilyMotherID`.

### `ChildTable`

One row per `(child, family)` tuple. This is the authoritative
child→family link and the only place `rel_father` /
`rel_mother` (= RelFather / RelMother: `1` = biological /
adoptive, `0` = not, etc., RM-specific semantics) is stored.

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `ChildID` | INTEGER | → `PersonTable.PersonID` |
| `FamilyID` | INTEGER | → `FamilyTable.FamilyID` |
| `RelFather`, `RelMother` | INTEGER | relationship flags (`1` = biological in RM's convention) |
| `ChildOrder` | INTEGER | sibling position within the family; not birth order |
| `IsPrivate` | INTEGER | |
| `ProofFather`, `ProofMother` | INTEGER | |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxChildFamilyID`, `idxChildID`, `idxChildOrder`.

### Parents vs. co-parents — read correctly

`scaffolding-context.md` documents the trap; the trap is
specifically that `FamilyTable WHERE FatherID=? OR MotherID=?`
gives you the co-parents across every family the person
participated in, **which is not what genealogy calls
"parents"**. The right walk for a Person's parents is
`ChildTable → FamilyTable.FatherID/MotherID`. Adoption and
multiple marriages mean `load_parents` can return more than two
`ParentRef`s — expose them all and let callers disambiguate via
`family_id`.

## Lookups and reference tables

### `PlaceTable`

| Column | Type | Notes |
|---|---|---|
| `PlaceID` | INTEGER | PK |
| `PlaceType` | INTEGER | `0` = associated-with-records, `1` = master, etc. |
| `Name` | TEXT | display name, `COLLATE RMNOCASE` |
| `Abbrev` | TEXT | short form |
| `Normalized` | TEXT | canonical form RM uses for matching |
| `Latitude`, `Longitude` | INTEGER | stored as fixed-point |
| `LatLongExact` | INTEGER | 0/1 |
| `MasterID` | INTEGER | → other `PlaceTable.PlaceID` for the master record |
| `Note` | TEXT | |
| `Reverse` | TEXT | full name reversed for indexed text search, `COLLATE RMNOCASE` |
| `fsID`, `anID` | INTEGER | FamilySearch / Ancestry link ids |
| `UTCModDate` | FLOAT | |

Indexes: `idxPlaceName`, `idxReversePlaceName`, `idxPlaceAbbrev`.

`rmread.event._load_place_names` reads `PlaceTable.Name` for the
place ids a person's events actually reference (one batched query per
`load_events` call). It does not follow `MasterID`; if a research
workflow needs the master-canonical name, join through `MasterID`
yourself.

### `FactTypeTable`

| Column | Type | Notes |
|---|---|---|
| `FactTypeID` | INTEGER | PK; **this is the integer `EventType` keys against** |
| `OwnerType` | INTEGER | `0` = Person event, `1` = Family event — so the same ID space carries both kinds |
| `Name` | TEXT | human-readable (`COLLATE RMNOCASE`) |
| `Abbrev` | TEXT | |
| `GedcomTag` | TEXT | round-trips to GEDCOM |
| `UseValue`, `UseDate`, `UsePlace` | INTEGER | RM UI flags |
| `Sentence` | TEXT | RM's auto-sentence template |
| `Flags` | INTEGER | |
| `UTCModDate` | FLOAT | |

Indexes: `idxFactTypeName`, `idxFactTypeAbbrev`,
`idxFactTypeGedcomTag`.

#### Verified IDs for the names `rmread` cares about

Pulled from `SampleTree.rmtree` with
`SELECT FactTypeID, Name FROM FactTypeTable`:

| `Name` | `FactTypeID` | `GedcomTag` |
|---|---|---|
| Birth | `1` | `BIRT` |
| Death | `2` | `DEAT` |
| Christen | `3` | `CHR` |
| Burial | `4` | `BURI` |
| Cremation | `5` | `CREM` |
| Adoption | `6` | `ADOP` |
| Baptism | `7` | `BAPM` |
| Census | `18` | `CENS` |
| Census (family) | `311` | `CENS` |
| Occupation | `26` | `OCCU` |
| Probate | `19` | `PROB` |
| Will | `20` | `WILL` |
| Residence | `29` | `RESI` |
| Residence (family) | `310` | `RESI` |
| Marriage | `300` | `MARR` |
| Divorce | `302` | `DIV` |

The full set of 72 fact types and their `OwnerType` is in
`fact_types` of the introspection JSON.

> **See [Verified-in-this-DB caveats](#verified-in-this-db-caveats) — `rmread.event.DEFAULT_EVENT_TYPES` disagrees with several of these IDs.**

#### Fallback for unknown IDs

RM users add custom fact types without rows in `FactTypeTable`.
`rmread.event._fact_type_name` returns `f"Unknown({event_type})"` rather than raising. Keep this in the rendering layer,
not in the SQL filter, so SQL stays parameter-only. The names are
resolved against `_load_fact_type_names`' whole-table map — one query
per `load_events` call, not one per event row.

### `RoleTable`

Witness / role definitions.

| Column | Type | Notes |
|---|---|---|
| `RoleID` | INTEGER | PK |
| `RoleName` | TEXT | |
| `EventType` | INTEGER | → `FactTypeTable.FactTypeID`; the role applies to events of this type |
| `RoleType` | INTEGER | |
| `Sentence` | TEXT | display template |
| `UTCModDate` | FLOAT | |

Index: `idxRoleEventType`.

### `TagTable`

RM tags are addressed as `(TagType, TagValue)` — the type selects
the namespace, the value selects the row.

| Column | Type | Notes |
|---|---|---|
| `TagID` | INTEGER | PK |
| `TagType` | INTEGER | tag namespace selector |
| `TagValue` | INTEGER | tag value |
| `TagName` | TEXT | display label |
| `Description` | TEXT | |
| `UTCModDate` | FLOAT | |

Index: `idxTagType`.

## Citation, source, multimedia, address, URL

These all share a **link-table polymorphism** pattern: a primary
record table holds the actual entity, and a `*LinkTable`
associates it with the right owner through an `(OwnerType,
OwnerID)` pair. The integer values for `OwnerType` are **not
consistent across link tables** — they share an enum convention
with `EventTable.OwnerType` (0=Person, 1=Family, 2=Source) but
extend it. `SampleTree.rmtree` distributions are listed under
each table below.

### `CitationTable` + `CitationLinkTable`

`CitationTable` is the citation itself; `SourceTable` is the
parent source it cites. `CitationLinkTable` attaches the
citation to a person / family / source / event via
`(OwnerType, OwnerID)`.

`CitationTable`:

| Column | Type | Notes |
|---|---|---|
| `CitationID` | INTEGER | PK |
| `SourceID` | INTEGER | → `SourceTable.SourceID` |
| `Comments` | TEXT | |
| `ActualText` | TEXT | transcribed source text |
| `RefNumber` | TEXT | |
| `Footnote`, `ShortFootnote`, `Bibliography` | TEXT | rendered forms |
| `Fields` | BLOB | template-filled field values |
| `UTCModDate` | FLOAT | |
| `CitationName` | TEXT | `COLLATE RMNOCASE` — user-facing label |

Indexes: `idxCitationName`, `idxCitationSourceID`.

`CitationLinkTable`:

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `CitationID` | INTEGER | → `CitationTable.CitationID` |
| `OwnerType` | INTEGER | polymorphic discriminator (see below) |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` |
| `SortOrder` | INTEGER | |
| `Quality` | TEXT | evidence-quality tag |
| `IsPrivate`, `Flags` | INTEGER | |
| `UTCModDate` | FLOAT | |

Index: `idxCitationLinkOwnerID`.

`SampleTree.rmtree` distribution: `OwnerType=0` (Person) 17,
`1` (Family) 48, `2` (Source) 604, `7` 24, `19` 9. The 7 and 19
buckets appear to be RM-internal extensions; verify against
your own DB before hard-coding.

### `SourceTable`

The source itself (book, register, archive) that citations
refer to.

| Column | Type | Notes |
|---|---|---|
| `SourceID` | INTEGER | PK |
| `Name` | TEXT | user-facing title |
| `RefNumber` | TEXT | |
| `ActualText` | TEXT | |
| `Comments` | TEXT | |
| `IsPrivate` | INTEGER | 0/1 |
| `TemplateID` | INTEGER | → `SourceTemplateTable.TemplateID` |
| `Fields` | BLOB | template-filled field values |
| `UTCModDate` | FLOAT | |

Index: `idxSourceName`.

### `SourceTemplateTable`

| Column | Type | Notes |
|---|---|---|
| `TemplateID` | INTEGER | PK |
| `Name` | TEXT | |
| `Description` | TEXT | |
| `Favorite` | INTEGER | 0/1 |
| `Category` | TEXT | |
| `Footnote`, `ShortFootnote`, `Bibliography` | TEXT | |
| `FieldDefs` | BLOB | the template's field definitions |
| `UTCModDate` | FLOAT | |

Index: `idxSourceTemplateName`.

### `MultimediaTable` + `MediaLinkTable`

`MultimediaTable` is the media item (image, document, audio).
`MediaLinkTable` attaches it to a person / family / source /
event / place / citation via `(OwnerType, OwnerID)`. The link
table also stores crop coordinates for image regions.

`MultimediaTable`:

| Column | Type | Notes |
|---|---|---|
| `MediaID` | INTEGER | PK |
| `MediaType` | INTEGER | RM-internal kind code (1 = image, 2 = document, …) |
| `MediaPath` | TEXT | absolute or relative path on the originating machine |
| `MediaFile` | TEXT | filename, `COLLATE RMNOCASE` |
| `URL` | TEXT | web URL when present |
| `Thumbnail` | BLOB | embedded thumbnail |
| `Caption` | TEXT | |
| `RefNumber` | TEXT | |
| `Date` | TEXT | raw RM date |
| `SortDate` | BIGINT | |
| `Description` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxMediaFile`, `idxMediaURL`.

`MediaLinkTable`:

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `MediaID` | INTEGER | → `MultimediaTable.MediaID` |
| `OwnerType` | INTEGER | polymorphic discriminator |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` |
| `IsPrimary` | INTEGER | preferred image for that owner |
| `Include1`…`Include4` | INTEGER | RM-side include flags |
| `SortOrder` | INTEGER | |
| `RectLeft`, `RectTop`, `RectRight`, `RectBottom` | INTEGER | image region, normalised 0–1000 |
| `Comments` | TEXT | |
| `UTCModDate` | FLOAT | |

Index: `idxMediaOwnerID`.

`SampleTree.rmtree` distribution: `OwnerType=0` (Person) 3, `2`
(Source) 5, `3` 79, `4` 80. The 3 / 4 buckets likely mean
Citation / Event respectively — verify against your DB.

### `AddressTable` + `AddressLinkTable`

`AddressTable` holds postal / contact addresses (and the
researcher, business and repository addresses RM uses
internally).

`AddressTable`:

| Column | Type | Notes |
|---|---|---|
| `AddressID` | INTEGER | PK |
| `AddressType` | INTEGER | kind code (0 = unspecified, …) |
| `Name` | TEXT | label, `COLLATE RMNOCASE` |
| `Street1`, `Street2`, `City`, `State`, `Zip`, `Country` | TEXT | |
| `Phone1`, `Phone2`, `Fax`, `Email`, `URL` | TEXT | |
| `Latitude`, `Longitude` | INTEGER | fixed-point |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Index: `idxAddressName`.

`AddressLinkTable`:

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `OwnerType` | INTEGER | polymorphic discriminator |
| `AddressID` | INTEGER | → `AddressTable.AddressID` |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` |
| `AddressNum` | INTEGER | position in a multi-address owner |
| `Details` | TEXT | |
| `UTCModDate` | FLOAT | |

`SampleTree.rmtree` distribution: only `OwnerType=3` is present
(14 rows). Likely meaning — citation-or-event; verify against
your DB before depending on it.

### `URLTable`

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `OwnerType` | INTEGER | polymorphic discriminator |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` |
| `LinkType` | INTEGER | URL role (0 = generic, etc.) |
| `Name` | TEXT | label |
| `URL` | TEXT | |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

`SampleTree.rmtree`: 48 rows, all `LinkType=0`.

## Auxiliary tables

### `DNATable`

Genetic-link records (not raw DNA data, just relationship
metadata).

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `ID1`, `ID2` | INTEGER | the two `PersonID`s being compared |
| `Label1`, `Label2` | TEXT | |
| `DNAProvider` | INTEGER | 1 = Ancestry, 2 = FamilyTreeDNA, 3 = 23andMe, 4 = MyHeritage, … |
| `SharedCM`, `SharedPercent`, `LargeSeg` | FLOAT | shared-DNA statistics |
| `SharedSegs` | INTEGER | |
| `Date` | TEXT | |
| `Relate1`, `Relate2` | INTEGER | relationship-to-root flags |
| `CommonAnc` | INTEGER | common-ancestor `PersonID` when known |
| `CommonAncType` | INTEGER | |
| `Verified` | INTEGER | 0/1 |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxDnaId1`, `idxDnaId2`.

### `FANTable` + `FANTypeTable`

FAN = "Friends, Associates, Neighbours" — cluster-research links
between two people via a named association.

`FANTable`:

| Column | Type | Notes |
|---|---|---|
| `FanID` | INTEGER | PK |
| `ID1`, `ID2` | INTEGER | the two `PersonID`s |
| `FanTypeID` | INTEGER | → `FANTypeTable.FANTypeID` |
| `PlaceID`, `SiteID` | INTEGER | |
| `Date` | TEXT | |
| `SortDate` | BIGINT | |
| `Description`, `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Indexes: `idxFanId1`, `idxFanId2`.

`FANTypeTable`:

| Column | Type | Notes |
|---|---|---|
| `FANTypeID` | INTEGER | PK |
| `Name` | TEXT | `COLLATE RMNOCASE` |
| `Role1`, `Role2` | TEXT | role of each side of the link |
| `Sentence1`, `Sentence2` | TEXT | rendered forms |
| `UTCModDate` | FLOAT | |

Index: `idxFANTypeName`.

### `WitnessTable`

Witnesses to events (godsparents at a baptism, signatories to a
will, etc.).

| Column | Type | Notes |
|---|---|---|
| `WitnessID` | INTEGER | PK |
| `EventID` | INTEGER | → `EventTable.EventID` |
| `PersonID` | INTEGER | → `PersonTable.PersonID` |
| `WitnessOrder` | INTEGER | |
| `Role` | INTEGER | → `RoleTable.RoleID` |
| `Sentence` | TEXT | rendered |
| `Note` | TEXT | |
| `Given`, `Surname`, `Prefix`, `Suffix` | TEXT | denormalised name snapshot at the time the link was recorded |
| `UTCModDate` | FLOAT | |

Indexes: `idxWitnessEventID`, `idxWitnessPersonID`.

The denormalised name columns exist because RM stores the
witness's *name at the time of the event*, not just a pointer
back to a current `NameTable` row. Use them as a snapshot; for
the current Person record, join on `PersonID`.

### `TaskTable` + `TaskLinkTable`

RM's research-task tracker. Tasks can be linked to an owner (a
person, family, source, event, place, citation, …) via
`(OwnerType, OwnerID)`.

`TaskTable`:

| Column | | Notes |
|---|---|---|
| `TaskID` | INTEGER | PK |
| `TaskType` | INTEGER | kind code |
| `RefNumber` | TEXT | |
| `Name` | TEXT | |
| `Status` | INTEGER | 0 = open, 1 = done, … |
| `Priority` | INTEGER | |
| `Date1`, `Date2`, `Date3` | TEXT | up to three date fields |
| `SortDate1`, `SortDate2`, `SortDate3` | BIGINT | |
| `Filename` | TEXT | attached filename when the task has one |
| `Details`, `Results` | TEXT | |
| `UTCModDate` | FLOAT | |
| `Exclude` | INTEGER | RM-internal flag |

Index: `idxTaskName`.

`TaskLinkTable`:

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `TaskID` | INTEGER | → `TaskTable.TaskID` |
| `OwnerType` | INTEGER | polymorphic discriminator |
| `OwnerID` | INTEGER | meaning depends on `OwnerType` |
| `UTCModDate` | FLOAT | |

Index: `idxTaskOwnerID`.

### `ExclusionTable`

Records that explicitly mark two `PersonID`s as **not** the
same person (against accidental auto-merge).

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `ExclusionType` | INTEGER | |
| `ID1`, `ID2` | INTEGER | the two `PersonID`s |
| `UTCModDate` | FLOAT | |

Index: `idxExclusionIndex`.

### `HealthTable`

Per-person health / cause-of-death notes.

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `OwnerID` | INTEGER | → `PersonTable.PersonID` |
| `Condition` | INTEGER | controlled-vocabulary code |
| `SubCondition` | TEXT | free-text sub-tag |
| `Date` | FLOAT | stored as float in this table (different from other `Date TEXT` columns) |
| `Note` | TEXT | |
| `UTCModDate` | FLOAT | |

Index: `idxHealthOwnerId`.

### `GroupTable`

Pre-RM-4 grouping: one row per `(GroupID, StartID, EndID)`
range of records (used to fold a sequenced collection of
`PersonID`s into a single displayed group).

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `GroupID` | INTEGER | |
| `StartID` | INTEGER | first `PersonID` in the range |
| `EndID` | INTEGER | last `PersonID` in the range |
| `UTCModDate` | FLOAT | |

### `PayloadTable`

Generic BLOB storage for records that don't warrant a dedicated
table. `rmread` does not read this.

| Column | Type | Notes |
|---|---|---|
| `RecID` | INTEGER | PK |
| `RecType` | INTEGER | the "logical table" of the payload |
| `OwnerType` | INTEGER | polymorphic |
| `OwnerID` | INTEGER | |
| `Title` | TEXT | |
| `DataRec` | BLOB | |
| `UTCModDate` | FLOAT | |

Index: `idxPayloadType`.

### `AncestryTable` + `FamilySearchTable`

Sync-link records to the two cloud-tree providers. Both are
structurally identical: one row per (RM-side record → provider
record) link, with sync status and timestamps.

| Column | Type | Notes |
|---|---|---|
| `LinkID` | INTEGER | PK |
| `LinkType` | INTEGER | 0 = person, 1 = family, … |
| `rmID` | INTEGER | the RM `PersonID` / `FamilyID` / `SourceID` / etc. |
| provider-id | TEXT | `anID` (Ancestry) / `fsID` (FamilySearch) |
| `Modified` | INTEGER | 0/1 — needs-sync flag |
| version | TEXT | provider-protocol version |
| date | FLOAT | last sync (`anDate` or `fsDate`) |
| `Status` | INTEGER | provider-specific |
| `UTCModDate` | FLOAT | |
| `TreeID` | TEXT | the provider tree id |

Ancestry: `idxLinkAncestryRmId`, `idxLinkAncestryanID`.
FamilySearch: `idxLinkRmId`, `idxLinkfsID`.

## Conventions every `*LinkTable` shares

When you write a query against a `*LinkTable`:

1. Always filter on `OwnerType` first. A `PersonID` may also
   appear as `OwnerID` for the same `LinkType` in another
   `OwnerType` bucket — `WHERE OwnerID=?` alone over-joins.
2. Don't assume `OwnerType=0/1/2` is the whole enum. The
   distributions in `SampleTree.rmtree` show `OwnerType=3`,
   `4`, `7`, `19` in the wild. The values depend on the link
   table — see per-table notes above.
3. Use `idx*OwnerID` indexes (`idxCitationLinkOwnerID`,
   `idxMediaOwnerID`, `idxTaskOwnerID`) when you join on
   `(OwnerType, OwnerID)`.

## The `RMNOCASE` collation

RM's TEXT columns frequently declare
`COLLATE RMNOCASE` — a case-fold + Unicode-diacritic-strip
collation RM registers at open time. Python's sqlite3 doesn't
ship it. An adapter that opens the file in Python and runs
`COUNT(*) FROM AddressTable` (which has `Name TEXT COLLATE
RMNOCASE` on `Name` and is therefore a fully-collated table)
will hit `OperationalError: no such collation sequence:
RMNOCASE` at first use.

Re-register the collation before querying, e.g.:

```python
import sqlite3, unicodedata

def rmnocase(s, _name=None):
    if s is None: return None
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()

con = sqlite3.connect("file:Tree.rmtree?mode=ro", uri=True)
con.create_collation("RMNOCASE", rmnocase)
con.execute("PRAGMA query_only = ON")
```

Without that, **even read-only queries fail** — a real
showstopper for any future code path that opens via raw sqlite3
rather than through `rmread.db.RMDatabase`.

## Verified-in-this-DB caveats

Things the SampleTree.rmtree inspection caught:

1. **`rmread.event.DEFAULT_EVENT_TYPES` uses the wrong IDs.**
   `src/rmread/event.py` ships:
   ```python
   DEFAULT_EVENT_TYPES = (
       1,    # Birth         ← ok
       2,    # Death         ← ok
       3,    # Burial        ← wrong: this is Christen. Real Burial is 4
       8,    # Christening   ← wrong: this is Bar Mitzvah. Real Christening is 3
       9,    # Baptism       ← wrong: this is Bas Mitzvah. Real Baptism is 7
       10,   # Cremation     ← wrong: this is Blessing. Real Cremation is 5
       17,   # Occupation    ← wrong: this is Immigration. Real Occupation is 26
       22,   # Census        ← wrong: this is Retirement. Real Census is 18
       25,   # Probate       ← wrong: this is Nationality. Real Probate is 19
       27,   # Will          ← wrong: this is Property. Real Will is 20
       33,   # Residence     ← wrong: this is LDS Seal-to-parents. Real Residence is 29
   )
   ```
   The IDs used are off — by RM's numbering these are mostly
   fact types unrelated to civil genealogy. Default
   `load_events(pid)` against a real RM 11 DB therefore matches
   the wrong fact rows and surfaces events as e.g. "Bar Mitzvah"
   for what `rm-dump` claims to be "Christening". The fix:
   change the tuple to `(1, 2, 4, 3, 7, 5, 26, 18, 19, 20, 29)`
   and the inline comments.

   The fact-type *names* the loader outputs (looked up via
   `FactTypeTable`) are correct — it's the **filter** that
   picks the wrong rows.

2. **`CitationTable.CitationName` uses `RMNOCASE`**, which
   python's sqlite3 doesn't register. `rmread` doesn't currently
   read this column, so it's invisible until any code does.

3. **RMNOCASE propagates unexpectedly.** A vanilla
   `COUNT(*) FROM AddressTable` through Python's sqlite3
   triggers the `no such collation sequence` error. See
   [The `RMNOCASE` collation](#the-rmnocase-collation).

4. **`EventTable.FamilyID` was 0 in every row of this
   870-event sample.** Even for `OwnerType=1` (family-owned)
   events. Authoritative family-events join is
   `WHERE OwnerType=1 AND OwnerID=family_id`.

5. **No `OwnerType=2` rows in EventTable for this sample.**
   Source-attached events exist in the schema (`OwnerType=2` is
   documented) — this just means `SampleTree.rmtree` has no
   source-attached events. The column supports them.

## Source

Captured against the dev `SampleTree.rmtree` (RM 11.0,
SQLite 3.x, 4.6 MB, 33 tables, 6,231 rows). Regenerate the
column lists and fact-type table by running
`PRAGMA table_info(<table>)` and
`SELECT * FROM FactTypeTable` against any real `.rmtree` —
column names and fact-type IDs are stable across RM 7→11.

The full introspection (per-table JSON column lists, all
indexes, the entire 72-row `FactTypeTable`) is also persisted
in the in-repo artefact `tests/_schema.py` for the synthetic
fixture used by the test suite.
