# AT-50 - Structural Opx core, not product acceptance

Checkpoint completed 2026-10-17; preparation started 2026-10-13.

Slice based on `b74d56048ce167baca7674f60bac4a9522dae213`.
ADR 0027, Master 11/20.2. Only a new pure Python module, independent tests and
documentation; registry, seven installed definitions, service, persistence,
frontend and Tauri files unchanged. No user project or source file touched.

## Observed evidence

`tests/test_orthopyroxene_structural_formula.py`: 10 passing tests. Independent
enstatite/ferrosilite/Mg-Fe mixture, MgAl2SiO6 and MgFe3AlSiO6 endpoints check
full bulk/site numbers, charge 12 and conservation. Droop endpoint Fe3=1 is a
declared ideal transformed total-Fe case, not an independent natural iron
measurement. All optional declared oxides also have independent literal mass,
valence and oxygen-balance expectations. Inputs stay unchanged; JSON is finite.
Strict invalid inputs, unavailable Mn/Ca/Na, censored values, impossible Droop,
Si excess, anions and duplicate/incompatible Fe reject without preview values.
Nonideal site sums warn, not silently normalize.

WinPyrox actual PDF p1339/p1350/p1353 and continuation p1354 inspected.
PDF SHA256: `050ec0965cb52a5b6b03adb347db7a7d21302a3b1fd84744cc806690b94e7e94`.
Table 5 S1 labels **En or Cen**, not unambiguous Opx. The independently printed
bulk reference is converted by charge 12/11.934 to our measured-split six-O
basis; bulk tolerance .003 APFU, hand ideal-site reference .006 APFU.
Table 7 uses Papike, not a Droop oracle. Published E17-016 original input lacks
Mn and rejects this structural contract; a labelled synthetic Mn=0 extension
checks bulk arithmetic only, not the measured composition.

Ejima et al. 2018, DOI10.3390/min8050204, section5.1 is a promising independent
natural Opx ferric reference; measured Mössbauer ordering differs from ideal
Mg-first allocation. Full trustworthy Table1 data/uncertainties have not yet
been obtained/visually checked. Publisher reads returned429, USGS PDF reads403,
CLI download failed DNS; no partial OCR table has been promoted to a fixture.
No invented oxide input and no claim that Droop reproduces measured Fe3.

## Regression

- `python scripts/validate_contracts.py`: pass.
- `PYTHONPATH=src python -m unittest discover -s tests`: 249 pass.
- `npm run test:ui`: 69 pass (including 20 real-service integration tests).
- `npm run test:tauri-contract`: 26 pass.
- `npm run test:sites`: 4 pass.
- `npm run build`: pass; existing 513.89kB chunk warning unchanged.
- Existing packaged sidecar `qa_amphibole_service.py --executable
  desktop/src-tauri/binaries/petrolab-service.exe --all-methods`: all seven
  installed methods pass save/retry/history/stale/provenance/source checks.
  This executable does **not** exercise the unregistered new Opx core.
- Baseline exact-head CI b74d560: Architecture#294 and Windows#280 success.

Native UI has not changed in this slice; no new native acceptance/screenshots
are claimed. Previous AT49 screenshots remain historical baseline, not evidence
for the future installed Opx method. New module is intentionally absent from
`formula.methods.list` (explicit regression); old Opx remains the only/default
Opx method. Old Opx and Cpx structural source hashes have separate assertions.

Verdict: **core-only preparation passes; complete AT50 product path NOT accepted**.
No `validated` promotion or completed natural Opx method claim.

## Next exact slice

1. Obtain original complete independent ferric Opx oxides/units/Fe provenance,
   inspect Table1 and section5.1 of Ejima2018 or another primary unambiguous
   Opx reference. Do not invert published APFU to manufacture measured oxides.
2. Separate measured Fe split, oxide six-O normalization and physical Fe-Mg
   occupancy. Ideal ordering must not be forced to match Mössbauer occupancy.
   Review applicability/rejection policy; natural stoichiometric Fe3 failure
   may correctly reject, not clamp/relabel as measured.
3. Add original fixture + independent bulk/ferric checks; update ADR0027.
4. Install a separately pinned definition in `src/petrolab/formula_methods.py`,
   update workflow test/catalog assertions and packaged all-methods cases.
   Never change old `orthopyroxene.oxygen6/0.1.0` definition/default/runs.
5. Existing `desktop/tests/import-workspace.integration.test.jsx`: explicit Opx
   assignment, old/new selection, parameters discard preview but preserve
   error choices/history, atomic batch, save/reopen/stale, source hashes.
6. Rebuild sidecar. One isolated Tauri QA instance at1363x936: settings/sites
   closed, one main action, no clipped select/horizontal scrolling, actual
   Tab/Enter/Space and full restart history. Add report and state screenshots.
7. Commands: contracts, full unittest, UI/Tauri/Sites/build, packaged all-methods
   and batch gates. Complete product acceptance only after these proofs.
