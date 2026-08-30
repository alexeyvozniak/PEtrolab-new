"""User-driven import mapping revisions for the Desktop review screen.

React sends only explicit user decisions.  This service owns recipe semantics,
recalculates the semantic fingerprint and validates the revised recipe against
the immutable source before it can be planned or applied.
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
    "Mineral": ("metadata", "metadata"),
    "Generation": ("metadata", "metadata"),
    "Measurement": ("measurement", "measured"),
}
VALID_UNITS = {"wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"}
IRON_FIELDS = {"FeO", "FeOt", "Fe2O3", "Fe2O3t", "Fe_total"}


def revise_import_mapping(
    source_path: str | Path,
    recipe: dict[str, Any],
    sheet_name: str,
    source_column_index: int,
    target: str,
    canonical_field: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Return one validated recipe revision for one explicit mapping decision."""
    inspection = inspect_source(source_path)
    if target not in TARGETS:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown mapping target.", {"target": target})
    if not isinstance(source_column_index, int) or source_column_index < 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source column index is invalid.")

    revised = deepcopy(recipe)
    mapping: dict[str, Any] | None = None
    for section in revised.get("sections", []):
        if section.get("sheet_name") != sheet_name:
            continue
        for candidate in section.get("mappings", []):
            if candidate.get("source_column_index") == source_column_index:
                mapping = candidate
                break
        if mapping is not None:
            break
    if mapping is None:
        raise ImportCommandError(
            "RECIPE_SCHEMA_INCOMPATIBLE",
            "Mapping does not exist in this recipe.",
            {"sheet_name": sheet_name, "source_column_index": source_column_index},
        )

    role, semantics = TARGETS[target]
    source_header = str(mapping.get("source_header") or "")
    if target == "Ignore":
        field = source_header or "Ignored"
        selected_unit = None
    elif target == "Measurement":
        field = (canonical_field or source_header).strip()
        if not field:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Measurement field name is required.")
        if unit not in VALID_UNITS:
            raise ImportCommandError("UNKNOWN_UNIT", "Choose an explicit unit for the measurement.", {"unit": unit})
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

    mapped_iron = any(
        item.get("target_role") == "measurement" and item.get("canonical_field") in IRON_FIELDS
        for section in revised.get("sections", [])
        for item in section.get("mappings", [])
    )
    revised.setdefault("global_decisions", {})["fe_semantics"] = (
        "preserve_reported_form_for_review" if mapped_iron else "not_present"
    )
    revised["semantic_fingerprint"] = semantic_fingerprint(revised)
    validation = validate_recipe(inspection, revised)
    return {"recipe": revised, "validation": validation}
