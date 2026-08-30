"""User-driven import mapping and block revisions.

React sends explicit decisions. Python owns recognition, recipe semantics,
fingerprints and validation. Multiple edits are applied atomically.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .import_preview import ImportCommandError, inspect_source, semantic_fingerprint, validate_recipe
from .import_recognition import IRON_FIELDS, VALID_UNITS, mappings_for_column_header, mappings_for_row_header, normalized


TARGETS = {
    "Ignore": ("ignore", "ignored"),
    "Analysis": ("identity", "identity"),
    "Sample": ("identity", "identity"),
    "Point": ("identity", "identity"),
    "Mineral": ("metadata", "metadata"),
    "Generation": ("metadata", "metadata"),
    "Measurement": ("measurement", "measured"),
}


def _find_section(revised: dict[str, Any], block_id: str) -> dict[str, Any]:
    for section in revised.get("sections", []):
        if section.get("block_id") == block_id:
            return section
    raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Logical block does not exist in this recipe.", {"block_id": block_id})


def _mapping_index(mapping: dict[str, Any]) -> tuple[str, int]:
    axis = mapping.get("source_axis") or ("column" if "source_column_index" in mapping else "row")
    key = "source_column_index" if axis == "column" else "source_row_index"
    index = mapping.get(key)
    if axis not in {"column", "row"} or not isinstance(index, int) or index < 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping source index is invalid.")
    return str(axis), index


def _find_mapping(section: dict[str, Any], source_axis: str, source_index: int) -> dict[str, Any]:
    for mapping in section.get("mappings", []):
        axis, index = _mapping_index(mapping)
        if axis == source_axis and index == source_index:
            return mapping
    raise ImportCommandError(
        "RECIPE_SCHEMA_INCOMPATIBLE",
        "Mapping does not exist in this block.",
        {"block_id": section.get("block_id"), "source_axis": source_axis, "source_index": source_index},
    )


def _apply_mapping_decision(revised: dict[str, Any], decision: dict[str, Any]) -> None:
    block_id = decision.get("block_id")
    source_axis = decision.get("source_axis", "column")
    source_index = decision.get("source_index")
    target = decision.get("target")
    if not isinstance(block_id, str) or not block_id:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping decision needs a block ID.")
    if source_axis not in {"column", "row"} or not isinstance(source_index, int) or source_index < 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source mapping coordinate is invalid.")
    if target not in TARGETS:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown mapping target.", {"target": target})

    section = _find_section(revised, block_id)
    mapping = _find_mapping(section, source_axis, source_index)
    role, semantics = TARGETS[target]
    source_header = str(mapping.get("source_header") or "")

    if target == "Ignore":
        field = source_header or "Ignored"
        selected_unit = None
    elif target == "Measurement":
        raw_field = decision.get("canonical_field")
        field = (raw_field if isinstance(raw_field, str) else source_header).strip()
        unit = decision.get("unit")
        if not field:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Measurement field name is required.")
        if unit not in VALID_UNITS:
            raise ImportCommandError(
                "UNKNOWN_UNIT",
                "Choose an explicit unit for every measurement.",
                {"block_id": block_id, "header": source_header, "unit": unit},
            )
        selected_unit = unit
    else:
        field = target
        selected_unit = None

    mapping.update({
        "target_role": role,
        "canonical_field": field,
        "unit": selected_unit,
        "measurement_semantics": semantics,
    })


def _rebuild_section_mappings(inspection: Any, section: dict[str, Any]) -> list[dict[str, Any]]:
    sheet = next((item for item in inspection.sheets if item.name == section["sheet_name"]), None)
    if sheet is None:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Block sheet is unavailable.")
    context = section.get("unit_context")
    context_unit = context.get("unit") if isinstance(context, dict) else None
    if section.get("orientation", "rows_are_analyses") == "rows_are_analyses":
        header_row = int(section["header_row"])
        mappings, _ = mappings_for_row_header(sheet.rows[header_row - 1], context_unit)
        return mappings
    mappings, _ = mappings_for_column_header(
        sheet.rows,
        int(section.get("header_column", 1)),
        int(section["data_start_row"]),
        int(section["data_end_row"]),
        context_unit,
    )
    return mappings


def _apply_section_decision(inspection: Any, revised: dict[str, Any], decision: dict[str, Any]) -> None:
    block_id = decision.get("block_id")
    if not isinstance(block_id, str) or not block_id:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Block decision needs a block ID.")
    section = _find_section(revised, block_id)
    previous_orientation = section.get("orientation", "rows_are_analyses")

    for field in ("enabled", "header_row", "data_start_row", "data_end_row", "header_column", "data_start_column", "data_end_column", "analysis_axis_role", "analysis_axis_field"):
        if field in decision:
            section[field] = decision[field]
    if "orientation" in decision:
        orientation = decision["orientation"]
        if orientation not in {"rows_are_analyses", "columns_are_analyses"}:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown block orientation.")
        section["orientation"] = orientation

    orientation = section.get("orientation", "rows_are_analyses")
    if orientation == "columns_are_analyses":
        sheet = next(item for item in inspection.sheets if item.name == section["sheet_name"])
        max_columns = max((len(row) for row in sheet.rows), default=0)
        section.setdefault("header_column", 1)
        section.setdefault("data_start_column", 2)
        section.setdefault("data_end_column", max_columns)
        section.setdefault("analysis_axis_role", "Analysis")
        section.setdefault("analysis_axis_field", "Analysis")
    if previous_orientation != orientation or decision.get("rebuild_mappings"):
        section["mappings"] = _rebuild_section_mappings(inspection, section)


def _refresh_fe_semantics(revised: dict[str, Any]) -> None:
    mapped_iron = any(
        item.get("target_role") == "measurement" and normalized(item.get("canonical_field")) in {normalized(field) for field in IRON_FIELDS}
        for section in revised.get("sections", []) if section.get("enabled", True)
        for item in section.get("mappings", [])
    )
    revised.setdefault("global_decisions", {})["fe_semantics"] = (
        "preserve_reported_form_for_review" if mapped_iron else "not_present"
    )


def revise_import_mappings(
    source_path: str | Path,
    recipe: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(decisions, list) or not decisions:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "At least one mapping decision is required.")
    inspection = inspect_source(source_path)
    revised = deepcopy(recipe)
    seen: set[tuple[str, str, int]] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping decision must be an object.")
        key = (str(decision.get("block_id") or ""), str(decision.get("source_axis") or "column"), decision.get("source_index"))
        if key in seen:
            raise ImportCommandError("DUPLICATE_MAPPING", "A source field was edited more than once in one batch.")
        seen.add(key)
        _apply_mapping_decision(revised, decision)
    _refresh_fe_semantics(revised)
    revised["semantic_fingerprint"] = semantic_fingerprint(revised)
    validation = validate_recipe(inspection, revised)
    return {"recipe": revised, "validation": validation, "applied_decision_count": len(decisions)}


def revise_import_sections(
    source_path: str | Path,
    recipe: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(decisions, list) or not decisions:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "At least one block decision is required.")
    inspection = inspect_source(source_path)
    revised = deepcopy(recipe)
    seen: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Block decision must be an object.")
        block_id = str(decision.get("block_id") or "")
        if block_id in seen:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "A block was edited more than once in one batch.")
        seen.add(block_id)
        _apply_section_decision(inspection, revised, decision)
    _refresh_fe_semantics(revised)
    revised["semantic_fingerprint"] = semantic_fingerprint(revised)
    validation = validate_recipe(inspection, revised)
    return {"recipe": revised, "validation": validation, "applied_decision_count": len(decisions)}


def revise_import_mapping(
    source_path: str | Path,
    recipe: dict[str, Any],
    sheet_name: str,
    source_column_index: int,
    target: str,
    canonical_field: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for older callers that identify the first block on a sheet."""
    block_id = next(
        (section["block_id"] for section in recipe.get("sections", []) if section.get("sheet_name") == sheet_name),
        None,
    )
    if block_id is None:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Sheet has no import block.")
    return revise_import_mappings(source_path, recipe, [{
        "block_id": block_id,
        "source_axis": "column",
        "source_index": source_column_index,
        "target": target,
        "canonical_field": canonical_field,
        "unit": unit,
    }])
