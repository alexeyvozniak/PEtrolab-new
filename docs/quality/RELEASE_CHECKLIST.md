# Release QA checklist

Before a PetroLab milestone/release:

- architecture/contracts are green;
- full Python test suite is green;
- frontend contracts are green;
- Windows real Desktop E2E is green;
- Windows installer smoke is green;
- private normative real-workbook corpus passes with `--require-all` and an approved baseline;
- no raw private workbook or private baseline is tracked by Git.
