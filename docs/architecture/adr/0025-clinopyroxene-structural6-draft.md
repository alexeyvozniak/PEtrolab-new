# ADR 0025 - Separate structural clinopyroxene method

2026-10-12. Master 11/20.2, US-28/29, existing single-analysis inspector.
No new screen, database migration, classifier, adapter or state manager.

Install `clinopyroxene.structural6/0.1.0` alongside unchanged
`clinopyroxene.oxygen6/0.1.0`. The old method remains the default for existing
Ca-rich assignments; select the structural method in existing settings.
The new method also accepts explicitly assigned Na/Na-Ca clinopyroxenes.

Numeric wt.% SiO2/Al2O3/MgO/MnO/CaO/Na2O and the chosen Fe basis are required;
explicit zero is distinct from absent/censored input. Optional measured
Ti/Cr/Ni/K/V/Zr/Sc/Zn/Co/Li oxides are retained with declared valences.
Positive F/Cl/H2O and unsupported oxides reject; numeric anion zeros are retained.
No missing component is turned into a measured zero. Unknown trace inputs are
explicit exclusions with IDs. No 100 wt.% normalization.

`all_fe2`: six oxide oxygens, one FeO/FeOt. `reported_split`: separate
FeO/Fe2O3, six oxygens; totals never become measured split iron.
`stoichiometric_droop`: one FeO/FeOt, initial six-O cation sum S, scale 4/S,
Fe3=12*(1-4/S), remaining Fe2. Only Fe variable-valent, only O anion and four
occupied cation sites assumed; impossible Fe3 rejects, not arbitrary clamping.
Floating roundoff <=1e-10 is the only explicitly reported adjustment.

Restricted ideal allocation from [Yavuz 2013](https://doi.org/10.2138/am.2013.4292),
p1339, implementing Morimoto 1988: T Si then Al then Fe3 to two; excess Al/Fe3
to M1, Ti/Cr/V/Zr/Sc/Zn/Ni/Co then Mg/Fe2/Mn fill M1 to one; remaining
Mg/Fe2/Mn, Li/Ca/Na/K to M2. Si>2 rejects (not silently discarded or assigned
to an unsupported site). Fixed-cation M1 overfill/site deficits warn rather
than separately normalizing positions. Every element is conserved.
This is an ideal allocation estimate, NOT temperature-dependent Fe-Mg partition
of Nimis (2000), measured occupancy, species or thermobarometry.
Wo/En/Fs are only Ca/Mg/Fe2 ternary diagnostics, absent when denominator zero.

Fe3 estimates, original input IDs, full unrounded bulk/site values, charge and
site sums, rounded display string, parameters and definition fingerprints use
existing immutable history. Python supplies site names and an explicit
`site_order` array; JSON object key order is not a transport contract because
Tauri serde may alphabetize it. React only displays this supplied order.
Method stays draft; no scientific validation or nomenclature promotion.

Independent benchmarks: diopside/hedenbergite/jadeite/aegirine/Ca-Tschermak
stoichiometry, impossible Droop; WinPyrox Table 5 S4 (Rock 1990 composition)
bulk printed Si1.788/Al.271/Fe3.237/Fe2.248/Mg.465/Ca.835/Na.102.
The printed default four-cation values have charge 12.064 despite a "6 oxygen"
label. An independent reference conversion multiplies them by 12/12.064 for
our measured-split six-O basis, tolerance .003 APFU. Site oracle is hand
allocation from those converted values; Table 5 Nimis partition rows and Table 6 Papike iron values
are NOT oracles for this different model. A separate independent total-Fe
reconstruction of S4 checks Droop charge/element balance, NOT reproduction of
the independently supplied ferric fraction (which differs from the estimate),
explicitly documented as a transformed test input, not original measured FeOt.
AT-48 includes old/new switching, atomic save/history, unchanged source,
real NDJSON/UI/packaged/native screenshots and keyboard at 1363x936.
