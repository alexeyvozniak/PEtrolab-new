# ADR 0011: Logical import blocks and orientation-normalized planning

**Status:** Accepted for Desktop v2 import work  
**Date:** 2026-08-31

## Context

The first Desktop import alpha treated one worksheet as one table and one physical row as one Analysis. Real PetroLab workbooks violate both assumptions: a sheet can contain several tables, repeated headers, long preambles, helper regions, transposed tables and multiple analytical methods.

Keeping these rules in React would violate the project boundary. Rewriting/transposing source files would violate source immutability and provenance.

## Decision

### 1. Logical block is the unit of import review

`Import Recipe.sections[]` represents logical source blocks rather than whole sheets. Multiple sections may reference one sheet.

Each section owns:

- stable `block_id`;
- `sheet_name`;
- enabled state;
- orientation;
- physical source boundaries;
- header position;
- logical data range;
- mappings;
- explicit unit/method context when present.

### 2. Python core owns block detection and normalization

Python inspection detects candidate blocks and serves bounded raw previews. React only edits explicit block/mapping decisions and renders projections.

Tauri remains a file/process boundary and does not parse workbook semantics.

### 3. Orientation is normalized in memory

For ordinary blocks, logical rows equal physical rows.

For transposed blocks, Python creates a logical transposed matrix in memory for validation/planning. The original workbook is never rewritten. Every logical cell retains a reference to its physical source row and column so provenance can be persisted.

### 4. Provenance becomes cell-address aware

Row number + source column name is insufficient for orientation-normalized planning. New import plans expose physical `source_row_number`, `source_column_index` and source header for every value. Persistence may keep legacy row fields for compatibility, but no new feature may rely on logical position as physical provenance.

### 5. Repeated headers are structure, not data

A row/column whose normalized header signature equals the active block header is skipped as structural content. Detection should normally split such content into multiple blocks, but planning has the same guard for manually widened ranges.

### 6. Units from source context are explicit evidence

A block-level unit can be auto-applied only if an inspected source cell states a recognized unit. The plan stores the evidence coordinate/text. A likely unit based only on instrument/file naming remains a suggestion requiring user confirmation.

`at.%` is distinct from `mol%`.

### 7. Measurement identity includes set/method context

New planning structures carry optional `measurement_set` and `method` labels in addition to `canonical_field`. This prevents same-named fields from different analytical groups from being collapsed in projections. Existing records without these labels remain valid.

## Consequences

- `import.inspect_source` remains lightweight; raw windows are fetched with a dedicated preview command.
- import recipe schema advances for block/orientation decisions while old recipe revisions remain immutable.
- tests generate anonymized synthetic workbooks that reproduce real layouts instead of committing user scientific data.
- native BIFF `.xls` parsing is not introduced by this ADR. `.xls` must be identified distinctly and reported honestly until a reviewed reader/conversion strategy is implemented.
- UI must not show Mineral/Generation as fully supported until persistence is lossless.

## Rejected alternatives

### One worksheet = one table
Rejected because it already fails on repeated headers, instrument preambles and multiple composition blocks.

### Transpose source files before import
Rejected because it mutates/creates a derived source representation that can obscure physical provenance and complicate reproducibility.

### Parse blocks in React
Rejected because import semantics belong to Python core and would become untestable/duplicated across UI states.

### Guess units by chemistry field
Rejected because the same field may be reported in different units and scientific rules require explicit units.