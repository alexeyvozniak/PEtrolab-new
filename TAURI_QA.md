# Tauri shell QA

## Passed locally

- `npm run build` completed.
- `npm run test:sites` passed 4 tests.
- `npm run test:tauri-contract` passed 3 tests: one Python child owner, versioned frontend envelope and approved window dimensions.
- Python contract validation and 38 backend tests passed alongside the shell work.

## Blocked external gate

`npm run tauri build` invoked the Tauri CLI, then failed before compilation because this environment has neither `cargo` nor `rustc`:

```text
failed to run 'cargo metadata' ... No such file or directory (os error 2)
```

No executable, installer or browser-visible Tauri window has been claimed as verified. The next gate is to run the documented `npm run tauri dev` and `npm run tauri build` in an environment with the Rust toolchain, then execute the real import scenario and compare the rendered screen with the approved reference.

final result: blocked by missing Rust toolchain
