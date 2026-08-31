# ADR 0012: Logical import blocks and orientation-normalized planning

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

### 2. Python core owns block detection and bounded raw-source windows

Python inspection detects candidate blocks and serves bounded raw previews. React only edits explicit block/mapping decisions and renders projections.

A raw preview window is a view onto the full physical worksheet used range. It is not part of the recipe and has no semantic effect. Desktop may request another window at any row at any time, including while block-boundary edits are still only a local draft. This lets the UI page/jump/recentre without applying a recipe revision.

The service returns physical row numbers, column labels and used-range bounds. React never loads the entire large workbook merely to make a scrollable preview; it requests bounded windows lazily. Navigation state therefore belongs to presentation state, while workbook parsing remains Python-owned.

Tauri remains a file/process boundary and does not parse workbook semantics.

### 3. Orientation suggestion is conservative and reviewable

For every detected logical block, Python may evaluate whether its field labels form a stronger column-oriented pattern than a row-oriented one.

A transposed suggestion is allowed only when source structure provides positive evidence, including several recognized field labels down one physical column and multiple populated Analysis labels across the block header row. File names, sheet names and instrument names are not evidence.

When this threshold is met, the suggested recipe may start with `orientation = columns_are_analyses`, but it must also emit `TRANSPOSED_TABLE_LIKELY`. The Desktop review shows that orientation explicitly and permits a user to switch back before save. Weak or ambiguous cases remain `rows_are_analyses`.

This is a semantic suggestion only. The source workbook is never rewritten or physically transposed.

### 4. Orientation is normalized in memory

For ordinary blocks, logical rows equal physical rows.

For transposed blocks, Python creates a logical transposed view in memory for validation/planning. Every logical cell retains a reference to its physical source row and column so provenance can be persisted.

### 5. Provenance becomes cell-address aware

Row number + source column name is insufficient for orientation-normalized planning. New import plans expose physical `source_row_number`, `source_column_index` and source header for every value. Persistence may keep legacy row fields for compatibility, but no new feature may rely on logical position as physical provenance.

### 6. Repeated headers and instrument preambles are structure, not data

A row/column whose normalized header signature equals the active block header is skipped as structural content. Detection should normally split such content into multiple blocks, but planning has the same guard for manually widened ranges.

Instrument/service preambles (for example `Sample: ...`, `Type: ...`, `Processing option: ...`, standalone unit-context rows) do not become logical analytical blocks merely because they contain a known keyword. A candidate header must have multi-field header evidence and data-like rows beneath it. Preamble rows may still provide explicit context (such as units) to the actual analytical block that follows.

### 7. Units from source context are explicit evidence

A block-level unit can be auto-applied only if an inspected source cell states a recognized unit outside a mixed per-column header row. The plan stores the evidence coordinate/text. A likely unit based only on instrument/file naming remains a suggestion requiring user confirmation.

`at.%` is distinct from `mol%`.

### 8. Measurement identity includes set/method context

New planning structures carry optional `measurement_set` and `method` labels in addition to `canonical_field`. This prevents same-named fields from different analytical groups from being collapsed in projections. Existing records without these labels remain valid.

### 9. Free-text Mineral and Generation remain source metadata until explicit assignment

A source column mapped as `Mineral` or `Generation` is persisted losslessly as Analysis source metadata with physical source-cell provenance. It is not automatically promoted into the controlled `Mineral` or `Generation` domain entities.

This keeps the original scientific label visible and searchable while preserving the later ability to make an explicit, versioned taxonomy/classification assignment.

### 10. Duplicate candidates require an explicit recipe decision

Duplicate detection never merges Analyses.

The default recipe policy is `review_each`. If candidate groups exist, a reviewed import is not save-ready until the policy is changed by an explicit duplicate-review command. The current supported terminal decision is `keep_all`: all records remain separate and the decision is stored in the immutable recipe snapshot.

Complementary records with the same identity but different measurement subsets are therefore warned about and retained separately. `skip_exact_after_review` remains reserved until row-level exclusion and its provenance are implemented; UI must not pretend that it is available.

## Consequences

- `import.inspect_source` remains lightweight; raw windows are fetched with a dedicated preview command.
- raw preview navigation can move to any row without creating recipe revisions or reparsing workbook semantics in React.
- import recipe schema advances for block/orientation decisions while old recipe revisions remain immutable.
- tests generate anonymized synthetic workbooks that reproduce real layouts instead of committing user scientific data.
- automatic orientation suggestion is regression-tested against both a clearly transposed workbook and an ordinary workbook that must remain row-oriented.
- instrument preamble rows must be regression-tested against false block detection.
- native BIFF `.xls` parsing is not introduced by this ADR. `.xls` must be identified distinctly and reported honestly until a reviewed reader/conversion strategy is implemented.
- source `Mineral` / `Generation` can be displayed after import because persistence is now lossless, but the UI must label them as source values rather than controlled assignments.
- save readiness depends on duplicate review when duplicate candidates are present.

## Rejected alternatives

### One worksheet = one table
Rejected because it already fails on repeated headers, instrument preambles and multiple composition blocks.

### Load the complete workbook into React for scrolling
Rejected because workbook parsing belongs to Python, large workbooks would create unnecessary UI memory/serialization cost, and view navigation does not need to become application semantics.

### Transpose source files before import
Rejected because it mutates/creates a derived source representation that can obscure physical provenance and complicate reproducibility.

### Parse blocks in React
Rejected because import semantics belong to Python core and would become untestable/duplicated across UI states.

### Guess transposed orientation from file or sheet names
Rejected because naming conventions are not scientific evidence and would create silent false positives.

### Guess units by chemistry field
Rejected because the same field may be reported in different units and scientific rules require explicit units.

### Silently merge or drop duplicate identities
Rejected because identical Analysis/Sample labels can represent complementary methods or blocks. Any merge, exclusion or link must be a separate explicit scientific/data-management decision with provenance.