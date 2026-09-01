"""Strict PetroLab Clean Table v1 classification and recipe construction.

A false negative is acceptable: ambiguous files fall back to raw review.
A false positive is not: this module never guesses a missing unit or role.
"""

from __future__ import annotations

import re
from typing import Any

from .import_preview import SourceInspection, create_import_plan, semantic_fingerprint


CLEAN_TABLE_VERSION = "1.0"
VALID_MEASUREMENT_UNITS = ("wt.%", "at.%", "ppm", "ppb", "apfu", "mol%", "ratio")

IDENTITY_ALIASES = {
    "analysis": "Analysis",
    "sample": "Sample",
    "point": "Point",
}

METADATA_ALIASES = {
    "mineral": "Mineral",
    "generation": "Generation",
    "rock": "Rock",
    "source": "Source",
    "doi": "DOI",
    "method": "Method",
    "measurementset": "Measurement set",
    "comment": "Comment",
    "classification": "Classification",
    "formulanote": "Formula / note",
    "parentmethod": "Parent Method",
    "agema": "Age [Ma]",
}

# These values are measurements from the source workbook, but their semantics
# are calculated/source-derived rather than direct instrumental measurements.
SOURCE_DERIVED_FIELDS = {"total", "mg#", "xmg", "fe3+"}
IRON_FIELDS = {"feo", "feot", "fe2o3", "fe2o3t", "fe", "fetotal"}

# Helper sheets bundled with the official human-facing template. They are not
# scientific data and may be ignored only by this exact template contract.
OFFICIAL_HELPER_SHEETS = {
    "00_Инструкция",
    "08_Сырые_сценарии",
    "09_Словарь_заголовков",
    "10_Чеклист",
}


