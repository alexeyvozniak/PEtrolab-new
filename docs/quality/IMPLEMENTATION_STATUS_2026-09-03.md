# QA automation implementation status — 2026-09-03

Implemented in `chore/regression-e2e-gates`:

- separate Windows Tauri WebDriver smoke workflow;
- matching Microsoft Edge Driver installation for Windows WebDriver;
- Selenium smoke that launches the real desktop executable and checks Import ↔ Analyses navigation;
- public immutable import regression gate;
- normative registry for nine private real Excel workbooks;
- private real-corpus runner with source immutability, SHA-256 and approved-baseline enforcement;
- milestone QA policy and one-command core gate.

Not included in this slice:

- raw scientific workbooks themselves, because the repository is public;
- automatic updater/signing, which requires a separate signed-release configuration;
- full native file-picker E2E import flow; the current desktop smoke intentionally establishes the real-app automation layer first.
