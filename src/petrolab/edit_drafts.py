"""Persistent proposals and conflict evidence for imported measurements."""

from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID
from xml.etree.ElementTree import ParseError

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError, _read_xlsx
from .xlsx_edit import corrected_workbook, exclusive_file


def _measurement(connection, measurement_id):
    return connection.execute("""
        SELECT m.*, a.source_id, a.sheet_name, b.source_fingerprint_sha256, r.import_batch_id AS retracted,
               b.status AS batch_status,
               COALESCE(s.linked_path, json_extract(b.plan_json, '$.original_source_path')) AS external_path
        FROM measurement m JOIN analysis a USING (analysis_id)
        JOIN import_batch b ON b.import_batch_id = a.import_batch_id
        JOIN source_file s ON s.source_id = a.source_id
        LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
        WHERE m.measurement_id = ?
    """, (measurement_id,)).fetchone()


def save_edit_draft(database_path, measurement_id, new_value):
    if not isinstance(measurement_id, str) or str(UUID(measurement_id)) != measurement_id:
        raise ValueError("measurement_id")
    if new_value is not None and (not isinstance(new_value, str) or len(new_value) > 32767):
        raise ValueError("new_value")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        measurement = _measurement(connection, measurement_id)
        if not measurement or measurement["batch_status"] != "applied" or measurement["retracted"] is not None:
            raise ImportCommandError("EDIT_MEASUREMENT_UNAVAILABLE", "Измерение недоступно для черновика.")
        if new_value == measurement["raw_token"]:
            raise ImportCommandError("EDIT_VALUE_UNCHANGED", "Введите значение, отличающееся от исходного.")
        now = _now()
        draft = {
            "id": _id(),
            "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
            "source_id": measurement["source_id"], "source_fingerprint_at_start": measurement["source_fingerprint_sha256"],
            "changes": [{"analysis_id": measurement["analysis_id"], "field": measurement["canonical_field"],
                         "old_value": measurement["raw_token"], "new_value": new_value, "unit": measurement["unit"]}],
            "status": "draft", "created_at": now, "updated_at": now,
            "conflict": {"kind": "none", "detected_at": None, "current_source_fingerprint": None, "current_values": []},
        }
        connection.execute("INSERT INTO edit_draft VALUES (?, ?, ?)", (draft["id"], measurement_id, json.dumps(draft, ensure_ascii=False)))
        return draft


