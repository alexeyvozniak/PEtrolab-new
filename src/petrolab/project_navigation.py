"""Read models for project overview and global analysis search."""

from contextlib import closing
from pathlib import Path

from .desktop_workflow import analysis_identity
from .import_apply import open_project


def _search_text(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("search")
    return value.strip().casefold()


def search_analyses(database_path, query="", mineral="", source="", method="", source_id="", limit=50, offset=0, sample_id=""):
    if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
        raise ValueError("pagination")
    exact_source = _search_text(source_id)
    exact_sample = _search_text(sample_id)
    parameters = (*map(_search_text, (query, mineral, source, method)), exact_source, exact_source, exact_sample, exact_sample)
    with closing(open_project(database_path)) as connection:
        connection.create_function("casefold", 1, lambda value: str(value or "").casefold(), deterministic=True)
        connection.execute("BEGIN")
        projection = """
            WITH candidates AS (
                SELECT a.analysis_id, a.identity_json, a.sheet_name, a.source_row_number, a.block_id, recipe.recipe_json,
                       a.source_column_number, a.created_at, s.source_id, s.display_name AS source_name,
                       s.source_fingerprint_sha256 AS source_sha256,
                       json_extract(e.sample_association_json, '$.sample_id') AS sample_id,
                       COALESCE(p.sample_name, json_extract(e.sample_association_json, '$.reported.value'), '') AS sample_name,
                       COALESCE(json_extract(e.mineral_verification_json, '$.accepted.target'),
                                json_extract(e.mineral_assignment_json, '$.value'),
                                json_extract(e.reported_mineral_json, '$.value'), '') AS mineral,
                       COALESCE(json_extract(e.analytical_method_json, '$.value'), '') AS method
                FROM analysis a JOIN source_file s ON s.source_id = a.source_id
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                JOIN import_recipe_revision recipe ON recipe.recipe_revision_id = b.recipe_revision_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                LEFT JOIN analysis_import_semantics e ON e.analysis_id = a.analysis_id
                LEFT JOIN sample p ON p.sample_id = json_extract(e.sample_association_json, '$.sample_id')
                WHERE b.status = 'applied' AND x.import_batch_id IS NULL
            ), matches AS (
                SELECT * FROM candidates
                WHERE instr(casefold(identity_json || ' ' || sample_name || ' ' || mineral || ' ' || method || ' ' || source_name || ' ' || sheet_name), ?)
                  AND instr(casefold(mineral), ?) AND instr(casefold(source_name), ?) AND instr(casefold(method), ?)
                  AND (? = '' OR source_id = ?)
                  AND (? = '' OR sample_id = ?)
            )
        """
        total = connection.execute(projection + "SELECT count(*) FROM matches", parameters).fetchone()[0]
        rows = connection.execute(projection + """
            SELECT * FROM matches ORDER BY created_at DESC, sheet_name, source_row_number, source_column_number, analysis_id
            LIMIT ? OFFSET ?
        """, (*parameters, limit, offset)).fetchall()
        analyses = []
        for row in rows:
            record = dict(row)
            fields = analysis_identity(row)
            record["identity"] = fields.get("Analysis") or fields.get("Point") or fields.get("Sample") or next((value for value in fields.values() if value), "")
            record.pop("recipe_json")
            record.pop("identity_json")
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
            WHERE b.status = 'applied' AND x.import_batch_id IS NULL
            ORDER BY b.applied_at DESC, b.rowid DESC LIMIT 12
        """).fetchall()
        groups = connection.execute("""
            SELECT g.id, g.name, g.created_at, g.created_by,
                   (SELECT COUNT(*) FROM work_group_analysis WHERE work_group_id = g.id) AS analysis_count
            FROM work_group g ORDER BY g.created_at DESC, g.rowid DESC LIMIT 5
        """).fetchall()
        name = Path(database_path).stem.replace("-", " ")
        return {"project_id": identity, "project_name": "Локальный проект PetroLab" if name == "petrolab v2" else name,
                "recent_imports": [dict(row) for row in imports], "recent_groups": [dict(row) for row in groups]}
