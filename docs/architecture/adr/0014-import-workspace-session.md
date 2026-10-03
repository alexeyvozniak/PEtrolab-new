# ADR 0014: Import Workspace session and decision model

**Status:** Accepted for implementation
**Date:** 2026-09-01
**Related:** ADR 0013, Import Workspace v1

## Context

ADR 0013 correctly separates the `clean_table_fast` and `raw_review` presentations while retaining one scientific import pipeline. The initial desktop implementation still renders detailed review as a vertical sequence of cards and operates around one source at a time.

The approved Import Workspace design requires:

- several staged files and sheets in one visible queue;
- a stable physical-source preview;
- sheet-specific structure and semantic decisions;
- exact issue navigation;
- scientifically safe bulk decisions;
- an atomic final commit;
- the same validation, recipe, plan and provenance path for fast and detailed import.

These requirements need an orchestration model above the existing immutable Import Recipe and Import Plan. They do not justify a second scientific pipeline.

## Decision

### 1. Import Workspace is an orchestration boundary

Add a transient `ImportWorkspaceSession`. It coordinates staged sources, inspected sheets, explicit decisions, plans and commit readiness.

It is not a new scientific domain entity and is not persisted as imported data.

A session contains:

- `workspace_id`;
- `schema_version`;
- staged source descriptors;
- active source and sheet references;
- per-sheet review states;
- issue records;
- recipe and plan fingerprints;
- commit readiness summary;
- draft revision and timestamps.

### 2. Staged sources remain immutable

Each source descriptor contains at minimum:

- stable session-local `source_id`;
- original display path;
- managed staged path;
- SHA-256 fingerprint;
- size and modification metadata observed during staging;
- source kind and adapter version;
- inspection status.

Scientific services read the staged managed copy. The original and staged source are never rewritten during review.

Before planning and again before commit, PetroLab verifies the staged fingerprint. A mismatch invalidates affected plans and blocks commit.

### 3. Review state is source- and sheet-scoped

Each `SheetReviewState` is keyed by `source_id + physical_sheet_name` and contains:

- inclusion state and explicit exclusion reason;
- classification: `clean`, `review_required`, `ignored_empty`;
- header row;
- orientation: `analyses_in_rows` or `analyses_in_columns`;
- logical block definitions;
- field mappings;
- explicit Measurement units;
- optional reviewed Mineral and Method defaults;
- unresolved issue identifiers;
- recipe fragment fingerprint.

A decision made for one sheet changes only that sheet unless the scientific service returns an explicit eligible bulk scope.

### 4. Python owns classification and scientific validity

React renders session state and submits user decisions. It must not:

- classify a source as Clean Table;
- infer a Measurement unit;
- infer Fe form;
- decide that sheets are similar;
- invent logical block boundaries;
- enable commit from client-only checks.

Python creates the authoritative issue list, allowed actions, eligible bulk scopes and commit-readiness result.

### 5. Issues are first-class review records

Use a versioned `ImportReviewIssue` shape:

- `issue_id`;
- stable `code`;
- `severity`: `info | warning | error`;
- `blocking`;
- `source_id`;
- physical sheet and cell/range coordinates when applicable;
- logical block reference when applicable;
- plain-language parameters, not preformatted UI markup;
- allowed decisions;
- current explicit decision;
- `bulk_scope_id` when safe bulk application is available.

Issues remain reproducible after re-plan: stable codes and physical coordinates are inputs to deterministic issue identifiers.

### 6. Bulk application requires a service-issued scope

A `BulkDecisionScope` is created only by Python and contains:

- `bulk_scope_id`;
- decision kind;
- exact eligible sheet/field targets;
- normalized source header;
- explicit source unit;
- target scientific role and domain;
- orientation;
- logical-field signature;
- classifier/adapter version;
- explanatory scope summary.

File names, sheet names, instrument labels and previous user habits are not semantic evidence.

