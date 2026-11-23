"""Explicit Analysis Generation assignments and their journal inverses."""

from contextlib import closing
import json
from uuid import UUID

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError


def list_generations(database_path):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("SELECT id, name, created_by, created_at FROM generation ORDER BY name_key")
        return {"generations": [dict(row) for row in rows]}


def _assignments(connection, analysis_ids):
    rows = connection.execute("""
        SELECT a.analysis_id, g.generation_id, g.assignment_id, g.revision
        FROM analysis a JOIN import_batch b USING (import_batch_id)
        LEFT JOIN import_batch_retraction r USING (import_batch_id)
        LEFT JOIN analysis_generation g USING (analysis_id)
        WHERE a.analysis_id IN (SELECT value FROM json_each(?))
          AND b.status = 'applied' AND r.import_batch_id IS NULL
    """, (json.dumps(analysis_ids),))
    indexed = {row["analysis_id"]: dict(row) for row in rows}
    if len(indexed) != len(analysis_ids):
        raise ImportCommandError("GENERATION_ANALYSIS_UNAVAILABLE", "Часть выбранных анализов недоступна.",
                                 {"analysis_ids": [item for item in analysis_ids if item not in indexed]})
    return [indexed[item] for item in analysis_ids]


def _journal_entry(connection, action, actor, before, after, parameters, inverse_action):
    entry = {
        "id": _id(), "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
        "action": action, "category": "domain",
        "scope": [{"entity_type": "analysis", "entity_id": row["analysis_id"],
                   "expected_revision": row["revision"] or 0, "result_revision": revision or 0}
                  for row, revision in zip(before, after, strict=True)],
        "parameters": parameters, "reversible": inverse_action is not None, "inverse_action": inverse_action,
        "state": "applied", "actor": actor, "created_at": _now(),
    }
    connection.execute("INSERT INTO operation_journal (id, entry_json) VALUES (?, ?)",
                       (entry["id"], json.dumps(entry, ensure_ascii=False)))
    return entry


def _write_assignment(connection, item):
    if item["generation_id"] is None:
        connection.execute("DELETE FROM analysis_generation WHERE analysis_id = ?", (item["analysis_id"],))
        return
    connection.execute("""
        INSERT INTO analysis_generation (analysis_id, generation_id, assignment_id, revision)
        VALUES (:analysis_id, :generation_id, :assignment_id, :revision)
        ON CONFLICT (analysis_id) DO UPDATE SET
            generation_id = excluded.generation_id, assignment_id = excluded.assignment_id, revision = excluded.revision
    """, item)


def assign_generation(database_path, analysis_ids, actor, *, generation_id=None, new_name=None):
    if (not analysis_ids or not isinstance(analysis_ids, list)
            or not all(isinstance(item, str) and str(UUID(item)) == item for item in analysis_ids)
            or len(set(analysis_ids)) != len(analysis_ids)):
        raise ValueError("analysis_ids")
    if not isinstance(actor, str) or not actor.strip() or len(actor.strip()) > 120:
        raise ValueError("actor")
    if (generation_id is None) == (new_name is None):
        raise ValueError("generation_id or new_name")
    if new_name is not None and (not isinstance(new_name, str) or not 1 <= len(new_name.strip()) <= 120):
        raise ValueError("new_name")
    if generation_id is not None and (not isinstance(generation_id, str) or str(UUID(generation_id)) != generation_id):
        raise ValueError("generation_id")

    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        before = _assignments(connection, analysis_ids)
        if new_name is not None:
            name = new_name.strip()
            if connection.execute("SELECT 1 FROM generation WHERE name_key = ?", (name.casefold(),)).fetchone():
                raise ImportCommandError("GENERATION_NAME_EXISTS", "Выберите существующее поколение по его имени.")
            generation_id = _id()
            connection.execute("INSERT INTO generation VALUES (?, ?, ?, ?, ?)",
                               (generation_id, name, name.casefold(), actor.strip(), _now()))
        elif connection.execute("SELECT 1 FROM generation WHERE id = ?", (generation_id,)).fetchone() is None:
            raise ImportCommandError("GENERATION_UNAVAILABLE", "Поколение недоступно в этом проекте.")
        changed = [row for row in before if row["generation_id"] != generation_id]
        if not changed:
            raise ImportCommandError("GENERATION_ALREADY_ASSIGNED", "У выбранных анализов уже назначено это поколение.")
        revisions = [(row["revision"] or 0) + 1 for row in changed]
        entry = _journal_entry(
            connection, "assign_generation", actor.strip(), changed, revisions,
            {"generation_id": generation_id, "analysis_ids": [row["analysis_id"] for row in changed]},
            {"action": "restore_generation", "parameters": {"assignments": changed}},
        )
        for row, revision in zip(changed, revisions, strict=True):
            _write_assignment(connection, {**row, "generation_id": generation_id, "assignment_id": entry["id"], "revision": revision})
        return entry


def undo_generation(database_path, operation_id, actor):
    if not isinstance(actor, str) or not actor.strip() or len(actor.strip()) > 120:
        raise ValueError("actor")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT entry_json FROM operation_journal WHERE id = ?", (operation_id,)).fetchone()
        entry = json.loads(row[0]) if row else {}
        if entry.get("action") != "assign_generation" or entry.get("state") != "applied":
            raise ImportCommandError("GENERATION_UNDO_UNAVAILABLE", "Назначение недоступно для отмены.")
        original = entry["inverse_action"]["parameters"]["assignments"]
        before = _assignments(connection, [item["analysis_id"] for item in original])
        touched = [item["analysis_id"] for item in before if item["assignment_id"] != operation_id]
        if touched:
            raise ImportCommandError("GENERATION_UNDO_CONFLICT", "После этого назначения некоторые поколения изменились.",
                                     {"analysis_ids": touched})
        for item in original:
            _write_assignment(connection, item)
        entry["state"] = "undone"
        connection.execute("UPDATE operation_journal SET entry_json = ? WHERE id = ?",
                           (json.dumps(entry, ensure_ascii=False), operation_id))
        return _journal_entry(connection, "restore_generation", actor.strip(), before, [item["revision"] for item in original],
                              {"assignment_operation_id": operation_id}, None)
