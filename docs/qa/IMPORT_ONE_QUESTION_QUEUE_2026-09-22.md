# One-question import queue — 2026-09-22

## Audit scope

Focused Product Design audit of a second real complex workbook in the native Tauri runtime at 1363×936. This slice changes only presentation and accessibility of service-issued import questions. Scientific interpretation, import decisions, provenance and source data are unchanged.

Fixture: `fixtures/import/real-world/2016-05-04.xls`

Source SHA-256 before and after the run:

`87ed1cc6a96074aa92d2dfb4f50c4ad00cbcfe1015b9588dde35a208d7ede8e8`

## Evidence

- [before: all questions and duplicate review compete for the inspector](screenshots/import-2016-complex-baseline-1363x936-20260922.png)
- [after: one current question and compact disclosures](screenshots/import-2016-one-question-after-1363x936-20260922.png)
- [keyboard: Enter opens the remaining question queue](screenshots/import-2016-question-queue-keyboard-open-1363x936-20260922.png)

## Findings and result

| Step | Finding | Result | Health |
| --- | --- | --- | --- |
| Open the complex workbook | 24 questions and 16 duplicate groups occupied the narrow inspector at once. | One current question remains visible; the other 23 are behind “Ещё 23 вопроса”. | Pass |
| Keep the physical source in context | The source table was present but the expanded inspector competed strongly for attention. | The source table remains the central workspace while secondary queues are collapsed. | Pass |
| Review possible duplicates | The full duplicate explanation and groups appeared before structural questions were resolved. | “Проверить совпадения · 16 групп” is a separate native disclosure and no longer displaces the current question. | Pass |
| Navigate by keyboard | Disclosure focus was not visually covered by the import-specific focus rule. | Buttons, selects, inputs and summaries share a 3 px `:focus-visible` outline; Enter opens the native disclosure. | Pass |
| Announce progress | The changing question count was visual text only and the grouped unit prompt was not a heading. | Question count is a polite atomic status; the grouped unit prompt is a labelled `section` with an `h2`. | Pass |

## Acceptance checks

- Native Tauri opened `2016-05-04.xls` at 1363×936.
- Exactly one of 24 blocking questions was visible on entry.
- The remaining 23 questions, one advisory and 16 duplicate groups were closed by default.
- Keyboard focus was visible on the question disclosure and Enter opened it.
- The physical source table remained visible; there was no application-level horizontal scrollbar.
- An independent UI test covers one visible question, a closed queue, live status semantics, focus and disclosure opening; native evidence covers Enter activation.
- The source SHA-256 stayed unchanged.

## Accessibility limits

This is a focused keyboard and semantic pass, not a WCAG-conformance claim. A real screen-reader session and Windows High Contrast session were not run. Static review confirms that the changed controls use native `details`/`summary`, text plus icons rather than color alone, and an explicit focus outline. Tauri did not visibly change zoom in response to `Ctrl++` during this run, so high-zoom reflow remains an environment/runtime verification item rather than a claim of this slice.
