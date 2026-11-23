"""Project journal projections and dispatch to the existing domain inverses."""

from contextlib import closing
import json
from uuid import UUID

from .generations import undo_generation
from .import_apply import open_project
from .import_preview import ImportCommandError
from .plot_data import undo_plot_visibility
from .sample_workspace import undo_point_link


def _operation_id(value, field):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError(field)
    return value


def _entry_row(connection, operation_id):
    row = connection.execute(
        "SELECT rowid, entry_json FROM operation_journal WHERE id = ?", (operation_id,),
    ).fetchone()
    if row is None:
        raise ImportCommandError("OPERATION_NOT_FOUND", "Запись журнала не найдена в этом проекте.")
    return row


def list_operations(database_path, *, category=None, before_id=None, limit=50):
    if category is not None and category not in ("domain", "view_only", "persistence"):
        raise ValueError("category")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit")
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        before = _entry_row(connection, _operation_id(before_id, "before_id"))["rowid"] if before_id is not None else None
        rows = connection.execute("""
            SELECT id, json_extract(entry_json, '$.action') AS action,
                   json_extract(entry_json, '$.category') AS category, json_extract(entry_json, '$.state') AS state,
                   json_extract(entry_json, '$.actor') AS actor, json_extract(entry_json, '$.created_at') AS created_at,
                   json_array_length(entry_json, '$.scope') AS scope_count,
                   json_extract(entry_json, '$.reversible') AS reversible
            FROM operation_journal
            WHERE (? IS NULL OR rowid < ?) AND (? IS NULL OR json_extract(entry_json, '$.category') = ?)
            ORDER BY rowid DESC LIMIT ?
        """, (before, before, category, category, limit + 1)).fetchall()
    entries = [{**dict(row), "reversible": bool(row["reversible"])} for row in rows[:limit]]
    return {"entries": entries, "next_before_id": entries[-1]["id"] if len(rows) > limit else None}


def open_operation(database_path, operation_id):
    _operation_id(operation_id, "operation_id")
    with closing(open_project(database_path)) as connection:
        return json.loads(_entry_row(connection, operation_id)["entry_json"])


def undo_operation(database_path, operation_id, actor, *, session_id=None, hidden_analysis_ids=None):
    entry = open_operation(database_path, operation_id)
    if entry["state"] != "applied" or not entry["reversible"]:
        raise ImportCommandError("OPERATION_UNDO_UNAVAILABLE", "Эта операция недоступна для отмены.")
    if entry["action"] == "assign_generation":
        return undo_generation(database_path, operation_id, actor)
    if entry["action"] in ("link_analytical_point", "unlink_analytical_point"):
        return undo_point_link(database_path, operation_id, actor)
    if entry["action"] in ("hide_plot_points", "restore_plot_points"):
        return undo_plot_visibility(database_path, operation_id, session_id, hidden_analysis_ids, actor=actor)
    raise ImportCommandError("OPERATION_UNDO_UNAVAILABLE", "Эта операция недоступна для отмены.")
