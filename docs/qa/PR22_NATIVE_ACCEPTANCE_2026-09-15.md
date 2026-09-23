# PR 22 native acceptance — 2026-09-15

## Scope and isolation

The Windows Tauri runtime was started with an isolated application identifier,
`org.petrolab.desktop.qa20260915`, so the existing PetroLab project was not
modified. The synthetic source was `petrolab-native-qa-mica.csv`; its SHA-256
before and after the run was
`959cc915723353e5fbcf71b921282a24289c60d277010635d9881bb4c1e4aa55`.
The window was checked at 1363 × 936.

## Formula acceptance

The real runtime completed this path through the Python NDJSON service:

1. import one mica analysis and accept the high-confidence
   `trioctahedral mica` suggestion;
2. explicitly replace it with `phlogopite`, including a manual reason;
3. run the one-button default formula preview;
4. open advanced Fe, anion-basis and OH parameters;
5. change a parameter and observe the old preview disappear;
6. save the result, leave the view and reopen one saved history item;
7. request split Fe without Fe2O3 and observe an error while every selected
   parameter remains unchanged;
8. Tab from the last parameter to the calculation action and activate it with
   Enter.

At 1363 × 936 all three selected values fit inside their controls and the
page has no horizontal scroll. Compact labels are presentation metadata returned
by Python. The full method descriptions remain visible below the controls and in
saved history. No method status was changed from `draft`.

Evidence:

- [one-button preview](screenshots/pr22-mica-quick-20260915.png)
- [advanced parameters at 1363 × 936](screenshots/pr22-mica-settings-20260915.png)
- [reopened saved history](screenshots/pr22-mica-history-20260915.png)
- [error preserving selected parameters](screenshots/pr22-mica-error-20260915.png)

## Image integration finding

Folder selection, recursive discovery, SHA-256 inspection and explicit
Sample/Thin Section assignment work in the real Windows runtime. The same
isolated project exposes a cross-slice gap at the next step: the imported table
contains Analysis point identity `P-01`, but `media.points.list` returns no
`AnalyticalPoint`, so the placement screen shows `Analytical points: 0` and a
marker cannot be placed. This is deferred as a separate small integration slice;
the image flow must not invent a point in React or Tauri.

## Automated verification commands

```text
python scripts/validate_contracts.py
PYTHONPATH=src python -m unittest discover -s tests
cd desktop
npm run test:ui
npm run test:tauri-contract
npm run build
npm run test:sites
```
