PRAGMA foreign_keys = ON;

CREATE TABLE import_workspace_commit (
    workspace_commit_id TEXT PRIMARY KEY,
    source_count INTEGER NOT NULL CHECK (source_count > 0),
    draft_revision INTEGER NOT NULL CHECK (draft_revision >= 0),
    status TEXT NOT NULL CHECK (status IN ('planned', 'applied', 'rolled_back', 'rejected')),
    created_at TEXT NOT NULL,
    applied_at TEXT,
    CHECK ((status = 'applied' AND applied_at IS NOT NULL) OR (status != 'applied' AND applied_at IS NULL))
);

ALTER TABLE import_batch ADD COLUMN workspace_commit_id TEXT REFERENCES import_workspace_commit(workspace_commit_id);
CREATE INDEX idx_import_batch_workspace_commit ON import_batch(workspace_commit_id);

CREATE TABLE import_workspace_draft (
    workspace_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    draft_revision INTEGER NOT NULL CHECK (draft_revision >= 0),
    draft_json TEXT NOT NULL,
    source_fingerprints_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_import_workspace_draft_updated ON import_workspace_draft(updated_at DESC);