The client submits `bulk_scope_id + decision`. The service revalidates the scope against current source and recipe fingerprints before applying it. Stale or widened scopes are rejected.

### 7. Fast and detailed modes share the same shell

`clean_table_fast` is a presentation state of Import Workspace:

- sheet states are already ready;
- no required issue is unresolved;
- the right inspector is collapsed;
- the plan summary and physical preview remain inspectable;
- detailed review expands the existing workspace without replacing the recipe.

`raw_review` uses the same session with visible source controls and issue inspector.

Opening detailed review must not change source classification, recipe or plan by itself.

### 8. Re-plan is deterministic and incremental

Every accepted decision produces a new draft revision and invalidates only dependent recipe fragments and plans.

The service then:

1. validates the decision;
2. updates the affected sheet state;
3. rebuilds affected recipe fragments;
4. rebuilds affected Import Plans;
5. recalculates duplicates and issues across the whole included session;
6. returns the complete authoritative readiness summary.

The client never merges partial issue lists from independent guesses.

### 9. Batch commit is atomic

The default commit covers all included ready sheets in the session.

Commit preconditions:

- every included source fingerprint matches;
- every included sheet has a valid recipe fragment;
- no blocking issue remains;
- duplicate decisions are explicit;
- every planned Measurement has explicit unit semantics;
- plan fingerprints match the current draft revision.

All database writes occur in one SQLite transaction. Managed artifacts created for the session are removed if persistence fails. A failure leaves no partially imported included source.

A later explicit product decision may add per-source commit, but it must not be silently substituted for atomic batch behaviour.

### 10. Exact provenance remains physical

Virtual matrices, transposition and normalized previews are presentation/interpretation layers.

Every persisted value retains:

- source fingerprint;
- physical sheet;
- physical row and column;
- raw token;
- parser/adapter version;
- recipe fragment fingerprint;
- plan fingerprint;
- workspace commit identifier.

### 11. Draft restore is fingerprint-bound

Autosaved workspace drafts contain staged source references, fingerprints and explicit decisions. They do not become provenance roots and do not embed normalized scientific records as authoritative data.

Restore is rejected or downgraded to a new inspection when a required source fingerprint or schema version is incompatible.

### 12. Service command boundary

Implement the workspace through versioned scientific-service commands:

- `import.workspace.create`;
- `import.workspace.add_sources`;
- `import.workspace.get`;
- `import.workspace.preview_window`;
- `import.workspace.apply_decision`;
- `import.workspace.apply_bulk_decision`;
- `import.workspace.replan`;
- `import.workspace.commit`;
- `import.workspace.discard`.

Existing single-source commands remain internal building blocks until compatibility can be removed safely.

Every mutating command accepts the expected draft revision. Revision mismatch returns a stale-draft error instead of overwriting newer decisions.

## Required contract tests

Architecture is not complete until automated contracts prove:

1. two sheets can keep different header rows, orientations, Mineral defaults and Method defaults;
2. a decision without a service-issued bulk scope affects one target only;
3. a bulk scope cannot cross a unit, Fe-form, role, orientation or source-fingerprint difference;
4. a stale bulk scope is rejected;
5. changing a staged source invalidates planning and commit;
6. one failing included source rolls back the whole batch;
7. excluded sheets remain visible with reasons and contribute no records;
8. `<DL` and similar raw tokens survive preview and provenance;
9. transposed preview maps back to exact physical cells;
10. clean fast presentation and detailed review produce the same plan fingerprint when no decision changes;
11. React cannot enable commit when Python reports a blocker;
12. draft restore is rejected on incompatible fingerprint or schema version.

## Consequences

- routine clean imports stay short;
- difficult workbooks gain a stable table-centred review surface;
- multi-file import does not create partial projects;
- sheet-specific decisions cannot leak silently;
- bulk editing remains efficient but scientifically bounded;
- implementation requires a new orchestration layer and session-level tests;
- image/media import can later reuse staged-source and draft-revision concepts without entering the table scientific pipeline.
