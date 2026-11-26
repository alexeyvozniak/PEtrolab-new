"""Atomic application of a validated import plan to local SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .import_preview import (
    ImportCommandError, create_import_plan, inspect_source, recipe_sheet_layout, semantic_fingerprint, validate_recipe,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _id() -> str:
    return str(uuid.uuid4())


def _column_letters(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _cell_value(row: tuple[str | None, ...], index: int) -> str | None:
    return row[index] if 0 <= index < len(row) else None


def _duplicate_groups(plan: dict[str, Any]) -> list[list[str]]:
    for warning in plan.get("warnings", []):
        if warning.get("code") == "DUPLICATE_CANDIDATES" and isinstance(warning.get("preview_ids"), list):
            return [list(group) for group in warning["preview_ids"] if isinstance(group, list)]
    return []


def _duplicate_groups_fingerprint(groups: list[list[str]]) -> str:
    canonical_groups = sorted(sorted(str(item) for item in group) for group in groups)
    payload = json.dumps(canonical_groups, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_duplicate_review(plan: dict[str, Any], recipe: dict[str, Any]) -> None:
    groups = _duplicate_groups(plan)
    if not groups:
        return
    decisions = recipe.get("global_decisions") or {}
    policy = decisions.get("duplicate_policy")
    if policy == "skip_exact_after_review":
        raise ImportCommandError(
            "DUPLICATE_POLICY_NOT_IMPLEMENTED",
            "Skipping duplicate rows is not implemented in this import version; no records were written.",
        )
    if policy != "keep_all":
        raise ImportCommandError(
            "DUPLICATE_REVIEW_REQUIRED",
            "Duplicate candidates must be reviewed before this import can be saved.",
            {"candidate_group_count": len(groups)},
        )
    # Recipe schema v1 predates persisted duplicate-review evidence. Preserve
    # compatibility for immutable old recipes, but v2 must carry proof that the
    # keep-all decision was made against these exact candidate groups.
    if int(recipe.get("schema_version", 1)) < 2:
        return
    review = decisions.get("duplicate_review")
    expected = _duplicate_groups_fingerprint(groups)
    if not isinstance(review, dict) or review.get("decision") != "keep_all" or review.get("groups_fingerprint_sha256") != expected:
        raise ImportCommandError(
            "DUPLICATE_REVIEW_REQUIRED",
            "The saved duplicate review does not match the current import plan.",
            {"candidate_group_count": len(groups)},
        )


def _require_non_empty_plan(plan: dict[str, Any]) -> None:
    summary = plan.get("summary") if isinstance(plan, dict) else None
    analysis_count = summary.get("planned_analysis_count", 0) if isinstance(summary, dict) else 0
    measurement_count = summary.get("planned_measurement_count", 0) if isinstance(summary, dict) else 0
    if not isinstance(analysis_count, int) or not isinstance(measurement_count, int) or analysis_count < 1 or measurement_count < 1:
        raise ImportCommandError(
            "IMPORT_PLAN_EMPTY",
            "Import needs at least one Analysis and one Measurement; no records were written.",
            {"planned_analysis_count": analysis_count, "planned_measurement_count": measurement_count},
        )


def _require_mapping_review(recipe: dict[str, Any]) -> None:
    """Keep an undecided populated source field from being silently discarded.

    The UI makes this state visible, but the service must enforce it too: a
    direct NDJSON caller cannot bypass the scientist's explicit assignment or
    explicit Ignore decision.
    """
    unresolved: list[dict[str, Any]] = []
    for section in recipe.get("sections", []):
        if not section.get("enabled", True):
            continue
        for mapping in section.get("mappings", []):
            if mapping.get("target_role") == "ignore" and mapping.get("review_decision") == "unresolved":
                unresolved.append({
                    "sheet_name": section.get("sheet_name"),
                    "block_id": section.get("block_id"),
                    "source_header": mapping.get("source_header"),
                })
    if unresolved:
        raise ImportCommandError(
            "MAPPING_REVIEW_REQUIRED",
            "Every populated unrecognized field needs an explicit assignment or an explicit Ignore decision before import.",
            {"unresolved_field_count": len(unresolved), "examples": unresolved[:8]},
        )


def _section_for_record(recipe: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    for section in recipe.get("sections", []):
        if section.get("sheet_name") == record.get("sheet_name") and section.get("block_id") == record.get("block_id"):
            return section
    raise ImportCommandError(
        "RECIPE_SCHEMA_INCOMPATIBLE",
        "Planned record no longer resolves to its logical block.",
        {"sheet_name": record.get("sheet_name"), "block_id": record.get("block_id")},
    )


def _source_metadata_for_record(inspection: Any, recipe: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    """Read source metadata losslessly without promoting it to controlled entities."""
    from .semantic_import import cell_ignored
    section = _section_for_record(recipe, record)
    sheet = next((item for item in inspection.sheets if item.name == record["sheet_name"]), None)
    if sheet is None:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Planned record sheet is unavailable.")
    mappings = [item for item in section.get("mappings", []) if item.get("target_role") == "metadata"]
    orientation = record.get("orientation", "rows_are_analyses")
    result: list[dict[str, Any]] = []
    if orientation == "rows_are_analyses":
        row_number = int(record["row_number"])
        row = sheet.rows[row_number - 1]
        for mapping in mappings:
            column_index = mapping.get("source_column_index")
            if not isinstance(column_index, int) or column_index < 0:
                continue
            if cell_ignored(recipe, record['block_id'], row_number, column_index):
                continue
            result.append({
                "canonical_field": mapping.get("canonical_field") or mapping.get("source_header") or "Metadata",
                "raw_token": _cell_value(row, column_index),
                "source_header": str(mapping.get("source_header") or ""),
                "source_row_number": row_number,
                "source_column_index": column_index,
                "source_cell": f"{_column_letters(column_index)}{row_number}",
            })
        return result

    source_column_number = record.get("source_column_number")
    if not isinstance(source_column_number, int) or source_column_number < 1:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Transposed record has no physical source column.")
    column_index = source_column_number - 1
    for mapping in mappings:
        row_index = mapping.get("source_row_index")
        if not isinstance(row_index, int) or row_index < 0 or row_index >= len(sheet.rows):
            continue
        row_number = row_index + 1
        if cell_ignored(recipe, record['block_id'], row_number, column_index):
            continue
        result.append({
            "canonical_field": mapping.get("canonical_field") or mapping.get("source_header") or "Metadata",
            "raw_token": _cell_value(sheet.rows[row_index], column_index),
            "source_header": str(mapping.get("source_header") or ""),
            "source_row_number": row_number,
            "source_column_index": column_index,
            "source_cell": f"{_column_letters(column_index)}{row_number}",
        })
    return result


def open_project(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    existing_tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
    )}
    if existing_tables and "schema_migration" not in existing_tables:
        connection.close()
        raise ImportCommandError(
            "PROJECT_SCHEMA_UNSUPPORTED",
            "Файл не содержит истории миграций PetroLab. Проект не изменён.",
            {},
        )
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migration (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migration")}
    if not applied and existing_tables - {"schema_migration"}:
        connection.close()
        raise ImportCommandError(
            "PROJECT_SCHEMA_UNSUPPORTED",
            "История миграций проекта пуста, но база содержит данные. Проект не изменён.",
            {},
        )
    migrations = sorted(MIGRATIONS.glob("*.sql"))
    supported_versions = {int(item.name.split("_", 1)[0]) for item in migrations}
    if not supported_versions or applied - supported_versions:
        connection.close()
        raise ImportCommandError(
            "PROJECT_SCHEMA_UNSUPPORTED",
            "Проект создан более новой или несовместимой версией PetroLab. Откройте его в совместимой версии приложения.",
            {"unsupported_migrations": sorted(applied - supported_versions)},
        )
    missing_versions = sorted(version for version in supported_versions if version < max(applied, default=0) and version not in applied)
    if missing_versions:
        connection.close()
        raise ImportCommandError(
            "PROJECT_SCHEMA_UNSUPPORTED",
            "В истории миграций проекта пропущены записи. Проект не изменён.",
            {"missing_migrations": missing_versions},
        )
    if 11 in applied and not {"project_identity", "work_group", "work_group_analysis"} <= existing_tables:
        connection.close()
        raise ImportCommandError(
            "PROJECT_SCHEMA_UNSUPPORTED",
            "Структура проекта не соответствует миграции рабочих групп. Проект не изменён.",
            {"incompatible_migration": 11},
        )
    if 12 in applied and "table_view" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции представлений таблицы.",
                                 {"incompatible_migration": 12})
    if 13 in applied and "edit_draft" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции черновиков правок.",
                                 {"incompatible_migration": 13})
    if 14 in applied and "operation_journal" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции журнала операций.",
                                 {"incompatible_migration": 14})
    if 15 in applied and "plot_specification" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции раскладок.",
                                 {"incompatible_migration": 15})
    if 16 in applied and not {"sample_context", "sample_note"} <= existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции паспортов образцов.",
                                 {"incompatible_migration": 16})
    if 17 in applied and not {"calculation_run", "work_group_calculation_origin"} <= existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции расчётов.",
                                 {"incompatible_migration": 17})
    if 18 in applied and not {"workspace_snapshot", "analysis_template"} <= existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции рабочих состояний.",
                                 {"incompatible_migration": 18})
    if 19 in applied and "media_link" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции связей медиа.",
                                 {"incompatible_migration": 19})
    if 20 in applied and "media_import_draft" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции черновиков изображений.",
                                 {"incompatible_migration": 20})
    if 21 in applied and not any(row["name"] == "thin_section_id" and not row["notnull"]
                                 for row in connection.execute("PRAGMA table_info(media_asset)")):
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции полевых снимков.",
                                 {"incompatible_migration": 21})
    if 22 in applied and not {"generation", "analysis_generation"} <= existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции поколений.",
                                 {"incompatible_migration": 22})
    if 24 in applied and "project_plot_colors" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции цветовых схем.",
                                 {"incompatible_migration": 24})
    if 25 in applied and "project_plot_presets" not in existing_tables:
        connection.close()
        raise ImportCommandError("PROJECT_SCHEMA_UNSUPPORTED", "Структура проекта не соответствует миграции избранных диаграмм.",
                                 {"incompatible_migration": 25})
    meta_exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_meta'").fetchone()
    if meta_exists:
        meta = connection.execute("SELECT project_schema_version FROM project_meta WHERE singleton = 1").fetchone()
        if meta and meta[0] > max(applied, default=0):
            connection.close()
            raise ImportCommandError(
                "PROJECT_SCHEMA_UNSUPPORTED",
                "Версия схемы проекта не соответствует истории миграций. Проект не изменён.",
                {"project_schema_version": meta[0], "latest_recorded_migration": max(applied, default=0)},
            )
    pending = [item for item in migrations if int(item.name.split("_", 1)[0]) not in applied]
    backup_path = None
    if applied and pending:
        backup_path = Path(str(database_path) + f".before-v{int(pending[0].name.split('_', 1)[0])}-{_id()}.bak")
        with closing(sqlite3.connect(backup_path)) as backup:
            connection.backup(backup)
    for migration in migrations:
        version = int(migration.name.split("_", 1)[0])
        if version in applied:
            continue
        # executescript commits a pending transaction before executing its input;
        # an outer `with connection` therefore cannot roll back partial DDL.
        # Put both the migration and its history entry in the same transaction.
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + migration.read_text(encoding="utf-8")
                + f"\nINSERT INTO schema_migration (version, applied_at) VALUES ({version}, '{_now()}');\nCOMMIT;"
            )
        except (sqlite3.Error, OSError, UnicodeError) as exc:
            connection.rollback()
            connection.close()
            raise ImportCommandError(
                "PROJECT_MIGRATION_FAILED",
                ("Не удалось обновить проект. Последняя миграция отменена; перед повторной попыткой проверьте резервную копию."
                 if backup_path else "Не удалось создать проект. Последняя миграция отменена; резервная копия не создавалась."),
                {"migration": migration.name, "backup_path": str(backup_path) if backup_path else None},
            ) from exc
    latest_version = max(int(migration.name.split("_", 1)[0]) for migration in migrations)
    with connection:
        connection.execute(
            "INSERT OR IGNORE INTO project_meta (singleton, project_schema_version, created_at) VALUES (1, ?, ?)",
            (latest_version, _now()),
        )
        connection.execute(
            "UPDATE project_meta SET project_schema_version = ? WHERE singleton = 1 AND project_schema_version <> ?",
            (latest_version, latest_version),
        )
    return connection


def _managed_copy_path(database_path: str | Path, source_id: str, source_path: str | Path) -> Path:
    database = Path(database_path)
    suffix = Path(source_path).suffix.lower()
    return database.parent / "sources" / f"{source_id}{suffix}"


def _prepare_managed_copy(database_path: str | Path, source_id: str, source_path: str | Path, expected_sha256: str) -> Path:
    destination = _managed_copy_path(database_path, source_id, source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    from .import_preview import _fingerprint

    try:
        shutil.copyfile(source_path, temporary)
        if _fingerprint(temporary) != expected_sha256:
            raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Source changed while its managed copy was being prepared.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _insert_recipe_revision(connection: sqlite3.Connection, source_id: str, recipe: dict[str, Any], timestamp: str, supersedes_recipe_revision_id: str | None = None) -> str:
    revision_id = _id()
    if supersedes_recipe_revision_id is not None:
        predecessor = connection.execute(
            "SELECT source_id FROM import_recipe_revision WHERE recipe_revision_id = ?", (supersedes_recipe_revision_id,)
        ).fetchone()
        if predecessor is None or predecessor["source_id"] != source_id:
            raise ImportCommandError("INVALID_ASSIGNMENT", "Superseded recipe revision does not belong to this Source.")
    connection.execute(
        """INSERT INTO import_recipe_revision
        (recipe_revision_id, source_id, schema_version, semantic_fingerprint_sha256, recipe_json, created_at, supersedes_recipe_revision_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (revision_id, source_id, int(recipe.get("schema_version", 1)), semantic_fingerprint(recipe),
         json.dumps(recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")), timestamp,
         supersedes_recipe_revision_id),
    )
    return revision_id


def _source_path_for_revision(database_path: str | Path, row: sqlite3.Row) -> Path:
    if row["source_kind"] == "linked_reference":
        return Path(row["linked_path"])
    managed_relative_path = row["managed_relative_path"]
    if not managed_relative_path:
        raise ImportCommandError("SOURCE_UNREADABLE", "Managed source has no stored copy.")
    base = Path(database_path).parent.resolve()
    source = (base / managed_relative_path).resolve()
    if base not in source.parents:
        raise ImportCommandError("SOURCE_UNREADABLE", "Managed source path is invalid.")
    return source


def save_import_recipe_revision(database_path: str | Path, source_id: str, recipe: dict[str, Any], supersedes_recipe_revision_id: str | None = None) -> dict[str, Any]:
    connection = open_project(database_path)
    try:
        source = connection.execute(
            "SELECT source_kind, linked_path, managed_relative_path, source_fingerprint_sha256 FROM source_file WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if source is None:
            raise ImportCommandError("INVALID_ASSIGNMENT", "Source does not exist.")
        inspection = inspect_source(_source_path_for_revision(database_path, source))
        if inspection.fingerprint != source["source_fingerprint_sha256"]:
            if source["source_kind"] == "linked_reference":
                with connection:
                    connection.execute("UPDATE source_file SET state = 'source_changed', last_verified_at = ? WHERE source_id = ?", (_now(), source_id))
            raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Source changed; recipe revision was not saved.")
        validate_recipe(inspection, recipe)
        timestamp = _now()
        with connection:
            revision_id = _insert_recipe_revision(connection, source_id, recipe, timestamp, supersedes_recipe_revision_id)
        return {
            "recipe_revision_id": revision_id,
            "source_id": source_id,
            "supersedes_recipe_revision_id": supersedes_recipe_revision_id,
            "semantic_fingerprint": semantic_fingerprint(recipe),
        }
    finally:
        connection.close()


def open_import_recipe_revision(database_path: str | Path, recipe_revision_id: str, source_path: str | Path) -> dict[str, Any]:
    with closing(open_project(database_path)) as connection:
        saved = connection.execute(
            """SELECT r.*, s.source_kind, s.linked_path, s.managed_relative_path, s.source_fingerprint_sha256
               FROM import_recipe_revision r JOIN source_file s USING (source_id)
               WHERE r.recipe_revision_id = ?""",
            (recipe_revision_id,),
        ).fetchone()
    if saved is None:
        raise ImportCommandError("RECIPE_REVISION_NOT_FOUND", "Saved import recipe revision does not exist.")

    recipe = json.loads(saved["recipe_json"])
    report = {"report_version": 1, "from_schema_version": saved["schema_version"], "to_schema_version": 2,
              "changes": [], "dropped_fields": []}
    result = {"recipe_revision_id": recipe_revision_id, "source_id": saved["source_id"],
              "semantic_fingerprint": saved["semantic_fingerprint_sha256"], "migration_report": report}
    try:
        if (recipe.get("schema_version", 1) != saved["schema_version"]
                or semantic_fingerprint(recipe) != result["semantic_fingerprint"]):
            raise ImportCommandError("RECIPE_REVISION_INTEGRITY", "Saved recipe version or semantic fingerprint differs from its revision.")
        target = inspect_source(source_path)
        different_source = target.fingerprint != saved["source_fingerprint_sha256"]
        original = inspect_source(_source_path_for_revision(database_path, saved)) if different_source else target
        if original.fingerprint != saved["source_fingerprint_sha256"]:
            raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Original source changed and cannot be used to verify compatibility.")
        validate_recipe(original, recipe)

        if different_source:
            decisions = recipe["global_decisions"]
            portable = {"fe_semantics", "censored_value_policy", "duplicate_policy", "unit_policy",
                        "mineral_verification_enabled"}
            empty_safe = {"duplicate_review", "semantic_annotations", "semantic_history", "project_aliases",
                          "mineral_acceptances", "sample_assignments"}
            bound = sorted(field for field in decisions.keys() - portable
                           if field not in empty_safe or decisions[field] not in (None, [], {}))
            if bound:
                raise ImportCommandError("RECIPE_SOURCE_BOUND_DECISIONS", "Saved decisions refer to the original source or project.",
                                         {"blocked_fields": [f"global_decisions.{field}" for field in bound]})
            if target.source_format != original.source_format:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source format differs from the saved recipe.")
            left = {sheet.name: recipe_sheet_layout(sheet, recipe["sections"]) for sheet in original.sheets}
            right = {sheet.name: recipe_sheet_layout(sheet, recipe["sections"]) for sheet in target.sheets}
            mismatches = sorted(name for name in left.keys() | right.keys() if left.get(name) != right.get(name))
            if mismatches:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "The candidate workbook has a different physical layout.",
                                         {"sheets": mismatches})
        if recipe.get("schema_version") != 2:
            report["changes"].append({"field": "schema_version", "action": "converted", "reason": "Legacy runtime recipe opened as v2."})
        if recipe.get("source_file_sha256") != target.fingerprint:
            report["changes"].append({"field": "source_file_sha256", "action": "converted", "reason": "Recipe bound to the verified candidate source."})
        recipe.update(schema_version=2, source_file_sha256=target.fingerprint)
        plan = create_import_plan(target, recipe)
    except ImportCommandError as error:
        return {**result, "status": "incompatible", "recipe": None, "issue": error.projection()["error"]}
    try:
        blockers = [issue for issue in plan["issues"] if issue.get("blocking")]
        if blockers:
            raise ImportCommandError(blockers[0]["code"], blockers[0]["message"], {"issues": blockers})
        _require_non_empty_plan(plan)
        _require_mapping_review(recipe)
        _require_duplicate_review(plan, recipe)
    except ImportCommandError as error:
        field = "global_decisions.duplicate_review" if error.code == "DUPLICATE_REVIEW_REQUIRED" else "import_plan"
        report["changes"].append({"field": field, "action": "blocked", "reason": error.message})
        return {**result, "status": "review_required", "recipe": recipe, "issue": error.projection()["error"]}
    return {**result, "status": "compatible", "recipe": recipe}


def _validated_import(source_path, recipe, expected_fingerprint=None):
    inspection = inspect_source(source_path)
    if expected_fingerprint is not None and inspection.fingerprint != expected_fingerprint:
        raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Файл изменился после добавления. Добавьте его заново.")
    plan = create_import_plan(inspection, recipe)
    blockers = [issue for issue in plan.get("issues", []) if issue.get("blocking")]
    if blockers:
        raise ImportCommandError(blockers[0]["code"], blockers[0]["message"], {"issues": blockers})
    _require_non_empty_plan(plan)
    _require_mapping_review(recipe)
    _require_duplicate_review(plan, recipe)
    return inspection, plan


def _persist_samples(connection, records, timestamp):
    assignments = {}
    for record in records:
        assignment = record["sample_association"].get("assignment")
        if assignment is None:
            continue
        sample_id = assignment["sample_id"]
        previous = assignments.setdefault(sample_id, assignment)
        if previous["sample_name"] != assignment["sample_name"] or previous["mode"] != assignment["mode"]:
            raise ImportCommandError("SAMPLE_ASSIGNMENT_CONFLICT", "Назначения одного образца не согласованы.")
    for sample_id, assignment in assignments.items():
        sample = connection.execute("SELECT sample_name FROM sample WHERE sample_id = ?", (sample_id,)).fetchone()
        name = assignment["sample_name"]
        if assignment["mode"] == "existing":
            if sample is None or sample["sample_name"] != name:
                raise ImportCommandError("STALE_SAMPLE_ASSIGNMENT", "Образец изменился. Назначьте его снова.")
        else:
            if sample is not None or connection.execute("SELECT 1 FROM sample WHERE sample_name = ?", (name,)).fetchone():
                raise ImportCommandError("SAMPLE_NAME_EXISTS", "Образец уже существует. Выберите его по ID или задайте другое имя.")
            connection.execute("INSERT INTO sample (sample_id, sample_name, created_at) VALUES (?, ?, ?)",
                               (sample_id, name, timestamp))


# Limit queued SQL parameters; never split the outer import transaction.
IMPORT_WRITE_BATCH_ROWS = 8192


def _persist_import(connection, database_path, source_path, recipe, inspection, plan, managed_files):
    source_kind = "managed_copy" if recipe["ownership_mode"] == "managed_copy" else "linked_reference"
    source_id, batch_id = _id(), _id()
    managed_copy = None
    if source_kind == "managed_copy":
        managed_copy = _prepare_managed_copy(database_path, source_id, source_path, inspection.fingerprint)
        managed_files.append(managed_copy)
    timestamp = _now()
    metadata_count = 0
    connection.execute(
        """INSERT INTO source_file
        (source_id, source_kind, display_name, source_fingerprint_sha256, linked_path, last_verified_at, state, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'current', ?)""",
        (source_id, source_kind, Path(source_path).name, inspection.fingerprint,
         plan["original_source_path"] if source_kind == "linked_reference" else None, timestamp, timestamp),
    )
    if managed_copy is not None:
        connection.execute(
            "UPDATE source_file SET managed_relative_path = ? WHERE source_id = ?",
            (managed_copy.relative_to(Path(database_path).parent).as_posix(), source_id),
        )
    recipe_revision_id = _insert_recipe_revision(connection, source_id, recipe, timestamp)
    connection.execute(
        """INSERT INTO import_batch
        (import_batch_id, source_id, recipe_revision_id, source_fingerprint_sha256, status, plan_json, created_at, applied_at)
        VALUES (?, ?, ?, ?, 'planned', ?, ?, NULL)""",
        (batch_id, source_id, recipe_revision_id, inspection.fingerprint,
         json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")), timestamp),
    )
    # Insertion order of SQL keys preserves parent-before-child foreign keys.
    # Parameter order within each table is unchanged. Flushes use the caller's
    # existing transaction; no intermediate commit or constraint bypass.
    pending = {}
    queued_count = 0

    def enqueue(sql, parameters):
        nonlocal queued_count
        pending.setdefault(sql, []).append(parameters)
        queued_count += 1

    def flush():
        nonlocal queued_count
        for sql, parameters in pending.items():
            connection.executemany(sql, parameters)
        pending.clear()
        queued_count = 0

    for record in plan["planned_records"]:
        analysis_id = _id()
        orientation = record.get("orientation", "rows_are_analyses")
        enqueue(
            """INSERT INTO analysis
            (analysis_id, import_batch_id, source_id, preview_id, sheet_name, source_row_number, block_id,
             identity_json, created_at, source_column_number, source_orientation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id, batch_id, source_id, record["preview_id"], record["sheet_name"], record["row_number"],
                record["block_id"], json.dumps(record["identity"], ensure_ascii=False), timestamp,
                record.get("source_column_number"), orientation,
            ),
        )
        enqueue(
            '''INSERT INTO analysis_import_semantics
               (analysis_id, sample_association_json, reported_mineral_json, mineral_assignment_json,
                mineral_verification_json, analytical_method_json) VALUES (?, ?, ?, ?, ?, ?)''',
            (analysis_id, *(json.dumps(record.get(key), ensure_ascii=False, sort_keys=True) for key in
             ('sample_association', 'reported_mineral', 'mineral_assignment', 'mineral_verification', 'analytical_method'))),
        )
        for metadata in _source_metadata_for_record(inspection, recipe, record):
            enqueue(
                """INSERT INTO analysis_source_metadata
                (analysis_source_metadata_id, analysis_id, import_batch_id, canonical_field, raw_token,
                 source_header, source_row_number, source_column_index, source_cell, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(), analysis_id, batch_id, metadata["canonical_field"], metadata["raw_token"],
                    metadata["source_header"], metadata["source_row_number"], metadata["source_column_index"],
                    metadata["source_cell"], timestamp,
                ),
            )
            metadata_count += 1
        for measurement in record["measurements"]:
            enqueue(
                """INSERT INTO measurement
                (measurement_id, analysis_id, canonical_field, unit, raw_token, qualifier, detection_limit,
                 source_column_name, source_column_index, created_at, source_row_number,
                 physical_source_column_index, source_cell, measurement_set, method,
                 value_status, reported_fe_form, fe_handling)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(), analysis_id, measurement["field"], measurement["unit"], measurement["raw_token"],
                    measurement["qualifier"], measurement["detection_limit"], measurement["source_header"],
                    measurement["source_column_index"], timestamp, measurement["physical_source_row_number"],
                    measurement["physical_source_column_index"], measurement["source_cell"],
                    measurement.get("measurement_set"), measurement.get("method"),
                    measurement["value_status"], measurement["reported_fe_form"], measurement["fe_handling"],
                ),
            )
            if orientation == "rows_are_analyses":
                enqueue(
                    """INSERT INTO source_row_provenance
                    (provenance_id, import_batch_id, sheet_name, row_number, source_column_name, raw_token,
                     normalized_token, qualifier, analysis_id, value_status)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                    (
                        _id(), batch_id, record["sheet_name"], measurement["physical_source_row_number"],
                        measurement["source_header"], measurement["raw_token"], measurement["qualifier"], analysis_id, measurement["value_status"],
                    ),
                )
            enqueue(
                """INSERT INTO source_cell_provenance
                (provenance_id, import_batch_id, analysis_id, sheet_name, source_row_number,
                 source_column_index, source_cell, source_header, raw_token, qualifier, value_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(), batch_id, analysis_id, record["sheet_name"], measurement["physical_source_row_number"],
                    measurement["physical_source_column_index"], measurement["source_cell"],
                    measurement["source_header"], measurement["raw_token"], measurement["qualifier"],
                    measurement["value_status"],
                ),
            )
        if queued_count >= IMPORT_WRITE_BATCH_ROWS:
            flush()
    flush()
    connection.execute("UPDATE import_batch SET status = 'applied', applied_at = ? WHERE import_batch_id = ?", (timestamp, batch_id))
    return {
        "import_batch_id": batch_id,
        "source_id": source_id,
        "recipe_revision_id": recipe_revision_id,
        "analysis_count": plan["summary"]["planned_analysis_count"],
        "measurement_count": plan["summary"]["planned_measurement_count"],
        "source_metadata_count": metadata_count,
        "warnings": plan["warnings"],
    }


def workspace_commit_exists(connection, workspace_id):
    return connection.execute(
        "SELECT 1 FROM import_batch WHERE json_extract(plan_json, '$.workspace_commit.workspace_id') = ? LIMIT 1",
        (workspace_id,),
    ).fetchone() is not None


def apply_import_batch(database_path, sources, *, workspace_commit=None, finalize_source=None):
    prepared = []
    for source_path, recipe, expected_fingerprint, original_source_path in sources:
        inspection, plan = _validated_import(source_path, recipe, expected_fingerprint)
        if workspace_commit is not None:
            plan_fingerprint = hashlib.sha256(json.dumps(
                plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            plan["workspace_commit"] = {
                **workspace_commit,
                "plan_fingerprint": plan_fingerprint,
                "recipe_fingerprint": semantic_fingerprint(recipe),
            }
        plan["original_source_path"] = str(Path(original_source_path).resolve())
        prepared.append((source_path, recipe, inspection, plan))

    managed_files = []
    with closing(open_project(database_path)) as connection:
        try:
            with connection:
                if workspace_commit is not None:
                    connection.execute("BEGIN IMMEDIATE")
                    if workspace_commit_exists(connection, workspace_commit["workspace_id"]):
                        raise ImportCommandError("WORKSPACE_ALREADY_COMMITTED", "Эта очередь уже сохранена в проекте.")
                _persist_samples(connection, (
                    record for _, _, _, plan in prepared for record in plan["planned_records"]
                ), _now())
                results = []
                for index, source in enumerate(prepared):
                    result = _persist_import(connection, database_path, *source, managed_files)
                    if finalize_source is not None:
                        finalize_source(connection, index, source[3], result)
                    results.append(result)
                return results
        except Exception:
            for managed_file in managed_files:
                managed_file.unlink(missing_ok=True)
            raise


def apply_import_plan(database_path: str | Path, source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    """Apply a fresh plan atomically; this function never writes the source file."""
    return apply_import_batch(database_path, [(source_path, recipe, None, source_path)])[0]


def check_linked_source(database_path: str | Path, source_id: str) -> dict[str, Any]:
    connection = open_project(database_path)
    try:
        row = connection.execute(
            "SELECT source_kind, linked_path, source_fingerprint_sha256 FROM source_file WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            raise ImportCommandError("INVALID_ASSIGNMENT", "Source does not exist.")
        if row["source_kind"] != "linked_reference":
            return {"source_id": source_id, "state": "current", "checked": False}
        path = Path(row["linked_path"])
        if not path.is_file():
            state, observed = "unavailable", None
        else:
            from .import_preview import _fingerprint
            observed = _fingerprint(path)
            state = "current" if observed == row["source_fingerprint_sha256"] else "source_changed"
        with connection:
            connection.execute("UPDATE source_file SET state = ?, last_verified_at = ? WHERE source_id = ?", (state, _now(), source_id))
        return {"source_id": source_id, "state": state, "checked": True, "observed_fingerprint": observed}
    finally:
        connection.close()


def latest_active_import(connection: sqlite3.Connection) -> dict[str, Any] | None:
    rows = connection.execute("""
        WITH active AS (
            SELECT b.import_batch_id, b.source_id, b.applied_at, s.display_name, b.rowid AS batch_order,
                   json_extract(b.plan_json, '$.workspace_commit.commit_id') AS commit_id
            FROM import_batch b
            JOIN source_file s ON s.source_id = b.source_id
            LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
            WHERE b.status = 'applied' AND r.import_batch_id IS NULL AND json_type(b.plan_json, '$.manual_entry') IS NULL
        ), latest AS (
            SELECT * FROM active ORDER BY applied_at DESC, batch_order DESC LIMIT 1
        )
        SELECT a.*, (SELECT COUNT(*) FROM analysis WHERE import_batch_id = a.import_batch_id) AS analysis_count
        FROM active a JOIN latest l ON a.import_batch_id = l.import_batch_id OR a.commit_id = l.commit_id
        ORDER BY a.applied_at DESC, a.batch_order DESC
    """).fetchall()
    if not rows:
        return None
    latest = rows[0]
    return {
        "import_batch_id": latest["import_batch_id"],
        "source_id": latest["source_id"],
        "source_name": ", ".join(row["display_name"] for row in reversed(rows)),
        "analysis_count": sum(row["analysis_count"] for row in rows),
        "applied_at": latest["applied_at"],
        "import_batch_ids": [row["import_batch_id"] for row in rows],
    }


def retract_latest_import(database_path: str | Path, reason: str = "user_retracted") -> dict[str, Any]:
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = latest_active_import(connection)
        if latest is None:
            raise ImportCommandError("INVALID_ASSIGNMENT", "There is no active applied import to retract.")
        timestamp = _now()
        connection.executemany(
            """INSERT INTO import_batch_retraction (retraction_id, import_batch_id, reason, created_at)
               VALUES (?, ?, ?, ?)""",
            [(_id(), batch_id, reason or "user_retracted", timestamp) for batch_id in latest["import_batch_ids"]],
        )
        return {**latest, "retracted_at": timestamp}


def rollback_incomplete_batch(database_path: str | Path, import_batch_id: str) -> dict[str, Any]:
    connection = open_project(database_path)
    try:
        with connection:
            row = connection.execute("SELECT status FROM import_batch WHERE import_batch_id = ?", (import_batch_id,)).fetchone()
            if row is None:
                raise ImportCommandError("INVALID_ASSIGNMENT", "Import Batch does not exist.")
            if row["status"] != "planned":
                raise ImportCommandError("INVALID_ASSIGNMENT", "Only an incomplete planned batch can be rolled back.")
            connection.execute("UPDATE import_batch SET status = 'rolled_back' WHERE import_batch_id = ?", (import_batch_id,))
        return {"import_batch_id": import_batch_id, "status": "rolled_back"}
    finally:
        connection.close()
