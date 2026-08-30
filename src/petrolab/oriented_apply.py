"""Atomic persistence for orientation-aware import plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .import_apply import _id, _insert_recipe_revision, _now, _prepare_managed_copy, open_project
from .import_preview import ImportCommandError, inspect_source
from .oriented_import import create_oriented_import_plan, validate_oriented_recipe


def apply_oriented_import_plan(database_path: str | Path, source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    """Apply a validated row- or column-oriented plan without touching the source."""
    inspection = inspect_source(source_path)
    validate_oriented_recipe(inspection, recipe)
    plan = create_oriented_import_plan(inspection, recipe)
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
                    (analysis_id, import_batch_id, source_id, preview_id, sheet_name, source_row_number,
                     source_orientation, source_record_index, block_id, identity_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        analysis_id,
                        batch_id,
                        source_id,
                        record["preview_id"],
                        record["sheet_name"],
                        record["row_number"],
                        record.get("source_orientation", "rows"),
                        record.get("source_record_index", record["row_number"]),
                        record["block_id"],
                        json.dumps(record["identity"], ensure_ascii=False),
                        timestamp,
                    ),
                )
                for measurement in record["measurements"]:
                    source_row_number = int(measurement.get("source_row_number", record["row_number"]))
                    source_column_index = int(measurement["source_column_index"])
                    source_cell_reference = measurement.get("source_cell_reference")
                    connection.execute(
                        """INSERT INTO measurement
                        (measurement_id, analysis_id, canonical_field, unit, raw_token, qualifier, detection_limit,
                         source_column_name, source_column_index, source_row_number, source_cell_reference, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            _id(), analysis_id, measurement["field"], measurement["unit"], measurement["raw_token"],
                            measurement["qualifier"], measurement["detection_limit"], measurement["source_header"],
                            source_column_index, source_row_number, source_cell_reference, timestamp,
                        ),
                    )
                    connection.execute(
                        """INSERT INTO source_row_provenance
                        (provenance_id, import_batch_id, sheet_name, row_number, source_column_index,
                         source_column_name, source_cell_reference, raw_token, normalized_token, qualifier, analysis_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                        (
                            _id(), batch_id, record["sheet_name"], source_row_number, source_column_index,
                            measurement["source_header"], source_cell_reference, measurement["raw_token"],
                            measurement["qualifier"], analysis_id,
                        ),
                    )
            connection.execute(
                "UPDATE import_batch SET status = 'applied', applied_at = ? WHERE import_batch_id = ?",
                (timestamp, batch_id),
            )
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
