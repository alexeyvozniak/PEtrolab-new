# Import Review v2

**Status:** approved direction from real-file testing, 2026-08-31  
**Scope:** Desktop v2 analytical import only

## Why this replaces the current alpha flow

Real PetroLab workbooks are not one uniform table. They include long instrument preambles, repeated headers, several logical tables on one sheet, wide literature compilations, mixed methods, transposed layouts, block-level units, helper sheets and embedded media. The import UI therefore reviews **logical blocks**, not just worksheets and columns.

The user must not act as a manual QA parser. The default path should require only confirmation of ambiguous decisions.

## Primary path

`Choose file -> PetroLab detects candidate blocks -> review raw preview -> enable/disable blocks -> confirm orientation/header/range -> confirm mappings and units -> review resulting Analyses/Measurements -> Save`

A file can contain zero, one or many logical blocks per sheet. Each block is reviewed independently.

## Block card

Every detected block is shown as one compact card containing:

- sheet name and block label;
- enabled/disabled switch;
- orientation: `Analyses in rows` or `Analyses in columns`;
- physical source range and detected header position;
- data start/end;
- explicit unit context found in the source, with provenance of the source cell/row;
- 4–8 raw source rows/columns around the block;
- counts of proposed Analysis and Measurement records;
- warnings that apply only to that block.

The preview always shows source values, not normalized values.

## Automatic decisions allowed

PetroLab may automatically apply a decision only when the source states it unambiguously or the structure is deterministic.

Examples:

- `All results in weight%`, `wt.%`, `ppm`, `ppb`, `at.%` can supply a block/column unit;
- a repeated header row with the exact same normalized header signature is not an Analysis row;
- a sheet that is an exact subset of another imported block is flagged as a duplicate candidate;
- obvious chemistry headers may be proposed as Measurement fields;
- `Sample`, `Point`, `Analysis`, `Mineral`, `Generation` headers may be proposed to their corresponding roles.

PetroLab must not silently infer scientific meaning from position, colour, filename, sheet name or numeric magnitude.

## Manual review behaviour

- Mapping edits are staged locally in the UI and committed with one `Apply mapping` action.
- A common unit can be applied to all Measurement candidates in a block in one action.
- The user can select multiple columns/rows and assign one role in bulk.
- Saving is disabled while draft mapping changes remain unapplied.
- Saving is disabled if enabled blocks would create Analysis records without Measurements, unless the block is explicitly marked metadata-only by a future approved workflow.
- The user can disable a helper/calculation sheet or one of several blocks without disabling the entire workbook.

## Repeated and multiple tables

- Each repeated header starts a new candidate block.
- The candidate block ends before the next detected header or at the explicit user-defined boundary.
- Exact repeated headers are skipped from data even if they occur inside a manually widened range.
- Same-schema adjacent blocks can be reviewed together, but provenance retains the original block and source coordinates.

## Transposed tables

Orientation is a block property, not a workbook property.

For `Analyses in columns`, PetroLab creates a logical transposed view for planning while preserving physical source coordinates. No rewritten/transposed source file is created.

The raw preview must show both physical orientation and the normalized logical preview so the user can see what will become one Analysis.

## Units

Supported source units for this slice include at minimum:

- `wt.%` / mass %;
- `at.%` / atomic %;
- `ppm`;
- `ppb`;
- `apfu`;
- `mol%`;
- `ratio` / dimensionless.

`at.%` and `mol%` are distinct and must never be substituted for each other.

If a unit is not stated in the source, PetroLab can suggest a likely field but must require confirmation of the unit before saving.

## Method and duplicate field names

A Measurement is not identified only by `canonical_field`. The import plan must preserve a measurement-set/method context so two fields named `SiO2` from different analytical groups do not collide.

The UI may initially show this as a short group label such as `EPMA`, `SIMS`, `WDS`, `EDS`, `LA-ICP-MS`, or a user-defined set. The stored source header and physical cell coordinates remain authoritative provenance.

## Imported identities and metadata

The import review must expose roles for:

- Analysis identifier;
- Sample;
- Point;
- Mineral;
- Generation;
- Measurement;
- Metadata / note;
- Ignore.

These roles must persist without being faked as display-only identity strings. Until a role has a lossless persistence path, it must not be presented as fully supported.

## Safety and rollback

- Source files remain immutable.
- The final review shows total enabled blocks, Analysis count, Measurement count, unresolved warnings and duplicate candidates.
- The most recent accidental import can be retracted from the active project without deleting provenance/history.
- No automatic duplicate removal occurs.

## Real-world regression gate

Before the next user-facing import build, CI must cover anonymized/synthetic versions of the real patterns recorded in issue #8:

- narrow isotope table with unfamiliar headers;
- long preamble + explicit block unit;
- repeated same-schema headers;
- multiple blocks per sheet;
- wide literature compilation;
- mixed EPMA + SIMS with duplicate canonical names;
- ordinary and transposed orientation;
- exact subset sheet duplicate;
- old `.xls` detection and explicit unsupported/converted path until native support is implemented;
- Cyrillic paths and repeated file opening on Windows.

The original scientific workbooks are not committed to the public repository.