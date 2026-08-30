"""M1.2 atomic application of a validated import plan to local SQLite."""

from __future__ import annotations

import json
import sqlite3
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .import_preview import ImportCommandError, create_import_plan, inspect_source, semantic_fingerprint, validate_recipe


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _id() -> str:
    return str(uuid.uuid4())


def open_project(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migration (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migration")}
    migrations = sorted(MIGRATIONS.glob("*.sql"))
    for migration in migrations:
        version = int(migration.name.split("_", 1)[0])
        if version in applied:
            continue
        with connection:
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migration (version, applied_at) VALUES (?, ?)", (version, _now()))
    latest_version = max(int(migration.name.split("_", 1)[0]) for migration in migrations)
    with connection:
        connection.execute(
            "INSERT OR IGNORE INTO project_meta (singleton, project_schema_version, created_at) VALUES (1, ?, ?)",
            (latest_version, _now()),
        )
        connection.execute("UPDATE project_meta SET project_schema_version = ? WHERE singleton = 1", (latest_version,))
    return connection


def _managed_copy_path(database_path: str | Path, source_id: str, source_path: str | Path) -> Path:
    database = Path(database_path)
    suffix = Path(source_path).suffix.lower()
    return database.parent / "sources" / f"{source_id}{suffix}"


def _prepare_managed_copy(database_path: str | Path, source_id: str, source_path: str | Path, expected_sha256: str) -> Path:
    destination = _managed_copy_path(database_path, source_id, source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source_path, temporary)
    from .import_preview import _fingerprint

    if _fingerprint(temporary) != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Source changed while its managed copy was being prepared.")
    temporary.replace(destination)
    return destination


def _insert_recipe_revision(
    connection: sqlite3.Connection,
    source_id: str,
    recipe: dict[str, Any],
    timestamp: str,
    supersedes_recipe_revision_id: str | None = None,
) -> str:
    """Persist an immutable recipe snapshot after it has been validated."""
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


def save_import_recipe_revision(
    database_path: str | Path,
    source_id: str,
    recipe: dict[str, Any],
    supersedes_recipe_revision_id: str | None = None,
) -> dict[str, Any]:
    """Save a new, validated recipe revision without rewriting an earlier one."""
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


def apply_import_plan(database_path: str | Path, source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    """Apply a fresh plan atomically; this function never writes the source file."""
    inspection = inspect_source(source_path)
    plan = create_import_plan(inspection, recipe)
    source_kind = "managed_copy" if recipe["ownership_mode"] == "managed_copy" else "linked_reference"
    source_id, batch_id = _id(), _id()
    managed_copy: Path | None = None
    if source_kind == "managed_copy":
        managed_copy = _prepare_managed_copy(database_path, source_id, source_path, inspection.fingerprint)
    connection = open_project(database_path)
    try:
        timestamp = _now()
        with connection:
            connection.execute(
                """INSERT INTO source_file
                (source_id, source_kind, display_name, source_fingerprint_sha256, linked_path, last_verified_at, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'current', ?)""",
                (source_id, source_kind, Path(source_path).name, inspection.fingerprint,
                 str(Path(source_path).resolve()) if source_kind == "linked_reference" else None, timestamp, timestamp),
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
            for record in plan["planned_records"]:
                analysis_id = _id()
                connection.execute(
                    """INSERT INTO analysis
                    (analysis_id, import_batch_id, source_id, preview_id, sheet_name, source_row_number, block_id, identity_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (analysis_id, batch_id, source_id, record["preview_id"], record["sheet_name"], record["row_number"],
                     record["block_id"], json.dumps(record["identity"], ensure_ascii=False), timestamp),
                )
                for measurement in record["measurements"]:
                    connection.execute(
                        """INSERT INTO measurement
                        (measurement_id, analysis_id, canonical_field, unit, raw_token, qualifier, detection_limit, source_column_name, source_column_index, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (_id(), analysis_id, measurement["field"], measurement["unit"], measurement["raw_token"],
                         measurement["qualifier"], measurement["detection_limit"], measurement["source_header"],
                         measurement["source_column_index"], timestamp),
                    )
                    connection.execute(
                        """INSERT INTO source_row_provenance
                        (provenance_id, import_batch_id, sheet_name, row_number, source_column_name, raw_token, normalized_token, qualifier, analysis_id)
                        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                        (_id(), batch_id, record["sheet_name"], record["row_number"], measurement["source_header"],
                         measurement["raw_token"], measurement["qualifier"], analysis_id),
                    )
            connection.execute("UPDATE import_batch SET status = 'applied', applied_at = ? WHERE import_batch_id = ?", (timestamp, batch_id))
        return {
            "import_batch_id": batch_id,
            "source_id": source_id,
            "recipe_revision_id": recipe_revision_id,
            "analysis_count": plan["summary"]["planned_analysis_count"],
            "measurement_count": sum(len(record["measurements"]) for record in plan["planned_records"]),
            "warnings": plan["warnings"],
        }
    except Exception:
        if managed_copy is not None:
            managed_copy.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def check_linked_source(database_path: str | Path, source_id: str) -> dict[str, Any]:
    """Re-fingerprint a linked file and report change; never import or refresh it."""
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
            state = "unavailable"
            observed = None
        else:
            from .import_preview import _fingerprint

            observed = _fingerprint(path)
            state = "current" if observed == row["source_fingerprint_sha256"] else "source_changed"
        with connection:
            connection.execute("UPDATE source_file SET state = ?, last_verified_at = ? WHERE source_id = ?", (state, _now(), source_id))
        return {"source_id": source_id, "state": state, "checked": True, "observed_fingerprint": observed}
    finally:
        connection.close()


def retract_latest_import(database_path: str | Path, reason: str = "user_retracted") -> dict[str, Any]:
    """Hide the latest applied import from active projections while preserving its audit trail."""
    connection = open_project(database_path)
    try:
        row = connection.execute(
            """SELECT b.import_batch_id, b.source_id, b.applied_at, s.display_name,
                      COUNT(a.analysis_id) AS analysis_count
               FROM import_batch b
               JOIN source_file s ON s.source_id = b.source_id
               LEFT JOIN analysis a ON a.import_batch_id = b.import_batch_id
               LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
               WHERE b.status = 'applied' AND r.import_batch_id IS NULL
               GROUP BY b.import_batch_id, b.source_id, b.applied_at, s.display_name
               ORDER BY b.applied_at DESC, b.rowid DESC
               LIMIT 1"""
        ).fetchone()
        if row is None:
            raise ImportCommandError("INVALID_ASSIGNMENT", "There is no active applied import to retract.")
        timestamp = _now()
        with connection:
            connection.execute(
                """INSERT INTO import_batch_retraction (retraction_id, import_batch_id, reason, created_at)
                   VALUES (?, ?, ?, ?)""",
                (_id(), row["import_batch_id"], reason or "user_retracted", timestamp),
            )
        return {
            "import_batch_id": row["import_batch_id"],
            "source_id": row["source_id"],
            "source_name": row["display_name"],
            "analysis_count": row["analysis_count"],
            "retracted_at": timestamp,
        }
    finally:
        connection.close()


def rollback_incomplete_batch(database_path: str | Path, import_batch_id: str) -> dict[str, Any]:
    """Only a non-applied batch may be marked rolled back; applied data is immutable."""
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
