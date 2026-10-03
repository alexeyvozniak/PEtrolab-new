# ADR 0012: Logical import blocks and orientation-normalized planning

**Status:** Accepted for Desktop v2 import work  
**Date:** 2026-09-01

## Context

The first Desktop import alpha treated one worksheet as one table and one physical row as one Analysis. Real PetroLab workbooks violate both assumptions: a sheet can contain several tables, repeated headers, long preambles, helper regions, transposed tables and multiple analytical methods.

Keeping these rules in React would violate the project boundary. Rewriting/transposing source files would violate source immutability and provenance.

The first Import Review v2 UI also exposed a second problem: structure edits were held in a local React draft until a separate `Apply structure` action. During that draft, semantic mapping was globally disabled and still rendered the old recipe. This made a simple action such as disabling one wrong block appear to do nothing and freeze otherwise-valid blocks.

A related data-model problem existed in row-oriented mapping: only non-empty header cells were converted into mappings. A physical Excel column containing values under a blank/unknown header could therefore disappear from user review entirely.

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

A raw preview window is a view onto the full physical worksheet used range. It is not part of the recipe and has no semantic effect. Desktop may request another window at any row at any time. This lets the UI page/jump/recentre without applying a recipe revision.

The service returns physical row numbers, column labels and used-range bounds. React never loads the entire large workbook merely to make a scrollable preview; it requests bounded windows lazily. Navigation state therefore belongs to presentation state, while workbook parsing remains Python-owned.

Tauri remains a file/process boundary and does not parse workbook semantics.

### 3. Valid structure edits are auto-applied recipe revisions

The Desktop may keep text-field keystrokes in a short local debounce buffer, but a valid structural change is not a long-lived user-visible draft requiring a second confirmation button.

- enable/disable toggles are submitted immediately;
- valid row/column-bound and orientation changes are submitted after a short debounce;
- Python `revise_import_sections` remains the only authority that rebuilds mappings, fingerprints and validation;
- the last valid recipe remains active until Python accepts the new structural revision;
- on failure the UI marks the affected edit invalid and keeps the previous valid recipe rather than globally freezing unrelated semantic mapping.

This preserves the design/architecture boundary without exposing an internal two-phase state machine to the user.

### 4. Every populated physical source field remains reviewable

Automatic semantic recognition is advisory; it must never determine whether a physical field is visible to the user.

For `rows_are_analyses`, Python creates a mapping entry for every physical source column that either:

- has a non-empty header cell, or
- contains at least one non-empty cell in the selected data-row range.

A blank-header populated column receives an explicit mapping with `source_header = null`, physical `source_column_index`, and conservative `ignore/ignored` semantics. Unknown non-empty headers are also retained as ignored mappings. React renders a coordinate fallback such as `Q · без заголовка`.

For `columns_are_analyses`, the equivalent rule applies to physical source rows inside the selected field-row range.

Thus `Ignore` is an explicit reversible recipe decision; disappearance from the mapping UI is never used as a synonym for ignore.

### 5. Orientation suggestion is conservative and reviewable

For every detected logical block, Python may evaluate whether its field labels form a stronger column-oriented pattern than a row-oriented one.

A transposed suggestion is allowed only when source structure provides positive evidence, including several recognized field labels down one physical column and multiple populated Analysis labels across the block header row. File names, sheet names and instrument names are not evidence.

When this threshold is met, the suggested recipe may start with `orientation = columns_are_analyses`, but it must also emit `TRANSPOSED_TABLE_LIKELY`. The Desktop review shows that orientation explicitly and permits a user to switch it back before save. Weak or ambiguous cases remain row-oriented.

This is a semantic suggestion only. The source workbook is never rewritten or physically transposed.

### 6. Orientation is normalized in memory

For ordinary blocks, logical rows equal physical rows.

For transposed blocks, Python creates a logical transposed view in memory for validation/planning. Every logical cell retains a reference to its physical source row and column so provenance can be persisted.

