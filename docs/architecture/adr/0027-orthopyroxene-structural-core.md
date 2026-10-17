# ADR 0027 - Unregistered structural orthopyroxene core

2026-10-17 (prepared since 2026-10-13). Core-only research slice,
**not installed in Formula Registry**.
Master 11/20.2 and structural implementation plan; no new UI, persistence,
adapter, classifier or service command. AT-50 below distinguishes core checks
from the pending complete product path.

## Decision

Prepare a direct, separately frozen Python implementation with intended ID
`orthopyroxene.structural6/0.1.0`, without changing or importing the scientific
implementation of `orthopyroxene.oxygen6` or `clinopyroxene.structural6`.
The existing seven installed definitions/fingerprints/defaults remain intact.
Do not add it to the catalog until a suitable independently published Opx
ferric/basis benchmark and integration acceptance are obtained.

## Bounded algorithm

Numeric wt.% SiO2/Al2O3/MgO/MnO/CaO/Na2O and the chosen Fe basis are required.
Optional measured Ti/Cr/Ni/K/V/Zr/Sc/Zn/Co/Li oxide contributions retain their
declared valences and atoms. Missing, censored, duplicate, nonfinite, negative,
mixed-unit and unsupported oxide inputs reject; no synthetic zero or silently
discarded oxide. Positive F/Cl/H2O reject the anhydrous basis. Numeric anion
zeros retain Measurement IDs. Non-compositional trace exclusions retain IDs.

`all_fe2`: six oxide oxygens, exactly one FeO/FeOt, Fe3 not measured or estimated.
`reported_split`: separate FeO/Fe2O3 with compatible reported forms, six O.
`stoichiometric_droop`: total Fe as FeO, initial six-O cation sum S, scale 4/S,
Fe3 = 12*(1-4/S), residual Fe2; only Fe variable-valent, only oxygen anions,
four occupied cation positions. Impossible estimates reject, not clamp. Only
floating roundoff <=1e-10 APFU may be adjusted with an explicit warning.
Measured-split and all-Fe2 are never silently rescaled to four cations.

The generic ideal pyroxene allocation in [Yavuz 2013 p1339](https://doi.org/10.2138/am.2013.4292)
(Morimoto 1988) fills T with Si/Al/Fe3 to two; excess Al/Fe3 and declared
fixed-valence M1 elements, then Mg/Fe2/Mn to one; residual Mg/Fe2/Mn and
Li/Ca/Na/K go to M2. Si>2 rejects, deficits/overfilled positions warn without
discarding atoms or normalizing each position. Every element is conserved.
This is **not real Opx Fe-Mg ordering**, measured occupancy, symmetry,
nomenclature, end-member decomposition or thermobarometry. In particular,
Mg-first allocation of a 50/50 Mg-Fe composition is only a bookkeeping model.

Results retain full bulk/site APFU, charge, site/cation sums, used/excluded IDs,
Fe estimate basis and assumptions. `site_order=['T','M1','M2']` is explicit.
The string is rounded only for display. Wo/En/Fs are Ca/Mg/Fe2 proportions,
not species; no mass total normalization or assumed uncertainty.

## Independent evidence and limits

- Stoichiometric enstatite/ferrosilite/1:1 mixture and MgAl2SiO6 exercise atom,
  charge and ideal-position conservation without production-derived oracles.
- MgFe3AlSiO6 uses independent split-Fe oxide masses. A separate declared
  total-Fe reconstruction checks the exact Droop endpoint Fe3=1, not physical
  occurrence or independent natural Fe3 measurement.
- WinPyrox p1350 Table 5 S1 contains printed ferric bulk cations, but the paper
  labels it **En or Cen**. Its printed charge is 11.934 despite a six-O label;
  independent reference conversion uses 12/11.934 before comparison to our
  measured-split six-O basis (.003 bulk/.006 hand-allocation APFU tolerance).
  This tests a generic pyroxene calculation, **not unambiguous natural Opx**.
- WinPyrox Table 7 uses Papike Fe3 and no four-cation normalization. It must
  not be used as an expected Droop result or silently reinterpreted as split
  measured Fe.
- Published experimental E17-016 Opx lacks Mn and Fe3. The untouched input
  rejects the stricter structural contract. A clearly synthetic Mn=0 extension
  checks printed bulk values only; it is not an original measured composition.
- [Ejima et al. 2018 section 5.1](https://doi.org/10.3390/min8050204) supplies an
  independent natural Opx ferric/occupancy candidate. Its Mössbauer Fe split
  and occupancy are distinct from charge-balance and ideal allocation. Before
  use, obtain/inspect complete Table 1, units, measurement uncertainty and
  original Fe provenance. Do not reconstruct missing oxides from its formula
  and call those reconstructed inputs independent measured data.

No scientific validation promotion. Required before installation: trustworthy
complete natural Opx reference inputs, independently checked basis/Fe results,
reviewed applicability, separate Scientific Method Definition/implementation
pin, old-method coexistence, NDJSON atomic save/stale/history and existing
1363x936 inspector/native screenshots/keyboard plus bounded batch checks.
