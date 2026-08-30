PRAGMA foreign_keys = ON;

ALTER TABLE analysis ADD COLUMN source_orientation TEXT NOT NULL DEFAULT 'rows' CHECK (source_orientation IN ('rows', 'columns'));
ALTER TABLE analysis ADD COLUMN source_record_index INTEGER;
UPDATE analysis SET source_record_index = source_row_number WHERE source_record_index IS NULL;

ALTER TABLE measurement ADD COLUMN source_row_number INTEGER;
ALTER TABLE measurement ADD COLUMN source_cell_reference TEXT;
UPDATE measurement
SET source_row_number = (
    SELECT a.source_row_number FROM analysis a WHERE a.analysis_id = measurement.analysis_id
)
WHERE source_row_number IS NULL;

CREATE TABLE source_row_provenance_v2 (
    provenance_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    source_column_index INTEGER NOT NULL CHECK (source_column_index >= 0),
    source_column_name TEXT NOT NULL,
    source_cell_reference TEXT,
    raw_token TEXT,
    normalized_token TEXT,
    qualifier TEXT CHECK (qualifier IN ('below_detection_limit', 'missing', 'not_applicable')),
    analysis_id TEXT REFERENCES analysis(analysis_id),
    UNIQUE(import_batch_id, sheet_name, row_number, source_column_index)
);

INSERT INTO source_row_provenance_v2 (
    provenance_id, import_batch_id, sheet_name, row_number, source_column_index,
    source_column_name, source_cell_reference, raw_token, normalized_token, qualifier, analysis_id
)
SELECT
    p.provenance_id,
    p.import_batch_id,
    p.sheet_name,
    p.row_number,
    COALESCE((
        SELECT MIN(m.source_column_index)
        FROM measurement m
        WHERE m.analysis_id = p.analysis_id AND m.source_column_name = p.source_column_name
    ), 0),
    p.source_column_name,
    NULL,
    p.raw_token,
    p.normalized_token,
    p.qualifier,
    p.analysis_id
FROM source_row_provenance p;

DROP TABLE source_row_provenance;
ALTER TABLE source_row_provenance_v2 RENAME TO source_row_provenance;
CREATE INDEX idx_provenance_batch_row ON source_row_provenance(import_batch_id, sheet_name, row_number, source_column_index);
