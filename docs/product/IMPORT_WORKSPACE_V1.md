# Import Workspace v1

**Status:** Approved design
**Date:** 2026-09-01
**Related:** PR #13, ADR 0013, ADR 0014

## Outcome

PetroLab must make routine tabular import short without hiding scientific ambiguity. A geologist can add several Excel/CSV sources, see the physical source table, resolve only real problems, and commit one reproducible batch without changing the source files.

The approved presentation is a calm three-column scientific workspace:

1. source files and sheets;
2. the physical source table;
3. unresolved issues and the selected decision.

A fixed commit bar stays visible at the bottom.

## One workspace, two presentation states

The scientific service classifies sources conservatively.

### Table ready for import

When the Clean Table contract is proven:

- the same workspace opens;
- sheet statuses are ready;
- the issue inspector is collapsed;
- recognized fields, units, Analysis and Measurement counts remain inspectable;
- the primary import action is immediately available;
- `Clean Table v1` is secondary technical information, not the main user-facing title;
- the user can open detailed review without changing the recipe or provenance path.

### Detailed review

When any ambiguity remains:

- the source table remains the central object;
- the exact sheet, row, column or block is highlighted;
- the right inspector explains one selected issue in plain language;
- blocking scientific ambiguity must be resolved or the affected sheet explicitly excluded;
- the import button explains why it is disabled.

Falling back to detailed review is not presented as an error.

## Source and sheet list

The left pane contains a queue of staged files and their sheets. Each sheet has one state:

- **Ready** — no required decision remains;
- **N questions** — required decisions remain;
- **Not imported** — explicitly excluded with a visible reason;
- **Empty sheet** — safely ignored under an explicit contract.

Each sheet owns its own reviewed interpretation:

- header row;
- analysis orientation (rows or columns);
- logical block boundaries;
- included/excluded state;
- field mappings and units;
- optional sheet-scoped Mineral and Method interpretation defaults.

A setting from one sheet must never silently overwrite a different sheet.

## Physical source preview

The centre pane shows the immutable physical source:

- real row numbers and column letters;
- original headers and raw tokens;
- `<DL`, `bdl`, `n.d.`, `<0.01` and blanks without rewriting;
- repeated headers, blank headers, hidden rows and physical block boundaries;
- a second header tier containing PetroLab's interpreted role and explicit unit.

Transposed sources are shown as a virtual analysis table only when the user requests that view. Provenance still points to the real physical cells.

## Issue inspector

The right pane first lists unresolved issues. Selecting an issue navigates to and highlights its exact source location.

Every issue contains:

- stable code;
- plain-language explanation;
- severity;
- whether it blocks commit;
- physical source coordinates or logical block;
- allowed decisions;
- current decision;
- the exact scope eligible for safe bulk application.

Examples of blocking issues:

- Fe form is not explicit;
- Measurement unit is unknown;
- populated header is blank or duplicated;
- Analysis identity is missing or duplicated;
- repeated header or block boundary is unresolved;
- a source changed after inspection.

Warnings that do not change scientific meaning may remain non-blocking, but they must be preserved in the import record.

## Safe bulk decisions

The UI may offer a bulk action only when the scientific service returns an eligible scope. User-facing copy must name the proven scope, for example:

> Apply to 2 sheets with the same source header and unit.

The UI must not infer similarity from file name, sheet name, instrument name or user history.

## Commit bar

The fixed bottom bar shows:

- staged file count;
- included sheet count;
- planned Analysis and Measurement counts;
- skipped rows/sheets;
- required decision count;
- immutable-source guarantee;
- preview action;
- primary commit action and its blocking reason.

The default batch commit is atomic. No included source is partially imported when another included source fails validation or persistence.

## Drafts

Workspace decisions are autosaved as a resumable draft. A draft stores source fingerprints and explicit interpretation decisions, not copied scientific measurements. Resume is allowed only when all required source fingerprints still match.

## Terminology

Prefer:

- `Импорт таблиц`;
- `Таблица готова к импорту`;
- `Подробная проверка`;
- `Нерешённые вопросы`;
- `Исходные файлы не изменятся`.

Use `Clean Table v1` as secondary technical detail.

## Not in this design slice

Image placement and analytical-point annotation will later use the same staged-source concept, but they do not weaken or bypass this table-import contract.
