# ADR 0023 — Draft amphibole 23 O bulk core

Date: 2026-10-03. Status: pure Python core only; not exposed in the Formula
Registry or desktop UI.

## Decision

Start the amphibole item after Cpx/Opx in the approved formula sequence with
one limited `amphibole.oxygen23/0.1.0` calculation. It accepts measured oxide
wt.% for Mg-Ca amphiboles and returns bulk cations per 23 oxygen equivalents.
There is no new adapter, state manager, database table or Tauri boundary.
Do not offer this method to users until the separate registry/preview/save
slice has its own contract and real-service acceptance test.

## Scientific boundary

[Hawthorne et al. (2012), IMA amphibole nomenclature report](https://www.frankhawthorne.com/_files/ugd/70a3a9_b5b8aceb3d5c456f99e12c346061c1e4.pdf)
defines the general amphibole formula A B₂ C₅ T₈ O₂₂ W₂. Here 23 O is a
conventional oxygen-equivalent normalization of measured oxide cations; it
does **not** identify the W anion, determine OH, or perform A/B/C/T site
allocation. Oxide moles are wt.% divided by oxide formula mass, and each
bulk cation amount is scaled by 23 / total oxide-oxygen moles. Frozen atomic
masses use the [CIAAW abridged 2024 table](https://ciaaw.org/abridged-atomic-weights.htm).
The input mass total is reported, not forced to 100%.

This first version requires positive numeric SiO2, MgO and CaO; explicit zero
is diagnosed separately from missing. FeO or FeOt is optional but, when supplied, all Fe
is explicitly treated as Fe²⁺; both forms together and Fe₂O₃/Fe₂O₃t are
rejected. F, Cl and H₂O are rejected rather than silently ignored. Missing,
censored, duplicate, negative, nonfinite, wrong-unit and unsupported oxide
inputs block calculation. Non-compositional inputs outside wt.% are listed
with Measurement IDs as exclusions. Unmeasured Fe and optional oxides are
reported as unmeasured, not imputed as zero.

The result is `draft`. It has no Fe³⁺ estimate, W-site reconstruction,
cation site allocation, end-member fractions, uncertainty or species name.
The restricted Mg-Ca scope does not cover Na amphiboles or Fe-rich Mg-free
compositions. Any broader basis requires a new reviewed method version.

## Independent checks and next slice

Ideal tremolite Ca₂Mg₅Si₈O₂₂(OH)₂ independently gives bulk Si=8, Mg=5,
Ca=2 and 15 cations on 23 oxide oxygens. [Published synthetic Ni-bearing
tremolite TN8, Table 2](https://www.mdpi.com/2079-4991/13/8/1303) gives
Si=8.0, Mg=4.4, Ca=1.6, Ni=1.0 APFU at one-decimal precision; the test
uses the paper's listed oxide wt.% and a 0.1 APFU tolerance, accounting for
rounding and reported spot variability. Tests also exercise Fe policy,
missing/censored/duplicate inputs, source immutability and finite JSON.

Next, separately connect this frozen method to the existing Formula Registry,
NDJSON preview/save/history and accepted mineral assignment. Add an AT-45
real-service and native visual check for source immutability, Measurement ID
provenance, stale result after input change, error recovery and 1363×936
layout. Do not call it validated merely because these two benchmarks pass.
