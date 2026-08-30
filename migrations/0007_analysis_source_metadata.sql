PRAGMA foreign_keys = ON;

CREATE TABLE analysis_source_metadata (
    analysis_source_metadata_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    canonical_field TEXT NOT NULL,
    raw_token TEXT,
    source_header TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    source_cell TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(analysis_id, canonical_field, source_row_number, source_column_index)
);

CREATE INDEX idx_analysis_source_metadata_analysis ON analysis_source_metadata(analysis_id);
CREATE INDEX idx_analysis_source_metadata_field ON analysis_source_metadata(canonical_field, raw_token);
