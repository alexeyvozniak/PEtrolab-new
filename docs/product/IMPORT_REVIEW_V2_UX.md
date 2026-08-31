# PetroLab Desktop v2 — Import Review UX contract

**Status:** implementation contract for the current import-quality pass  
**Date:** 2026-08-31

## Goal

A user must be able to open a real laboratory spreadsheet, understand exactly what PetroLab thinks the tables mean, correct structural or semantic mistakes, review ambiguity, and save only after all blocking decisions are explicit.

The UI is a review surface. Scientific/import semantics remain in Python.

## Ordered flow

1. **Source** — choose a file; PetroLab stages a local read copy without modifying the source.
2. **Where are the data?** — show raw source rows, logical blocks, boundaries and orientation.
3. **What do fields mean?** — map identity, source metadata and Measurements; require explicit units and allow method / measurement-set context.
4. **Ambiguities** — show duplicates and other blocking review decisions.
5. **What will be written?** — show normalized planned Analyses/Measurements with source-cell provenance.
6. **Save** — enabled only when every blocking draft or ambiguity is resolved.

## Logical blocks

- One worksheet may contain zero, one or many logical blocks.
- Blocks can be disabled without deleting source data.
- A block may be row-oriented or column-oriented (transposed).
- Python evaluates both plausible orientations for a detected block. When the field labels form a strong column-oriented pattern and the row above contains multiple Analysis labels, PetroLab may **suggest** the transposed orientation.
- A transposed suggestion must be visible in the import review as `По столбцам (инвертировано)` and accompanied by a `TRANSPOSED_TABLE_LIKELY` warning. The user can switch it back before any data are saved.
- PetroLab never rewrites or physically transposes the source workbook to make this suggestion.
- If confidence is insufficient, the default remains row-oriented; orientation is never guessed merely from a file name or instrument name.
- Raw preview must precede semantic mapping.
- Repeated headers must never silently become Analysis rows.

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

- block-structure edits are unapplied;
- field-mapping edits are unapplied;
- no enabled logical block exists;
- no Analysis or no Measurement will be produced;
- a Measurement lacks an explicit recognized unit;
- duplicate candidates exist and duplicate policy is still `review_each`.

## Error recovery

Choosing a bad replacement file must not destroy the current valid review state. Cancel/import-reset must always be available. A mapped/network source path is staged locally before the Python service reads it.

## Acceptance examples

The regression matrix must cover at least:

- long preambles and unit context rows;
- repeated headers;
- several logical tables on one sheet;
- transposed tables, including conservative automatic orientation suggestion and manual override;
- atomic percent distinct from mol percent;
- unfamiliar isotope/numeric tables;
- same canonical field from different analytical methods;
- Mineral/Generation source metadata with exact source-cell provenance;
- complementary blocks sharing the same Analysis/Sample identity;
- legacy `.xls` reported honestly rather than misclassified.