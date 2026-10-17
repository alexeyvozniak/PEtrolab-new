# Current-decision import focus — 2026-09-22

## Audit scope

Focused Product Design audit of two real Excel workbooks in the native Tauri runtime at 1363×936. This slice changes only how existing Python-issued import issues and bulk scopes are presented. Scientific interpretation, import decisions, provenance, persistence and source files are unchanged.

Fixtures and SHA-256 before and after the run:

- `fixtures/import/real-world/2016-05-04.xls` — `87ed1cc6a96074aa92d2dfb4f50c4ad00cbcfe1015b9588dde35a208d7ede8e8`
- `fixtures/import/real-world/MORB.xlsx` — `51e03dacb3dbdc5e60a869bfb7ccb5196069fd7c27352d8e2d4d50f3b15465cc`

## Evidence

- [before: an unrelated bulk action competes with the current Fe question](screenshots/import-bulk-ignore-noise-before-1363x936-20260922.png)
- [after: the exact Fe mapping is the only expanded field](screenshots/import-current-fe-focused-after-1363x936-20260922.png)
- [after: a bulk ignore scope becomes one direct current question](screenshots/import-bulk-ignore-current-question-1363x936-20260922.png)

## Findings and result

| Step | Finding | Result | Health |
| --- | --- | --- | --- |
| 1. Open a workbook with several unresolved issue types | A workbook-wide “ignore all unknown fields” action appeared while the user was answering an unrelated Fe question. | Only the Python scope attached to the selected issue is rendered. Unrelated bulk actions stay hidden until their issue becomes current. | Pass |
| 2. Move to the current issue | The issue queue and the physical table could point at different logical blocks until the user clicked the issue. | The first unresolved issue activates its exact source block automatically, without changing the source data. | Pass |
| 3. Resolve ambiguous Fe | Opening field settings exposed every mapping in a 46-field block. | The default view contains only the Fe mapping named by the current issue; “Все 46” keeps full inspection available. | Pass |
| 4. Review unknown fields | The same unknown-field problem appeared as a queue row, a global count and a generic bulk action. | The active server scope is one question, one short field list and one explicit “Не импортировать 1 поле” action. | Pass |
| 5. Keep the source in context | Inspector noise reduced the useful source-table area and made it harder to connect a decision to the workbook. | The immutable physical table remains central and visibly highlights the current field. There is no application-level horizontal scrollbar. | Pass |

## Acceptance checks

- Native Tauri opened both real workbooks at 1363×936.
- The current Fe question activated the exact `Cpx · таблица 2` block and showed one mapping card by default.
- Full mappings remained available through the explicit “Все” control.
- The MORB unknown field appeared as one direct bulk-ignore question with one primary action; detailed field settings stayed closed.
- The UI test covers exact block activation and server-issued bulk-ignore dispatch.
- The real Python integration test covers the one-card Fe view and preservation of raw source values.
- Both fixture hashes stayed unchanged.

## Evidence limits

This is a focused native rendering, keyboard-semantics and source-integrity check, not a WCAG-conformance claim. A screen-reader session and Windows High Contrast session were not run. The changed prompt uses a native heading and button, while detailed mappings remain reachable through native controls.
