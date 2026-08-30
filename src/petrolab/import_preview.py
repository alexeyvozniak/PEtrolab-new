"""Read-only M1.1 import inspection, recipe validation and planning.

This module intentionally has no SQLite, UI or Tauri dependency.  It reads a
source file, records its exact SHA-256 fingerprint and returns plain JSON-safe
projections.  Applying a plan is a later M1.2 responsibility.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


XLSX_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": XLSX_MAIN, "r": XLSX_REL, "pr": PACKAGE_REL}
KNOWN_HEADER_TOKENS = {
    "analysis", "sample", "point", "mineral", "sio2", "mgo", "tio2", "f",
    "feo", "feot", "fe2o3", "li", "rb", "ba",
}
IRON_FIELDS = {"feo", "feot", "fe2o3", "fe2o3t", "fe_total"}
VALID_UNITS = {"wt.%", "mass%", "ppm", "ppb", "apfu", "mol%", "ratio"}
OLE_COMPOUND_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
VALID_OWNERSHIP_MODES = {"linked_external", "managed_copy"}
ROLE_SEMANTICS = {
    "identity": {"identity"},
    "metadata": {"metadata"},
    "interpretation": {"source_interpretation"},
    "ignore": {"ignored"},
    "measurement": {"measured", "source_derived"},
}


class ImportCommandError(ValueError):
    """Structured M1.1 failure with a stable UI-safe code."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def projection(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


@dataclass(frozen=True)
class SheetInspection:
    name: str
    rows: tuple[tuple[str | None, ...], ...]
    header_rows: tuple[int, ...]
    warnings: tuple[dict[str, Any], ...] = ()

    def projection(self) -> dict[str, Any]:
        used_rows = len(self.rows)
        used_columns = max((len(row) for row in self.rows), default=0)
        return {
            "name": self.name,
            "used_range": {"rows": used_rows, "columns": used_columns},
            "candidate_header_rows": list(self.header_rows),
        }


@dataclass(frozen=True)
class SourceInspection:
    path: Path
    source_format: str
    fingerprint: str
    sheets: tuple[SheetInspection, ...]
    warnings: tuple[dict[str, Any], ...] = ()

    def projection(self) -> dict[str, Any]:
        return {
            "source_path": self.path.name,
            "source_format": self.source_format,
            "source_fingerprint": self.fingerprint,
            "sheets": [sheet.projection() for sheet in self.sheets],
            "candidate_blocks": [
                {"sheet_name": sheet.name, "header_row": row, "block_id": f"{sheet.name}:{row}"}
                for sheet in self.sheets
                for row in sheet.header_rows
            ],
            "warnings": [*self.warnings, *(warning for sheet in self.sheets for warning in sheet.warnings)],
        }


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_fingerprint(recipe: dict[str, Any]) -> str:
    """Fingerprint only the decisions that determine how source values are read.

    Source bytes and entity lifecycle metadata intentionally stay out of this
    hash: their identities are represented separately by `source_file_sha256`
    and recipe revision IDs.
    """
    semantic_projection = {
        "source_format": recipe.get("source_format"),
        "ownership_mode": recipe.get("ownership_mode"),
        "sections": recipe.get("sections"),
        "global_decisions": recipe.get("global_decisions"),
    }
    canonical = json.dumps(semantic_projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _column_index(reference: str) -> int:
    letters = re.match(r"([A-Z]+)", reference)
    if not letters:
        return 0
    value = 0
    for letter in letters.group(1):
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _header_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower().replace("₂", "2").replace("₃", "3"))


def _header_candidates(rows: list[list[str | None]]) -> tuple[int, ...]:
    candidates: list[int] = []
    for number, row in enumerate(rows, start=1):
        matches = sum(
            any(_header_token(value).startswith(token) for token in KNOWN_HEADER_TOKENS)
            for value in row
            if value
        )
        if matches >= 2:
            candidates.append(number)
    return tuple(candidates)


