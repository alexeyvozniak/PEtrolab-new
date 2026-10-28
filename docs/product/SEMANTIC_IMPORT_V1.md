# Semantic Excel import v1

Approved behavior: user extension of 2026-09-05; existing import columns/ranges
reference and Import Workspace v1 layout. Architecture: ADR 0015.

Stage 1 shows physical sources, headers, components, units, Analysis identity and
Sample association. Select a cell, row, column or rectangle (drag or Shift), then
use the visible action area or its right-click equivalent. Assign Sample,
reported Mineral, Method, a column role, header or data block; Ignore is reversible.
An annotation is visible over the table and lists origin, evidence and coordinates.
Range selection here is not the project's Analysis Selection/Filter/Work Group.

Sample ID, Sample name, Source, method and Analysis ID remain distinct. Missing
Sample is unresolved, not an import error. Source coordinates identify records;
Sample alone is never used to collapse analyses. Name matches across sources do
not create physical-sample links without explicit evidence or a user decision.

Drag the annotation extension handle, inspect the proposed bounds and confirm.
Conflicts and physical structural boundaries stop extension. Cancel/undo leaves
raw values untouched. Alternate numeric bounds make the same action accessible
without precision dragging. Decisions replan through Python before commit.

Stage 2 lists mineral conflicts, uncertain predictions and missing reported values.
Matching high-confidence results can be reviewed as a group. Predictions never
replace reported mineral. Each accepted interpretation records the classifier
version, evidence, input fingerprint and explicit user decision.

Acceptance additions: all canonical elements and supported isotope notation;
Co/Ca, S/Si, Na/Nb remain distinct; fuzzy aliases cannot auto-assign; source hashes
unchanged; unresolved Sample persists; range undo and boundary-safe extension;
raw-to-canonical evidence inspectable; classifier prediction does not overwrite
reported Mineral; real-world matrix reports unknown truth as unverified rather
than claiming no false merges from counts alone.

Compact-window acceptance: at the supported 1180 x 800 desktop size the initial
preview starts at the physical header, leaving actual analysis rows visible.
Earlier preamble rows remain available through navigation. The raw table, range
action area and commit bar remain accessible together; controls may scroll inside
their own pane. Embedded drawings are explicitly identified as not rendered;
their absence in this cell-only preview is not interpreted as missing chemistry.

Delivery boundary: v1 retains reported Sample labels, suggestions and source
evidence but does not yet offer an existing-physical-Sample picker. These records
remain explicitly unlinked. Multi-source atomic commit and disk draft restoration
remain outside ADR 0014 v1. Neither is simulated by silently committing per source.
