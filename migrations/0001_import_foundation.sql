-- M1 only. No future screen tables belong in this migration.
PRAGMA foreign_keys = ON;

CREATE TABLE project_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    project_schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE source_file (
    source_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('managed_copy', 'linked_reference')),
    display_name TEXT NOT NULL,
    source_fingerprint_sha256 TEXT NOT NULL,
    linked_path TEXT,
    last_verified_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('current', 'source_changed', 'unavailable')),
    created_at TEXT NOT NULL,
    CHECK ((source_kind = 'managed_copy' AND linked_path IS NULL) OR source_kind = 'linked_reference')
);

CREATE TABLE import_recipe_revision (
    recipe_revision_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_file(source_id),
    schema_version INTEGER NOT NULL,
    semantic_fingerprint_sha256 TEXT NOT NULL,
    recipe_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    supersedes_recipe_revision_id TEXT REFERENCES import_recipe_revision(recipe_revision_id)
);

CREATE TABLE import_batch (
    import_batch_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_file(source_id),
    recipe_revision_id TEXT NOT NULL REFERENCES import_recipe_revision(recipe_revision_id),
    source_fingerprint_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'applied', 'rolled_back', 'rejected')),
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    applied_at TEXT,
    CHECK ((status = 'applied' AND applied_at IS NOT NULL) OR (status != 'applied' AND applied_at IS NULL))
);

CREATE TABLE source_row_provenance (
    provenance_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    source_column_name TEXT NOT NULL,
    raw_token TEXT,
    normalized_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing', 'not_applicable')),
    UNIQUE(import_batch_id, sheet_name, row_number, source_column_name)
);

CREATE INDEX idx_import_batch_source ON import_batch(source_id);
CREATE INDEX idx_provenance_batch_row ON source_row_provenance(import_batch_id, sheet_name, row_number);
