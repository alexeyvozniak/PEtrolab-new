PRAGMA foreign_keys = ON;

-- Applied imports are immutable history, but a mistaken import can be retracted
-- from active project projections without deleting its provenance.
CREATE TABLE import_batch_retraction (
    retraction_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL UNIQUE REFERENCES import_batch(import_batch_id),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_import_retraction_batch ON import_batch_retraction(import_batch_id);
