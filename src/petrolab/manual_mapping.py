"""User-driven import mapping revisions for the Desktop review screen.

React sends explicit user decisions. Python owns recipe semantics, fingerprints
and validation. Multiple UI edits are applied atomically so a user never has to
commit one source column at a time.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .import_preview import ImportCommandError, inspect_source, semantic_fingerprint, validate_recipe


TARGETS = {
    "Ignore": ("ignore", "ignored"),
    "Analysis": ("identity", "identity"),
    "Sample": ("identity", "identity"),
    "Point": ("identity", "identity"),
    "Measurement": ("measurement", "measured"),
}
VALID_UNITS = {"wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"}
IRON_FIELDS = {"feo", "feot", "fe2o3", "fe2o3t", "fetotal"}


def _normalized_field(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("₂", "2").replace("₃", "3")
    return "".join(character for character in value if character.isalnum())


def _find_mapping(revised: dict[str, Any], sheet_name: str, source_column_index: int) -> dict[str, Any]:
    for section in revised.get("sections", []):
        if section.get("sheet_name") != sheet_name:
            continue
        for mapping in section.get("mappings", []):
            if mapping.get("source_column_index") == source_column_index:
                return mapping
    raise ImportCommandError(
        "RECIPE_SCHEMA_INCOMPATIBLE",
        "Mapping does not exist in this recipe.",
        {"sheet_name": sheet_name, "source_column_index": source_column_index},
    )


def _apply_decision(revised: dict[str, Any], decision: dict[str, Any]) -> None:
    sheet_name = decision.get("sheet_name")
    source_column_index = decision.get("source_column_index")
    target = decision.get("target")
    if not isinstance(sheet_name, str) or not sheet_name:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping decision needs a sheet name.")
    if not isinstance(source_column_index, int) or source_column_index < 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source column index is invalid.")
    if target not in TARGETS:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown mapping target.", {"target": target})

    mapping = _find_mapping(revised, sheet_name, source_column_index)
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
                {"sheet_name": sheet_name, "header": source_header, "unit": unit},
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


def revise_import_mappings(
    source_path: str | Path,
    recipe: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply all mapping decisions, then fingerprint and validate exactly once."""
    if not isinstance(decisions, list) or not decisions:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "At least one mapping decision is required.")

    inspection = inspect_source(source_path)
    revised = deepcopy(recipe)
    seen: set[tuple[str, int]] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping decision must be an object.")
        key = (str(decision.get("sheet_name") or ""), decision.get("source_column_index"))
        if key in seen:
            raise ImportCommandError("DUPLICATE_MAPPING", "A source column was edited more than once in one batch.")
        seen.add(key)
        _apply_decision(revised, decision)

    mapped_iron = any(
        item.get("target_role") == "measurement" and _normalized_field(item.get("canonical_field")) in IRON_FIELDS
        for section in revised.get("sections", [])
        for item in section.get("mappings", [])
    )
    revised.setdefault("global_decisions", {})["fe_semantics"] = (
        "preserve_reported_form_for_review" if mapped_iron else "not_present"
    )
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
    """Compatibility wrapper for one decision."""
    return revise_import_mappings(source_path, recipe, [{
        "sheet_name": sheet_name,
        "source_column_index": source_column_index,
        "target": target,
        "canonical_field": canonical_field,
        "unit": unit,
    }])
