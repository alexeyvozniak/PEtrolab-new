PRAGMA foreign_keys = ON;

CREATE TABLE sample (
    sample_id TEXT PRIMARY KEY,
    sample_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE thin_section (
    thin_section_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL REFERENCES sample(sample_id),
    thin_section_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(sample_id, thin_section_name)
);

CREATE TABLE analytical_point (
    analytical_point_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL REFERENCES sample(sample_id),
    point_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(sample_id, point_name)
);

CREATE TABLE analytical_point_analysis (
    analytical_point_id TEXT NOT NULL REFERENCES analytical_point(analytical_point_id),
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    link_type TEXT NOT NULL CHECK (link_type IN ('same_point', 'same_grain', 'same_zone', 'repeat_measurement')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (analytical_point_id, analysis_id)
);

CREATE TABLE media_import_batch (
    media_import_batch_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('applied', 'rejected')),
    semantic_fingerprint_sha256 TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    applied_at TEXT
);

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
    thin_section_id TEXT NOT NULL REFERENCES thin_section(thin_section_id),
    created_at TEXT NOT NULL,
    CHECK (
      (source_kind = 'managed_copy' AND linked_path IS NULL AND managed_relative_path IS NOT NULL)
      OR
      (source_kind = 'linked_reference' AND linked_path IS NOT NULL AND managed_relative_path IS NULL)
    )
);

CREATE TABLE spatial_annotation (
    spatial_annotation_id TEXT PRIMARY KEY,
    thin_section_id TEXT NOT NULL REFERENCES thin_section(thin_section_id),
    media_asset_id TEXT NOT NULL REFERENCES media_asset(media_asset_id),
    geometry_kind TEXT NOT NULL CHECK (geometry_kind IN ('point', 'rectangle', 'square')),
    x_px REAL NOT NULL CHECK (x_px >= 0),
    y_px REAL NOT NULL CHECK (y_px >= 0),
    width_px REAL,
    height_px REAL,
    image_width_px INTEGER NOT NULL CHECK (image_width_px > 0),
    image_height_px INTEGER NOT NULL CHECK (image_height_px > 0),
    created_at TEXT NOT NULL,
    CHECK (
      (geometry_kind = 'point' AND width_px IS NULL AND height_px IS NULL)
      OR
      (geometry_kind IN ('rectangle', 'square') AND width_px > 0 AND height_px > 0)
    )
);

CREATE TABLE analytical_point_annotation (
    analytical_point_id TEXT NOT NULL REFERENCES analytical_point(analytical_point_id),
    spatial_annotation_id TEXT NOT NULL REFERENCES spatial_annotation(spatial_annotation_id),
    cross_sample_exception INTEGER NOT NULL CHECK (cross_sample_exception IN (0, 1)),
    exception_reason TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (analytical_point_id, spatial_annotation_id),
    CHECK (
      (cross_sample_exception = 0 AND exception_reason IS NULL)
      OR
      (cross_sample_exception = 1 AND length(trim(exception_reason)) > 0)
    )
);

CREATE INDEX idx_media_asset_sample ON media_asset(sample_id, thin_section_id);
CREATE INDEX idx_annotation_asset ON spatial_annotation(media_asset_id);
CREATE INDEX idx_point_analysis_analysis ON analytical_point_analysis(analysis_id);
