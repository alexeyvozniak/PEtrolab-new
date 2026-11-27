"""Project sample cards and explicit analysis links."""

from contextlib import closing
from datetime import date
import json
from uuid import UUID

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .media_import import LINK_TYPES, validate_point_input, write_point_journal


_ACTIVE_SAMPLE_ANALYSES = """
    SELECT a.source_id,
           json_extract(e.sample_association_json, '$.sample_id') AS sample_id,
           COALESCE(json_extract(e.mineral_verification_json, '$.accepted.target'),
                    json_extract(e.mineral_assignment_json, '$.value'),
                    json_extract(e.reported_mineral_json, '$.value')) AS mineral
    FROM analysis a JOIN analysis_import_semantics e USING (analysis_id)
    JOIN import_batch b USING (import_batch_id)
    LEFT JOIN import_batch_retraction r USING (import_batch_id)
    WHERE b.status = 'applied' AND r.import_batch_id IS NULL
"""


def list_project_samples(database_path):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute(f"""
            WITH active AS ({_ACTIVE_SAMPLE_ANALYSES}),
                 totals AS (SELECT sample_id, COUNT(*) AS analysis_count FROM active GROUP BY sample_id)
            SELECT s.sample_id, s.sample_name, COALESCE(t.analysis_count, 0) AS analysis_count
            FROM sample s LEFT JOIN totals t USING (sample_id)
            ORDER BY s.sample_name, s.sample_id
        """)
        return [dict(row) for row in rows]


def _sample_id(sample_id):
    if not isinstance(sample_id, str) or str(UUID(sample_id)) != sample_id:
        raise ValueError("sample_id")


def _require_sample(connection, sample_id):
    sample = connection.execute("SELECT sample_id, sample_name, created_at FROM sample WHERE sample_id = ?", (sample_id,)).fetchone()
    if not sample:
        raise ImportCommandError("SAMPLE_UNAVAILABLE", "Образец недоступен в этом проекте.")
    return sample


_CONTEXT_FIELDS = ("locality", "storage", "collection_position", "collector", "collection_date")


def get_project_sample(database_path, sample_id):
    _sample_id(sample_id)
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        sample = _require_sample(connection, sample_id)
        context = connection.execute("""
            SELECT locality, storage, collection_position, collector, collection_date, revision
            FROM sample_context WHERE sample_id = ?
        """, (sample_id,)).fetchone()
        notes = connection.execute("""
            SELECT note_id, author, body, created_at FROM sample_note WHERE sample_id = ?
            ORDER BY created_at DESC, rowid DESC
        """, (sample_id,))
        summary = connection.execute(f"""
            WITH active AS ({_ACTIVE_SAMPLE_ANALYSES})
            SELECT COUNT(*) AS analysis_count FROM active WHERE sample_id = ?
        """, (sample_id,)).fetchone()
        minerals = connection.execute(f"""
            WITH active AS ({_ACTIVE_SAMPLE_ANALYSES})
            SELECT DISTINCT mineral FROM active WHERE sample_id = ? AND mineral IS NOT NULL AND mineral != '' ORDER BY mineral
        """, (sample_id,))
        sources = connection.execute(f"""
            WITH active AS ({_ACTIVE_SAMPLE_ANALYSES})
            SELECT s.source_id, s.display_name AS source_name, COUNT(*) AS analysis_count
            FROM active JOIN source_file s USING (source_id)
            WHERE sample_id = ?
            GROUP BY s.source_id, s.display_name ORDER BY s.display_name, s.source_id
        """, (sample_id,))
        points = connection.execute("""
            SELECT p.analytical_point_id, p.point_name, COUNT(l.analysis_id) AS analysis_count,
                   EXISTS (SELECT 1 FROM analytical_point_annotation pa WHERE pa.analytical_point_id = p.analytical_point_id) AS placed
            FROM analytical_point p LEFT JOIN analytical_point_analysis l USING (analytical_point_id)
            WHERE p.sample_id = ? GROUP BY p.analytical_point_id, p.point_name ORDER BY p.point_name
        """, (sample_id,))
        sections = connection.execute("""
            SELECT thin_section_id, thin_section_name FROM thin_section WHERE sample_id = ? ORDER BY thin_section_name
        """, (sample_id,))
        images = connection.execute("""
            SELECT media_asset_id, thin_section_id, display_name, media_type, width_px, height_px
            FROM media_asset WHERE sample_id = ? ORDER BY display_name
        """, (sample_id,))
        return {**dict(sample), **dict(summary), "minerals": [row[0] for row in minerals],
                "sources": [dict(row) for row in sources], "points": [dict(row) for row in points],
                "thin_sections": [dict(row) for row in sections], "images": [dict(row) for row in images],
                "context": dict(context) if context else {**dict.fromkeys(_CONTEXT_FIELDS, ""), "revision": 0},
                "notes": [dict(row) for row in notes]}


