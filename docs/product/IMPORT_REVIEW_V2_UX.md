# PetroLab Desktop v2 — Import Review UX contract

**Status:** implementation contract for the current import-quality pass  
**Date:** 2026-09-01

## Goal

A user must be able to open a real laboratory spreadsheet, understand exactly what PetroLab thinks the tables mean, correct structural or semantic mistakes, review ambiguity, and save only after all blocking decisions are explicit.

The UI is a review surface. Scientific/import semantics remain in Python.

## Ordered flow

1. **Source** — choose a file; PetroLab stages a local read copy without modifying the source.
2. **Where are the data?** — show raw source rows, logical blocks, boundaries and orientation.
3. **What do fields mean?** — show every physical source field used by the selected block, then map identity, source metadata and Measurements; require explicit units and allow method / measurement-set context.
4. **Ambiguities** — show duplicates and other blocking review decisions.
5. **What will be written?** — show normalized planned Analyses/Measurements with source-cell provenance.
6. **Save** — enabled only when every blocking ambiguity is resolved.

## Logical blocks

- One worksheet may contain zero, one or many logical blocks.
- Blocks can be disabled without deleting source data.
- **Disabling/enabling a block is immediate.** It must not leave the mapping stage frozen behind an unapplied structural draft.
- Valid edits of header/data bounds and orientation are applied automatically after a short debounce. A user must not understand a hidden two-phase `edit -> apply structure -> edit mappings` state machine.
- While an automatic structure update is running, the affected review controls may show a short busy state; after success, the mapping stage reflects the new recipe immediately.
- A block may be row-oriented or column-oriented (transposed).
- Python evaluates both plausible orientations for a detected block. When the field labels form a strong column-oriented pattern and the row above contains multiple Analysis labels, PetroLab may **suggest** the transposed orientation.
- A transposed suggestion must be visible in the import review as `По столбцам (инвертировано)` and accompanied by a `TRANSPOSED_TABLE_LIKELY` warning. The user can switch it back before any data are saved.
- PetroLab never rewrites or physically transposes the source workbook to make this suggestion.
- If confidence is insufficient, the default remains row-oriented; orientation is never guessed merely from a file name or instrument name.
- Raw preview must precede semantic mapping.
- Repeated headers must never silently become Analysis rows.
- Instrument/service preambles such as `Sample: ...`, `Type: ...`, `Processing option: ...` and standalone unit-context rows are context, not standalone analytical blocks unless they satisfy the same multi-field/data evidence as a real table header.

## Physical source fields must remain user-reviewable

The mapping stage must never hide a physical source column merely because automatic recognition did not understand it.

For a row-oriented block:

- every physical Excel column that has a header **or contains at least one non-empty value inside the selected data rows** is represented in the block mappings;
- a column with a blank header is shown explicitly by its Excel coordinate, for example `Q · без заголовка`, and defaults to `Не импортировать`;
- unknown headers also default conservatively to `Не импортировать` rather than disappearing;
- the user can explicitly promote any visible physical field to `Analysis`, `Sample`, `Point`, `Mineral`, `Generation` or `Measurement`;
- the UI shows the physical column letter/index so duplicate or empty headers remain distinguishable;
- excluded/ignored columns remain visible during review so the user can reverse the decision.

The same principle applies to transposed blocks using physical source rows as fields.

## Raw source navigation

The raw Excel preview is a window onto the **whole used range of the worksheet**, not a decorative fixed snippet.

For every logical block:

- the user can move the preview backward/forward through the sheet without applying the block first;
- the user can jump directly to an arbitrary source row;
- editing `Строка заголовка`, `Первая строка данных` or the corresponding transposed bounds recentres the preview around that row automatically;
- the preview clearly shows which physical rows are currently loaded and the total used row count;
- horizontal scrolling remains available for wide analytical tables;
- navigation changes only what is displayed; it must never alter the recipe or source data;
- bounded windows are fetched lazily from Python so large workbooks are not copied into React memory wholesale.

A user must never need to know a hidden implementation window size in order to reach the actual analytical header.

## Source metadata

`Mineral` and `Generation` imported from free text are shown as **source metadata**, not as controlled taxonomy assignments.

The user must see these values after import. PetroLab keeps the physical source-cell coordinate so later controlled assignments can cite the original source value.

## Measurement context

Two values with the same canonical field are not necessarily the same Measurement. The mapping review exposes optional **Method** and **Measurement set** fields (for example EPMA, SIMS, major elements, trace elements). The Analyses view must keep same-named Measurements distinguishable.

## Duplicate review

A duplicate candidate is an ambiguity, not an instruction to merge or discard data.

When duplicate candidate groups exist:

- PetroLab shows the groups before save;
- the initial recipe state is `review_each`;
- save remains blocked while the recipe still says `review_each`;
- a user may explicitly confirm **keep all after review**; that decision becomes part of the immutable recipe revision;
- complementary records with the same identity (for example major-elements and trace-elements blocks) remain separate Analyses unless a later explicit linking workflow says otherwise;
- this pass does not silently implement “skip exact duplicates”. Row-level exclusion can be added later only with explicit provenance.

## Blocking conditions

Save is disabled while any of these is true:

- an automatic structure revision is currently running or has failed validation;
- field-mapping edits are unapplied;
- no enabled logical block exists;
- no Analysis or no Measurement will be produced;
- a Measurement lacks an explicit recognized unit;
- duplicate candidates exist and duplicate policy is still `review_each`.

A valid block toggle or structural edit must not leave the mapping stage permanently disabled waiting for a second hidden confirmation action.

## Error recovery

Choosing a bad replacement file must not destroy the current valid review state. Cancel/import-reset must always be available. A mapped/network source path is staged locally before the Python service reads it.

If an automatically applied structure edit fails validation, PetroLab keeps the last valid recipe active, marks the edited block clearly, and allows the user to correct the draft. Other already-valid blocks must not become impossible to inspect because of an unrelated stale state.

## Acceptance examples

The regression matrix must cover at least:

- long preambles and unit context rows;
- service metadata rows before an instrument header must not become separate logical blocks;
- raw preview navigation beyond the initial window and direct jump to a later row;
- changing a draft header/data-row field recentres preview and auto-applies a valid structural revision;
- disabling block 1 immediately removes block 1 from semantic mapping and leaves block 2 editable;
- blank-header physical columns containing data remain visible as ignored reviewable fields;
- unknown but populated physical columns never disappear from mapping review;
- repeated headers;
- several logical tables on one sheet;
- transposed tables, including conservative automatic orientation suggestion and manual override;
- atomic percent distinct from mol percent;
- unfamiliar isotope/numeric tables;
- same canonical field from different analytical methods;
- Mineral/Generation source metadata with exact source-cell provenance;
- complementary blocks sharing the same Analysis/Sample identity;
- legacy `.xls` reported honestly rather than misclassified.