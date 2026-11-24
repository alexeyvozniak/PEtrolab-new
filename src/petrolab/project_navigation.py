"""Read models for project overview and global analysis search."""

from contextlib import closing
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from uuid import UUID

from .desktop_workflow import analysis_identity
from .import_apply import _id, open_project
from .import_preview import ImportCommandError

_PUBLICATION_FIELDS = json.dumps([
    "Source", "Publication authors", "Publication year", "Publication title", "Publication journal", "DOI", "Publication URL",
])
_DOI_PREFIX = r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)"


def _publication_link(field, value):
    value = value.strip()
    if field == "DOI":
        identifier = re.sub(_DOI_PREFIX, "", value, flags=re.IGNORECASE)
        if re.fullmatch(r"10\.\d{4,9}/[^\s]+", identifier):
            return "https://doi.org/" + quote(identifier, safe="/")
    if field == "Publication URL" and not any(character.isspace() or ord(character) < 32 for character in value):
        try:
            link = urlsplit(value)
            if link.scheme in {"https", "http"} and link.hostname and link.username is None and link.password is None:
                return value
        except ValueError:
            pass
    return None


def _search_text(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("search")
    return value.strip().casefold()


def search_analyses(database_path, query="", mineral="", source="", method="", source_id="", limit=50, offset=0, sample_id="", *, ids_only=False,
                    analysis_ids=None):
    if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
        raise ValueError("pagination")
    exact_source = _search_text(source_id)
    exact_sample = _search_text(sample_id)
    if analysis_ids is not None and (not isinstance(analysis_ids, list)
            or not all(isinstance(value, str) and str(UUID(value)) == value for value in analysis_ids)
            or len(analysis_ids) != len(set(analysis_ids))):
        raise ValueError("analysis_ids")
    parameters = dict(zip(("query", "mineral", "source", "method"), map(_search_text, (query, mineral, source, method))))
    parameters.update(exact_source=exact_source, exact_sample=exact_sample, publication_fields=_PUBLICATION_FIELDS,
                      query_doi=re.sub(_DOI_PREFIX, "", parameters["query"]) or parameters["query"],
                      source_doi=re.sub(_DOI_PREFIX, "", parameters["source"]) or parameters["source"])
    selection_join = ""
    selection_position = "NULL"
    order = " ORDER BY created_at DESC, sheet_name, source_row_number, source_column_number, analysis_id"
    if analysis_ids is not None:
        parameters["selection_ids"] = json.dumps(analysis_ids)
        selection_join = "JOIN json_each(:selection_ids) AS selected ON selected.value = a.analysis_id"
        selection_position = "selected.key"
        order = " ORDER BY selection_position"
    with closing(open_project(database_path)) as connection:
        connection.create_function("casefold", 1, lambda value: str(value or "").casefold(), deterministic=True)
        connection.execute("BEGIN")
        projection = f"""
            WITH candidates AS (
                SELECT a.analysis_id, a.identity_json, a.sheet_name, a.source_row_number, a.block_id, recipe.recipe_json,
                       {selection_position} AS selection_position,
                       a.source_column_number, a.created_at, s.source_id, s.display_name AS source_name,
                       s.source_fingerprint_sha256 AS source_sha256,
                       json_extract(e.sample_association_json, '$.sample_id') AS sample_id,
                       COALESCE(p.sample_name, json_extract(e.sample_association_json, '$.reported.value'), '') AS sample_name,
                       COALESCE(json_extract(e.mineral_verification_json, '$.accepted.target'),
                                json_extract(e.mineral_assignment_json, '$.value'),
                                json_extract(e.reported_mineral_json, '$.value'), '') AS mineral,
                       COALESCE(json_extract(e.analytical_method_json, '$.value'), '') AS method
                FROM analysis a JOIN source_file s ON s.source_id = a.source_id
                {selection_join}
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                JOIN import_recipe_revision recipe ON recipe.recipe_revision_id = b.recipe_revision_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                LEFT JOIN analysis_import_semantics e ON e.analysis_id = a.analysis_id
                LEFT JOIN sample p ON p.sample_id = json_extract(e.sample_association_json, '$.sample_id')
                WHERE b.status = 'applied' AND x.import_batch_id IS NULL
            ), matches AS (
                SELECT * FROM candidates c
                WHERE (instr(casefold(identity_json || ' ' || sample_name || ' ' || mineral || ' ' || method || ' ' || source_name || ' ' || sheet_name), :query)
                       OR EXISTS (SELECT 1 FROM analysis_source_metadata m WHERE m.analysis_id = c.analysis_id
                                  AND m.canonical_field IN (SELECT value FROM json_each(:publication_fields))
                                  AND instr(casefold(m.raw_token), CASE WHEN m.canonical_field = 'DOI' THEN :query_doi ELSE :query END)))
                  AND instr(casefold(mineral), :mineral) AND instr(casefold(method), :method)
                  AND (instr(casefold(source_name), :source)
                       OR EXISTS (SELECT 1 FROM analysis_source_metadata m WHERE m.analysis_id = c.analysis_id
                                  AND m.canonical_field IN (SELECT value FROM json_each(:publication_fields))
                                  AND instr(casefold(m.raw_token), CASE WHEN m.canonical_field = 'DOI' THEN :source_doi ELSE :source END)))
                  AND (:exact_source = '' OR source_id = :exact_source)
                  AND (:exact_sample = '' OR sample_id = :exact_sample)
            )
        """
        if ids_only:
            ids = connection.execute(projection + "SELECT analysis_id FROM matches" + order, parameters)
            return {"analysis_ids": [row[0] for row in ids]}
        total = connection.execute(projection + "SELECT count(*) FROM matches", parameters).fetchone()[0]
        rows = connection.execute(projection + """
            SELECT * FROM matches
        """ + order + " LIMIT :limit OFFSET :offset", {**parameters, "limit": limit, "offset": offset}).fetchall()
        publications = {}
        for entry in connection.execute("""
            SELECT analysis_id, canonical_field, raw_token, source_cell FROM analysis_source_metadata
            WHERE analysis_id IN (SELECT value FROM json_each(:ids))
              AND canonical_field IN (SELECT value FROM json_each(:fields))
              AND trim(raw_token) <> ''
            ORDER BY source_row_number, source_column_index
        """, {"ids": json.dumps([row["analysis_id"] for row in rows]), "fields": _PUBLICATION_FIELDS}):
            field, value = entry["canonical_field"], entry["raw_token"]
            publications.setdefault(entry["analysis_id"], []).append({
                "field": field, "value": value, "source_cell": entry["source_cell"], "url": _publication_link(field, value),
            })
        analyses = []
        for row in rows:
            record = dict(row)
            fields = analysis_identity(row)
            record["identity"] = fields.get("Analysis") or fields.get("Point") or fields.get("Sample") or next((value for value in fields.values() if value), "")
            record.pop("recipe_json")
            record.pop("identity_json")
            record.pop("selection_position")
            record["publication_metadata"] = publications.get(row["analysis_id"], [])
            analyses.append(record)
        return {"analyses": analyses, "total": total, "offset": offset, "has_more": offset + len(analyses) < total}


def project_overview(database_path):
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        identity = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
        imports = connection.execute("""
            SELECT b.import_batch_id, b.source_id, s.display_name AS source_name, b.applied_at,
                   (SELECT COUNT(*) FROM analysis WHERE import_batch_id = b.import_batch_id) AS analysis_count
            FROM import_batch b JOIN source_file s ON s.source_id = b.source_id
            LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
            WHERE b.status = 'applied' AND x.import_batch_id IS NULL AND json_type(b.plan_json, '$.manual_entry') IS NULL
            ORDER BY b.applied_at DESC, b.rowid DESC LIMIT 12
        """).fetchall()
        groups = connection.execute("""
            SELECT g.id, g.name, g.created_at, g.created_by,
                   (SELECT COUNT(*) FROM work_group_analysis WHERE work_group_id = g.id) AS analysis_count
            FROM work_group g ORDER BY g.created_at DESC, g.rowid DESC LIMIT 5
        """).fetchall()
        name = Path(database_path).stem.replace("-", " ")
        tasks = connection.execute("SELECT id, title, completed, revision FROM project_work_plan_task ORDER BY rowid")
        return {"project_id": identity, "project_name": "Локальный проект PetroLab" if name == "petrolab v2" else name,
                "recent_imports": [dict(row) for row in imports], "recent_groups": [dict(row) for row in groups],
                "work_plan": [{**dict(row), "completed": bool(row["completed"])} for row in tasks]}


def save_work_plan_task(database_path, task_id, title, completed, expected_revision):
    if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 240 or type(completed) is not bool
            or type(expected_revision) is not int or expected_revision < 0
            or (task_id is None and expected_revision != 0)
            or (task_id is not None and (not isinstance(task_id, str) or len(task_id) != 36 or expected_revision == 0))):
        raise ValueError("work_plan_task")
    title = title.strip()
    revision = expected_revision + 1
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if task_id is None:
            task_id = _id()
            connection.execute("INSERT INTO project_work_plan_task VALUES (?, ?, ?, ?)",
                               (task_id, title, completed, revision))
        else:
            result = connection.execute("""
                UPDATE project_work_plan_task SET title = ?, completed = ?, revision = ?
                WHERE id = ? AND revision = ?
            """, (title, completed, revision, task_id, expected_revision))
            if result.rowcount != 1:
                raise ImportCommandError("WORK_PLAN_TASK_CONFLICT", "Задача изменилась. Откройте обзор заново перед сохранением.")
    return {"id": task_id, "title": title, "completed": completed, "revision": revision}
