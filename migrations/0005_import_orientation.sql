PRAGMA foreign_keys = ON;

ALTER TABLE analysis ADD COLUMN source_orientation TEXT NOT NULL DEFAULT 'rows' CHECK (source_orientation IN ('rows', 'columns'));
ALTER TABLE analysis ADD COLUMN source_record_index INTEGER;
UPDATE analysis SET source_record_index = source_row_number WHERE source_record_index IS NULL;

ALTER TABLE measurement ADD COLUMN source_row_number INTEGER;
ALTER TABLE measurement ADD COLUMN source_cell_reference TEXT;
UPDATE measurement SET source_row_number = 1 WHERE source_row_number IS NULL;

ALTER TABLE source_row_provenance ADD COLUMN source_column_index INTEGER;
ALTER TABLE source_row_provenance ADD COLUMN source_cell_reference TEXT;
