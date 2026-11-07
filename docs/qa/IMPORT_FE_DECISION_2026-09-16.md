# Ambiguous iron import decision

Scope: approved Excel-first import workspace, US-02/US-03 and AT-02/AT-03.
The slice does not convert measurements and does not move scientific rules into
React or Tauri.

## Problem reproduced

Fixture `01-tokens-and-iron.xlsx` contains a physical column `Fe (wt.%)` whose
unit is known but whose reported iron form is not. The previous UI displayed an
Fe warning while also saying that there were no fields to resolve. Reassigning
the canonical field did not update `reported_fe_form`, so formula preparation
still received unresolved iron semantics.

## Verified behaviour

- The import inspector asks one direct question: what the Fe column means.
- Reported form and unit are separate, always-visible controls.
- Choosing FeOt leaves the field visible until `Применить сопоставление` is
  invoked and clearly marks the draft as unapplied.
- The choice records `reported_fe_form=FeOt`; the raw value `10` remains `10`
  and the original header remains visible in the physical table.
- After apply, the question count becomes zero, the interpreted heading is
  `FeOt · wt.%`, and `Сохранить импорт в проект` becomes available.
- The native select accepts keyboard focus and the Home/Arrow/Enter sequence.
- The original fixture SHA-256 is unchanged before and after the flow:
  `1506C4D1C7B87EB31462494A9AC786CA4962B6B24BEF178B8F62BD57C2414CBD`.

## Native visual evidence

Runtime: Tauri development application on Windows at 1363×936.

- [Question shown with source table visible](screenshots/import-fe-decision-before-1363x936-20260916.png)
- [FeOt selected, explicit unapplied state](screenshots/import-fe-decision-pending-1363x936-20260916.png)
- [Decision applied and import enabled](screenshots/import-fe-decision-applied-1363x936-20260916.png)

No horizontal page scrolling or clipped form labels were observed in these
states. The three-pane import workspace remains information-dense, but the
blocking Fe task no longer requires opening the all-fields view or guessing
whether the unit selector controls oxidation/reporting form.

## Automated regression evidence

- Python integration coverage proves that explicit FeOt mapping is recorded,
  no conversion occurs, and original workbook bytes stay unchanged.
- React integration coverage proves the single-question flow, draft visibility,
  request payload, and source-value preservation.
- Tauri shell contracts protect the user-facing Fe decision and no-conversion
  explanation.
