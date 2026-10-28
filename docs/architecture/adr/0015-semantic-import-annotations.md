# ADR 0015 — Semantic interpretation over immutable Excel cells

Status: accepted for the import extension explicitly requested on 2026-09-05.

The existing ADR 0014 workspace remains the single session owner. Python owns
canonical analyte recognition, sample evidence, range validation, replanning and
mineral suggestions. React sends physical coordinates and explicit decisions.
No additional bridge, state manager or scientific rules in React are introduced.

## Recognition and identity

The built-in dictionary is versioned data, with exact canonical names, safe
normalization, explicit aliases and deterministic isotope parsing. Fuzzy results
are suggestions only. Analyte and unit are separate; a bare percent sign does
not establish mass versus atomic percent. Raw headers are always retained.
Project aliases require explicit confirmation and must not shadow a different
canonical analyte. User-global aliases are reserved, not implicitly written.

Sample is already optional in DOMAIN_MODEL. Source, sheet and block names never
create Samples. A reported identifier is evidence of a relationship, not proof
that equally named specimens from unrelated sources are the same physical object.
Unresolved associations retain reported values and coordinates. Cross-source
entity links require an explicit user assignment to an existing Sample ID.
Repeated/merged values can propagate only inside explicit source ranges; labels
in preambles and proximity alone remain suggestions. No name-pattern-only merge.

## Semantic ranges

An Import Recipe may contain versioned semantic annotations bound to the source
SHA-256, sheet, block and physical rectangle (1-based rows, 0-based columns).
Annotations store role, value, origin, evidence and reversible history. They do
not update source cells. Column/header/block operations use the existing mapping
and section revision functions. Range assignments add interpretation over records.

Extension is previewed before confirmation. Conflicting explicit assignments,
repeated headers and another detected block reject extension. Undo restores the
previous interpretation, not a previous copy of the source workbook.

## Mineral verification

Structure/identity review precedes mineral verification. Reuse the locally
available PetroLab scientific recognition functions and reference data, with
source hashes and equivalence tests; do not import Streamlit/UI/persistence.
Missing/censored or incompatible chemical inputs are never filled with zero.
Reported text, classifier candidates/confidence and explicit accepted assignment
are distinct. Group-level predictions do not establish a species. Bulk acceptance
requires a service-issued homogeneous high-confidence scope and explicit action.

## Verification

Tests cover collision-safe analytes, raw headers/tokens, false-merge protection,
range conflict/undo/fill boundaries, source/revision rejection, classifier input
gates and separation of reported/predicted/accepted minerals. Native screenshots
must demonstrate selection actions with the raw physical table still central.

The current multi-source review queue still has no atomic batch commit or disk
draft restore; these ADR 0014 capabilities must not be simulated by per-file apply.