def save_sample_context(database_path, sample_id, context, expected_revision):
    _sample_id(sample_id)
    if (not isinstance(context, dict) or set(context) != set(_CONTEXT_FIELDS)
            or any(not isinstance(value, str) or len(value) > 2000 for value in context.values())
            or type(expected_revision) is not int or expected_revision < 0):
        raise ValueError("sample_context")
    values = {key: context[key].strip() for key in _CONTEXT_FIELDS}
    collected = values["collection_date"]
    if collected and date.fromisoformat(collected).isoformat() != collected:
        raise ValueError("collection_date")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_sample(connection, sample_id)
        current = connection.execute("SELECT revision FROM sample_context WHERE sample_id = ?", (sample_id,)).fetchone()
        if expected_revision != (current[0] if current else 0):
            raise ImportCommandError("SAMPLE_CONTEXT_CONFLICT", "Паспорт изменился. Откройте карточку заново перед сохранением.")
        revision = expected_revision + 1
        connection.execute("""
            INSERT INTO sample_context VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sample_id) DO UPDATE SET locality = excluded.locality, storage = excluded.storage,
                collection_position = excluded.collection_position, collector = excluded.collector,
                collection_date = excluded.collection_date, revision = excluded.revision
        """, (sample_id, *values.values(), revision))
        return {**values, "revision": revision}


def add_sample_note(database_path, sample_id, author, body):
    _sample_id(sample_id)
    if (not isinstance(author, str) or not 1 <= len(author.strip()) <= 120
            or not isinstance(body, str) or not 1 <= len(body.strip()) <= 10000):
        raise ValueError("sample_note")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_sample(connection, sample_id)
        note = {"note_id": _id(), "author": author.strip(), "body": body.strip(), "created_at": _now()}
        connection.execute("INSERT INTO sample_note VALUES (?, ?, ?, ?, ?)",
                           (note["note_id"], sample_id, note["author"], note["body"], note["created_at"]))
        return note


def get_point_analyses(database_path, point_id):
    _sample_id(point_id)
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT a.analysis_id, a.identity_json, a.sheet_name, a.source_row_number, a.source_column_number,
                   s.display_name AS source_name, l.link_type, l.created_at,
                   COALESCE(json_extract(e.analytical_method_json, '$.value'), '') AS method,
                   b.status = 'applied' AND r.import_batch_id IS NULL AS active
            FROM analytical_point_analysis l JOIN analysis a USING (analysis_id)
            JOIN import_batch b USING (import_batch_id)
            JOIN source_file s ON s.source_id = a.source_id
            LEFT JOIN analysis_import_semantics e USING (analysis_id)
            LEFT JOIN import_batch_retraction r USING (import_batch_id)
            WHERE l.analytical_point_id = ? ORDER BY s.display_name, a.sheet_name, a.source_row_number, a.analysis_id
        """, (point_id,))
        return [_point_analysis(row) for row in rows]


def get_analysis_photo_locations(database_path, analysis_id):
    """Exact persisted spatial links for an active analysis, never name matching."""
    _sample_id(analysis_id)
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT m.media_asset_id, m.display_name, m.sample_id, s.sample_name,
                   p.analytical_point_id, p.point_name, l.link_type,
                   a.spatial_annotation_id, a.geometry_kind, a.x_px, a.y_px, a.width_px, a.height_px,
                   pa.cross_sample_exception, pa.exception_reason
            FROM analytical_point_analysis l
            JOIN analysis n USING (analysis_id)
            JOIN import_batch b USING (import_batch_id)
            LEFT JOIN import_batch_retraction r USING (import_batch_id)
            JOIN analytical_point p USING (analytical_point_id)
            JOIN analytical_point_annotation pa USING (analytical_point_id)
            JOIN spatial_annotation a USING (spatial_annotation_id)
            JOIN media_asset m USING (media_asset_id)
            JOIN sample s ON s.sample_id = m.sample_id
            WHERE l.analysis_id = ? AND b.status = 'applied' AND r.import_batch_id IS NULL
            ORDER BY m.display_name, m.media_asset_id, p.point_name, a.spatial_annotation_id
        """, (analysis_id,))
        return [dict(row) for row in rows]


def _point_analysis(row):
    record = dict(row)
    record["identity"] = " · ".join(value for value in json.loads(record.pop("identity_json")) if value)
    record["active"] = bool(record["active"])
    return record


