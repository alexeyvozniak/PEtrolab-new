PRAGMA foreign_keys = ON;

-- A physical source field may legitimately have no header cell. Its provenance
-- remains unambiguous through source row/column coordinates and source_cell.
-- Rebuild the three early tables whose v1 schemas required a non-null header.

ALTER TABLE measurement RENAME TO measurement_old_0008;
DROP INDEX IF EXISTS idx_measurement_analysis;

CREATE TABLE measurement (
    measurement_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    canonical_field TEXT NOT NULL,
    unit TEXT NOT NULL,
    raw_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing')),
    detection_limit REAL,
    source_column_name TEXT,
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    created_at TEXT NOT NULL,
    source_row_number INTEGER,
    physical_source_column_index INTEGER,
    source_cell TEXT,
    measurement_set TEXT,
    method TEXT,
    UNIQUE(analysis_id, canonical_field, source_column_index)
);

INSERT INTO measurement (
    measurement_id, analysis_id, canonical_field, unit, raw_token, qualifier,
    detection_limit, source_column_name, source_column_index, created_at,
    source_row_number, physical_source_column_index, source_cell, measurement_set, method
)
SELECT
    measurement_id, analysis_id, canonical_field, unit, raw_token, qualifier,
    detection_limit, source_column_name, source_column_index, created_at,
    source_row_number, physical_source_column_index, source_cell, measurement_set, method
FROM measurement_old_0008;

DROP TABLE measurement_old_0008;
CREATE INDEX idx_measurement_analysis ON measurement(analysis_id);

ALTER TABLE source_row_provenance RENAME TO source_row_provenance_old_0008;
DROP INDEX IF EXISTS idx_provenance_batch_row;

CREATE TABLE source_row_provenance (
    provenance_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    source_column_name TEXT,
    raw_token TEXT,
    normalized_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing', 'not_applicable')),
    analysis_id TEXT REFERENCES analysis(analysis_id),
    UNIQUE(import_batch_id, sheet_name, row_number, source_column_name)
);

INSERT INTO source_row_provenance (
    provenance_id, import_batch_id, sheet_name, row_number, source_column_name,
    raw_token, normalized_token, qualifier, analysis_id
)
SELECT
    provenance_id, import_batch_id, sheet_name, row_number, source_column_name,
    raw_token, normalized_token, qualifier, analysis_id
FROM source_row_provenance_old_0008;

DROP TABLE source_row_provenance_old_0008;
CREATE INDEX idx_provenance_batch_row ON source_row_provenance(import_batch_id, sheet_name, row_number);

ALTER TABLE source_cell_provenance RENAME TO source_cell_provenance_old_0008;
DROP INDEX IF EXISTS idx_source_cell_provenance_analysis;
DROP INDEX IF EXISTS idx_source_cell_provenance_source;

CREATE TABLE source_cell_provenance (
    provenance_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    sheet_name TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    source_cell TEXT NOT NULL,
    source_header TEXT,
    raw_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing', 'not_applicable')),
    UNIQUE(import_batch_id, analysis_id, sheet_name, source_row_number, source_column_index, source_header)
);

INSERT INTO source_cell_provenance (
    provenance_id, import_batch_id, analysis_id, sheet_name, source_row_number,
    source_column_index, source_cell, source_header, raw_token, qualifier
)
SELECT
    provenance_id, import_batch_id, analysis_id, sheet_name, source_row_number,
    source_column_index, source_cell, source_header, raw_token, qualifier
FROM source_cell_provenance_old_0008;

DROP TABLE source_cell_provenance_old_0008;
CREATE INDEX idx_source_cell_provenance_analysis ON source_cell_provenance(analysis_id);
CREATE INDEX idx_source_cell_provenance_source ON source_cell_provenance(import_batch_id, sheet_name, source_row_number, source_column_index);
