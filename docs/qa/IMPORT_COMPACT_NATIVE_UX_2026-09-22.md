# Compact native import UX — 2026-09-22

## Audit scope

Bounded UX audit of the real Excel import workspace in the native Tauri runtime at 1363×936. The scientific planner, import decisions, provenance and source data were not changed.

User goal: understand what needs attention, answer one current question and save the import without reading repeated explanations.

Fixture: `fixtures/import/real-world/mica+Chl_all_zond.xlsx`

Source SHA-256 before and after the run:

`81c6978d9893da92f4fe9e32f651ca05c2a170339c8040e2da96e8bbecf1745b`

## Evidence

Before:

- [required unit question](screenshots/import-density-before-question-1363x936-20260922.png)
- [ready state](screenshots/import-density-before-ready-1363x936-20260922.png)

After:

- [quiet file chooser](screenshots/import-density-after-entry-1363x936-20260922.png)
- [one focused question](screenshots/import-density-after-question-1363x936-20260922.png)
- [compact ready state](screenshots/import-density-after-ready-1363x936-20260922.png)

## Findings and result

| Step | Before | After | Health |
| --- | --- | --- | --- |
| Open the workbook | The queue reported 48 questions while the server exposed one grouped decision. | The source, sheet and inspector all report one question. | Pass |
| Understand the next action | The same unit problem appeared in the issue list, guided card and mapping panel. | One guided card contains the question, select and action. | Pass |
| Review non-blocking information | Drawing and empty-plan advisories competed with the required decision. | Advisories are under a closed native `details` disclosure. | Pass |
| Review field mappings | Detailed mapping controls were always visible, including disabled actions. | “Поля таблицы” is closed by default and remains available on demand. | Pass |
| Inspect the source | Explanatory copy and duplicate status rows reduced the visible table area. | The physical table remains central and always visible; redundant copy and the idle structure status were removed. | Pass |
| Save | Four separate metrics and a repeated safety statement competed with the primary action. | The footer shows one compact result summary, blockers only when present, preview and the primary save action. | Pass |

## Acceptance checks

- Native Tauri runtime opened the real workbook at 1363×936.
- The initial state showed exactly one grouped unit question for 48 fields.
- Advisory and detailed field disclosures were closed by default.
- A unit could be selected with the keyboard and applied to the server-issued scope.
- The stale question disappeared after the decision and “Сохранить импорт в проект” became enabled.
- The physical Excel table stayed visible in both states.
- No application-level horizontal scrollbar appeared; only the intentionally scrollable wide source table used horizontal scrolling.
- The source SHA-256 did not change.

## Evidence limits

This pass verifies the real Windows/Tauri rendering, the grouped unit decision and the ready state for one complex workbook. It is not a complete accessibility audit and does not claim WCAG conformance. Screen-reader announcements, high-contrast mode and zoom above the supported window baseline remain separate checks.
