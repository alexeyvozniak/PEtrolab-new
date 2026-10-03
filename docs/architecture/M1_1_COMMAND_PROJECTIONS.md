# M1.1: projections and failures

All M1.1 commands are read-only. `source_fingerprint` is SHA-256 of the exact input bytes. A response is either `result` or `error`; a UI must never parse exception text.

| Command | Result projection | Blocking errors | Warnings that permit preview |
|---|---|---|---|
| `import.inspect_source` | sheets, used ranges, headers, candidate blocks, source fingerprint | unreadable file; encrypted workbook; unsupported encoding | hidden rows, merged headers, formula cells without cached values |
| `import.recipe.validate` | normalized mapping, recognized units, Fe decision, duplicate policy, compatibility report | fingerprint mismatch; unknown unit for a mapped Measurement; unresolved Fe semantics; recipe schema mismatch | decimal comma normalized; `<DL>` token detected; missing token detected; duplicate candidates |
| `import.plan.create` | immutable planned Analysis/Measurement counts, source-row provenance, warnings, exact duplicate candidates | any blocking validation error; ambiguous column mapped twice; invalid sample/point assignment | excluded blank rows; values below detection limit retained with qualifier; rows awaiting user assignment |
| `import.recipe.bulk_scopes` | service-issued groups of unresolved measurement fields with an identical physical-field signature | invalid recipe or source fingerprint | no source or project write |
| `import.recipe.apply_bulk_unit` | revised immutable recipe after one explicit unit decision for one scope | `STALE_BULK_SCOPE`; unknown unit; recipe/source mismatch | no project write; scope is recomputed before application |
| `import.recipe.bulk_ignore_scopes` | service-issued exact set of all currently unresolved unrecognized fields; measurement candidates are excluded | invalid recipe or source fingerprint | no source or project write |
| `import.recipe.apply_bulk_ignore` | revised immutable recipe after one explicit exclude decision for one exact repeated group | `STALE_BULK_SCOPE`; recipe/source mismatch | no project write; source values remain in the immutable source file |

Stable error codes: `SOURCE_UNREADABLE`, `SOURCE_FINGERPRINT_MISMATCH`, `WORKBOOK_ENCRYPTED`, `UNSUPPORTED_ENCODING`, `UNKNOWN_UNIT`, `IRON_SEMANTICS_REQUIRED`, `RECIPE_SCHEMA_INCOMPATIBLE`, `DUPLICATE_MAPPING`, `INVALID_ASSIGNMENT`, `IMPORT_PLAN_EMPTY`, `MAPPING_REVIEW_REQUIRED`, `STALE_BULK_SCOPE`.

Non-blocking XLSX inspection warnings are `HIDDEN_ROWS`, `MERGED_HEADERS`, and `FORMULA_WITHOUT_CACHED_VALUE`. Each names the affected sheet and exact rows, ranges or cell addresses so the UI can route the user to the decision without guessing.

## Transport envelope

The Tauri shell sends exactly one UTF-8 JSON object per stdin line to the Python child. Every normal command has `protocol_version: "1.0"`, a UUID `request_id`, `command`, and an object `payload`. The response repeats `protocol_version` and `request_id`, then contains exactly one of `result` or `error`. It has no traceback. Transport errors are `INVALID_REQUEST`, `UNKNOWN_COMMAND`, `PROTOCOL_VERSION_UNSUPPORTED`, and `INTERNAL_ERROR`.

`shutdown` is the one supervisor command outside the import command table. A valid request receives `{ "result": { "status": "shutting_down" } }`, after which the child stops reading. It is not a scientific command and creates no project data.

M1.2/1.3 add `import.plan.apply`, `import.batch.rollback`, `import.recipe.save_revision` and `source.check_linked`. The apply command receives the current source and recipe rather than a mutable cached plan; it rebuilds the plan and checks the source fingerprint immediately before one SQLite transaction. A source change therefore blocks writing rather than applying an old preview. A saved revision always receives a new immutable ID and may name only a predecessor from the same Source.

The plan includes neither SQLite writes nor generated UUIDs persisted in the project. Its preview IDs are deterministic hashes of `source_fingerprint + sheet + row + mapped block`; `import.plan.apply` later assigns project UUIDs in one transaction.

`Import Recipe.ownership_mode` is an explicit domain choice: `linked_external` or `managed_copy`. SQLite serializes the first as `linked_reference`; this is an adapter enum, not a third ownership option. M1 accepts XLS, XLSX, CSV and TSV. Legacy `.xls` is parsed as BIFF through the dedicated reader and is never silently interpreted as an XLSX file.

`semantic_fingerprint` is SHA-256 of canonical JSON containing only `source_format`, `ownership_mode`, `sections` and `global_decisions`. It excludes recipe IDs, names, timestamps, migration report and source bytes. `source_file_sha256` separately protects the exact source revision. A stale or manually changed semantic fingerprint blocks validation and application.
