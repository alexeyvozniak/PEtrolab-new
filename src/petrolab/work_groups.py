"""Immutable named snapshots of project Analysis IDs."""

from contextlib import closing
import json
from uuid import UUID

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError


def create_work_group(database_path, name, analysis_ids, created_by, description="", *, calculation_origin=None):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ImportCommandError("WORK_GROUP_NAME_INVALID", "Укажите название рабочей группы до 120 символов.")
    if not isinstance(created_by, str) or not created_by.strip():
        raise ImportCommandError("WORK_GROUP_AUTHOR_REQUIRED", "Укажите автора рабочей группы.")
    if not isinstance(description, str) or len(description) > 2000:
        raise ValueError("description")
    if not isinstance(analysis_ids, list) or not analysis_ids or not all(isinstance(item, str) for item in analysis_ids):
        raise ValueError("analysis_ids")
    for analysis_id in analysis_ids:
        if str(UUID(analysis_id)) != analysis_id:
            raise ValueError("analysis_ids")
    if len(set(analysis_ids)) != len(analysis_ids):
        raise ValueError("analysis_ids")

    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        unavailable = connection.execute("""
            SELECT requested.value FROM json_each(?) requested
            LEFT JOIN analysis a ON a.analysis_id = requested.value
            LEFT JOIN import_batch b ON b.import_batch_id = a.import_batch_id
            LEFT JOIN import_batch_retraction r ON r.import_batch_id = a.import_batch_id
            WHERE a.analysis_id IS NULL OR b.status != 'applied' OR r.import_batch_id IS NOT NULL
        """, (json.dumps(analysis_ids),)).fetchall()
        if unavailable:
            raise ImportCommandError("WORK_GROUP_ANALYSES_UNAVAILABLE", "Часть выбранных анализов недоступна в проекте.",
                                     {"unavailable_count": len(unavailable)})
        group = {
            "id": _id(),
            "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
            "name": name.strip(),
            "description": description,
            "created_by": created_by.strip(),
            "created_at": _now(),
        }
        connection.execute("""
            INSERT INTO work_group (id, project_id, name, description, created_by, created_at)
            VALUES (:id, :project_id, :name, :description, :created_by, :created_at)
        """, group)
        connection.executemany("""
            INSERT INTO work_group_analysis (work_group_id, analysis_id, position) VALUES (?, ?, ?)
        """, [(group["id"], analysis_id, position) for position, analysis_id in enumerate(analysis_ids)])
        if calculation_origin is not None:
            connection.execute("INSERT INTO work_group_calculation_origin VALUES (?, ?, ?)",
                               (group["id"], calculation_origin["calculation_run_id"], calculation_origin["cluster"]))
            group["calculation_origin"] = calculation_origin
        return {**group, "analysis_ids": analysis_ids, "revision": 1}


def list_work_groups(database_path):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT g.*, ga.analysis_id, origin.calculation_run_id, origin.cluster,
                   (b.status = 'applied' AND r.import_batch_id IS NULL) AS active
            FROM work_group g
            JOIN work_group_analysis ga ON ga.work_group_id = g.id
            JOIN analysis a ON a.analysis_id = ga.analysis_id
            JOIN import_batch b ON b.import_batch_id = a.import_batch_id
            LEFT JOIN work_group_calculation_origin origin ON origin.work_group_id = g.id
            LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
            ORDER BY g.created_at DESC, g.rowid DESC, ga.position
        """)
        groups = {}
        for row in rows:
            item = groups.get(row["id"])
            if item is None:
                group = {key: row[key] for key in ("id", "project_id", "name", "description", "created_by", "created_at")}
                if row["calculation_run_id"] is not None:
                    group["calculation_origin"] = {"calculation_run_id": row["calculation_run_id"], "cluster": row["cluster"]}
                item = {"group": {**group, "analysis_ids": [], "revision": 1}, "unavailable_analysis_ids": []}
                groups[row["id"]] = item
            item["group"]["analysis_ids"].append(row["analysis_id"])
            if not row["active"]:
                item["unavailable_analysis_ids"].append(row["analysis_id"])
        return {"groups": list(groups.values())}
