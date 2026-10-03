# Import unit review simplification

Scope: the existing approved physical-table / source-queue / inspector screen,
AT-02 and AT-03. No import decisions, unit conversion or scientific rules changed.

## Behaviour

- Pending edits remain visible in "Нужно решить" until explicitly applied.
- A user can change a chosen unit again or reset the edits without searching
  for the field under "Все".
- Unit options explain mass, atomic and molar percentages. Stored unit keys
  remain unchanged.
- Optional bulk controls are collapsed; all physical fields remain accessible.
- A status message distinguishes unapplied edits from saved decisions.

## Regression evidence

The real Python integration test selects wt.%, changes it to ppm, resets it,
selects wt.% again and applies the mapping. It checks that the field remains
visible before apply and disappears from the unresolved view only afterward.
The second unresolved measurement still blocks import.

30 UI tests and 24 Tauri contracts pass. The preceding implementation pass also
passed 176 Python tests, contract validation, production build and 4 Sites tests.

Visual acceptance remains pending: the browser connector reports no available
browser, and the separate screenshot-browser launch was rejected by policy.
This note does not claim a new screenshot or complete native UX acceptance.

## Windows CI prerequisite

Direct cargo test bypasses Tauri's beforeDevCommand/beforeBuildCommand.
The Windows workflow now generates the existing deterministic icon before
Cargo tests and stops if generation fails. A contract test protects the order.
