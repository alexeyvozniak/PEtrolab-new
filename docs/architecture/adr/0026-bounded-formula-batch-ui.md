# ADR 0026 — Bounded formula batch in existing mineral inspector

Accepted behaviour by user, 2026-10-13. US-33/AT-49. Extends ADR-0019's
single-analysis UI, not its scientific methods, storage or scope limit.

One explicit ephemeral Selection lives in App and is passed to Analyses and
Minerals. Focus, queues, Filter and loading another page do not alter it.
Checks in Minerals add/remove IDs; a separate command selects the currently
loaded filtered rows. Hidden selected count is visible. No auto-select-all
dataset, Work Group creation, auto-pruning of unavailable IDs or hidden chunking.

The same inspector displays one batch FormulaPanel for 1–100 selected IDs.
Settings/info are closed. Python `formula.methods.list` optionally receives
project_database_path + analysis_ids and returns only common installed methods
after rereading accepted assignments; clients do not send trusted assignments.
Unaccepted/unavailable/mixed groups are explicit scope issues. Unknown method
compatibility is not inferred in React. Existing unscoped/single-label catalog
calls stay supported, with mutually exclusive scoped/label inputs.

Formula preview/save remain existing commands, one method and explicit parameter
set per whole scope, recalculated atomically by Python. Failed results retain
IDs and block save. Only one result/error is expanded at a time; a short summary
and next error navigation guide review. Explicit remove from Selection creates
a different scope and requires a new preview. No save-the-good-rows shortcut.

Scope/method/parameter changes discard the visible preview, not historical runs.
Late responses from replaced contexts cannot revive preview or overwrite choices.
Same method parameters survive scope changes; preset initializes a new method,
not every calculation. History is read from a named member of the scope;
the shared immutable run is reachable from every member.

No new adapter, bridge, wrapper, state manager, job queue, migration, formula or
scientific validation promotion. Larger/mixed-method batches remain deferred
until progress/cancellation/atomicity and scientific applicability are agreed.