def list_edit_drafts(database_path, analysis_id):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT d.definition_json, m.source_cell, m.measurement_id, j.entry_json,
                   COALESCE(s.linked_path, json_extract(b.plan_json, '$.original_source_path')) AS external_path
            FROM edit_draft d JOIN measurement m USING (measurement_id)
            JOIN analysis a USING (analysis_id)
            JOIN source_file s ON s.source_id = a.source_id
            JOIN import_batch b ON b.import_batch_id = a.import_batch_id
            LEFT JOIN operation_journal j ON j.edit_draft_id = d.id
            WHERE m.analysis_id = ? ORDER BY d.rowid DESC
        """, (analysis_id,))
        return {"drafts": [{"draft": json.loads(row[0]), "source_cell": row[1], "measurement_id": row[2],
                            "operation": json.loads(row[3]) if row[3] else None, "external_path": row[4]} for row in rows]}


def _source_evidence(measurement, change, content=None):
    path = measurement["external_path"]
    if not path:
        return "missing_source", None, []
    if content is None:
        try:
            content = Path(path).read_bytes()
        except OSError:
            return "missing_source", None, []
    fingerprint = sha256(content).hexdigest()
    values = []
    if Path(path).suffix.lower() == ".xlsx":
        try:
            sheet = next((sheet for sheet in _read_xlsx(BytesIO(content)) if sheet.name == measurement["sheet_name"]), None)
            row = measurement["source_row_number"]
            column = measurement["physical_source_column_index"]
            if sheet is not None and row is not None and column is not None:
                observed = sheet.rows[row - 1][column] if row <= len(sheet.rows) and column < len(sheet.rows[row - 1]) else None
                values.append({"analysis_id": change["analysis_id"], "field": change["field"], "current_value": observed})
        except (ImportCommandError, ParseError, KeyError):
            pass
    if fingerprint != measurement["source_fingerprint_sha256"]:
        return "source_changed", fingerprint, values
    if values and values[0]["current_value"] != change["old_value"]:
        return "value_changed", fingerprint, values
    return "none", fingerprint, values


def _load_draft(connection, draft_id):
    stored = connection.execute("SELECT * FROM edit_draft WHERE id = ?", (draft_id,)).fetchone()
    if not stored:
        raise ImportCommandError("EDIT_DRAFT_NOT_FOUND", "Черновик не найден.")
    measurement = _measurement(connection, stored["measurement_id"])
    if not measurement or measurement["batch_status"] != "applied" or measurement["retracted"] is not None:
        raise ImportCommandError("EDIT_MEASUREMENT_UNAVAILABLE", "Измерение недоступно для проверки черновика.")
    return json.loads(stored["definition_json"]), measurement


def _record_evidence(connection, draft, kind, fingerprint, values):
    draft["status"] = "draft" if kind == "none" else "conflict"
    draft["updated_at"] = _now()
    draft["conflict"] = {"kind": kind, "current_source_fingerprint": fingerprint, "current_values": values,
                         "detected_at": draft["updated_at"] if kind != "none" else None}
    _persist_draft(connection, draft)
    return draft


def _persist_draft(connection, draft):
    connection.execute("UPDATE edit_draft SET definition_json = ? WHERE id = ?",
                       (json.dumps(draft, ensure_ascii=False), draft["id"]))


def check_edit_draft(database_path, draft_id):
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        draft, measurement = _load_draft(connection, draft_id)
        if draft["status"] == "committed":
            return draft
        return _record_evidence(connection, draft, *_source_evidence(measurement, draft["changes"][0]))


def _write_content(stream, content):
    stream.seek(0)
    stream.write(content)
    stream.truncate()
    stream.flush()
    os.fsync(stream.fileno())


def _persist_operation(connection, draft_id, entry):
    connection.execute("""
        INSERT INTO operation_journal (id, edit_draft_id, entry_json) VALUES (?, ?, ?)
        ON CONFLICT(edit_draft_id) DO UPDATE SET entry_json = excluded.entry_json
    """, (entry["id"], draft_id, json.dumps(entry, ensure_ascii=False)))


def _finish_edit(connection, draft, entry):
    entry["state"] = "applied"
    entry["parameters"]["phase"] = "completed"
    draft["status"] = "committed"
    draft["updated_at"] = _now()
    draft["conflict"] = {"kind": "none", "detected_at": None, "current_source_fingerprint": None, "current_values": []}
    result = {"applied": True, "draft": draft, "operation": entry}
    try:
        with connection:
            _persist_operation(connection, draft["id"], entry)
            _persist_draft(connection, draft)
    except sqlite3.Error:
        result["maintenance_error"] = "XLSX сохранён. Повторите команду, чтобы завершить запись в журнал."
    return result


def commit_edit_draft(database_path, draft_id, actor, reason):
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ImportCommandError("EDIT_CONFIRMATION_REQUIRED", "Укажите автора и причину правки.")
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        draft, measurement = _load_draft(connection, draft_id)
        previous = connection.execute("SELECT entry_json FROM operation_journal WHERE edit_draft_id = ?", (draft_id,)).fetchone()
        entry = json.loads(previous[0]) if previous else None
        if draft["status"] == "committed":
            return {"applied": True, "draft": draft, "operation": entry}
        external = measurement["external_path"]
        if not external or not Path(external).is_file():
            draft = _record_evidence(connection, draft, "missing_source", None, [])
            connection.commit()
            return {"applied": False, "draft": draft}
        path = Path(external)
        if path.suffix.lower() != ".xlsx":
            raise ImportCommandError("EDIT_XLSX_UNSUPPORTED", "Защищённая запись поддерживается для файлов XLSX.")
        change = draft["changes"][0]
        with exclusive_file(path) as stream:
            original = stream.read()
            observed_hash = sha256(original).hexdigest()
            if entry and entry["parameters"]["after_sha256"] == observed_hash:
                return _finish_edit(connection, draft, entry)
            kind, fingerprint, values = _source_evidence(measurement, change, original)
            if kind != "none":
                draft = _record_evidence(connection, draft, kind, fingerprint, values)
                connection.commit()
                return {"applied": False, "draft": draft}
            if not values or measurement["source_cell"] is None:
                raise ImportCommandError("EDIT_XLSX_UNSUPPORTED", "Исходная ячейка не подтверждена.")
            corrected = corrected_workbook(original, measurement["sheet_name"], measurement["source_cell"],
                                           change["old_value"], change["new_value"])
            operation_id = entry["id"] if entry else _id()
            backup = path.with_name(f"{path.name}.before-edit-{operation_id}.bak")
            try:
                if backup.exists():
                    if backup.read_bytes() != original:
                        raise ImportCommandError("EDIT_BACKUP_INVALID", "Резервная копия не соответствует исходному файлу.",
                                                 {"backup_path": str(backup)})
                else:
                    with backup.open("xb") as stream_backup:
                        stream_backup.write(original)
                        stream_backup.flush()
                        os.fsync(stream_backup.fileno())
            except OSError as error:
                raise ImportCommandError("EDIT_BACKUP_FAILED", "Не удалось создать резервную копию. Исходный файл не изменён.") from error
            entry = {
                "id": operation_id, "project_id": draft["project_id"], "action": "commit_edit_draft", "category": "persistence",
                "scope": [{"entity_type": "edit_draft", "entity_id": draft_id, "expected_revision": None, "result_revision": None}],
                "parameters": {"phase": "prepared", "source_path": str(path), "backup_path": str(backup), "reason": reason.strip(),
                               "before_sha256": observed_hash, "after_sha256": sha256(corrected).hexdigest(),
                               "sheet_name": measurement["sheet_name"], "source_cell": measurement["source_cell"],
                               "measurement_id": measurement["measurement_id"], "change": change},
                "reversible": False, "inverse_action": None, "state": "failed", "actor": actor.strip(), "created_at": _now(),
            }
            _persist_operation(connection, draft_id, entry)
            connection.commit()
            try:
                _write_content(stream, corrected)
            except OSError as error:
                try:
                    _write_content(stream, original)
                except OSError:
                    raise ImportCommandError("EDIT_RECOVERY_REQUIRED", "Не удалось восстановить исходный файл после сбоя записи.",
                                             {"backup_path": str(backup)}) from error
                raise ImportCommandError("EDIT_WRITE_FAILED", "Запись не удалась. Исходный файл восстановлен.",
                                         {"backup_path": str(backup)}) from error
            return _finish_edit(connection, draft, entry)
