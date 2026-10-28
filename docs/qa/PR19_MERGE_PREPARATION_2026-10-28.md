# PR #19: focused merge preparation — 2026-10-28

Base head: `65ffb3229abb2c3f105d5bf8448ccb07dac4cde1`.
Status: automated regression repaired; native/visual acceptance remains open.

## User path and boundaries

A geologist opens Images, chooses files or a folder, reviews explicit Sample,
Thin Section and media-type assignments, optionally places points, reviews the
batch and explicitly applies it. File selection must open the assignment screen.
Empty folders must explain why no batch opened. Source paths, confirmations and
the review scope remain visible; only the final apply writes project records.
This repair changes neither layout nor scientific validation or persistence.

## Reproduced failure and repair

The exact original head reproduced Windows run `34839590794`: 13 failing and 11
passing UI/integration tests. App passed `onChooseFiles` to ImagesWorkspace,
whose existing prop is `onChoose`; the file button therefore had no handler.
The empty-folder message also differed from its existing regression expectation.
Both production corrections already exist in integration commit `ed1f7b7` and
are backported here without the mineral/formula integration.

After those corrections, 23 tests passed and one exposed an asynchronous review
transition: the test queried “К размещению” before the plan response rendered.
The test now awaits that button with `findByRole`, matching integration commit
`92e9a0c`. No assertion was removed and no timeout was increased.

## Verification on the repaired tree

- Contracts: pass.
- Python unittest discovery: 135 passed.
- UI: 24 passed, including five real Python NDJSON integration tests. Existing
  cases exercise file/folder entry, empty folders, point geometry, cross-Sample
  justification, review/return, duplicates and preview failure/retry.
- Tauri source contracts: 22 passed.
- Production build and Sites packaging: pass; Sites tests: 4 passed.
- `git diff --check`: pass.

Commands: `PYTHONPATH=src python scripts/validate_contracts.py`,
`PYTHONPATH=src python -m unittest discover -s tests`; from desktop:
`npm run test:ui`, `npm run test:tauri-contract`, `npm run build`,
`npm run test:sites`.

## Still required

### Follow-up from the new Windows run

Run `40730052016` on `a66b9b6` passed Python, packaged scientific service and
the repaired frontend/UI gate. It then failed in `Test Tauri shell`: the clean
runner had no `src-tauri/icons/icon.ico`. `cargo test` invokes tauri-build without
the CLI's beforeBuildCommand, where the icon was previously generated.
The workflow now runs the existing deterministic icon generator and checks its
exit status before cargo test, matching the already working #22 workflow.
No Rust logic, icon design or test assertion is changed. Icon generation and
Pillow decoding of the resulting 256×256 ICO/PNG were checked locally. Native
Rust compilation/testing remains the Windows CI gate.

Windows CI must run on the new exact head, including installer build and launch.
No Windows/native picker, real-project image transaction, narrow/wide visual
walkthrough or new screenshot is claimed by this Linux verification. The local
Vite preview started, but Chromium was unavailable and its download returned an
invalid archive, so browser visual QA is blocked in this environment.
Existing screenshots remain historical evidence, not evidence for this head.
Keep PR #19 draft pending its native and visual acceptance.
