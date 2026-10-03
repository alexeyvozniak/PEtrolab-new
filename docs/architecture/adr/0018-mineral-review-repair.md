# ADR 0018 — Explicit mineral assignments and honest review queues

Status: accepted implementation scope for the user's 2026-09-11 repair request.
Extends ADR 0016; preserves the approved three-pane review and import range tools.

- An explicit import range annotation is a human interpretation bound to the
  immutable source, not a classifier acceptance. Project projection resolves its
  label to the controlled catalog without rewriting the stored annotation.
  Recognized labels are `manually_assigned`; unknown text is retained as
  `manual_unresolved`, never discarded or falsely reported as a stale calculation.
- Post-import manual decisions accept only catalog names/chemical targets and
  require a reason, input fingerprint and ruleset. Add an append-only decision
  kind through a forward SQLite migration; never edit historical decisions.
- Exact Russian aliases and common abbreviations are versioned separately from
  the reused scientific classifier. No fuzzy assignment and no new species inference.
- Only explicit decisions are in the accepted queue. Automatic consistent rows
  remain pending acceptance. Stale decisions always require attention.
- Keep the complete-major-element gate. Missing K2O is not zero. The bounded
  exception is missing/censored F or Cl in an otherwise complete olivine input:
  remove unavailable tokens (not substitute zero), allow only the existing
  olivine group suggestion, and display every excluded volatile. Other phases
  retain the conservative gate until independently tested per-target contracts.
- Missing-component names, excluded inputs and manual labels are visible. Scores
  are rule points, not probability; a manual decision does not validate chemistry.
- Formula calculation is not implemented by this repair. The UI must state this;
  the continuation document specifies executable methods, benchmarks and provenance.

Acceptance: manual range round-trip and undo, alias resolution, optional F/Cl,
required-core rejection, stale rejection, manual post-import accept/clear/history,
queue separation, visible error recovery, keyboard controls and current screenshots.