def _normalized(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("₂", "2").replace("₃", "3")
    return "".join(character for character in value if character.isalnum() or character in {"#", "+"})


def _last_nonempty_row(rows: tuple[tuple[str | None, ...], ...]) -> int:
    for row_number in range(len(rows), 0, -1):
        if any(value not in (None, "") for value in rows[row_number - 1]):
            return row_number
    return 0


def _used_columns(rows: tuple[tuple[str | None, ...], ...], end_row: int) -> list[int]:
    maximum = max((len(row) for row in rows[:end_row]), default=0)
    return [
        column
        for column in range(maximum)
        if any(column < len(row) and row[column] not in (None, "") for row in rows[:end_row])
    ]


def _unit_from_header(header: str) -> tuple[str, str] | None:
    stripped = header.strip()
    # Clean Table requires an explicit bracketed unit so ordinary words such as
    # "ppm note" cannot accidentally become measurements.
    match = re.fullmatch(r"(.+?)\s*\[\s*([^\]]+)\s*\]\s*", stripped)
    if not match:
        return None
    field = match.group(1).strip()
    raw_unit = re.sub(r"\s+", "", match.group(2).lower())
    unit_aliases = {
        "wt.%": "wt.%", "wt%": "wt.%", "mass%": "wt.%", "weight%": "wt.%", "мас.%": "wt.%", "мас%": "wt.%",
        "at.%": "at.%", "at%": "at.%", "atomic%": "at.%", "атом.%": "at.%", "атом%": "at.%",
        "ppm": "ppm", "мкг/г": "ppm",
        "ppb": "ppb",
        "apfu": "apfu", "а.е.ф.": "apfu",
        "mol%": "mol%", "мол.%": "mol%", "мол%": "mol%",
        "ratio": "ratio",
    }
    unit = unit_aliases.get(raw_unit)
    if not field or unit not in VALID_MEASUREMENT_UNITS:
        return None
    return field, unit


def _mapping(column: int, header: str) -> tuple[dict[str, Any] | None, str | None]:
    token = _normalized(header)
    identity = IDENTITY_ALIASES.get(token)
    if identity:
        return ({
            "source_axis": "column",
            "source_column_index": column,
            "source_header": header,
            "target_role": "identity",
            "canonical_field": identity,
            "unit": None,
            "measurement_semantics": "identity",
        }, None)

    metadata = METADATA_ALIASES.get(token)
    if metadata:
        return ({
            "source_axis": "column",
            "source_column_index": column,
            "source_header": header,
            "target_role": "metadata",
            "canonical_field": metadata,
            "unit": None,
            "measurement_semantics": "metadata",
        }, None)

    measurement = _unit_from_header(header)
    if measurement:
        field, unit = measurement
        field_token = _normalized(field)
        return ({
            "source_axis": "column",
            "source_column_index": column,
            "source_header": header,
            "target_role": "measurement",
            "canonical_field": field,
            "unit": unit,
            "measurement_semantics": "source_derived" if field_token in SOURCE_DERIVED_FIELDS else "measured",
        }, None)

    return None, "UNRECOGNIZED_CLEAN_FIELD"


def _section_summary(section: dict[str, Any]) -> dict[str, Any]:
    identities = [item["canonical_field"] for item in section["mappings"] if item["target_role"] == "identity"]
    metadata = [item["canonical_field"] for item in section["mappings"] if item["target_role"] == "metadata"]
    measurements = [
        {
            "field": item["canonical_field"],
            "unit": item["unit"],
            "semantics": item["measurement_semantics"],
        }
        for item in section["mappings"] if item["target_role"] == "measurement"
    ]
    return {
        "sheet_name": section["sheet_name"],
        "analysis_fields": identities,
        "metadata_fields": metadata,
        "measurements": measurements,
    }


def classify_clean_table(inspection: SourceInspection) -> dict[str, Any]:
    """Return strict fast-path classification and, when valid, a complete recipe."""
    reasons: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    mapped_iron = False
    ignored_helper_sheets: list[str] = []

    inspection_warnings = [
        warning
        for warning in inspection.projection().get("warnings", [])
        if warning.get("sheet_name") not in OFFICIAL_HELPER_SHEETS
    ]
    for warning in inspection_warnings:
        reasons.append({"code": warning.get("code", "SOURCE_WARNING"), "sheet_name": warning.get("sheet_name")})

    for sheet in inspection.sheets:
        end_row = _last_nonempty_row(sheet.rows)
        if end_row == 0:
            continue
        if sheet.name in OFFICIAL_HELPER_SHEETS:
            ignored_helper_sheets.append(sheet.name)
            continue
        if end_row < 2:
            reasons.append({"code": "CLEAN_TABLE_NO_DATA_ROWS", "sheet_name": sheet.name})
            continue

        used_columns = _used_columns(sheet.rows, end_row)
        header = sheet.rows[0] if sheet.rows else ()
        if not used_columns:
            continue

        headers: list[str] = []
        mappings: list[dict[str, Any]] = []
        sheet_failed = False
        for column in used_columns:
            raw_header = header[column] if column < len(header) else None
            if raw_header in (None, ""):
                reasons.append({"code": "CLEAN_TABLE_BLANK_HEADER", "sheet_name": sheet.name, "source_column_index": column})
                sheet_failed = True
                continue
            text = str(raw_header).strip()
            headers.append(text)
            mapping, error = _mapping(column, text)
            if mapping is None:
                reasons.append({"code": error or "UNRECOGNIZED_CLEAN_FIELD", "sheet_name": sheet.name, "source_header": text, "source_column_index": column})
                sheet_failed = True
            else:
                mappings.append(mapping)

        normalized_headers = [_normalized(item) for item in headers]
        duplicates = sorted({item for item in normalized_headers if item and normalized_headers.count(item) > 1})
        if duplicates:
            reasons.append({"code": "CLEAN_TABLE_DUPLICATE_HEADER", "sheet_name": sheet.name, "headers": duplicates})
            sheet_failed = True

        first_header_signature = tuple(_normalized(value) for value in header if value not in (None, ""))
        for row_number in range(2, end_row + 1):
            row = sheet.rows[row_number - 1]
            if not any(value not in (None, "") for value in row):
                reasons.append({"code": "CLEAN_TABLE_INTERNAL_BLANK_ROW", "sheet_name": sheet.name, "row_number": row_number})
                sheet_failed = True
                continue
            signature = tuple(_normalized(value) for value in row if value not in (None, ""))
            if first_header_signature and signature == first_header_signature:
                reasons.append({"code": "CLEAN_TABLE_REPEATED_HEADER", "sheet_name": sheet.name, "row_number": row_number})
                sheet_failed = True

        identity_fields = [item["canonical_field"] for item in mappings if item["target_role"] == "identity"]
        measurement_fields = [item for item in mappings if item["target_role"] == "measurement"]
        if "Analysis" not in identity_fields:
            reasons.append({"code": "CLEAN_TABLE_ANALYSIS_REQUIRED", "sheet_name": sheet.name})
            sheet_failed = True
        if not measurement_fields:
            reasons.append({"code": "CLEAN_TABLE_MEASUREMENT_REQUIRED", "sheet_name": sheet.name})
            sheet_failed = True

        if sheet_failed:
            continue

        mapped_iron = mapped_iron or any(_normalized(item["canonical_field"]) in IRON_FIELDS for item in measurement_fields)
        sections.append({
            "sheet_name": sheet.name,
            "block_id": f"{sheet.name}:clean:1",
            "enabled": True,
            "orientation": "rows_are_analyses",
            "header_row": 1,
            "data_start_row": 2,
            "data_end_row": end_row,
            "unit_context": None,
            "mappings": mappings,
        })

    if not sections:
        reasons.append({"code": "CLEAN_TABLE_NO_VALID_DATA_SHEETS"})

    if reasons:
        return {
            "mode": "raw_review",
            "clean_table_version": CLEAN_TABLE_VERSION,
            "reasons": reasons,
            "ignored_helper_sheets": ignored_helper_sheets,
            "sections": [],
            "recipe": None,
        }

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
    plan = create_import_plan(inspection, recipe)
    if plan["summary"].get("duplicate_candidate_groups", 0):
        return {
            "mode": "raw_review",
            "clean_table_version": CLEAN_TABLE_VERSION,
            "reasons": [{"code": "CLEAN_TABLE_DUPLICATE_IDENTITIES", "candidate_group_count": plan["summary"]["duplicate_candidate_groups"]}],
            "ignored_helper_sheets": ignored_helper_sheets,
            "sections": [_section_summary(section) for section in sections],
            "recipe": None,
        }

    return {
        "mode": "clean_table_fast",
        "clean_table_version": CLEAN_TABLE_VERSION,
        "reasons": [],
        "ignored_helper_sheets": ignored_helper_sheets,
        "sections": [_section_summary(section) for section in sections],
        "plan_summary": plan["summary"],
        "recipe": recipe,
    }
