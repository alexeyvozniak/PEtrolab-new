"""Spatial areas and reversible photo links within a thin section."""

from contextlib import closing

from .import_apply import _id, _now, open_project
from .media_display import _asset_source
from .media_import import _fail, _sha256, _uuid, _validate_geometry, apply_media_import_plan, create_media_import_plan


def create_media_region(database_path, media_id, geometry):
    asset, source = _asset_source(database_path, media_id)
    if _sha256(source) != asset["source_fingerprint_sha256"]:
        _fail("SOURCE_FINGERPRINT_MISMATCH", "Снимок изменился. Откройте актуальный файл.")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        bounds = _validate_geometry(geometry, asset["width_px"], asset["height_px"])
        if bounds["kind"] == "point":
            _fail("INVALID_GEOMETRY", "Выделите прямоугольную или квадратную область.")
        count = connection.execute("""SELECT COUNT(*) FROM spatial_annotation
            WHERE thin_section_id = ? AND label IS NOT NULL""", (asset["thin_section_id"],)).fetchone()[0]
        item = {"spatial_annotation_id": _id(), "geometry_kind": bounds["kind"], "label": f"Z-{count + 1:02d}",
                **{key: bounds[key] for key in ("x_px", "y_px", "width_px", "height_px")}}
        connection.execute("""INSERT INTO spatial_annotation
            (spatial_annotation_id, thin_section_id, media_asset_id, geometry_kind, x_px, y_px, width_px, height_px,
             image_width_px, image_height_px, created_at, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["spatial_annotation_id"], asset["thin_section_id"], media_id, item["geometry_kind"], item["x_px"],
             item["y_px"], item["width_px"], item["height_px"], asset["width_px"], asset["height_px"], _now(), item["label"]))
        return item


def list_media_links(database_path, annotation_id):
    _uuid(annotation_id, "spatial_annotation_id")
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""SELECT ml.media_link_id, ml.spatial_annotation_id, ml.media_asset_id,
                   ma.display_name, ma.media_type, ma.width_px, ma.height_px, ml.created_at
            FROM media_link ml JOIN media_asset ma USING (media_asset_id)
            WHERE ml.spatial_annotation_id = ? AND ml.detached_at IS NULL
            ORDER BY ml.created_at, ml.media_link_id""", (annotation_id,))
        return [dict(row) for row in rows]


def attach_media(connection, annotation_id, media_id):
    target = connection.execute("SELECT thin_section_id, media_asset_id FROM spatial_annotation WHERE spatial_annotation_id = ?",
                                (annotation_id,)).fetchone()
    asset = connection.execute("SELECT thin_section_id FROM media_asset WHERE media_asset_id = ?", (media_id,)).fetchone()
    if target is None or asset is None:
        _fail("MEDIA_LINK_UNAVAILABLE", "Фотография или цель привязки недоступна.")
    if target["thin_section_id"] != asset["thin_section_id"] or target["media_asset_id"] == media_id:
        _fail("MEDIA_LINK_SCOPE", "Выберите другую фотографию того же шлифа.")
    connection.execute("""INSERT INTO media_link (media_link_id, spatial_annotation_id, media_asset_id, created_at)
        VALUES (?, ?, ?, ?) ON CONFLICT (spatial_annotation_id, media_asset_id) DO UPDATE SET detached_at = NULL""",
        (_id(), annotation_id, media_id, _now()))
    return connection.execute("SELECT media_link_id FROM media_link WHERE spatial_annotation_id = ? AND media_asset_id = ?",
                              (annotation_id, media_id)).fetchone()[0]


def change_media_link(database_path, annotation_id, media_id, attached):
    _uuid(annotation_id, "spatial_annotation_id")
    _uuid(media_id, "media_asset_id")
    if type(attached) is not bool:
        raise ValueError("attached")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if attached:
            return {"media_link_id": attach_media(connection, annotation_id, media_id)}
        link = connection.execute("""UPDATE media_link SET detached_at = ?
            WHERE spatial_annotation_id = ? AND media_asset_id = ? AND detached_at IS NULL RETURNING media_link_id""",
            (_now(), annotation_id, media_id)).fetchone()
        if link is None:
            _fail("MEDIA_LINK_UNAVAILABLE", "Эту связь уже сняли.")
        return {"media_link_id": link[0]}


def import_linked_photo(database_path, annotation_id, source_path, media_type, expected_fingerprint):
    _uuid(annotation_id, "spatial_annotation_id")
    with closing(open_project(database_path)) as connection:
        target = connection.execute("""SELECT ts.sample_id, s.sample_name, ts.thin_section_name
            FROM spatial_annotation a JOIN thin_section ts USING (thin_section_id) JOIN sample s ON s.sample_id = ts.sample_id
            WHERE a.spatial_annotation_id = ?""", (annotation_id,)).fetchone()
    if target is None:
        _fail("MEDIA_LINK_UNAVAILABLE", "Цель привязки недоступна.")
    plan = create_media_import_plan(database_path, [{
        "source_path": source_path, "ownership_mode": "managed_copy", "media_type": media_type,
        "sample_name": target["sample_name"], "thin_section_name": target["thin_section_name"], "placements": [],
        "sample_target": {"mode": "existing", "sample_id": target["sample_id"]},
        "expected_source_fingerprint": expected_fingerprint,
    }])
    return apply_media_import_plan(database_path, plan, attach_to=annotation_id)
