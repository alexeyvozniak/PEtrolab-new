# ADR 0019 — First executable formula run

Status: implementation of the next step requested on 2026-09-11.

## Design before code

Approved behaviour: master specification §§11,20.2; AT-31 and AT-35;
`docs/design/reference/screens/import-mineral-mapping-v1.png`.
Keep the green three-pane review. Add formula controls to the inspector of one
explicitly accepted analysis: method/version → explicit Fe mode → preview → save.
The button names the exact one-analysis scope; focus alone never starts a run.
Measured wt.% and derived APFU appear in separate tables. Warnings remain visible.
Saved history can be reopened; errors do not erase the preview or Fe choice.
This bounded slice is post-import and single-analysis in UI; batch UI and
import-time formula previews remain deferred. No mock calculation in production.

## Method

Direct oxygen normalization described by Brady & Perkins (2007),
https://serc.carleton.edu/research_education/equilibria/mineralformulaerecalculation.html.
Atomic masses: CIAAW abridged 2024 table, https://ciaaw.org/abridged-atomic-weights.htm,
accessed 2026-09-11; constants frozen in code. Independent ideal stoichiometric
benchmarks define expected APFU without calling production to prepare expectations.

For each supported oxide: moles = wt.% / formula mass; oxygen sum = Σ(moles × O);
cation APFU = moles × cation count × 4 / oxygen sum. No mass-total normalization.
Fo = 100 Mg/(Mg+Fe2); Fa = 100 Fe2/(Mg+Fe2). Mn/Ca/Ni are not in that binary
denominator and are retained in APFU. No site allocation or Fe3+/OH estimation.
Two explicit Fe modes: all iron as Fe2 using exactly one FeO/FeOt column; or
separately reported FeO and Fe2O3. Total and split bases cannot coexist.
Require SiO2, MgO and the chosen Fe basis; numerical zeros are valid except
SiO2 and Mg+Fe2 denominator must be positive. Present missing/censored oxides
reject the row. Absent optional oxides are listed as unmeasured, never emitted as zero.
Unsupported wt.% fields reject the row; non-wt.% non-oxide fields are explicitly
excluded. Numerical sum/stoichiometry checks are warnings, not a QC assignment.

## Architecture and storage

Python owns a small versioned method registry and pure calculation. React sends
commands over the existing NDJSON transport; Tauri remains unchanged.
Commands: `formula.methods.list`, `formula.preview`, `formula.save`, `formula.runs.list`.
Preview/save use explicit unique analysis_ids (1–100), method_id/version and
parameters {fe_mode}. Save additionally requires the full preview fingerprint.
Invalid rows remain in the response and prevent saving the entire requested run.
No silent reduction of scope. No input values or derived values supplied by the
client are trusted for saving: Python recalculates in a BEGIN IMMEDIATE transaction.

Migration 13 adds project identity, immutable formula_run and formula_derived_value
tables. JSON documents follow existing Calculation Run and Derived Value schemas.
Result manifest retains the method definition, complete input snapshots, diagnostics,
used/excluded fields and parameters. Every value links actual Measurement IDs.
Source tables are not updated. Existing open_project migration backup remains.
Save is idempotent for identical fingerprints; retries return the existing run.
Read-time freshness compares current input/assignment and method fingerprints,
without rewriting historical payloads. Retracted analyses are stale. Parameter
changes invalidate the unsaved preview and produce a distinct immutable run.

## Acceptance

Ideal Fo100, Fa100, Fo50, Mn/Ca/Ni-bearing and split-Fe benchmarks; malformed,
missing, censored, negative, nonfinite, duplicate, wrong-unit and mixed-Fe inputs;
stale preview/method/assignment, atomic rollback, retry, project reopen, migration
backup, NDJSON round-trip and unchanged source bytes/Measurements. Browser QA uses
the real component; service integration tests independently verify persistence.
