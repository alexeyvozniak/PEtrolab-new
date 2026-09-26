# ADR 0022 — Draft orthopyroxene 6 O core boundary

Date: 2026-09-26. Status: Python scientific core and independent tests only;
not yet offered by Formula Registry or desktop UI.

## Decision and limits

Continue the approved orthopyroxene item in master specification §11 and the
one-family-at-a-time roadmap M3.3. This first slice adds a standalone,
versioned `orthopyroxene.oxygen6/0.1.0` calculation. It does not add a new
screen, classification rule, Tauri command, persistence path or user-visible
method. Existing `clinopyroxene.oxygen6/0.1.0` remains byte-for-byte unchanged.
The similar calculation is deliberately frozen in a separate source file so a
future correction to one method cannot silently alter the other's pinned
implementation. A shared algorithm may be introduced only with explicit new
method versions and a reviewed migration of historical definitions.

## Scientific contract

The [IMA pyroxene nomenclature report](https://doi.org/10.3406/bulmi.1988.8099)
uses a formula unit of six oxygens or four cations. This limited method
calculates bulk cation APFU from measured oxide wt.% normalized to six oxygens,
without normalizing mass total to 100%. Frozen masses come from the
[CIAAW abridged 2024 table](https://ciaaw.org/abridged-atomic-weights.htm).
Wo–En–Fs are the Ca–Mg–Fe²⁺ proportions in mol.% only, not a species name.

SiO2, MgO, CaO and the selected Fe basis must be present and numeric. Explicit
CaO = 0 is allowed, but absent CaO is not silently replaced by zero merely
because orthopyroxene is expected to have little Ca. `all_fe2` accepts exactly
one FeO or FeOt column with all Fe assumed Fe²⁺. `reported_split` requires
measured FeO and Fe2O3. Missing, censored, duplicate, negative, nonfinite,
unsupported wt.% and mixed-unit inputs block the result. Other non-compositional
inputs are excluded with Measurement IDs. No Fe³⁺ estimate, Droop correction,
site allocation, uncertainty or nomenclature is made. The result stays `draft`.

## Independent verification

Ideal enstatite, ferrosilite and a 1:1 mixture establish exact stoichiometric
expectations without calling production code. The [experimental E17–016 Opx
analysis, Table 6](https://academic.oup.com/view-large/392420083) independently
checks APFU and Wo–En–Fs against published rounded values. Its displayed
oxide entries sum to 100.76 wt.%, although the table prints TOTAL = 100.78;
the method reports the sum of the displayed inputs and makes no unexplained
adjustment. Domain and Fe-basis failures, immutable inputs and finite JSON
outputs are also tested.

## Next vertical slice

Before exposing this method: pin its implementation SHA-256 in a bundled
Scientific Method Definition, add explicit accepted `orthopyroxene` target
gating and NDJSON preview/save/history round-trip, verify stale and original
source invariance, and complete a real-service UI scenario at 1363×936 with
screenshots. AT-44 is the planned acceptance case. Do not promote to
`validated` solely because the ideal and one published benchmark pass.