def change_point_link(database_path, point_id, analysis_id, actor, link_type=None, *, analysis_ids=None):
    _sample_id(point_id)
    if analysis_ids is None:
        analysis_ids = [analysis_id]
    elif analysis_id is not None or link_type is None or not isinstance(analysis_ids, list) or not analysis_ids:
        raise ValueError("analysis_ids")
    for item in analysis_ids:
        _sample_id(item)
    if len(set(analysis_ids)) != len(analysis_ids):
        raise ValueError("analysis_ids must be distinct")
    if not isinstance(actor, str) or not 1 <= len(actor.strip()) <= 120:
        raise ValueError("actor")
    if link_type is not None and link_type not in LINK_TYPES:
        raise ValueError("link_type")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        point = connection.execute("SELECT sample_id FROM analytical_point WHERE analytical_point_id = ?", (point_id,)).fetchone()
        if not point:
            raise ImportCommandError("POINT_UNAVAILABLE", "Аналитическая точка недоступна.")
        current = connection.execute("""
            SELECT link_type, created_at FROM analytical_point_analysis
            WHERE analytical_point_id = ? AND analysis_id IN (SELECT value FROM json_each(?)) LIMIT 1
        """, (point_id, json.dumps(analysis_ids))).fetchone()
        if link_type is None:
            if current is None:
                raise ImportCommandError("POINT_LINK_UNAVAILABLE", "Эту связь уже сняли.")
            connection.execute("DELETE FROM analytical_point_analysis WHERE analytical_point_id = ? AND analysis_id = ?",
                               (point_id, analysis_id))
            return write_point_journal(connection, point_id, [analysis_id], actor.strip(), "unlink_analytical_point",
                                       current["link_type"], link_created_at=current["created_at"])
        if current is not None:
            raise ImportCommandError("POINT_LINK_EXISTS", "Этот анализ уже связан с точкой.")
        validate_point_input(connection, point[0], analysis_ids)
        timestamp = _now()
        connection.executemany("INSERT INTO analytical_point_analysis VALUES (?, ?, ?, ?)",
                               [(point_id, item, link_type, timestamp) for item in analysis_ids])
        return write_point_journal(connection, point_id, analysis_ids, actor.strip(), "link_analytical_point", link_type)


def undo_point_link(database_path, operation_id, actor):
    _sample_id(operation_id)
    if not isinstance(actor, str) or not 1 <= len(actor.strip()) <= 120:
        raise ValueError("actor")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        stored = connection.execute("SELECT rowid, entry_json FROM operation_journal WHERE id = ?", (operation_id,)).fetchone()
        entry = json.loads(stored["entry_json"]) if stored else {}
        if (entry.get("action") not in {"link_analytical_point", "unlink_analytical_point"}
                or entry.get("state") != "applied" or not entry.get("reversible")):
            raise ImportCommandError("POINT_LINK_UNDO_UNAVAILABLE", "Операция со связью недоступна для отмены.")

        action = entry["inverse_action"]["action"]
        parameters = entry["inverse_action"]["parameters"]
        point_id = parameters["analytical_point_id"]
        ids = parameters["analysis_ids"]
        link_type = parameters["link_type"]
        encoded_ids = json.dumps(ids)
        newer = connection.execute("""
            SELECT DISTINCT affected.value
            FROM operation_journal j, json_each(j.entry_json, '$.parameters.analysis_ids') affected
            WHERE j.rowid > ? AND json_extract(j.entry_json, '$.state') = 'applied'
              AND json_extract(j.entry_json, '$.action') IN ('link_analytical_point', 'unlink_analytical_point')
              AND json_extract(j.entry_json, '$.reversible') = 1
              AND json_extract(j.entry_json, '$.parameters.analytical_point_id') = ?
              AND affected.value IN (SELECT value FROM json_each(?))
        """, (stored["rowid"], point_id, encoded_ids)).fetchall()
        point = connection.execute("SELECT 1 FROM analytical_point WHERE analytical_point_id = ?", (point_id,)).fetchone()
        if point is None:
            raise ImportCommandError("POINT_UNAVAILABLE", "Аналитическая точка недоступна.")
        current = dict(connection.execute("""
            SELECT analysis_id, link_type FROM analytical_point_analysis
            WHERE analytical_point_id = ? AND analysis_id IN (SELECT value FROM json_each(?))
        """, (point_id, encoded_ids)).fetchall())
        expected = link_type if action == "unlink_analytical_point" else None
        changed = {row[0] for row in newer} | {item for item in ids if current.get(item) != expected}
        if changed:
            raise ImportCommandError("POINT_LINK_UNDO_CONFLICT", "После этой операции часть связей изменилась.",
                                     {"analysis_ids": [item for item in ids if item in changed]})

        if action == "link_analytical_point":
            active = {row[0] for row in connection.execute("""
                SELECT a.analysis_id FROM analysis a JOIN import_batch b USING (import_batch_id)
                LEFT JOIN import_batch_retraction r USING (import_batch_id)
                WHERE b.status = 'applied' AND r.import_batch_id IS NULL
                  AND a.analysis_id IN (SELECT value FROM json_each(?))
            """, (encoded_ids,))}
            if len(active) != len(ids):
                raise ImportCommandError("POINT_LINK_UNDO_CONFLICT", "Часть анализов этой связи недоступна.",
                                         {"analysis_ids": [item for item in ids if item not in active]})
            timestamp = parameters.get("link_created_at") or _now()
            connection.executemany("INSERT INTO analytical_point_analysis VALUES (?, ?, ?, ?)",
                                   [(point_id, item, link_type, timestamp) for item in ids])
        else:
            connection.execute("""
                DELETE FROM analytical_point_analysis
                WHERE analytical_point_id = ? AND analysis_id IN (SELECT value FROM json_each(?))
            """, (point_id, encoded_ids))
        entry["state"] = "undone"
        connection.execute("UPDATE operation_journal SET entry_json = ? WHERE id = ?",
                           (json.dumps(entry, ensure_ascii=False), operation_id))
        return write_point_journal(connection, point_id, ids, actor.strip(), action, link_type,
                                   reverses_operation_id=operation_id)
