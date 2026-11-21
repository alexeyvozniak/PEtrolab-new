ALTER TABLE spatial_annotation ADD COLUMN label TEXT;

CREATE TABLE media_link (
    media_link_id TEXT PRIMARY KEY,
    spatial_annotation_id TEXT NOT NULL REFERENCES spatial_annotation(spatial_annotation_id),
    media_asset_id TEXT NOT NULL REFERENCES media_asset(media_asset_id),
    created_at TEXT NOT NULL,
    detached_at TEXT,
    UNIQUE (spatial_annotation_id, media_asset_id)
);

CREATE INDEX idx_media_link_asset ON media_link(media_asset_id);