### 7. Provenance becomes cell-address aware

Row number + source column name is insufficient for orientation-normalized planning. New import plans expose physical `source_row_number`, `source_column_index` and source header for every value. Persistence may keep legacy row fields for compatibility, but no new feature may rely on logical position as physical provenance.

### 8. Repeated headers and instrument preambles are structure, not data

A row/column whose normalized header signature equals the active block header is skipped as structural content. Detection should normally split such content into multiple blocks, but planning has the same guard for manually widened ranges.

Instrument/service preambles (for example `Sample: ...`, `Type: ...`, `Processing option: ...`, standalone unit-context rows) do not become logical analytical blocks merely because they contain a known keyword. A candidate header must have multi-field header evidence and data-like rows beneath it. Preamble rows may still provide explicit context (such as units) to the actual analytical block that follows.

### 9. Units from source context are explicit evidence

A block-level unit can be auto-applied only if an inspected source cell states a recognized unit outside a mixed per-column header row. The plan stores the evidence coordinate/text. A likely unit based only on instrument/file naming remains a suggestion requiring user confirmation.

`at.%` is distinct from `mol%`.

### 10. Measurement identity includes set/method context

New planning structures carry optional `measurement_set` and `method` labels in addition to `canonical_field`. This prevents same-named fields from different analytical groups from being collapsed in projections. Existing records without these labels remain valid.

### 11. Free-text Mineral and Generation remain source metadata until explicit assignment

A source column mapped as `Mineral` or `Generation` is persisted losslessly as Analysis source metadata with physical source-cell provenance. It is not automatically promoted into the controlled `Mineral` or `Generation` domain entities.

This keeps the original scientific label visible and searchable while preserving the later ability to make an explicit, versioned taxonomy/classification assignment.

### 12. Duplicate candidates require an explicit recipe decision

Duplicate detection never merges Analyses.

The default recipe policy is `review_each`. If candidate groups exist, a reviewed import is not save-ready until the policy is changed by an explicit duplicate-review command. The current supported terminal decision is `keep_all`: all records remain separate and the decision is stored in the immutable recipe snapshot.

Complementary records with the same identity but different measurement subsets are therefore warned about and retained separately. `skip_exact_after_review` remains reserved until row-level exclusion and its provenance are implemented; UI must not pretend that it is available.

## Consequences

- `import.inspect_source` remains lightweight; raw windows are fetched with a dedicated preview command.
- raw preview navigation can move to any row without creating recipe revisions or reparsing workbook semantics in React.
- valid structure edits create Python-owned recipe revisions automatically instead of waiting for a user-visible `Apply structure` gate.
- blank-header and unknown populated fields remain visible and reversible in semantic review.
- import recipe schema remains compatible with old recipe revisions; newly suggested/rebuilt mappings may contain `source_header = null` for physically populated blank-header fields.
- tests generate anonymized synthetic workbooks that reproduce real layouts instead of committing user scientific data.
- automatic orientation suggestion is regression-tested against both a clearly transposed workbook and an ordinary workbook that must remain row-oriented.
- instrument preamble rows must be regression-tested against false block detection.
- native BIFF `.xls` parsing is not introduced by this ADR. `.xls` must be identified distinctly and reported honestly until a reviewed reader/conversion strategy is implemented.
- source `Mineral` / `Generation` can be displayed after import because persistence is now lossless, but the UI must label them as source values rather than controlled assignments.
- save readiness depends on duplicate review when duplicate candidates are present.

## Rejected alternatives

### Require an explicit `Apply structure` button before mapping
Rejected because it exposed an implementation state machine, left disabled blocks visible in the old recipe, and globally disabled unrelated mapping controls.

### Hide blank/unknown physical fields
Rejected because a user cannot recover a column that automatic recognition omitted. Unknown/blank fields must default to Ignore but remain visible.

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