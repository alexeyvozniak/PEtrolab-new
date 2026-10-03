"""Desktop-facing application services for the live PetroLab import slice.

Python owns structural recognition and project projections. The UI receives
logical blocks and explicit review warnings; it does not infer import semantics.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
from typing import Any

from .import_apply import open_project
from .import_preview import ImportCommandError, candidate_blocks, inspect_source, semantic_fingerprint, validate_recipe
from .import_recognition import (
    IRON_FIELDS,
    mappings_for_column_block,
    mappings_for_column_header,
    mappings_for_row_block,
)
from .manual_mapping import revise_import_mappings


SERVICE_PREAMBLE_PREFIXES = (
    "project:",
    "owner:",
    "site:",
    "sample:",
    "type:",
    "id:",
    "processing option:",
    "processing option :",
)


def _meaningful_row_values(row: Any) -> list[str]:
    return [str(value).strip() for value in row if value is not None and str(value).strip()]


def _looks_like_service_preamble(row: Any) -> bool:
    """Keep instrument metadata/context rows out of logical table sections."""
    values = _meaningful_row_values(row)
    if not values:
        return False
    first = values[0].lower()
    if first.startswith("all results in"):
        return len(values) <= 2
    if len(values) <= 2 and any(first.startswith(prefix) for prefix in SERVICE_PREAMBLE_PREFIXES):
        return True
    return False


def _transposed_candidate(sheet: Any, block: dict[str, Any], context_unit: str | None) -> dict[str, Any] | None:
    """Return conservative structural evidence for a column-oriented block."""
    header_row = int(block["header_row"])
    field_start = int(block["data_start_row"])
    field_end = int(block["data_end_row"])
    header = sheet.rows[header_row - 1]
    max_columns = max((len(row) for row in sheet.rows), default=0)
    if max_columns < 3:
        return None

    best: dict[str, Any] | None = None
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
            if _looks_like_service_preamble(header):
                continue
            context = block.get("unit_context")
            if isinstance(context, dict) and context.get("row_number") == header_row:
                context = None
            context_unit = context.get("unit") if isinstance(context, dict) else None

            row_mappings, row_mapping_warnings = mappings_for_row_block(
                sheet.rows,
                header_row,
                int(block["data_start_row"]),
                int(block["data_end_row"]),
                context_unit,
            )
            row_has_identity = any(mapping.get("target_role") == "identity" for mapping in row_mappings)
            row_measurement_evidence = sum(
                mapping.get("target_role") == "measurement" or mapping.get("suggested_target") == "measurement"
                for mapping in row_mappings
            )
            # A wide table with an explicit identity column and several
            # measurement-like headers is already structurally decisive. Do
            # not transpose it merely because its first column also contains
            # many analysis labels (for example "Спектр 1", "Спектр 2").
            transposed = None if row_has_identity and row_measurement_evidence >= 2 else _transposed_candidate(sheet, block, context_unit)
            if transposed is not None:
                mappings, mapping_warnings = mappings_for_column_block(
                    sheet.rows,
                    transposed["header_column"],
                    int(block["data_start_row"]),
                    int(block["data_end_row"]),
                    transposed["data_start_column"],
                    transposed["data_end_column"],
                    context_unit,
                )
                section: dict[str, Any] = {
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "enabled": True,
                    "orientation": "columns_are_analyses",
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
                mappings, mapping_warnings = row_mappings, row_mapping_warnings
                section = {
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "enabled": True,
                    "orientation": "rows_are_analyses",
                    "header_row": header_row,
                    "data_start_row": int(block["data_start_row"]),
                    "data_end_row": int(block["data_end_row"]),
                    "unit_context": context,
                    "mappings": mappings,
                }

            if not mappings:
                warnings.append({"code": "NO_COLUMNS_DETECTED", "sheet_name": sheet.name, "block_id": block["block_id"]})
                continue
            # A measurement-only export (for example an isotope data table)
            # often has no analytical name column at all.  Use its immutable
            # physical source row as a transparent local identifier instead of
            # creating thousands of anonymous Analyses.  This is provenance,
            # not a scientific classification.
            has_identity = any(mapping.get("target_role") == "identity" for mapping in mappings)
            has_measurement = any(mapping.get("target_role") == "measurement" for mapping in mappings)
            if section["orientation"] == "rows_are_analyses" and not has_identity and has_measurement:
                section["analysis_identity_policy"] = "source_row"
                warnings.append({
                    "code": "SOURCE_ROW_IDENTITY_ASSIGNED",
                    "sheet_name": sheet.name,
                    "block_id": block["block_id"],
                    "identity_field": "Source row",
                })
            for warning in mapping_warnings:
                warnings.append({"sheet_name": sheet.name, "block_id": block["block_id"], **warning})
            warned_coordinates = {
                (
                    warning.get("source_axis", "column"),
                    warning.get("source_column_index") if warning.get("source_axis", "column") == "column" else warning.get("source_row_index"),
                )
                for warning in mapping_warnings
            }
            for mapping in mappings:
                axis = mapping.get("source_axis", "column")
                index_key = "source_column_index" if axis == "column" else "source_row_index"
                coordinate = (axis, mapping.get(index_key))
                if (
                    mapping.get("target_role") == "ignore"
                    and mapping.get("review_decision") == "unresolved"
                    and coordinate not in warned_coordinates
                ):
                    warnings.append({
                        "code": "UNMAPPED_FIELD_REQUIRES_REVIEW",
                        "sheet_name": sheet.name,
                        "block_id": block["block_id"],
                        "source_axis": axis,
                        index_key: mapping.get(index_key),
                        "source_header": mapping.get("source_header"),
                    })
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


def bulk_unit_scopes(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    """Return server-issued scopes for one explicit unit decision.

    A scope contains only blocks with the same orientation and the same ordered
    set of unresolved recognised measurements.  The client cannot broaden it
    by filename, sheet name or prior choices.
    """
    inspection = inspect_source(source_path)
    validate_recipe(inspection, recipe)
    grouped: dict[tuple[str, tuple[tuple[str, str, str], ...]], list[tuple[dict[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    for section in recipe.get("sections", []):
        if not section.get("enabled", True):
            continue
        targets = [
            mapping for mapping in section.get("mappings", [])
            if mapping.get("target_role") == "ignore"
            and mapping.get("review_decision") == "unresolved"
            and mapping.get("suggested_target") == "measurement"
            and isinstance(mapping.get("suggested_canonical_field"), str)
            and mapping.get("suggested_canonical_field")
        ]
        if not targets:
            continue
        signature = tuple(sorted(
            (
                str(mapping.get("source_axis", "column")),
                str(mapping.get("source_header") or ""),
                str(mapping["suggested_canonical_field"]),
            )
            for mapping in targets
        ))
        grouped[(str(section.get("orientation", "rows_are_analyses")), signature)].append((section, targets))

    scopes: list[dict[str, Any]] = []
    recipe_fingerprint = semantic_fingerprint(recipe)
    for (orientation, signature), grouped_targets in sorted(grouped.items(), key=lambda item: min(str(pair[0].get("block_id")) for pair in item[1])):
        targets = [
            {
                "block_id": section["block_id"],
                "source_axis": mapping.get("source_axis", "column"),
                "source_index": mapping.get("source_column_index") if mapping.get("source_axis", "column") == "column" else mapping.get("source_row_index"),
                "canonical_field": mapping["suggested_canonical_field"],
            }
            for section, mappings in grouped_targets for mapping in mappings
        ]
        identity = {
            "source_fingerprint": inspection.fingerprint,
            "recipe_fingerprint": recipe_fingerprint,
            "orientation": orientation,
            "signature": signature,
            "targets": targets,
        }
        scope_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
        scopes.append({
            "bulk_scope_id": scope_id,
            "decision_kind": "measurement_unit",
            "orientation": orientation,
            "block_count": len(grouped_targets),
            "field_count": len(targets),
            "sheet_names": sorted({str(section["sheet_name"]) for section, _ in grouped_targets}),
            "fields": sorted({target["canonical_field"] for target in targets}),
            "targets": targets,
        })
    return {"source_fingerprint": inspection.fingerprint, "recipe_fingerprint": recipe_fingerprint, "scopes": scopes}


def apply_bulk_unit_scope(source_path: str | Path, recipe: dict[str, Any], bulk_scope_id: str, unit: str) -> dict[str, Any]:
    if not isinstance(bulk_scope_id, str) or not bulk_scope_id:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Bulk scope identifier is required.")
    scopes = bulk_unit_scopes(source_path, recipe)["scopes"]
    scope = next((item for item in scopes if item["bulk_scope_id"] == bulk_scope_id), None)
    if scope is None:
        raise ImportCommandError("STALE_BULK_SCOPE", "Bulk scope no longer matches the current source and recipe.")
    decisions = [
        {
            "block_id": target["block_id"],
            "source_axis": target["source_axis"],
            "source_index": target["source_index"],
            "target": "Measurement",
            "canonical_field": target["canonical_field"],
            "unit": unit,
        }
        for target in scope["targets"]
    ]
    revised = revise_import_mappings(source_path, recipe, decisions)
    return {**revised, "bulk_scope_id": bulk_scope_id, "applied_decision_count": len(decisions)}


def bulk_ignore_scopes(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    """Return the exact current set of unrecognized fields for explicit skip.

    Measurement candidates never enter this scope. The user may therefore
    skip all genuinely unrecognized fields once, after reviewing their names,
    without repeating the same Ignore decision for every physical block. The
    scope is bound to every coordinate and becomes stale after any recipe edit.
    """
    inspection = inspect_source(source_path)
    validate_recipe(inspection, recipe)
    targets: list[dict[str, Any]] = []
    for section in recipe.get("sections", []):
        if not section.get("enabled", True):
            continue
        for mapping in section.get("mappings", []):
            if not (
                mapping.get("target_role") == "ignore"
                and mapping.get("review_decision") == "unresolved"
                and mapping.get("suggested_target") != "measurement"
            ):
                continue
            axis = str(mapping.get("source_axis", "column"))
            index = mapping.get("source_column_index") if axis == "column" else mapping.get("source_row_index")
            targets.append({
                "block_id": section["block_id"],
                "sheet_name": section["sheet_name"],
                "source_axis": axis,
                "source_index": int(index),
                "source_header": str(mapping.get("source_header") or ""),
            })

    recipe_fingerprint = semantic_fingerprint(recipe)
    if not targets:
        return {"source_fingerprint": inspection.fingerprint, "recipe_fingerprint": recipe_fingerprint, "scopes": []}
    identity = {
        "source_fingerprint": inspection.fingerprint,
        "recipe_fingerprint": recipe_fingerprint,
        "decision_kind": "explicit_ignore_all_unrecognized",
        "targets": targets,
    }
    scope_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    scope = {
        "bulk_scope_id": scope_id,
        "decision_kind": "explicit_ignore_all_unrecognized",
        "block_count": len({target["block_id"] for target in targets}),
        "field_count": len(targets),
        "sheet_names": sorted({str(target["sheet_name"]) for target in targets}),
        "fields": sorted({target["source_header"] or "Без заголовка" for target in targets}),
        "targets": targets,
    }
    return {"source_fingerprint": inspection.fingerprint, "recipe_fingerprint": recipe_fingerprint, "scopes": [scope]}


def apply_bulk_ignore_scope(source_path: str | Path, recipe: dict[str, Any], bulk_scope_id: str) -> dict[str, Any]:
    if not isinstance(bulk_scope_id, str) or not bulk_scope_id:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Bulk scope identifier is required.")
    scopes = bulk_ignore_scopes(source_path, recipe)["scopes"]
    scope = next((item for item in scopes if item["bulk_scope_id"] == bulk_scope_id), None)
    if scope is None:
        raise ImportCommandError("STALE_BULK_SCOPE", "Bulk scope no longer matches the current source and recipe.")
    decisions = [
        {
            "block_id": target["block_id"],
            "source_axis": target["source_axis"],
            "source_index": target["source_index"],
            "target": "Ignore",
        }
        for target in scope["targets"]
    ]
    revised = revise_import_mappings(source_path, recipe, decisions)
    return {**revised, "bulk_scope_id": bulk_scope_id, "applied_decision_count": len(decisions)}


def _active_import_filter() -> str:
    return "b.status = 'applied' AND x.import_batch_id IS NULL"


def list_project_analyses(database_path: str | Path, limit: int = 500, offset: int = 0) -> dict[str, Any]:
    """Return active Analysis/Measurement rows plus lossless source metadata."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
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
                LIMIT ? OFFSET ?""",
            (limit, offset),
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
                elif section.get("analysis_identity_policy") == "source_row":
                    identity_names.append("Source row")
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
            "offset": offset,
            "has_more": offset + len(result) < total,
            "source_count": source_count,
            "import_batch_count": batch_count,
            "latest_import": latest_import,
            "analyses": result,
        }
    finally:
        connection.close()
