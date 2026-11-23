"""M2 batch media import and source-coordinate point placement.

The module owns validation and persistence projections. It checks whether source
pixels can be decoded and does not know about viewport zoom.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import struct
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError


MEDIA_FORMATS = {
    ".png": ("image/png", "png"),
    ".jpg": ("image/jpeg", "jpeg"),
    ".jpeg": ("image/jpeg", "jpeg"),
    ".tif": ("image/tiff", "tiff"),
    ".tiff": ("image/tiff", "tiff"),
    ".bmp": ("image/bmp", "bmp"),
}
STANDARD_MEDIA_TYPES = {"BSE", "PPL", "XPL"}
SAMPLE_PHOTO_TYPES = {"Полевое фото", "Ручной образец"}
OWNERSHIP_MODES = {"managed_copy", "linked_external"}
LINK_TYPES = {"same_point", "same_grain", "same_zone", "repeat_measurement"}


def _fail(code: str, message: str, **details: Any) -> None:
    raise ImportCommandError(code, message, details or None)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        _fail("MEDIA_UNREADABLE", "PNG header is invalid.", path=str(path))
    return struct.unpack(">II", header[16:24])


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    with path.open("rb") as source:
        if source.read(2) != b"\xff\xd8":
            _fail("MEDIA_UNREADABLE", "JPEG header is invalid.", path=str(path))
        while True:
            byte = source.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            while byte == b"\xff":
                byte = source.read(1)
            if not byte:
                break
            marker = byte[0]
            if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            length_bytes = source.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                break
            if marker in sof_markers:
                body = source.read(5)
                if len(body) != 5:
                    break
                height, width = struct.unpack(">HH", body[1:5])
                return width, height
            source.seek(length - 2, 1)
    _fail("MEDIA_UNREADABLE", "JPEG dimensions are unavailable.", path=str(path))


def _tiff_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(8)
        if len(header) != 8 or header[:2] not in {b"II", b"MM"}:
            _fail("MEDIA_UNREADABLE", "TIFF header is invalid.", path=str(path))
        endian = "<" if header[:2] == b"II" else ">"
        if struct.unpack(endian + "H", header[2:4])[0] != 42:
            _fail("MEDIA_UNREADABLE", "TIFF magic number is invalid.", path=str(path))
        source.seek(struct.unpack(endian + "I", header[4:8])[0])
        count_bytes = source.read(2)
        if len(count_bytes) != 2:
            _fail("MEDIA_UNREADABLE", "TIFF IFD is unavailable.", path=str(path))
        count = struct.unpack(endian + "H", count_bytes)[0]
        values: dict[int, int] = {}
        for _ in range(count):
            entry = source.read(12)
            if len(entry) != 12:
                break
            tag, value_type, value_count = struct.unpack(endian + "HHI", entry[:8])
            if tag not in {256, 257} or value_count != 1 or value_type not in {3, 4}:
                continue
            values[tag] = struct.unpack(endian + ("H" if value_type == 3 else "I"), entry[8:10] if value_type == 3 else entry[8:12])[0]
        if 256 in values and 257 in values:
            return values[256], values[257]
    _fail("MEDIA_UNREADABLE", "TIFF dimensions are unavailable.", path=str(path))


def _bmp_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(26)
    if len(header) != 26 or header[:2] != b"BM":
        _fail("MEDIA_UNREADABLE", "BMP header is invalid.", path=str(path))
    width, height = struct.unpack("<ii", header[18:26])
    return abs(width), abs(height)


def inspect_media_source(source_path: str | Path) -> dict[str, Any]:
    path = Path(source_path)
    if not path.is_file():
        _fail("MEDIA_UNREADABLE", "Media source is unavailable.", path=str(path))
    suffix = path.suffix.lower()
    if suffix not in MEDIA_FORMATS:
        _fail("MEDIA_FORMAT_UNSUPPORTED", "Only PNG, JPEG, TIFF and BMP images are supported.", path=str(path), suffix=suffix)
    mime_type, format_name = MEDIA_FORMATS[suffix]
    readers = {"png": _png_dimensions, "jpeg": _jpeg_dimensions, "tiff": _tiff_dimensions, "bmp": _bmp_dimensions}
    width, height = readers[format_name](path)
    if width <= 0 or height <= 0:
        _fail("MEDIA_UNREADABLE", "Image dimensions must be positive.", path=str(path))
    return {
        "source_path": str(path.resolve()),
        "display_name": path.name,
        "source_fingerprint": _sha256(path),
        "mime_type": mime_type,
        "format": format_name,
        "width_px": width,
        "height_px": height,
    }


def _require_readable_pixels(inspection: dict[str, Any]) -> None:
    source = Path(inspection["source_path"])
    try:
        with Image.open(source, formats=[inspection["format"].upper()]) as image:
            image.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        _fail("MEDIA_UNREADABLE", f"Не удалось прочитать пиксели изображения «{source.name}».", path=str(source))


def inspect_media_sources(source_paths: Iterable[str | Path]) -> dict[str, Any]:
    paths = list(source_paths)
    if not paths:
        _fail("INVALID_ASSIGNMENT", "At least one image path is required.")
    items = [inspect_media_source(path) for path in paths]
    by_fingerprint: dict[str, list[str]] = {}
    for item in items:
        by_fingerprint.setdefault(item["source_fingerprint"], []).append(item["source_path"])
    duplicate_groups = [group for group in by_fingerprint.values() if len(group) > 1]
    return {"items": items, "duplicate_groups": duplicate_groups}


def inspect_media_folder(folder: str) -> dict[str, Any]:
    root = Path(folder)
    try:
        paths = [path for path in root.iterdir() if path.suffix.lower() in MEDIA_FORMATS and not path.is_symlink() and path.is_file()]
    except OSError:
        _fail("MEDIA_FOLDER_UNAVAILABLE", "Не удалось прочитать папку с изображениями.")
    return inspect_media_sources(sorted(paths, key=lambda path: (path.name.casefold(), path.name))) if paths else {"items": [], "duplicate_groups": []}


def _text(value: Any, field: str, max_length: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        _fail("INVALID_ASSIGNMENT", f"{field} must be non-empty and at most {max_length} characters.", field=field)
    return value.strip()


def _uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail("INVALID_ASSIGNMENT", f"{field} must be a UUID.", field=field)
    try:
        uuid.UUID(value)
    except ValueError:
        _fail("INVALID_ASSIGNMENT", f"{field} must be a UUID.", field=field)
    return value


def _read_connection(database_path: str | Path) -> sqlite3.Connection:
    database = Path(database_path)
    if not database.is_file():
        _fail("PROJECT_UNAVAILABLE", "Project database must exist before media planning.")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_analytical_point(
    database_path: str | Path,
    sample_name: str,
    point_name: str,
    analysis_ids: list[str],
    link_type: str,
    *,
    sample_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if sample_id is None:
        sample_name = _text(sample_name, "sample_name")
    else:
        sample_id = _uuid(sample_id, "sample_id")
        actor = _text(actor, "actor", 120)
    point_name = _text(point_name, "point_name")
    if link_type not in LINK_TYPES:
        _fail("INVALID_ASSIGNMENT", "Analytical Point link type is unsupported.", link_type=link_type)
    if len(set(analysis_ids)) < 2 or len(set(analysis_ids)) != len(analysis_ids):
        _fail("INVALID_ASSIGNMENT", "Analytical Point requires at least two distinct Analysis IDs.")
    normalized_ids = [_uuid(value, "analysis_id") for value in analysis_ids]
    connection = open_project(database_path)
    try:
        timestamp = _now()
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            explicit = sample_id is not None
            if explicit:
                sample = connection.execute("SELECT sample_name FROM sample WHERE sample_id = ?", (sample_id,)).fetchone()
                if sample is None:
                    _fail("SAMPLE_UNAVAILABLE", "Физический образец недоступен.")
                sample_name = sample["sample_name"]
                validate_point_input(connection, sample_id, normalized_ids)
            else:
                known = {row[0] for row in connection.execute(
                    "SELECT analysis_id FROM analysis WHERE analysis_id IN (SELECT value FROM json_each(?))",
                    (json.dumps(normalized_ids),),
                )}
                if missing := sorted(set(normalized_ids) - known):
                    _fail("INVALID_ASSIGNMENT", "Analytical Point contains unknown Analysis IDs.", analysis_ids=missing)
                sample = connection.execute("SELECT sample_id FROM sample WHERE sample_name = ?", (sample_name,)).fetchone()
                sample_id = sample["sample_id"] if sample else _id()
                if sample is None:
                    connection.execute("INSERT INTO sample (sample_id, sample_name, created_at) VALUES (?, ?, ?)", (sample_id, sample_name, timestamp))
            if connection.execute("SELECT 1 FROM analytical_point WHERE sample_id = ? AND point_name = ?", (sample_id, point_name)).fetchone():
                _fail("POINT_ALREADY_EXISTS", "Analytical Point with this Sample and name already exists.")
            point_id = _id()
            connection.execute("INSERT INTO analytical_point (analytical_point_id, sample_id, point_name, created_at) VALUES (?, ?, ?, ?)", (point_id, sample_id, point_name, timestamp))
            connection.executemany(
                "INSERT INTO analytical_point_analysis (analytical_point_id, analysis_id, link_type, created_at) VALUES (?, ?, ?, ?)",
                [(point_id, analysis_id, link_type, timestamp) for analysis_id in normalized_ids],
            )
            journal = write_point_journal(connection, point_id, normalized_ids, actor, "link_analytical_point", link_type) if explicit else None
        result = {"analytical_point_id": point_id, "sample_id": sample_id, "sample_name": sample_name, "point_name": point_name, "analysis_ids": normalized_ids, "link_type": link_type}
        return {**result, "journal": journal} if journal else result
    finally:
        connection.close()


def validate_point_input(connection, sample_id, ids):
    scoped = connection.execute("""
        SELECT a.analysis_id FROM analysis a
        JOIN analysis_import_semantics e USING (analysis_id)
        JOIN import_batch b USING (import_batch_id)
        LEFT JOIN import_batch_retraction r USING (import_batch_id)
        WHERE b.status = 'applied' AND r.import_batch_id IS NULL
          AND json_extract(e.sample_association_json, '$.sample_id') = ?
          AND a.analysis_id IN (SELECT value FROM json_each(?))
    """, (sample_id, json.dumps(ids)))
    missing = sorted(set(ids) - {row[0] for row in scoped})
    if missing:
        _fail("POINT_SAMPLE_MISMATCH", "Часть анализов недоступна или не связана с выбранным физическим образцом.", analysis_ids=missing)


def write_point_journal(connection, point_id, ids, actor, action, link_type):
    inverse = "unlink_analytical_point" if action == "link_analytical_point" else "link_analytical_point"
    parameters = {"analytical_point_id": point_id, "analysis_ids": ids, "link_type": link_type}
    scope = [("analytical_point", point_id), *(("analysis", analysis_id) for analysis_id in ids)]
    entry = {
        "id": _id(), "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
        "action": action, "category": "domain",
        "scope": [{"entity_type": kind, "entity_id": entity, "expected_revision": None, "result_revision": None} for kind, entity in scope],
        "parameters": parameters, "reversible": True, "inverse_action": {"action": inverse, "parameters": parameters},
        "state": "applied", "actor": actor, "created_at": _now(),
    }
    connection.execute("INSERT INTO operation_journal (id, entry_json) VALUES (?, ?)",
                       (entry["id"], json.dumps(entry, ensure_ascii=False)))
    return entry


def _validate_geometry(geometry: Any, width: int, height: int) -> dict[str, Any]:
    if not isinstance(geometry, dict) or set(geometry) not in ({"kind", "x_px", "y_px"}, {"kind", "x_px", "y_px", "width_px", "height_px"}):
        _fail("INVALID_GEOMETRY", "Geometry fields are invalid.")
    kind = geometry.get("kind")
    if kind not in {"point", "rectangle", "square"}:
        _fail("INVALID_GEOMETRY", "Geometry kind is invalid.")
    try:
        x, y = float(geometry["x_px"]), float(geometry["y_px"])
    except (KeyError, TypeError, ValueError):
        _fail("INVALID_GEOMETRY", "Geometry coordinates must be numbers.")
    if not (0 <= x < width and 0 <= y < height):
        _fail("INVALID_GEOMETRY", "Geometry origin is outside the source image.", width_px=width, height_px=height)
    result: dict[str, Any] = {"kind": kind, "x_px": x, "y_px": y}
    if kind == "point":
        if len(geometry) != 3:
            _fail("INVALID_GEOMETRY", "Point geometry cannot have a size.")
        return result
    try:
        region_width, region_height = float(geometry["width_px"]), float(geometry["height_px"])
    except (KeyError, TypeError, ValueError):
        _fail("INVALID_GEOMETRY", "Region size must be numeric.")
    if region_width <= 0 or region_height <= 0 or x + region_width > width or y + region_height > height:
        _fail("INVALID_GEOMETRY", "Region extends outside the source image.", width_px=width, height_px=height)
    if kind == "square" and abs(region_width - region_height) > 1e-9:
        _fail("INVALID_GEOMETRY", "Square width and height must be equal.")
    return result | {"width_px": region_width, "height_px": region_height}


def _plan_fingerprint(plan: dict[str, Any]) -> str:
    semantic = {key: value for key, value in plan.items() if key != "semantic_fingerprint"}
    # The desktop JSON round trip turns whole-valued coordinates such as 36.0 into 36.
    items = []
    for item in semantic["items"]:
        placements = []
        for placement in item["placements"]:
            geometry = {
                key: float(value or 0) if type(value) in (int, float) else value
                for key, value in placement["geometry"].items()
            }
            placements.append({**placement, "geometry": geometry})
        items.append({**item, "placements": placements})
    semantic["items"] = items
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _plan_media_links(plan_items, assignments):
    placements = {
        (item["source_fingerprint"], point["analytical_point_id"]): (item, point)
        for item in plan_items for point in item["placements"]
    }
    links = []
    for photo, assignment in zip(plan_items, assignments, strict=True):
        references = assignment.get("attach_to_placements", [])
        if not isinstance(references, list):
            _fail("INVALID_ASSIGNMENT", "Media Link targets must be an array.")
        seen = set()
        for reference in references:
            if not isinstance(reference, dict) or set(reference) != {"source_fingerprint", "analytical_point_id"}:
                _fail("INVALID_ASSIGNMENT", "Media Link target fields are invalid.")
            point_id = _uuid(reference["analytical_point_id"], "analytical_point_id")
            fingerprint = _text(reference["source_fingerprint"], "source_fingerprint", 64)
            target = placements.get((fingerprint, point_id))
            if target is None:
                _fail("MEDIA_LINK_UNAVAILABLE", "Целевая точка или область больше не входит в план импорта.")
            parent, placement = target
            if parent is photo or (parent["sample_name"], parent["thin_section_name"]) != (photo["sample_name"], photo["thin_section_name"]):
                _fail("MEDIA_LINK_SCOPE", "Выберите точку или область на другом снимке того же шлифа.")
            annotation_id = placement["spatial_annotation_id"]
            if annotation_id in seen:
                _fail("INVALID_ASSIGNMENT", "Фотография уже привязана к этому размещению в плане.")
            seen.add(annotation_id)
            links.append({"media_asset_id": photo["media_asset_id"], "spatial_annotation_id": annotation_id})
    return links


def create_media_import_plan(database_path: str | Path, assignments: Any) -> dict[str, Any]:
    if not isinstance(assignments, list) or not assignments:
        _fail("INVALID_ASSIGNMENT", "assignments must be a non-empty array.")
    connection = _read_connection(database_path)
    try:
        plan_items: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        seen_fingerprints: dict[str, str] = {}
        for assignment in assignments:
            required = {"source_path", "ownership_mode", "media_type", "sample_name", "thin_section_name", "placements"}
            if (not isinstance(assignment, dict) or not required <= set(assignment)
                    or set(assignment) - required - {"expected_source_fingerprint", "sample_target", "attach_to_placements"}):
                _fail("INVALID_ASSIGNMENT", "Media assignment fields are invalid.")
            inspection = inspect_media_source(assignment["source_path"])
            if ("expected_source_fingerprint" in assignment
                    and assignment["expected_source_fingerprint"] != inspection["source_fingerprint"]):
                _fail("SOURCE_FINGERPRINT_MISMATCH", "Изображение изменилось после просмотра. Добавьте файл заново.",
                      path=inspection["source_path"])
            previous = seen_fingerprints.get(inspection["source_fingerprint"])
            if previous is not None:
                _fail("DUPLICATE_MEDIA_SOURCE", "The same physical image occurs more than once in the batch.", first_path=previous, duplicate_path=inspection["source_path"])
            seen_fingerprints[inspection["source_fingerprint"]] = inspection["source_path"]
            _require_readable_pixels(inspection)
            ownership = assignment["ownership_mode"]
            if ownership not in OWNERSHIP_MODES:
                _fail("INVALID_ASSIGNMENT", "Media ownership mode is invalid.")
            media_type = _text(assignment["media_type"], "media_type", 80)
            if media_type.upper() in STANDARD_MEDIA_TYPES:
                media_type = media_type.upper()
            sample_name = _text(assignment["sample_name"], "sample_name")
            section_name = assignment["thin_section_name"]
            if section_name is None:
                if media_type not in SAMPLE_PHOTO_TYPES or assignment["placements"]:
                    _fail("MEDIA_SECTION_REQUIRED", "Для снимка такого типа или с размещениями укажите шлиф.")
            else:
                section_name = _text(section_name, "thin_section_name")
            target = assignment.get("sample_target")
            if target is not None:
                _check_media_sample_target(connection, sample_name, target)
            existing = connection.execute(
                """SELECT ma.media_asset_id, s.sample_name, ts.thin_section_name, ma.media_type, ma.width_px, ma.height_px
                FROM media_asset ma JOIN sample s ON s.sample_id = ma.sample_id
                LEFT JOIN thin_section ts ON ts.thin_section_id = ma.thin_section_id
                WHERE ma.source_fingerprint_sha256 = ?""",
                (inspection["source_fingerprint"],),
            ).fetchone()
            if existing and (existing["sample_name"], existing["thin_section_name"], existing["media_type"], existing["width_px"], existing["height_px"]) != (sample_name, section_name, media_type, inspection["width_px"], inspection["height_px"]):
                _fail("MEDIA_ALREADY_IMPORTED", "The same physical image already has a different assignment.", media_asset_id=existing["media_asset_id"])
            placements = assignment["placements"]
            if not isinstance(placements, list):
                _fail("INVALID_ASSIGNMENT", "placements must be an array.")
            if not placements and section_name is not None:
                warnings.append({"code": "UNPLACED_MEDIA", "message": f"{inspection['display_name']} has no placed Analytical Points."})
            planned_placements = []
            seen_points: set[str] = set()
            for placement in placements:
                if not isinstance(placement, dict) or set(placement) != {"analytical_point_id", "geometry", "cross_sample_exception_reason"}:
                    _fail("INVALID_ASSIGNMENT", "Point placement fields are invalid.")
                point_id = _uuid(placement["analytical_point_id"], "analytical_point_id")
                if point_id in seen_points:
                    _fail("INVALID_ASSIGNMENT", "An Analytical Point may be placed only once on one image.", analytical_point_id=point_id)
                seen_points.add(point_id)
                point = connection.execute(
                    """SELECT ap.analytical_point_id, ap.point_name, s.sample_name FROM analytical_point ap
                    JOIN sample s ON s.sample_id = ap.sample_id WHERE ap.analytical_point_id = ?""", (point_id,)
                ).fetchone()
                if point is None:
                    _fail("INVALID_ASSIGNMENT", "Analytical Point does not exist.", analytical_point_id=point_id)
                if existing and connection.execute(
                    """SELECT 1 FROM analytical_point_annotation apa
                    JOIN spatial_annotation sa ON sa.spatial_annotation_id = apa.spatial_annotation_id
                    WHERE apa.analytical_point_id = ? AND sa.media_asset_id = ?""",
                    (point_id, existing["media_asset_id"]),
                ).fetchone():
                    _fail("POINT_ALREADY_PLACED", "Analytical Point is already placed on this image.", analytical_point_id=point_id)
                reason = placement["cross_sample_exception_reason"]
                if reason is not None:
                    reason = _text(reason, "cross_sample_exception_reason", 1000)
                if point["sample_name"] != sample_name and reason is None:
                    _fail("CROSS_SAMPLE_CONFIRMATION_REQUIRED", "A point from another Sample requires an explicit reason.", analytical_point_id=point_id, image_sample=sample_name, point_sample=point["sample_name"])
                if point["sample_name"] == sample_name and reason is not None:
                    _fail("INVALID_ASSIGNMENT", "Cross-Sample reason is not allowed when Samples match.", analytical_point_id=point_id)
                planned_placements.append({
                    "spatial_annotation_id": _id(),
                    "analytical_point_id": point_id,
                    "point_name": point["point_name"],
                    "point_sample_name": point["sample_name"],
                    "geometry": _validate_geometry(placement["geometry"], inspection["width_px"], inspection["height_px"]),
                    "cross_sample_exception_reason": reason,
                })
            plan_items.append({
                "media_asset_id": existing["media_asset_id"] if existing else _id(),
                **inspection,
                "ownership_mode": ownership,
                "media_type": media_type,
                "sample_name": sample_name,
                "thin_section_name": section_name,
                "existing_media_asset_id": existing["media_asset_id"] if existing else None,
                "placements": planned_placements,
            })
            plan_items[-1].pop("format")
            if target is not None:
                plan_items[-1]["sample_target"] = target
        plan = {"schema_version": 1, "semantic_fingerprint": "", "items": plan_items, "warnings": warnings,
                "unplaced_points": _unplaced_points(connection, plan_items)}
        if links := _plan_media_links(plan_items, assignments):
            plan.update(schema_version=2, media_links=links)
        if any(item["thin_section_name"] is None for item in plan_items):
            plan["schema_version"] = 3
        plan["semantic_fingerprint"] = _plan_fingerprint(plan)
        return plan
    finally:
        connection.close()


def _unplaced_points(connection, items):
    placements = {}
    for item in items:
        if item["thin_section_name"] is None:
            continue
        scope = (item["sample_name"], item["thin_section_name"])
        placements.setdefault(scope, set()).update(placement["analytical_point_id"] for placement in item["placements"])
    remaining = []
    for (sample_name, section_name), placed in placements.items():
        rows = connection.execute("""
            SELECT p.analytical_point_id, p.point_name FROM analytical_point p JOIN sample s USING (sample_id)
            WHERE s.sample_name = ? AND NOT EXISTS (
                SELECT 1 FROM analytical_point_annotation pa JOIN spatial_annotation a USING (spatial_annotation_id)
                JOIN thin_section ts USING (thin_section_id)
                WHERE pa.analytical_point_id = p.analytical_point_id AND ts.sample_id = s.sample_id AND ts.thin_section_name = ?
            ) ORDER BY p.point_name, p.analytical_point_id
        """, (sample_name, section_name))
        remaining.extend({**dict(row), "sample_name": sample_name, "thin_section_name": section_name}
                         for row in rows if row["analytical_point_id"] not in placed)
    return remaining


def _prepare_media_copy(database_path: str | Path, item: dict[str, Any]) -> Path:
    source = Path(item["source_path"])
    destination = Path(database_path).parent / "media" / f"{item['media_asset_id']}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copyfile(source, temporary)
        if _sha256(temporary) != item["source_fingerprint"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Image changed while its managed copy was prepared.", path=str(source))
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _check_media_sample_target(connection, sample_name, target):
    if not isinstance(target, dict) or set(target) != {"mode", "sample_id"}:
        _fail("INVALID_ASSIGNMENT", "Выберите физический образец явно.")
    current = connection.execute("SELECT sample_id FROM sample WHERE sample_name = ?", (sample_name,)).fetchone()
    mode = target["mode"]
    if mode == "new":
        if current is not None:
            _fail("SAMPLE_NAME_EXISTS", "Образец с этим именем уже существует. Выберите его из списка.")
        if target["sample_id"] is not None:
            _fail("INVALID_ASSIGNMENT", "Для нового образца идентификатор не указывается.")
    elif mode != "existing" or current is None or current[0] != _uuid(target["sample_id"], "sample_id"):
        _fail("SAMPLE_UNAVAILABLE", "Выбранный образец недоступен. Повторите назначение.")


def _ensure_sample_and_section(connection: sqlite3.Connection, sample_name: str, section_name: str | None, timestamp: str) -> tuple[str, str | None]:
    sample = connection.execute("SELECT sample_id FROM sample WHERE sample_name = ?", (sample_name,)).fetchone()
    sample_id = sample["sample_id"] if sample else _id()
    if sample is None:
        connection.execute("INSERT INTO sample (sample_id, sample_name, created_at) VALUES (?, ?, ?)", (sample_id, sample_name, timestamp))
    if section_name is None:
        return sample_id, None
    section = connection.execute("SELECT thin_section_id FROM thin_section WHERE sample_id = ? AND thin_section_name = ?", (sample_id, section_name)).fetchone()
    section_id = section["thin_section_id"] if section else _id()
    if section is None:
        connection.execute("INSERT INTO thin_section (thin_section_id, sample_id, thin_section_name, created_at) VALUES (?, ?, ?, ?)", (section_id, sample_id, section_name, timestamp))
    return sample_id, section_id


def _verify_media_plan_sources(plan, *, check_pixels=False):
    if not isinstance(plan, dict) or plan.get("schema_version") not in (1, 2, 3) or not isinstance(plan.get("items"), list) or not plan["items"]:
        _fail("PLAN_SCHEMA_INCOMPATIBLE", "Media import plan is invalid.")
    if plan.get("semantic_fingerprint") != _plan_fingerprint(plan):
        _fail("PLAN_FINGERPRINT_MISMATCH", "Media import plan changed after review.")
    links = plan.get("media_links")
    if ((plan["schema_version"] == 1 and "media_links" in plan)
            or (plan["schema_version"] == 2 and "media_links" not in plan)
            or ("media_links" in plan and (not isinstance(links, list) or not links))):
        _fail("PLAN_SCHEMA_INCOMPATIBLE", "Media Link list is invalid.")
    if links:
        assets = {item["media_asset_id"] for item in plan["items"]}
        annotations = {point["spatial_annotation_id"] for item in plan["items"] for point in item["placements"]}
        seen = set()
        for link in links:
            if not isinstance(link, dict) or set(link) != {"media_asset_id", "spatial_annotation_id"}:
                _fail("PLAN_SCHEMA_INCOMPATIBLE", "Media Link fields are invalid.")
            asset = _uuid(link["media_asset_id"], "media_asset_id")
            annotation = _uuid(link["spatial_annotation_id"], "spatial_annotation_id")
            if asset not in assets or annotation not in annotations or (asset, annotation) in seen:
                _fail("PLAN_SCHEMA_INCOMPATIBLE", "Media Link target is duplicated or outside the import plan.")
            seen.add((asset, annotation))
    for item in plan["items"]:
        if item["thin_section_name"] is None and (plan["schema_version"] != 3 or item["media_type"] not in SAMPLE_PHOTO_TYPES or item["placements"]):
            _fail("MEDIA_SECTION_REQUIRED", "Для снимка такого типа или с размещениями укажите шлиф.")
        current = inspect_media_source(item["source_path"])
        if current["source_fingerprint"] != item["source_fingerprint"] or current["width_px"] != item["width_px"] or current["height_px"] != item["height_px"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Image changed after planning.", path=item["source_path"])
        if check_pixels:
            _require_readable_pixels(current)


def load_media_import_draft(database_path):
    with closing(open_project(database_path)) as connection:
        draft = connection.execute("SELECT fingerprint, plan_json, saved_at FROM media_import_draft WHERE singleton = 1").fetchone()
    if draft is None:
        return None
    plan = json.loads(draft["plan_json"])
    issue = None
    try:
        _verify_media_plan_sources(plan)
    except (ImportCommandError, OSError):
        issue = "Файл черновика изменился или недоступен. Верните исходные файлы или начните новый импорт."
    return {"fingerprint": draft["fingerprint"], "saved_at": draft["saved_at"], "plan": plan if not issue else None, "issue": issue}


def save_media_import_draft(database_path, plan, expected_fingerprint=None):
    _verify_media_plan_sources(plan)
    fingerprint = plan["semantic_fingerprint"]
    saved_at = _now()
    encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT fingerprint FROM media_import_draft WHERE singleton = 1").fetchone()
        if (current[0] if current else None) != expected_fingerprint:
            _fail("MEDIA_DRAFT_CONFLICT", "Черновик изменился. Снова откройте импорт изображений.")
        connection.execute("""INSERT INTO media_import_draft (singleton, fingerprint, plan_json, saved_at) VALUES (1, ?, ?, ?)
            ON CONFLICT (singleton) DO UPDATE SET fingerprint = excluded.fingerprint, plan_json = excluded.plan_json, saved_at = excluded.saved_at""",
            (fingerprint, encoded, saved_at))
    return {"fingerprint": fingerprint, "saved_at": saved_at}


def apply_media_import_plan(database_path: str | Path, plan: Any, *, attach_to: str | None = None,
                            draft_fingerprint: str | None = None) -> dict[str, Any]:
    from .media_links import attach_media

    _verify_media_plan_sources(plan, check_pixels=True)
    connection = open_project(database_path)
    copied: list[Path] = []
    try:
        timestamp = _now()
        batch_id = _id()
        created_assets = 0
        reused_assets = 0
        annotation_count = 0
        link_ids = []
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if draft_fingerprint is not None:
                saved = connection.execute("SELECT fingerprint FROM media_import_draft WHERE singleton = 1").fetchone()
                if not saved or saved[0] != draft_fingerprint:
                    _fail("MEDIA_DRAFT_CONFLICT", "Черновик изменился или уже сохранён. Снова откройте импорт изображений.")
            for item in plan["items"]:
                if item.get("sample_target") is not None:
                    _check_media_sample_target(connection, item["sample_name"], item["sample_target"])
            connection.execute(
                "INSERT INTO media_import_batch (media_import_batch_id, status, semantic_fingerprint_sha256, plan_json, created_at, applied_at) VALUES (?, 'applied', ?, ?, ?, ?)",
                (batch_id, plan["semantic_fingerprint"], json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")), timestamp, timestamp),
            )
            for item in plan["items"]:
                sample_id, section_id = _ensure_sample_and_section(connection, item["sample_name"], item["thin_section_name"], timestamp)
                asset_id = item["media_asset_id"]
                existing = connection.execute("SELECT media_asset_id, sample_id, thin_section_id, media_type FROM media_asset WHERE source_fingerprint_sha256 = ?", (item["source_fingerprint"],)).fetchone()
                if existing:
                    if existing["media_asset_id"] != asset_id or (existing["sample_id"], existing["thin_section_id"], existing["media_type"]) != (sample_id, section_id, item["media_type"]):
                        _fail("MEDIA_ALREADY_IMPORTED", "Existing image assignment changed after planning.", media_asset_id=existing["media_asset_id"])
                    reused_assets += 1
                else:
                    source = Path(item["source_path"])
                    if item["ownership_mode"] == "managed_copy":
                        copied.append(_prepare_media_copy(database_path, item))
                    managed_relative = f"media/{asset_id}{source.suffix.lower()}" if item["ownership_mode"] == "managed_copy" else None
                    connection.execute(
                        """INSERT INTO media_asset
                        (media_asset_id, media_import_batch_id, source_kind, display_name, source_fingerprint_sha256, linked_path, managed_relative_path, media_type, mime_type, width_px, height_px, sample_id, thin_section_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (asset_id, batch_id, "managed_copy" if item["ownership_mode"] == "managed_copy" else "linked_reference", item["display_name"], item["source_fingerprint"], str(source.resolve()) if item["ownership_mode"] == "linked_external" else None, managed_relative, item["media_type"], item["mime_type"], item["width_px"], item["height_px"], sample_id, section_id, timestamp),
                    )
                    created_assets += 1
                for placement in item["placements"]:
                    point = connection.execute("SELECT sample_id FROM analytical_point WHERE analytical_point_id = ?", (placement["analytical_point_id"],)).fetchone()
                    if point is None:
                        _fail("INVALID_ASSIGNMENT", "Analytical Point disappeared after planning.", analytical_point_id=placement["analytical_point_id"])
                    is_cross_sample = point["sample_id"] != sample_id
                    reason = placement["cross_sample_exception_reason"]
                    if is_cross_sample != (reason is not None):
                        _fail("CROSS_SAMPLE_CONFIRMATION_REQUIRED", "Cross-Sample state changed after planning.")
                    geometry = _validate_geometry(placement["geometry"], item["width_px"], item["height_px"])
                    connection.execute(
                        """INSERT INTO spatial_annotation
                        (spatial_annotation_id, thin_section_id, media_asset_id, geometry_kind, x_px, y_px, width_px, height_px, image_width_px, image_height_px, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (placement["spatial_annotation_id"], section_id, asset_id, geometry["kind"], geometry["x_px"], geometry["y_px"], geometry.get("width_px"), geometry.get("height_px"), item["width_px"], item["height_px"], timestamp),
                    )
                    connection.execute(
                        "INSERT INTO analytical_point_annotation (analytical_point_id, spatial_annotation_id, cross_sample_exception, exception_reason, created_at) VALUES (?, ?, ?, ?, ?)",
                        (placement["analytical_point_id"], placement["spatial_annotation_id"], int(is_cross_sample), reason, timestamp),
                    )
                    annotation_count += 1
                if attach_to is not None:
                    link_ids.append(attach_media(connection, attach_to, asset_id))
            for link in plan.get("media_links", []):
                link_ids.append(attach_media(connection, link["spatial_annotation_id"], link["media_asset_id"]))
            if draft_fingerprint is not None:
                connection.execute("DELETE FROM media_import_draft WHERE singleton = 1 AND fingerprint = ?", (draft_fingerprint,))
        return {"media_import_batch_id": batch_id, "created_media_asset_count": created_assets, "reused_media_asset_count": reused_assets, "spatial_annotation_count": annotation_count,
                "warnings": plan.get("warnings", []), **({"media_link_ids": link_ids} if link_ids else {})}
    except Exception:
        for path in copied:
            path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
