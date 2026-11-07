# ADR 0021 — Draft clinopyroxene 6 O formula

Date: 2026-09-24. Status: implemented as a draft method.

## Decision

Add one bounded Ca-rich clinopyroxene method to the existing Python Formula
Registry and single-Analysis formula flow. No new screen, Tauri logic, database
migration or classification rule. An explicitly accepted clinopyroxene target is
required; a reported or suggested name alone does not authorize calculation.
This follows master specification §20.2, roadmap M3.3 and ADR 0019.

## Scientific scope

The [IMA pyroxene nomenclature report](https://doi.org/10.3406/bulmi.1988.8099)
uses a formula unit based on six oxygens or four cations. This slice only
normalizes measured oxide wt.% to six oxygens: oxide moles = wt.% / formula
mass; bulk element APFU = oxide moles × cations per oxide × 6 / oxygen moles.
Atomic masses are pinned from the [CIAAW abridged 2024 table](https://ciaaw.org/abridged-atomic-weights.htm).
Wo, En and Fs are 100 × Ca, Mg and Fe²⁺ divided by their sum. They are
reported in mol.% as a limited ternary diagnostic, not as a mineral name.

Required input is numeric SiO2, MgO, CaO and one explicit iron basis. Fe can
be `all_fe2` (one FeO or FeOt; all Fe assumed Fe²⁺) or `reported_split`
(separate measured FeO and Fe2O3). Missing, censored, negative, nonfinite,
duplicate, unsupported oxide or wrong-unit values block the result; absence of
optional oxides is recorded, never replaced by measured zero. Non-compositional
measurements outside wt.% are explicitly excluded with Measurement IDs.

This version does not estimate Fe³⁺, apply the Droop correction, allocate
M2/M1/T sites, calculate uncertainty or determine pyroxene nomenclature.
In particular, six-oxygen all-Fe²⁺ normalization is an explicit assumption,
not a substitute for the four-cation/charge-balance approach. It remains
`draft` even though the independent ideal endmembers and a [published
experimental clinopyroxene E16–085 table](https://academic.oup.com/view-large/392420083)
agree within the table's rounding. Scientific validation requires further
independent benchmarks and review of applicability; no status promotion is
implied by a passing test.

## Provenance and acceptance

Method ID `clinopyroxene.oxygen6`, version `0.1.0`, implementation hash,
definition fingerprint, iron mode, used/excluded inputs and source Measurement
IDs are stored through the existing immutable Calculation Run. The existing
stale check detects changed input, assignment and method. The source file and
Measurements are not rewritten. AT-43 covers the real import → explicit
mineral decision → one-click preview → save/reopen path, plus independent
Python benchmarks and source immutability.