def _read_xlsx(path: Path) -> tuple[SheetInspection, ...]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ImportCommandError("SOURCE_UNREADABLE", "Cannot read XLSX source.") from exc
    with archive:
        if any(info.flag_bits & 0x1 for info in archive.infolist()):
            raise ImportCommandError("WORKBOOK_ENCRYPTED", "Password-protected XLSX files cannot be inspected.")
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (KeyError, ET.ParseError) as exc:
            raise ImportCommandError("SOURCE_UNREADABLE", "Workbook metadata is invalid.") from exc
        relationship_targets = {
            relation.attrib["Id"]: relation.attrib["Target"].lstrip("/")
            for relation in rels.findall("pr:Relationship", NS)
        }
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(item.itertext()) for item in root.findall("x:si", NS)]
        inspections: list[SheetInspection] = []
        for sheet in workbook.findall("x:sheets/x:sheet", NS):
            relation_id = sheet.attrib.get(f"{{{XLSX_REL}}}id")
            target = relationship_targets.get(relation_id or "")
            if not target:
                raise ImportCommandError("SOURCE_UNREADABLE", "Worksheet relationship is missing.")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            root = ET.fromstring(archive.read(sheet_path))
            rows: list[list[str | None]] = []
            warnings: list[dict[str, Any]] = []
            hidden_rows: list[int] = []
            uncached_formula_cells: list[str] = []
            merged_ranges = [merged.attrib.get("ref") for merged in root.findall("x:mergeCells/x:mergeCell", NS)]
            if merged_ranges:
                warnings.append({"code": "MERGED_HEADERS", "sheet_name": sheet.attrib["name"], "ranges": merged_ranges})
            for row in root.findall("x:sheetData/x:row", NS):
                row_number = int(row.attrib.get("r", len(rows) + 1))
                while len(rows) < row_number - 1:
                    rows.append([])
                if row.attrib.get("hidden") in {"1", "true"}:
                    hidden_rows.append(row_number)
                cells: list[str | None] = []
                for cell in row.findall("x:c", NS):
                    index = _column_index(cell.attrib.get("r", "A1"))
                    while len(cells) <= index:
                        cells.append(None)
                    value_node = cell.find("x:v", NS)
                    value: str | None = value_node.text if value_node is not None else None
                    if cell.attrib.get("t") == "inlineStr":
                        inline = cell.find("x:is", NS)
                        value = "".join(inline.itertext()) if inline is not None else None
                    elif cell.attrib.get("t") == "s" and value is not None:
                        value = shared_strings[int(value)]
                    if cell.find("x:f", NS) is not None and value is None:
                        uncached_formula_cells.append(cell.attrib.get("r", ""))
                    cells[index] = value
                rows.append(cells)
            if hidden_rows:
                warnings.append({"code": "HIDDEN_ROWS", "sheet_name": sheet.attrib["name"], "row_numbers": hidden_rows})
            if uncached_formula_cells:
                warnings.append({"code": "FORMULA_WITHOUT_CACHED_VALUE", "sheet_name": sheet.attrib["name"], "cells": uncached_formula_cells})
            inspections.append(SheetInspection(sheet.attrib["name"], tuple(tuple(row) for row in rows), _header_candidates(rows), tuple(warnings)))
    return tuple(inspections)


