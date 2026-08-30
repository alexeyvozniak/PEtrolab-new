"""User-driven import recipe revisions for the Desktop review screen.

React sends only explicit user decisions. Python owns recipe semantics,
orientation rebuilding, semantic fingerprints and validation against the
immutable source.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .desktop_workflow import build_import_section, collect_recipe_warnings
from .import_preview import ImportCommandError, inspect_source, semantic_fingerprint
from .oriented_import import VALID_ORIENTATIONS, validate_oriented_recipe


TARGETS = {
    "Ignore": ("ignore", "ignored"),
    "Analysis": ("identity", "identity"),
    "Sample": ("identity", "identity"),
    "Point": ("identity", "identity"),
    "Measurement": ("measurement", "measured"),
}
VALID_UNITS = {"wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"}
IRON_FIELDS = {"fe", "feo", "feot", "fe2o3", "fe2o3t", "fetotal"}


def _normalized_field(value: str | None) -> str:
    if not value:
        return ""
    return "".join(character for character in value.lower() if character.isalnum())


def _refresh_decisions(recipe: dict[str, Any]) -> None:
    mapped_iron = any(
        item.get("target_role") == "measurement" and _normalized_field(item.get("canonical_field")) in IRON_FIELDS
        for section in recipe.get("sections", [])
        for item in section.get("mappings", [])
    )
    recipe.setdefault("global_decisions", {})["fe_semantics"] = (
        "preserve_reported_form_for_review" if mapped_iron else "not_present"
    )
    recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)


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
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source mapping index is invalid.")

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
        field = (canonical_field or mapping.get("canonical_field") or source_header).strip()
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
    _refresh_decisions(revised)
    validation = validate_oriented_recipe(inspection, revised)
    return {
        "recipe": revised,
        "validation": validation,
        "warnings": collect_recipe_warnings(inspection, revised),
    }


def revise_import_orientation(
    source_path: str | Path,
    recipe: dict[str, Any],
    sheet_name: str,
    orientation: str,
) -> dict[str, Any]:
    """Rebuild one worksheet section in rows- or columns-as-analyses orientation."""
    if orientation not in VALID_ORIENTATIONS:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown table orientation.", {"orientation": orientation})
    inspection = inspect_source(source_path)
    sheet = next((item for item in inspection.sheets if item.name == sheet_name), None)
    if sheet is None:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Worksheet does not exist.", {"sheet_name": sheet_name})

    rebuilt, _, _ = build_import_section(sheet, orientation)
    if rebuilt is None:
        label = "строк" if orientation == "rows" else "столбцов"
        raise ImportCommandError(
            "RECIPE_SCHEMA_INCOMPATIBLE",
            f"PetroLab не смог определить заголовки для режима «анализы по {label}». Нужна ручная настройка границ таблицы.",
            {"sheet_name": sheet_name, "orientation": orientation},
        )

    revised = deepcopy(recipe)
    replaced = False
    new_sections: list[dict[str, Any]] = []
    for section in revised.get("sections", []):
        if section.get("sheet_name") == sheet_name:
            if not replaced:
                new_sections.append(rebuilt)
                replaced = True
            continue
        new_sections.append(section)
    if not replaced:
        new_sections.append(rebuilt)
    revised["sections"] = new_sections
    _refresh_decisions(revised)
    validation = validate_oriented_recipe(inspection, revised)
    return {
        "recipe": revised,
        "validation": validation,
        "warnings": collect_recipe_warnings(inspection, revised),
    }
