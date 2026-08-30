"""Orientation-aware adapter over the existing import validation/planning core.

A transposed source is represented as a virtual matrix. The source file is
never changed; planned virtual cell coordinates are translated back to the
immutable source coordinates before persistence.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .import_preview import (
    ImportCommandError,
    SheetInspection,
    SourceInspection,
    _header_candidates,
    create_import_plan,
    semantic_fingerprint,
    validate_recipe,
)


VALID_ORIENTATIONS = {"rows", "columns"}


def excel_column_name(index: int) -> str:
    """Return an Excel-style column label for a zero-based column index."""
    if index < 0:
        raise ValueError(index)
    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def transpose_rows(rows: tuple[tuple[str | None, ...], ...]) -> tuple[tuple[str | None, ...], ...]:
    width = max((len(row) for row in rows), default=0)
    return tuple(
        tuple(rows[row_index][column_index] if column_index < len(rows[row_index]) else None for row_index in range(len(rows)))
        for column_index in range(width)
    )


def oriented_rows(sheet: SheetInspection, orientation: str) -> tuple[tuple[str | None, ...], ...]:
    if orientation == "rows":
        return sheet.rows
    if orientation == "columns":
        return transpose_rows(sheet.rows)
    raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown table orientation.", {"orientation": orientation})


def oriented_header_candidates(sheet: SheetInspection, orientation: str) -> tuple[int, ...]:
    rows = oriented_rows(sheet, orientation)
    return _header_candidates([list(row) for row in rows])


def source_cell_coordinates(orientation: str, virtual_row_number: int, virtual_column_index: int) -> tuple[int, int, str]:
    """Translate a virtual matrix coordinate to the immutable source cell."""
    if orientation == "rows":
        source_row_number = virtual_row_number
        source_column_index = virtual_column_index
    elif orientation == "columns":
        source_row_number = virtual_column_index + 1
        source_column_index = virtual_row_number - 1
    else:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown table orientation.", {"orientation": orientation})
    return source_row_number, source_column_index, f"{excel_column_name(source_column_index)}{source_row_number}"


def _materialize(inspection: SourceInspection, recipe: dict[str, Any]) -> tuple[SourceInspection, dict[str, Any]]:
    """Return a virtual inspection and a legacy-compatible recipe for core validation."""
    declared = recipe.get("semantic_fingerprint")
    calculated = semantic_fingerprint(recipe)
    if declared != calculated:
        raise ImportCommandError(
            "RECIPE_SCHEMA_INCOMPATIBLE",
            "Recipe semantic fingerprint does not match its current decisions.",
            {"expected": calculated, "observed": declared},
        )

    orientations: dict[str, str] = {}
    for section in recipe.get("sections", []):
        sheet_name = str(section.get("sheet_name", ""))
        orientation = str(section.get("orientation", "rows"))
        if orientation not in VALID_ORIENTATIONS:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown table orientation.", {"orientation": orientation})
        previous = orientations.setdefault(sheet_name, orientation)
        if previous != orientation:
            raise ImportCommandError(
                "RECIPE_SCHEMA_INCOMPATIBLE",
                "One worksheet cannot use two orientations in the same recipe revision.",
                {"sheet_name": sheet_name},
            )

    virtual_sheets: list[SheetInspection] = []
    for sheet in inspection.sheets:
        orientation = orientations.get(sheet.name, "rows")
        rows = oriented_rows(sheet, orientation)
        headers = _header_candidates([list(row) for row in rows])
        virtual_sheets.append(SheetInspection(sheet.name, rows, headers, sheet.warnings))

    virtual_inspection = SourceInspection(
        inspection.path,
        inspection.source_format,
        inspection.fingerprint,
        tuple(virtual_sheets),
        inspection.warnings,
    )
    core_recipe = deepcopy(recipe)
    for section in core_recipe.get("sections", []):
        section.pop("orientation", None)
    core_recipe["semantic_fingerprint"] = semantic_fingerprint(core_recipe)
    return virtual_inspection, core_recipe


def validate_oriented_recipe(inspection: SourceInspection, recipe: dict[str, Any]) -> dict[str, Any]:
    virtual_inspection, core_recipe = _materialize(inspection, recipe)
    result = validate_recipe(virtual_inspection, core_recipe)
    orientation_by_key = {
        (section.get("sheet_name"), section.get("block_id")): section.get("orientation", "rows")
        for section in recipe.get("sections", [])
    }
    for section in result.get("sections", []):
        section["orientation"] = orientation_by_key.get((section.get("sheet_name"), section.get("block_id")), "rows")
    return result


def create_oriented_import_plan(inspection: SourceInspection, recipe: dict[str, Any]) -> dict[str, Any]:
    virtual_inspection, core_recipe = _materialize(inspection, recipe)
    plan = create_import_plan(virtual_inspection, core_recipe)
    sections = {
        (section.get("sheet_name"), section.get("block_id")): section
        for section in recipe.get("sections", [])
    }
    for record in plan.get("planned_records", []):
        section = sections[(record["sheet_name"], record["block_id"])]
        orientation = section.get("orientation", "rows")
        virtual_row = int(record["row_number"])
        record["source_orientation"] = orientation
        record["source_record_axis"] = "row" if orientation == "rows" else "column"
        record["source_record_index"] = virtual_row
        record["source_record_label"] = (
            str(virtual_row) if orientation == "rows" else excel_column_name(virtual_row - 1)
        )
        for measurement in record.get("measurements", []):
            virtual_column = int(measurement["source_column_index"])
            source_row, source_column, cell = source_cell_coordinates(orientation, virtual_row, virtual_column)
            measurement["virtual_source_column_index"] = virtual_column
            measurement["source_row_number"] = source_row
            measurement["source_column_index"] = source_column
            measurement["source_cell_reference"] = cell
    plan["validation"] = validate_oriented_recipe(inspection, recipe)
    return plan


def run_oriented_recipe_validate(source_path: str, recipe: dict[str, Any]) -> dict[str, Any]:
    from .import_preview import inspect_source

    try:
        return {"result": validate_oriented_recipe(inspect_source(source_path), recipe)}
    except ImportCommandError as exc:
        return exc.projection()


def run_oriented_plan_create(source_path: str, recipe: dict[str, Any]) -> dict[str, Any]:
    from .import_preview import inspect_source

    try:
        return {"result": create_oriented_import_plan(inspect_source(source_path), recipe)}
    except ImportCommandError as exc:
        return exc.projection()