def _read_delimited(path: Path, delimiter: str) -> tuple[SheetInspection, ...]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportCommandError("UNSUPPORTED_ENCODING", "Delimited source must be UTF-8 encoded.") from exc
    rows = [[cell if cell != "" else None for cell in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return (SheetInspection(path.stem, tuple(tuple(row) for row in rows), _header_candidates(rows)),)


def inspect_source(source_path: str | Path) -> SourceInspection:
    path = Path(source_path)
    if not path.is_file():
        raise ImportCommandError("SOURCE_UNREADABLE", "Source file does not exist.", {"path": str(path)})
    suffix = path.suffix.lower()
    readers = {".xlsx": ("xlsx", _read_xlsx), ".csv": ("csv", lambda file: _read_delimited(file, ",")), ".tsv": ("tsv", lambda file: _read_delimited(file, "\t"))}
    if suffix not in readers:
        raise ImportCommandError("SOURCE_UNREADABLE", "Only XLSX, CSV and TSV are supported by M1.1.", {"suffix": suffix})
    if suffix == ".xlsx":
        with path.open("rb") as source:
            if source.read(8) == OLE_COMPOUND_SIGNATURE:
                raise ImportCommandError("WORKBOOK_ENCRYPTED", "Password-protected XLSX files cannot be inspected.")
    source_format, reader = readers[suffix]
    return SourceInspection(path, source_format, _fingerprint(path), reader(path))


def _sheet(inspection: SourceInspection, name: str) -> SheetInspection:
    for sheet in inspection.sheets:
        if sheet.name == name:
            return sheet
    raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe refers to an absent worksheet.", {"sheet_name": name})


def _mapping_value(mapping: dict[str, Any], name: str) -> Any:
    if name not in mapping:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe mapping is incomplete.", {"field": name})
    return mapping[name]


def validate_recipe(inspection: SourceInspection, recipe: dict[str, Any]) -> dict[str, Any]:
    if recipe.get("source_file_sha256") not in (None, inspection.fingerprint):
        raise ImportCommandError("SOURCE_FINGERPRINT_MISMATCH", "Recipe belongs to another source revision.")
    if recipe.get("source_format") != inspection.source_format:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe source format differs from inspected source.")
    if recipe.get("ownership_mode") not in VALID_OWNERSHIP_MODES:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe ownership mode must be explicit.")
    sections = recipe.get("sections")
    decisions = recipe.get("global_decisions")
    if not isinstance(sections, list) or not sections or not isinstance(decisions, dict):
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe requires sections and global decisions.")
    normalized_sections: list[dict[str, Any]] = []
    iron_found = False
    for section in sections:
        if not isinstance(section, dict):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe section must be an object.")
        sheet = _sheet(inspection, str(section.get("sheet_name", "")))
        header_row = section.get("header_row")
        if not isinstance(header_row, int) or header_row < 1 or header_row > len(sheet.rows):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe header row is outside the inspected sheet.")
        header = sheet.rows[header_row - 1]
        seen_columns: set[int] = set()
        mappings = section.get("mappings")
        if not isinstance(mappings, list) or not mappings:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe section has no mappings.")
        for mapping in mappings:
            column = _mapping_value(mapping, "source_column_index")
            role = _mapping_value(mapping, "target_role")
            if not isinstance(column, int) or column < 0 or column in seen_columns:
                raise ImportCommandError("DUPLICATE_MAPPING", "A source column can be mapped only once per block.")
            seen_columns.add(column)
            source_header = _mapping_value(mapping, "source_header")
            observed = header[column] if column < len(header) else None
            if observed != source_header:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source header differs from recipe.", {"expected": source_header, "observed": observed})
            if role not in ROLE_SEMANTICS:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe mapping role is unknown.", {"role": role})
            semantics = _mapping_value(mapping, "measurement_semantics")
            if semantics not in ROLE_SEMANTICS[role]:
                raise ImportCommandError(
                    "RECIPE_SCHEMA_INCOMPATIBLE",
                    "Mapping semantics do not match its role.",
                    {"target_role": role, "measurement_semantics": semantics},
                )
            if role == "measurement":
                unit = _mapping_value(mapping, "unit")
                if unit not in VALID_UNITS:
                    raise ImportCommandError("UNKNOWN_UNIT", "Every mapped measurement needs an explicit recognized unit.", {"header": source_header, "unit": unit})
                if not isinstance(mapping.get("canonical_field"), str) or not mapping["canonical_field"]:
                    raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Every imported measurement needs a canonical field.")
                field = _header_token(str(mapping.get("canonical_field") or source_header))
                iron_found = iron_found or field in IRON_FIELDS
        normalized_sections.append({"sheet_name": sheet.name, "block_id": section.get("block_id"), "header_row": header_row, "mapping_count": len(mappings)})
    if iron_found and decisions.get("fe_semantics") in (None, "not_present"):
        raise ImportCommandError("IRON_SEMANTICS_REQUIRED", "Mapped iron measurements need an explicit Fe decision.")
    if decisions.get("censored_value_policy") != "preserve_original_token_and_detection_limit":
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "M1.1 must preserve censored tokens and limits.")
    if decisions.get("duplicate_policy") not in {"review_each", "keep_all", "skip_exact_after_review"}:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Duplicate policy is required.")
    if decisions.get("unit_policy") != "explicit_per_measurement_column":
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Each measurement column must declare its unit.")
    declared_semantic_fingerprint = recipe.get("semantic_fingerprint")
    calculated_semantic_fingerprint = semantic_fingerprint(recipe)
    if declared_semantic_fingerprint != calculated_semantic_fingerprint:
        raise ImportCommandError(
            "RECIPE_SCHEMA_INCOMPATIBLE",
            "Recipe semantic fingerprint does not match its current decisions.",
            {"expected": calculated_semantic_fingerprint, "observed": declared_semantic_fingerprint},
        )
    return {"source_fingerprint": inspection.fingerprint, "sections": normalized_sections, "warnings": []}


def _qualifier(token: str | None) -> tuple[str | None, float | None]:
    if token is None or token == "":
        return "missing", None
    match = re.fullmatch(r"\s*<\s*([0-9]+(?:[.,][0-9]+)?)\s*", token)
    if match:
        return "below_detection_limit", float(match.group(1).replace(",", "."))
    return None, None


def _preview_id(fingerprint: str, sheet_name: str, row_number: int, block_id: str) -> str:
    raw = f"{fingerprint}:{sheet_name}:{row_number}:{block_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def create_import_plan(inspection: SourceInspection, recipe: dict[str, Any]) -> dict[str, Any]:
    validation = validate_recipe(inspection, recipe)
    entries: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    duplicate_keys: dict[tuple[str, ...], list[str]] = {}
    for section in recipe["sections"]:
        sheet = _sheet(inspection, section["sheet_name"])
        start = int(section["data_start_row"])
        end = section.get("data_end_row") or len(sheet.rows)
        if start < 1 or end < start or end > len(sheet.rows):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe data range is outside the inspected sheet.")
        mappings = section["mappings"]
        identity_mappings = [item for item in mappings if item["target_role"] == "identity"]
        for row_number in range(start, end + 1):
            row = sheet.rows[row_number - 1]
            tokens = {item["canonical_field"] or item["source_header"]: row[item["source_column_index"]] if item["source_column_index"] < len(row) else None for item in mappings}
            if not any(value not in (None, "") for value in tokens.values()):
                continue
            measurements = []
            for mapping in mappings:
                if mapping["target_role"] != "measurement":
                    continue
                token = tokens[mapping["canonical_field"] or mapping["source_header"]]
                qualifier, detection_limit = _qualifier(token)
                measurements.append({
                    "field": mapping["canonical_field"],
                    "unit": mapping["unit"],
                    "raw_token": token,
                    "qualifier": qualifier,
                    "detection_limit": detection_limit,
                    "source_header": mapping["source_header"],
                    "source_column_index": mapping["source_column_index"],
                })
            preview_id = _preview_id(inspection.fingerprint, sheet.name, row_number, section["block_id"])
            identity = tuple(str(tokens[item["canonical_field"] or item["source_header"]] or "") for item in identity_mappings)
            duplicate_keys.setdefault(identity, []).append(preview_id)
            entries.append({"preview_id": preview_id, "sheet_name": sheet.name, "row_number": row_number, "block_id": section["block_id"], "identity": identity, "measurements": measurements})
    duplicates = [ids for key, ids in duplicate_keys.items() if key and any(key) and len(ids) > 1]
    if duplicates:
        warnings.append({"code": "DUPLICATE_CANDIDATES", "preview_ids": duplicates, "policy": recipe["global_decisions"]["duplicate_policy"]})
    return {"source_fingerprint": inspection.fingerprint, "validation": validation, "planned_records": entries, "summary": {"planned_analysis_count": len(entries), "duplicate_candidate_groups": len(duplicates)}, "warnings": warnings}


def _run(operation: Any) -> dict[str, Any]:
    try:
        return {"result": operation()}
    except ImportCommandError as exc:
        return exc.projection()


def run_import_inspect_source(source_path: str | Path) -> dict[str, Any]:
    return _run(lambda: inspect_source(source_path).projection())


def run_import_recipe_validate(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    return _run(lambda: validate_recipe(inspect_source(source_path), recipe))


def run_import_plan_create(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    return _run(lambda: create_import_plan(inspect_source(source_path), recipe))
