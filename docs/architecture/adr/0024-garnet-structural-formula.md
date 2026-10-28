# ADR 0024 - Garnet structural formula, draft

Date: 2026-10-12. Existing single-analysis formula inspector, master specification
11/20.2, US-28/29 and AT-46. No new screen, adapter, database table or classifier.

## Method

`garnet.structural12/0.1.0` is an explicit anhydrous cubic silicate-garnet model.
Input numeric measured SiO2/Al2O3/MgO/MnO/CaO plus the chosen Fe basis in wt.%.
Zero is allowed except SiO2; absent required values never become measured zero.
Optional TiO2/Cr2O3/Na2O are retained. Present numeric F/Cl/H2O=0 can confirm
the restricted anhydrous basis and remain used inputs; positive/censored values
block it. Other unsupported compositional inputs, including exotic garnets,
are rejected rather than silently removed.

`all_fe2`: 12 oxide oxygens, all FeO/FeOt as Fe2+. `reported_split`: 12 oxide
oxygens from separate measured FeO/Fe2O3; totals cannot masquerade as split data.
`stoichiometric_droop`: one FeO/FeOt total, initial 12 O cations S; normalize
cation amounts by 8/S, estimate Fe3+ = 24*(1-8/S), retain Fe2+ as the remainder.
Fe is the only variable-valence element, O the only anion, eight occupied cation
sites assumed. Negative Fe3+ or Fe3+ above total Fe blocks this version (apart
from explicit roundoff <=1e-10), not a clamped plausible-looking result.
No unmeasured Mn3+, H, Li, vacancies or anion contents are inferred.

X/Y/Z assignment follows the restricted common-element sequence in
[Yavuz & Yildirim (2020), section 2.1](https://www.jgeosci.org/content/jgeosci.303_Yavuz.pdf),
which implements [Grew et al. (2013)](https://doi.org/10.2138/am.2013.4201):
Si to Z then Y; Al then Fe3+ fill Z, remainder Y; Ca/Na to X; Cr/Ti to Y;
remaining Z deficit can use Fe2+ then available Ti from overfull Y;
Mg then Fe2+ then Mn fill Y, remainder X. Element sums are preserved; capacities
and deficits are diagnosed, not silently normalized separately at each site.
The model reports estimated sites and an empirical formula, not measured
occupancy, mineral species, end-member fractions or an independent QC pass.

Frozen masses: CIAAW abridged 2024. No wt.% scaling to 100. `draft` remains.
Bulk APFU, site APFU, site sums and a dimensionless formula string are saved
through existing immutable runs. Units come from the installed definition;
history renders the saved definition, not a newer catalog. The compact formula
and any site-balance warning are visible; site detail remains collapsed in the
existing result inspector.

## Independent acceptance

Ideal pyrope/almandine/spessartine/grossular/uvarovite/andradite, majorite and
morimotoite provide stoichiometric allocation/charge tests without production
expectation generation. Table 4 SG1 (Hoinkes composition, Yavuz 2020) supplies
Si/Al/Fe3+/Fe2+/Mg/Mn/Ca = 2.938/1.972/.153/2.358/.525/.016/.039 with .003 APFU
rounding tolerance. Table 3 SG3 is not used as an acceptance oracle: its MgO=0
and positive X-Mg cannot be reproduced without changing the input.
Missing/censored/duplicate/wrong-unit/nonfinite/mixed-Fe, impossible Droop,
source/provenance, idempotence, atomic rejection, stale and reopened history
must pass through Python, real NDJSON, React and packaged/native checks.
