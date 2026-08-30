PRAGMA foreign_keys = ON;

ALTER TABLE source_file ADD COLUMN managed_relative_path TEXT;
CREATE UNIQUE INDEX idx_source_managed_path ON source_file(managed_relative_path)
    WHERE managed_relative_path IS NOT NULL;
