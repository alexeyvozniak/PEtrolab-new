"""Desktop-facing application services for the first live PetroLab vertical slice.

This module keeps import recognition and SQLite projections in Python so React
remains a presentation layer. Automatic recognition stays conservative about
units, while also returning enough structured review information for the UI to
make likely chemistry columns easy to confirm in bulk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .import_apply import open_project
from .import_preview import ImportCommandError, inspect_source, semantic_fingerprint


IDENTITY_FIELDS = {
    "analysis": "Analysis",
    "анализ": "Analysis",
    "sample": "Sample",
    "sampleid": "Sample",
    "образец": "Sample",
    "образецid": "Sample",
    "point": "Point",
    "spot": "Point",
    "точка": "Point",
}

METADATA_FIELDS = {
    "mineral": "Mineral",
    "минерал": "Mineral",
}

MEASUREMENT_FIELDS = {
    "sio2": "SiO2", "tio2": "TiO2", "al2o3": "Al2O3", "feo": "FeO", "feot": "FeOt",
    "fe2o3": "Fe2O3", "fe2o3t": "Fe2O3t", "mno": "MnO", "mgo": "MgO", "cao": "CaO",
    "na2o": "Na2O", "k2o": "K2O", "p2o5": "P2O5", "cr2o3": "Cr2O3", "nio": "NiO",
    "f": "F", "cl": "Cl", "li": "Li", "rb": "Rb", "ba": "Ba", "sr": "Sr", "ni": "Ni",
    "cr": "Cr", "co": "Co", "sc": "Sc", "v": "V", "cu": "Cu", "zn": "Zn", "ga": "Ga",
    "y": "Y", "zr": "Zr", "nb": "Nb", "mo": "Mo", "cs": "Cs", "la": "La", "ce": "Ce",
    "pr": "Pr", "nd": "Nd", "sm": "Sm", "eu": "Eu", "gd": "Gd", "tb": "Tb", "dy": "Dy",
    "ho": "Ho", "er": "Er", "tm": "Tm", "yb": "Yb", "lu": "Lu", "hf": "Hf", "ta": "Ta",
    "w": "W", "pb": "Pb", "th": "Th", "u": "U",
}

IRON_FIELDS = {"FeO", "FeOt", "Fe2O3", "Fe2O3t"}


def _normalized(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("₂", "2").replace("₃", "3")
    return "".join(character for character in value if character.isalnum())


def _field_token(header: str) -> str:
    text = header.strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.split(r"\s+", text, maxsplit=1)[0]
    return _normalized(text)


def _unit_from_header(header: str) -> str | None:
    lowered = header.lower().replace(" ", "")
    if "ppm" in lowered or "мкг/г" in lowered:
        return "ppm"
    if "ppb" in lowered:
        return "ppb"
    if "apfu" in lowered or "а.е.ф." in lowered:
        return "apfu"
    if "mol%" in lowered or "мол.%" in lowered or "мол%" in lowered:
        return "mol%"
    if "wt.%" in lowered or "wt%" in lowered or "mass%" in lowered or "мас.%" in lowered or "мас%" in lowered:
        return "wt.%"
    if "%" in lowered:
        return "wt.%"
    return None


def _mapping_for_header(column: int, header: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized = _normalized(header)
    field_token = _field_token(header)
    identity = IDENTITY_FIELDS.get(normalized) or IDENTITY_FIELDS.get(field_token)
    if identity:
        return ({
            "source_column_index": column,
            "source_header": header,
            "target_role": "identity",
            "canonical_field": identity,
            "unit": None,
            "measurement_semantics": "identity",
        }, None)
    metadata = METADATA_FIELDS.get(normalized) or METADATA_FIELDS.get(field_token)
    if metadata:
        return ({
            "source_column_index": column,
            "source_header": header,
            "target_role": "metadata",
            "canonical_field": metadata,
            "unit": None,
            "measurement_semantics": "metadata",
        }, None)
    measurement = MEASUREMENT_FIELDS.get(field_token)
    if measurement:
        unit = _unit_from_header(header)
        if unit:
            return ({
                "source_column_index": column,
                "source_header": header,
                "target_role": "measurement",
                "canonical_field": measurement,
                "unit": unit,
                "measurement_semantics": "measured",
            }, None)
        return ({
            "source_column_index": column,
            "source_header": header,
            "target_role": "ignore",
            "canonical_field": header,
            "unit": None,
            "measurement_semantics": "ignored",
        }, {
            "code": "UNIT_REQUIRES_REVIEW",
            "source_header": header,
            "source_column_index": column,
            "canonical_field": measurement,
        })
    return ({
        "source_column_index": column,
        "source_header": header,
        "target_role": "ignore",
        "canonical_field": header,
        "unit": None,
        "measurement_semantics": "ignored",
    }, None)


def suggest_import_recipe(source_path: str | Path) -> dict[str, Any]:
    """Create a conservative, immediately inspectable recipe for a real source."""
    inspection = inspect_source(source_path)
    sections: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(inspection.projection()["warnings"])
    mapped_iron = False

    for sheet in inspection.sheets:
        if not sheet.header_rows:
            warnings.append({"code": "HEADER_NOT_DETECTED", "sheet_name": sheet.name})
            continue
        header_row = sheet.header_rows[0]
        header = sheet.rows[header_row - 1]
        mappings: list[dict[str, Any]] = []
        for column, raw_header in enumerate(header):
            if raw_header in (None, ""):
                continue
            mapping, warning = _mapping_for_header(column, str(raw_header))
            mappings.append(mapping)
            if warning:
                warnings.append({"sheet_name": sheet.name, **warning})
            mapped_iron = mapped_iron or (mapping["target_role"] == "measurement" and mapping["canonical_field"] in IRON_FIELDS)
        if not mappings:
            warnings.append({"code": "NO_COLUMNS_DETECTED", "sheet_name": sheet.name})
            continue
        sections.append({
            "sheet_name": sheet.name,
            "block_id": f"{sheet.name}:{header_row}",
            "header_row": header_row,
            "data_start_row": header_row + 1,
            "data_end_row": len(sheet.rows),
            "mappings": mappings,
        })

    if not sections:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "No importable table headers were detected in the selected file.")

    recipe: dict[str, Any] = {
        "schema_version": 1,
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


def list_project_analyses(database_path: str | Path, limit: int = 500) -> dict[str, Any]:
    """Return active Analysis/Measurement rows plus latest-import metadata."""
    limit = max(1, min(int(limit), 2000))
    connection = open_project(database_path)
    try:
        active_filter = "b.status = 'applied' AND x.import_batch_id IS NULL"
        total = connection.execute(
            f"""SELECT COUNT(*)
                FROM analysis a
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                WHERE {active_filter}"""
        ).fetchone()[0]
        rows = connection.execute(
            f"""SELECT a.analysis_id, a.source_id, a.sheet_name, a.source_row_number, a.block_id,
                       a.identity_json, a.created_at, s.display_name AS source_name,
                       r.recipe_json
                FROM analysis a
                JOIN source_file s ON s.source_id = a.source_id
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                JOIN import_recipe_revision r ON r.recipe_revision_id = b.recipe_revision_id
                LEFT JOIN import_batch_retraction x ON x.import_batch_id = b.import_batch_id
                WHERE {active_filter}
                ORDER BY a.created_at DESC, a.sheet_name, a.source_row_number
                LIMIT ?""",
            (limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            identity_values = json.loads(row["identity_json"])
            recipe = json.loads(row["recipe_json"])
            identity_names: list[str] = []
            for section in recipe.get("sections", []):
                if section.get("sheet_name") == row["sheet_name"] and section.get("block_id") == row["block_id"]:
                    identity_names = [
                        mapping.get("canonical_field") or mapping.get("source_header")
                        for mapping in section.get("mappings", [])
                        if mapping.get("target_role") == "identity"
                    ]
                    break
            identity = {
                str(name): identity_values[index] if index < len(identity_values) else ""
                for index, name in enumerate(identity_names)
            }
            measurements = connection.execute(
                """SELECT canonical_field, unit, raw_token, qualifier, detection_limit
                   FROM measurement WHERE analysis_id = ? ORDER BY source_column_index""",
                (row["analysis_id"],),
            ).fetchall()
            result.append({
                "analysis_id": row["analysis_id"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "sheet_name": row["sheet_name"],
                "source_row_number": row["source_row_number"],
                "identity": identity,
                "measurements": {
                    measurement["canonical_field"]: {
                        "raw_token": measurement["raw_token"],
                        "unit": measurement["unit"],
                        "qualifier": measurement["qualifier"],
                        "detection_limit": measurement["detection_limit"],
                    }
                    for measurement in measurements
                },
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
