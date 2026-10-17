# Whitespace-only rows do not become Analyses

This is a small follow-up to the server-issued bulk unit decision. It preserves
the Import Workspace requirements in ADR 0014 and AT-02/AT-03: the user sees a
stable physical Excel table, resolves only real questions, and the original
workbook remains immutable.

## Reproduced defect

In `fixtures/import/real-world/mica+Chl_all_zond.xlsx`, row 37 of the third
detected block has no identity and only a whitespace token in a measurement
cell. Before unit mapping, that cell is ignored. After the legitimate `wt.%`
bulk decision it becomes a Measurement, so the old planner incorrectly created
an empty Analysis and blocked the user with `ANALYSIS_IDENTITY_REQUIRED`.

The user could not act on that inspector message: mappings were already
resolved, while the physical source row was only whitespace.

## Decision

The Python planner treats a row whose mapped values are all `None`, empty, or
whitespace-only strings as physically blank. It does not create an Analysis,
an identity issue, a duplicate candidate, or provenance for that row. Numeric
zero remains a value. No source bytes are trimmed or rewritten.

## Native acceptance at 1363×936

1. Before the bulk decision, the physical source and the single direct unit
   question remain together:
   [`identity-whitespace-before-1363x936-20260921.png`](screenshots/identity-whitespace-before-1363x936-20260921.png).
2. The former impossible identity blocker appears after `wt.%` in the
   unpatched behavior:
   [`identity-whitespace-problem-1363x936-20260921.png`](screenshots/identity-whitespace-problem-1363x936-20260921.png).
3. With the fix, the same one-click unit decision leaves zero required
   decisions, 22 planned Analyses, 352 Measurements, and the clear final
   action “Сохранить импорт в проект”:
   [`identity-whitespace-fixed-1363x936-20260921.png`](screenshots/identity-whitespace-fixed-1363x936-20260921.png).

The source SHA-256 before and after is
`81C6978D9893DA92F4FE9E32F651CA05C2A170339C8040E2DA96E8BBECF1745B`.

## Regression coverage

- `tests/test_import_workspace.py` creates a CSV with a whitespace-only
  trailing row and proves it produces one Analysis, no identity issue, and no
  source mutation.
- A local real-workbook check applies the service-issued `wt.%` scope and
  proves the workspace is ready without `ANALYSIS_IDENTITY_REQUIRED`.
