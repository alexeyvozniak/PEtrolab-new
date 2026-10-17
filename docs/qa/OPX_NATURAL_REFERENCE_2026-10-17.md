# AT-50 follow-up - independent natural Opx reference

Follows core checkpoint `16ac85f3f981224261b129b7c29caa91b2d742fb`.
The earlier core report is historical; the missing complete natural reference
has now been obtained. Still **not installed in registry/UI**, not full AT50.

## Primary evidence

Ejima et al. (2018), Minerals8(5)204, DOI10.3390/min8050204. The actual
[publisher PDF v3](https://mdpi-res.com/d_attachment/minerals/minerals-08-00204/article_deploy/minerals-08-00204-v3.pdf?version=1526551017)
was downloaded successfully using PowerShell Invoke-WebRequest (curl/git CLI
DNS still fails). SHA256:
`9731cce739581d572d5bac300995d14a1282c3970ca6e03b64b3cf51fca8e269`.
PDF skill: rendered pp5/11/12 and visually compared Table1 orthopyroxene mean,
standard deviations, footnote total Fe as FeO, and section5.1 Fe provenance.
The reference is an n=22 mean, not one independent analytical spot.

## Finished checks

`fixtures/formula/orthopyroxene_tariat2018_reference.json` retains the original
oxide means/standard deviations, printed and summed totals, original rounded
APFU, independent ferric fraction with stated uncertainty, authors' recast
iron oxides and separate physical occupancy. No production-generated oracle,
missing oxide inferred from APFU, fitted input or forced mass normalization.

Four independent tests in `tests/test_orthopyroxene_natural_reference.py`:

1. Original total-Fe input reproduces published bulk APFU within.001; sums99.84
   rather than replacing this with printed99.83. Fe3 is not measured zero.
2. Authors' recast FeO5.07/Fe2O3=1.00 reproduces published bulk/ferric APFU
   within.001 and independently measured ferric fraction0.15 within.01. These
   Fe oxides are explicitly **published derived values** from combined EPMA
   and Mossbauer measurements, not directly measured separate oxide columns.
   Fixture-level provenance is retained in used inputs; no new domain field
   or production conversion was introduced. Structural-core Fe wording no
   longer falsely asserts direct measurements for this input basis.
3. Droop on original total Fe gives ferric fraction<.001, far from measured.15.
   The calculation must retain this estimate/provenance and explicit caveat;
   do not force it to match the measured split or promote scientific status.
4. Source fixture and inputs remain unchanged, old Opx hash/default remain.

Ideal Mg-first M1/M2 Fe2 differs by>.04 APFU from the independently constrained
physical positions. This is an asserted model limit, not a tuned tolerance.
The abbreviated printed formula omits Ni and prints different Mn; both actual
Table1 components are conserved rather than deleted to obtain agreement.
Site sums remain diagnostic, not forcibly normalized to four cations.

## Regression / acceptance scope

Targeted old/core/natural Opx tests:18 pass (14 core/natural +4 old).
Full regression: contracts pass,253 Python,69 UI (20 real-service integration),
26 Tauri,4 Sites,build pass; existing513.89kB chunk warning unchanged.
Existing packaged all-methods gate passes for the seven installed methods.
Exact resulting commit/CI status is recorded in PR22. UI and installed catalog
were unchanged; this packaged gate does not exercise the unregistered core.
No new native screenshots or completed native/product acceptance are claimed.

Verdict: **natural-reference numerical/provenance slice passes; product AT50
still NOT accepted; all methods remain draft**.

## Next bounded product slice

Use this complete reference to finish applicability/Fe-input provenance review.
Add an independent Scientific Method Definition/implementation pin and only
then install Opx structural alongside the unchanged default oxygen6. Existing
`formula_methods.py`, new workflow test, all-methods packaged gate and
`desktop/tests/import-workspace.integration.test.jsx` must cover actual target
gating, old/new histories, Fe parameters, 1-100 exact IDs, atomic errors/retry,
stale detection, units/Measurement provenance and source immutability.
Rebuild sidecar and verify the existing inspector in an isolated Tauri profile
at1363x936 with actual screenshots, Tab/Enter/Space and full restart history.
Commands: contracts; full unittest; UI/Tauri/Sites/build; packaged all-methods
and batch gates. No new screen, scientific formula in React, forced Fe-Mg fit
or validated promotion is authorized by a passing numerical benchmark.
