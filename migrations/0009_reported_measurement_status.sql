-- Additive only: old raw values, qualifiers, IDs and provenance remain intact.
-- NULL status on old imports means not classified by this parser version.
ALTER TABLE measurement ADD COLUMN value_status TEXT;
ALTER TABLE measurement ADD COLUMN reported_fe_form TEXT;
ALTER TABLE measurement ADD COLUMN fe_handling TEXT;
ALTER TABLE source_row_provenance ADD COLUMN value_status TEXT;
ALTER TABLE source_cell_provenance ADD COLUMN value_status TEXT;
