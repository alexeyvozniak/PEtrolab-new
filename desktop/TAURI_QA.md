# Tauri Windows verification — 2026-09-06

## Verified baseline

Node 24.19.0 / npm 11.17.0, Rust/Cargo 1.98.1 with MSVC tooling,
Python 3.14.3 and editable PetroLab core are installed locally.
The PyInstaller service and generated Tauri icons are present.

Previous baseline: 93 Python tests, 3 UI tests, 17 Tauri source-contract tests.
Verified now: contract validation, 129 Python tests, 9 UI tests, 19 Tauri
source-contract tests, production frontend build and 4 Sites tests pass.
The UI suite includes 5 integration tests using the actual Python NDJSON service
and temporary databases, alongside 4 mocked boundary/UI tests.

Run `npm run build` **before** `npm run test:sites`: the fourth Sites test
checks generated artifacts. After building, all 4 Sites tests pass.

## Native development runtime

The existing `npm run tauri dev` process was verified: one Vite server on
127.0.0.1:1420, Cargo, a responsive PetroLab Tauri window, WebView2 and the
Python NDJSON child service. The real interface displayed 4 sources,
4 imports and 297 analyses. Do not start a second Vite alongside Tauri dev.

Vite must ignore `**/src-tauri/target/**` and `**/src-tauri/binaries/**`.
Windows locks generated executables/DLLs; watching them can cause EBUSY.
The contract test checks artifacts are excluded while App.jsx and
src-tauri/src/lib.rs remain eligible for watching.

## Separate release gate

Debug Tauri uses `python -m petrolab.ndjson_service`, not the packaged
PyInstaller executable. A dev launch does not prove installer installation,
bundled service startup or a clean-machine run. Those require a separate
packaged Windows smoke test. Tauri contract tests inspect source/configuration;
UI integration tests do not substitute for native import acceptance.

## Native import acceptance

Real 2023-07-10.xlsx, a second source, raw detection-limit tokens, semantic range
preview/confirmation/undo and grouped mineral acceptance were inspected in Tauri.
The supported 1180 x 800 minimum window keeps physical data, range controls and
the commit bar visible; long tables and range controls scroll independently.
The existing project still has 297 analyses and all 17 pre-migration data tables
match their pre-v10 backup on their original columns (read-only comparison).
See ../docs/qa/SEMANTIC_IMPORT_VERIFICATION_2026-09-06.md for evidence and limits.
