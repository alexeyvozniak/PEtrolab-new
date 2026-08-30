PRAGMA foreign_keys = ON;

CREATE TABLE analysis (
    analysis_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    source_id TEXT NOT NULL REFERENCES source_file(source_id),
    preview_id TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    block_id TEXT NOT NULL,
    identity_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(import_batch_id, preview_id)
);

CREATE TABLE measurement (
    measurement_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    canonical_field TEXT NOT NULL,
    unit TEXT NOT NULL,
    raw_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing')),
    detection_limit REAL,
    source_column_name TEXT NOT NULL,
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(analysis_id, canonical_field, source_column_index)
);

ALTER TABLE source_row_provenance ADD COLUMN analysis_id TEXT REFERENCES analysis(analysis_id);
CREATE INDEX idx_analysis_batch ON analysis(import_batch_id);
CREATE INDEX idx_measurement_analysis ON measurement(analysis_id);
