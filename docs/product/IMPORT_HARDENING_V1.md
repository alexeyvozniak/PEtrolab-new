# Import hardening acceptance — 2026-09-05

Implementation of Scientific Rules and AT-02/03; no concentration substitution,
Fe conversion, mineral assignment or new Sample identity rule is introduced.

An empty identity after mapping blocks planning readiness and apply. Existing
source-row recipe identity remains a provenance label, not an invented Sample.
Both row- and column-oriented records are checked after mapping and exclusions.

`value_status` records notation: `numeric`, `missing`, `below_detection_limit`,
`not_determined` (literal n.d./nd, not an assertion of below detection), or
`non_numeric`. Raw tokens are retained. `<0.01` keeps its numeric limit;
`<DL`/bdl have no invented limit. No numeric concentration is imputed.

Fe is strictly as reported, with no conversion. `reported_fe_form` is based on
the physical header, not a renamed canonical field. Ambiguous Fe remains
`unresolved`, accompanied by a visible nonblocking FE_STRICTLY_REPORTED warning.
The legacy recipe `preserve_reported_form_for_review` never establishes valence.

Migration 0009 only adds nullable status/Fe columns. Old imports remain unchanged
and NULL means no classification by the new parser. Existing databases receive
a SQLite backup before pending migrations. Plan JSON retains these same statuses.

Regression gates: identity Ignore/fix/apply, blank identity cells, transposed
identity, all requested tokens through plan/SQLite/provenance, Fe source forms,
unchanged source hashes, existing single-source import tests, visible UI blocker.
