"""Desktop-facing application services for the live PetroLab import slice.

Python owns structural recognition and project projections. The UI receives
logical blocks and explicit review warnings; it does not infer import semantics.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .import_apply import open_project
from .import_preview import ImportCommandError, candidate_blocks, inspect_source, semantic_fingerprint
from .import_recognition import IRON_FIELDS, mappings_for_column_header, mappings_for_row_header


def _transposed_candidate(sheet: Any, block: dict[str, Any], context_unit: str | None) -> dict[str, Any] | None:
    """Return conservative structural evidence for a column-oriented block.

    Detection deliberately requires several recognizable field labels down one
    physical column plus multiple populated Analysis labels across the header
    row. Names of files/sheets/instruments are never used as evidence.
    """
    header_row = int(block["header_row"])
    field_start = int(block["data_start_row"])
    field_end = int(block["data_end_row"])
    header = sheet.rows[header_row - 1]
    max_columns = max((len(row) for row in sheet.rows), default=0)
    if max_columns < 3:
        return None

    best: dict[str, Any] | None = None
    # Most real transposed analytical tables keep field labels in one of the
    # first few columns. Limiting the scan also avoids treating helper regions
    # far to the right as a second orientation for the same block.
    for header_column_index in range(min(max_columns, 4)):
        mappings, mapping_warnings = mappings_for_column_header(
            sheet.rows,
            header_column_index + 1,
            field_start,
            field_end,
            context_unit,
        )
        if not mappings:
            continue
        recognized = sum(1 for mapping in mappings if mapping.get("target_role") != "ignore")
        unit_pending = sum(1 for warning in mapping_warnings if warning.get("code") == "UNIT_REQUIRES_REVIEW")
        evidence_count = recognized + unit_pending
        if evidence_count < 3 or evidence_count / len(mappings) < 0.6:
            continue

        analysis_columns = [
            column_index
            for column_index in range(header_column_index + 1, len(header))
            if header[column_index] not in (None, "")
        ]
        if len(analysis_columns) < 2:
            continue

        candidate = {
            "header_column": header_column_index + 1,
            "data_start_column": min(analysis_columns) + 1,
            "data_end_column": max(analysis_columns) + 1,
            "analysis_column_count": len(analysis_columns),
            "field_evidence_count": evidence_count,
            "mappings": mappings,
            "mapping_warnings": mapping_warnings,
        }
        score = (evidence_count, len(analysis_columns), -header_column_index)
        if best is None or score > best["score"]:
            best = {**candidate, "score": score}
    return best


def suggest_import_recipe(source_path: str | Path) -> dict[str, Any]:
    """Create a conservative block-based recipe from a real source."""
    inspection = inspect_source(source_path)
    sections: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(inspection.projection()["warnings"])
    mapped_iron = False

    for sheet in inspection.sheets:
        blocks = candidate_blocks(sheet)
        if not blocks:
            warnings.append({"code": "HEADER_NOT_DETECTED", "sheet_name": sheet.name})
            continue
        for block in blocks:
            header_row = int(block["header_row"])
            header = sheet.rows[header_row - 1]
            context = block.get("unit_context")
            # A block unit is evidence only when it is stated outside the column
            # header itself. Mixed column headers such as Li (ppm) + F (unknown)
            # must not leak ppm into F.
            if isinstance(context, dict) and context.get("row_number") == header_row:
                context = None
            context_unit = context.get("unit") if isinstance(context, dict) else None

            transposed = _transposed_candidate(sheet, block, context_unit)
            if transposed is not None:
                mappings = transposed["mappings"]
                mapping_warnings = transposed["mapping_warnings"]
                orientation = "columns_are_analyses"
                section: dict[str, Any] = {
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "enabled": True,
                    "orientation": orientation,
                    "header_row": header_row,
                    "header_column": transposed["header_column"],
                    "data_start_row": int(block["data_start_row"]),
                    "data_end_row": int(block["data_end_row"]),
                    "data_start_column": transposed["data_start_column"],
                    "data_end_column": transposed["data_end_column"],
                    "analysis_axis_role": "Analysis",
                    "analysis_axis_field": "Analysis",
                    "unit_context": context,
                    "mappings": mappings,
                }
                warnings.append({
                    "code": "TRANSPOSED_TABLE_LIKELY",
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "header_column": transposed["header_column"],
                    "analysis_column_count": transposed["analysis_column_count"],
                    "field_evidence_count": transposed["field_evidence_count"],
                })
            else:
                mappings, mapping_warnings = mappings_for_row_header(header, context_unit)
                orientation = "rows_are_analyses"
                section = {
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "enabled": True,
                    "orientation": orientation,
                    "header_row": header_row,
                    "data_start_row": int(block["data_start_row"]),
                    "data_end_row": int(block["data_end_row"]),
                    "unit_context": context,
                    "mappings": mappings,
                }

            if not mappings:
                warnings.append({"code": "NO_COLUMNS_DETECTED", "sheet_name": sheet.name, "block_id": block["block_id"]})
                continue
            for warning in mapping_warnings:
                warnings.append({"sheet_name": sheet.name, "block_id": block["block_id"], **warning})
            mapped_iron = mapped_iron or any(
                mapping["target_role"] == "measurement" and mapping["canonical_field"] in IRON_FIELDS
                for mapping in mappings
            )
            sections.append(section)

    if not sections:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "No importable table blocks were detected in the selected file.")

    recipe: dict[str, Any] = {
        "schema_version": 2,
        "source_file_sha256": inspection.fingerprint,
        "source_format": inspection.source_format,
        "ownership_mode": "managed_copy",
        "sections": sections,
        "global_decisions": {
            "fe_semantics": "preserve_reported_form_for_review" if mapped_iron else "not_present",
            "censored_value_policy": "preserve_original_token_and_detection_limit",
            "duplicate_policy": "review_each",
            "unit_policy": "explicit_per_measurement_column",
        },
    }
    recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)
    return {"recipe": recipe, "warnings": warnings}


def _active_import_filter() -> str:
    return "b.status = 'applied' AND x.import_batch_id IS NULL"


def list_project_analyses(database_path: str | Path, limit: int = 500) -> dict[str, Any]:
    """Return active Analysis/Measurement rows plus lossless source metadata."""
    limit = max(1, min(int(limit), 2000))
    connection = open_project(database_path)
    try:
        active_filter = _active_import_filter()
        total = connection.execute(
            f"""SELECT COUNT(*)
                FROM analysis a
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                WHERE {active_filter}"""
        ).fetchone()[0]
        rows = connection.execute(
            f"""SELECT a.analysis_id, a.source_id, a.sheet_name, a.source_row_number,
                       a.source_column_number, a.source_orientation, a.block_id,
                       a.identity_json, a.created_at, s.display_name AS source_name, r.recipe_json
                FROM analysis a
                JOIN source_file s ON s.source_id = a.source_id
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                JOIN import_recipe_revision r ON r.recipe_revision_id = b.recipe_revision_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                WHERE {active_filter}
                ORDER BY a.created_at DESC, a.sheet_name, a.source_row_number, a.source_column_number
                LIMIT ?""",
            (limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            identity_values = json.loads(row["identity_json"])
            recipe = json.loads(row["recipe_json"])
            identity_names: list[str] = []
            for section in recipe.get("sections", []):
                if section.get("sheet_name") != row["sheet_name"] or section.get("block_id") != row["block_id"]:
                    continue
                if section.get("orientation", "rows_are_analyses") == "columns_are_analyses" and section.get("analysis_axis_role", "Analysis") != "Ignore":
                    identity_names.append(section.get("analysis_axis_field") or "Analysis")
                identity_names.extend(
                    mapping.get("canonical_field") or mapping.get("source_header")
                    for mapping in section.get("mappings", [])
                    if mapping.get("target_role") == "identity"
                )
                break
            identity = {
                str(name): identity_values[index] if index < len(identity_values) else ""
                for index, name in enumerate(identity_names)
            }
            source_metadata_rows = connection.execute(
                """SELECT canonical_field, raw_token, source_header, source_row_number,
                          source_column_index, source_cell
                   FROM analysis_source_metadata
                   WHERE analysis_id = ? ORDER BY source_column_index, rowid""",
                (row["analysis_id"],),
            ).fetchall()
            source_metadata_list = [
                {
                    "field": metadata["canonical_field"],
                    "raw_token": metadata["raw_token"],
                    "source_header": metadata["source_header"],
                    "source_row_number": metadata["source_row_number"],
                    "source_column_index": metadata["source_column_index"],
                    "source_cell": metadata["source_cell"],
                }
                for metadata in source_metadata_rows
            ]
            source_metadata: dict[str, Any] = {}
            for metadata in source_metadata_list:
                field = metadata["field"]
                key = field if field not in source_metadata else f"{field} · {metadata['source_header']}"
                source_metadata[key] = metadata["raw_token"]

            measurement_rows = connection.execute(
                """SELECT canonical_field, unit, raw_token, qualifier, detection_limit,
                          source_column_name, source_column_index, measurement_set, method, source_cell
                   FROM measurement WHERE analysis_id = ? ORDER BY source_column_index, rowid""",
                (row["analysis_id"],),
            ).fetchall()
            measurement_list = [
                {
                    "field": measurement["canonical_field"],
                    "raw_token": measurement["raw_token"],
                    "unit": measurement["unit"],
                    "qualifier": measurement["qualifier"],
                    "detection_limit": measurement["detection_limit"],
                    "source_header": measurement["source_column_name"],
                    "source_index": measurement["source_column_index"],
                    "source_cell": measurement["source_cell"],
                    "measurement_set": measurement["measurement_set"],
                    "method": measurement["method"],
                }
                for measurement in measurement_rows
            ]
            totals = Counter(item["field"] for item in measurement_list)
            seen: Counter[str] = Counter()
            measurement_map: dict[str, dict[str, Any]] = {}
            for measurement in measurement_list:
                field = measurement["field"]
                seen[field] += 1
                if totals[field] == 1:
                    key = field
                else:
                    context = measurement.get("measurement_set") or measurement.get("method") or measurement["source_header"]
                    key = f"{field} · {context}"
                    if key in measurement_map:
                        key = f"{key} [{seen[field]}]"
                measurement_map[key] = measurement
            result.append({
                "analysis_id": row["analysis_id"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "sheet_name": row["sheet_name"],
                "source_row_number": row["source_row_number"],
                "source_column_number": row["source_column_number"],
                "source_orientation": row["source_orientation"] or "rows_are_analyses",
                "identity": identity,
                "source_metadata": source_metadata,
                "source_metadata_list": source_metadata_list,
                "measurements": measurement_map,
                "measurement_list": measurement_list,
                "created_at": row["created_at"],
            })

        source_count = connection.execute(
            """SELECT COUNT(DISTINCT b.source_id)
               FROM import_batch b
               LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
               WHERE b.status = 'applied' AND x.import_batch_id IS NULL"""
        ).fetchone()[0]
        batch_count = connection.execute(
            """SELECT COUNT(*)
               FROM import_batch b
               LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
               WHERE b.status = 'applied' AND x.import_batch_id IS NULL"""
        ).fetchone()[0]
        latest = connection.execute(
            """SELECT b.import_batch_id, b.source_id, b.applied_at, s.display_name,
                      COUNT(a.analysis_id) AS analysis_count
               FROM import_batch b
               JOIN source_file s ON s.source_id = b.source_id
               LEFT JOIN analysis a ON a.import_batch_id = b.import_batch_id
               LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
               WHERE b.status = 'applied' AND x.import_batch_id IS NULL
               GROUP BY b.import_batch_id, b.source_id, b.applied_at, s.display_name
               ORDER BY b.applied_at DESC, b.rowid DESC
               LIMIT 1"""
        ).fetchone()
        latest_import = None if latest is None else {
            "import_batch_id": latest["import_batch_id"],
            "source_id": latest["source_id"],
            "source_name": latest["display_name"],
            "analysis_count": latest["analysis_count"],
            "applied_at": latest["applied_at"],
        }
        return {
            "total": total,
            "returned": len(result),
            "source_count": source_count,
            "import_batch_count": batch_count,
            "latest_import": latest_import,
            "analyses": result,
        }
    finally:
        connection.close()