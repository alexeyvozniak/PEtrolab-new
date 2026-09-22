# Sequential import decisions — 2026-09-22

## Audit scope

Focused Product Design audit of the real `2016-05-04.xls` workbook in the native Tauri runtime at 1363×936. This slice changes only how existing Python-issued import decisions are presented. Scientific interpretation, grouping, provenance, persistence and source data are unchanged.

Source SHA-256 before and after the run:

`87ed1cc6a96074aa92d2dfb4f50c4ad00cbcfe1015b9588dde35a208d7ede8e8`

## Evidence

- [before: issue queue, advisory and field settings compete at once](screenshots/import-sequential-before-1363x936-20260922.png)
- [after: one Fe question, one choice and one primary action](screenshots/import-sequential-after-1363x936-20260922.png)
- [answer ready: the explicit Fe choice enables Save answer](screenshots/import-sequential-answer-ready-1363x936-20260922.png)
- [next question: save advances the source highlight and decrements the count](screenshots/import-sequential-next-question-1363x936-20260922.png)

## Findings and result

| Step | Finding | Result | Health |
| --- | --- | --- | --- |
| 1. Open a complex workbook | The inspector showed the current issue, the remaining queue, advisories, field settings and duplicate review together. | While blocking decisions remain, the inspector shows only the current question and its answer controls. | Pass |
| 2. Answer ambiguous Fe | Role, unit, method and every field in the block competed with the actual Fe-form decision. | The default question shows only the Fe-form select, confirms the detected unit and states that source numbers are unchanged. | Pass |
| 3. Keep an escape hatch | A simplified flow must not prevent correcting an incorrect role or unit, or assigning different units inside a suggested group. | `Изменить роль или единицу` and `Задать единицы отдельно` reveal the existing Python-backed mapping controls only when requested. | Pass |
| 4. Save the answer | The user could not see a clear question-to-question rhythm among simultaneous panels. | `Сохранить ответ` applies one decision, the count changes from 24 to 23, and the physical source highlight moves from column N to column AR. | Pass |
| 5. Preserve source context | The workbook must remain the primary workspace during difficult import. | The physical spreadsheet remains central throughout the decision, save and next-question states; no application-level horizontal scrollbar is visible. | Pass |

## Acceptance checks

- Native Tauri opened the real workbook at 1363×936.
- Exactly one blocking question and its answer controls were visible in the right inspector.
- Queued questions, advisories, duplicate review and generic field settings were absent while the current question was unresolved.
- Choosing `FeOt` enabled `Сохранить ответ`; saving reduced the count from 24 to 23 and moved source context to the next Fe column.
- Grouped unit decisions retain an explicit per-field alternative without exposing all fields by default.
- Real Python integration tests verify per-field fallback, Fe preservation, decision persistence and automatic advance.
- The fixture hash stayed unchanged; the test import was not committed to the project.

## Evidence limits

This is a focused native rendering, source-integrity and keyboard-semantics check, not a WCAG-conformance claim. A screen-reader session and Windows High Contrast session were not run. The changed flow uses native headings, selects and buttons, and the automated UI suite verifies focusable controls and enabled/disabled action states.
