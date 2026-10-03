# ADR 0020 — Mica 22-charge calculation, core slice

Date: 2026-09-14. Status: draft method, Python core only.

## Design and scope

Continues the mica item in PR #21's description and master specification §11.
The approved method → explicit assumptions → preview → save flow remains the UI
target (ADR 0019). This slice adds the independent calculation and its tests;
the method is not advertised in the desktop registry until the next service/UI
slice can carry all its parameters and provenance. No new screen or migration.

## Scientific contract

Rieder et al. (1998), Nomenclature of the Micas, Canadian Mineralogist 36,
905–912; [MSA report](https://minsocam.org/msa/ima/ima98%2810%29.pdf).
The indexed primary-source text specifies 22 positive charges for an assumed
ideal anion group when H2O is unavailable. The complete PDF could not be fetched
in this session (HTTP 502); review its complete calculation section before
external scientific acceptance. This is not the measured-H2O or oxidized,
deprotonated 22+z variant. Neither is silently selected from Fe3+ or Ti content.

For oxide j, n_j = wt_j / molar_mass_j; cation moles = n_j * cation_count_j.
Q = sum(cation_moles * valence); APFU = cation_moles / Q * 22.
Atomic masses are pinned from the [CIAAW abridged 2024 table](https://ciaaw.org/abridged-atomic-weights.htm),
accessed 2026-09-14. F and Cl use elemental masses and the same scale;
they do not enter the positive-cation-charge denominator. No mass-total scaling.

Required explicit parameters: fe_mode (all_fe2 or reported_split),
anion_basis = ideal_O10_W2, oh_mode (not_calculated or ideal_2_minus_f_cl).
The latter estimates OH = 2 - F - Cl only with both measured halogens, including
explicit numeric zeros; absent or censored halogens never become zero.
The output labels this as OH_est_apfu and includes OH_est_basis and the exact
Measurement IDs. A halogen occupancy over 2 is an incompatibility error; tiny
floating-point excess <=1e-10 is reported and clamped only for this OH estimate.

Require SiO2, Al2O3, MgO, K2O and the chosen iron basis; zeros are allowed except
SiO2 must be positive. This is a conservative input gate, not a classifier.
Optional Ti/Cr/Mn/Ni/Ca/Na/Li/Ba and F/Cl are retained when measured; absent
components are listed as unmeasured. Missing Li is explicitly warned about.
Unsupported wt.% inputs (including H2O and Fe2O3t) reject the calculation;
non-compositional fields outside wt.% are excluded with their Measurement IDs.
Present missing/censored supported components reject the result. Original Fe
form is checked, so renamed total iron cannot masquerade as measured split Fe.

Outputs: bulk element APFU, cation sum, used oxide total, optional measured
F/Cl APFU, optional estimated OH, explicit assumptions/used/excluded/unmeasured.
No tetrahedral/octahedral allocation, vacancies, nomenclature, end-member
fractions, inferred Fe3+, inferred Li, or uncertainty are produced in this slice.
Charge closure follows from normalization and is not an independent quality test.

## Acceptance and continuation

Independent ideal phlogopite, annite, muscovite, fluorophlogopite and mixed
Ti/Fe3+ compositions; incomplete halogens; invalid iron forms; invalid values,
units and duplicates; unchanged input objects; finite JSON outputs.
Full Python suite and contract validation are required. No UI pixels change,
so existing UI screenshots are not presented as mica acceptance evidence.

Next small slice: add versioned mica definition and method-specific dispatch in
formula_methods.py/formula_workflow.py; retain olivine fingerprints, select the
correct definition when checking historical runs, and persist OH provenance.
Then extend FormulaPanel with explicit anion/OH choices and real-service tests.
Use the updated PR description as the working checklist, not a full PR/main audit.
