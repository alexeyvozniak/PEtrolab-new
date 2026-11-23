CREATE TEMP TABLE media_asset_v20 AS SELECT * FROM media_asset;
CREATE TEMP TABLE spatial_annotation_v20 AS SELECT * FROM spatial_annotation;
CREATE TEMP TABLE analytical_point_annotation_v20 AS SELECT * FROM analytical_point_annotation;
CREATE TEMP TABLE media_link_v20 AS SELECT * FROM media_link;

DELETE FROM media_link;
DELETE FROM analytical_point_annotation;
DELETE FROM spatial_annotation;
DROP TABLE media_asset;

CREATE TABLE media_asset (
    media_asset_id TEXT PRIMARY KEY,
    media_import_batch_id TEXT NOT NULL REFERENCES media_import_batch(media_import_batch_id),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('managed_copy', 'linked_reference')),
    display_name TEXT NOT NULL,
    source_fingerprint_sha256 TEXT NOT NULL UNIQUE,
    linked_path TEXT,
    managed_relative_path TEXT,
    media_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    width_px INTEGER NOT NULL CHECK (width_px > 0),
    height_px INTEGER NOT NULL CHECK (height_px > 0),
    sample_id TEXT NOT NULL REFERENCES sample(sample_id),
    thin_section_id TEXT REFERENCES thin_section(thin_section_id),
    created_at TEXT NOT NULL,
    CHECK (thin_section_id IS NOT NULL OR media_type IN ('Полевое фото', 'Ручной образец')),
    CHECK (
      (source_kind = 'managed_copy' AND linked_path IS NULL AND managed_relative_path IS NOT NULL)
      OR
      (source_kind = 'linked_reference' AND linked_path IS NOT NULL AND managed_relative_path IS NULL)
    )
);

INSERT INTO media_asset SELECT * FROM media_asset_v20;
INSERT INTO spatial_annotation SELECT * FROM spatial_annotation_v20;
INSERT INTO analytical_point_annotation SELECT * FROM analytical_point_annotation_v20;
INSERT INTO media_link SELECT * FROM media_link_v20;
CREATE INDEX idx_media_asset_sample ON media_asset(sample_id, thin_section_id);

DROP TABLE temp.media_link_v20;
DROP TABLE temp.analytical_point_annotation_v20;
DROP TABLE temp.spatial_annotation_v20;
DROP TABLE temp.media_asset_v20;
