# Mica formula natural benchmark — 2026-09-14

## Scope

This is the first published natural-composition benchmark for
`mica.charge22/0.1.0`. It checks bulk APFU only. It does not validate site
allocation, nomenclature, OH, the oxidized `22+z` variant, or promotion of the
method from `draft`.

## Published source and provenance

A.A.T. Shabani, F. Masoudi and F. Tecce (2010), *An Investigation on the
Composition of Biotite from Mashhad Granitoids, NE Iran*, Journal of Sciences,
Islamic Republic of Iran 21(4), 321–331, Table 2.

- Open paper: https://www.sid.ir/FileServer/JE/97320100403
- Material: natural biotite from G1 Mashhad granitoids, NE Iran.
- Benchmark row: `mean`, 56 electron-microprobe analyses.
- Fe provenance: the paper documents Fe2+/Fe3+ using wet chemistry and reports
  separate FeO and Fe2O3 values.
- The source reports structural formulae on a doubled 22-oxygen basis. Expected
  cations were divided by two before comparison with PetroLab's single
  `O10W2` formula unit. Published values, not production output, define the
  expectations in `tests/test_mica_formula.py`.

Input wt.%: SiO2 36.22, TiO2 2.88, Al2O3 16.27, Fe2O3 5.08, FeO 15.61,
MnO 0.59, MgO 9.66, BaO 0.26, CaO 0.07, Na2O 0.08, K2O 9.34, F 0.76,
Cl 0.01.

## Result

| Bulk output | Published / 2 | PetroLab 0.1.0 | Absolute difference |
|---|---:|---:|---:|
| Si | 2.740 | 2.739471 | 0.000529 |
| Al total | 1.450 | 1.450285 | 0.000285 |
| Ti | 0.165 | 0.163872 | 0.001128 |
| Fe3+ | 0.290 | 0.289131 | 0.000869 |
| Fe2+ | 0.985 | 0.987375 | 0.002375 |
| Mn | 0.040 | 0.037796 | 0.002204 |
| Mg | 1.090 | 1.089178 | 0.000822 |
| Ba | 0.010 | 0.007706 | 0.002294 |
| Ca | 0.005 | 0.005673 | 0.000673 |
| Na | 0.010 | 0.011731 | 0.001731 |
| K | 0.900 | 0.901195 | 0.001195 |
| F | 0.180 | 0.181792 | 0.001792 |
| Cl | 0.000 | 0.001282 | 0.001282 |

All values agree within 0.006 APFU, a tolerance chosen from the source table's
0.01 rounding on the doubled basis plus atomic-mass rounding. OH is deliberately
not asserted because the paper does not publish OH for this row.

## Remaining acceptance boundary

The complete Rieder/IMA calculation section still has to be reviewed before
scientific acceptance. The MSA report returned HTTP 502 in this run; the
Cambridge reprint exposed only its abstract without subscription access. The
method therefore remains `draft`. The next scientific slice must verify the
conditions separating 22 positive charges from measured-H2O and oxidized
`22+z` calculations, then add at least one independently published benchmark
covering measured halogens or the applicable oxidation boundary.
