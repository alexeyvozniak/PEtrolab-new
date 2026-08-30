# Import mapping UX v1

Status: implementation slice after live-file testing on 2026-08-30.

## Problem observed on real SEM/EDS workbook

PetroLab can locate sheets and table headers, but conservative auto-recognition intentionally leaves elemental columns such as F, Na, Mg, Al, Si, P, S, K, Ca as `ignore` when the unit is not explicit in the source header. The current UI then offers to save many Analysis records with no Measurements. That is unsafe and confusing.

## Design

1. Keep automatic recognition conservative. Never infer a unit silently.
2. Make every detected source column editable on the import review screen.
3. User can choose role: Ignore, Analysis, Sample, Point, Mineral, Generation, or Measurement.
4. Measurement requires an explicit canonical field and unit (`wt.%`, `ppm`, `ppb`, `apfu`, `mol%`, `ratio`).
5. Rebuilding and validating the recipe remains Python-core responsibility. React only sends user decisions and renders the returned recipe/plan.
6. Recompute the import plan after every accepted mapping edit.
7. Block Save when the plan contains Analysis records but zero Measurements. Explain why and highlight columns requiring review.
8. Surface planned Measurement count alongside planned Analysis count.
9. Do not modify the source workbook.

## Follow-up slice

Header-row/data-range editing, per-sheet enable/disable, raw row preview, and `normal|transposed` orientation are separate but adjacent controls and should reuse the same recipe-revision path.