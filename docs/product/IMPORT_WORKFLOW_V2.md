# Import workflow v2

Status: implementation slice from real-user testing on 2026-08-31.

## Problems observed

1. Per-row `Применить` made users edit many mappings but only one decision was actually committed to the recipe.
2. Known elemental SEM/EDS columns such as Na, Mg, Al, Si, P, S, K, Ca can be recognized as likely measurements, while their unit must remain explicit.
3. A common unit should be assignable to many selected measurement columns at once.
4. Saving must be impossible while there are unapplied draft mapping changes.
5. An accidentally saved test import needs a reversible, auditable way to disappear from the active project view.

## UX

- Mapping edits are drafts until one `Применить сопоставление` action.
- Known chemistry columns with unresolved units open as measurement candidates, not as silent ignores.
- Per sheet, user can select a unit and apply it to all measurement candidates on that sheet.
- One bulk apply sends all changed decisions to Python; Python revises, fingerprints, validates and replans once.
- Save is disabled when draft mapping changes remain or when there are Analysis records but zero Measurements.
- Analyses page exposes `Отменить последний импорт`. Retraction is logical/auditable: imported rows remain in SQLite history but are excluded from active projections.

## Adjacent next controls

- raw source preview;
- header/data start/end editing;
- sheet enable/disable;
- normal/transposed orientation;
- persisted Mineral and Generation entities.
