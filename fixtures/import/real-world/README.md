# PetroLab real-world import corpus

This directory is the normative regression corpus supplied by the project
owner. The original workbooks are kept byte-for-byte in Git and must never be
rewritten by an import test. `manifest.json` records their immutable SHA-256
fingerprints and the expected first-pass import projection.

The corpus intentionally includes difficult structures: legacy BIFF `.xls`,
multiple logical tables on one sheet, transposed candidates, repeated headers,
merged cells, measurement-only tables, duplicate identities, explicit unit
ambiguity and Cyrillic paths.

`tests/test_normative_raw_corpus.py` runs the same inspection, classification,
recipe suggestion, bulk-scope and plan creation code used by the desktop
application. A changed projection requires an explicit manifest revision and a
corresponding QA explanation.
