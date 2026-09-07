# ADR 0016 — Post-import mineral decisions

Status: accepted for the dedicated mineral review slice requested on 2026-09-07.

## Context

ADR 0015 separates the reported mineral, a versioned classifier suggestion and
an explicit accepted interpretation during import. Imported projects also need
the same review after the source has already been committed. Updating
`analysis_import_semantics.mineral_assignment_json` would rewrite the immutable
import snapshot and hide when the later scientific decision was made.

## Decision

Post-import decisions are stored as append-only `mineral_assignment_decision`
events. The current project projection overlays only the newest non-cleared
decision on the immutable import evidence. Clearing a decision appends a
`clear` event; it does not delete the earlier decision.

Every accepted decision contains the Analysis ID, controlled target, decision
kind, input fingerprint, classifier ruleset version, reason and timestamp. The
service recalculates the current suggestion before writing. A changed
composition, Fe basis or ruleset rejects a stale decision.

The service accepts only two targets exposed by the current evaluation:

- the current high- or medium-confidence classifier suggestion;
- the controlled target resolved from the reported source label.

Unknown reported text remains unresolved. The UI does not invent a controlled
target and the classifier never overwrites the source label or Measurements.

## UI boundary

The `Минералы` workspace is a task queue, not a second full chemistry table.
It keeps Analysis/Sample context, source position, reported label, suggestion,
confidence and status visible in one row. The review pane shows candidates,
rule evidence and explicit actions. `Анализы` remains the lossless wide-table
inspection surface.

React translates status and diagnostic text for presentation only. Target
eligibility, fingerprints, ruleset validation and persistence remain in Python.

## Verification

AT-35 covers consistent, conflicting, missing and accepted states. Automated
tests prove append-only acceptance, stale rejection, clearing without deletion,
unchanged reported evidence and the React-to-service flow.
