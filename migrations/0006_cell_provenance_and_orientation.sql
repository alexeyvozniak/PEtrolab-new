PRAGMA foreign_keys = ON;

ALTER TABLE analysis ADD COLUMN source_column_number INTEGER;
ALTER TABLE analysis ADD COLUMN source_orientation TEXT NOT NULL DEFAULT 'rows_are_analyses'
    CHECK (source_orientation IN ('rows_are_analyses', 'columns_are_analyses'));

ALTER TABLE measurement ADD COLUMN source_row_number INTEGER;
ALTER TABLE measurement ADD COLUMN physical_source_column_index INTEGER;
ALTER TABLE measurement ADD COLUMN source_cell TEXT;
ALTER TABLE measurement ADD COLUMN measurement_set TEXT;
ALTER TABLE measurement ADD COLUMN method TEXT;

CREATE TABLE source_cell_provenance (
    provenance_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    sheet_name TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    source_cell TEXT NOT NULL,
    source_header TEXT NOT NULL,
    raw_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing', 'not_applicable')),
    UNIQUE(import_batch_id, analysis_id, sheet_name, source_row_number, source_column_index, source_header)
);

CREATE INDEX idx_source_cell_provenance_analysis ON source_cell_provenance(analysis_id);
CREATE INDEX idx_source_cell_provenance_source ON source_cell_provenance(import_batch_id, sheet_name, source_row_number, source_column_index);
