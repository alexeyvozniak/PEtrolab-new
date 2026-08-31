"""Read-only analytical import inspection, validation and planning.

Workbook semantics stay in Python. Logical blocks may be row- or column-oriented,
but source files are never rewritten and planned values retain physical cell
coordinates.
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
    "analysis", "sample", "point", "spot", "mineral", "generation",
    "анализ", "образец", "точка", "минерал", "генерация", "спектр",
    "sio2", "mgo", "tio2", "al2o3", "feo", "feot", "fe2o3", "cao", "na2o", "k2o", "f",
    "li", "rb", "ba", "sr", "la", "ce", "nd", "u", "th",
}
IRON_FIELDS = {"feo", "feot", "fe2o3", "fe2o3t", "fetotal"}
VALID_UNITS = {"wt.%", "mass%", "at.%", "ppm", "ppb", "apfu", "mol%", "ratio"}
VALID_ORIENTATIONS = {"rows_are_analyses", "columns_are_analyses"}
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
        return {
            "name": self.name,
            "used_range": {
                "rows": len(self.rows),
                "columns": max((len(row) for row in self.rows), default=0),
            },
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
        blocks = [
            {"sheet_name": sheet.name, **block}
            for sheet in self.sheets
            for block in candidate_blocks(sheet)
        ]
        return {
            "source_path": self.path.name,
            "source_format": self.source_format,
            "source_fingerprint": self.fingerprint,
            "sheets": [sheet.projection() for sheet in self.sheets],
            "candidate_blocks": blocks,
            "warnings": [*self.warnings, *(warning for sheet in self.sheets for warning in sheet.warnings)],
        }


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_fingerprint(recipe: dict[str, Any]) -> str:
    projection = {
        "source_format": recipe.get("source_format"),
        "ownership_mode": recipe.get("ownership_mode"),
        "sections": recipe.get("sections"),
        "global_decisions": recipe.get("global_decisions"),
    }
    raw = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        return 0
    result = 0
    for letter in match.group(1):
        result = result * 26 + ord(letter) - ord("A") + 1
    return result - 1


def _column_letters(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _header_token(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("₂", "2").replace("₃", "3")
    return re.sub(r"[^a-zа-яё0-9]", "", value)


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    token = str(value).strip().replace("\u00a0", "").replace(",", ".")
    if not token or token.startswith("<"):
        return None
    try:
        return float(token.rstrip("%"))
    except ValueError:
        return None


def _header_signature(row: tuple[str | None, ...] | list[str | None]) -> tuple[str, ...]:
    return tuple(_header_token(value) for value in row if value not in (None, ""))


def _looks_like_generic_header(rows: list[list[str | None]], index: int) -> bool:
    """Detect unfamiliar tables without turning ordinary data rows into headers.

    Generic fallback is deliberately strict: all populated header cells must be
    textual labels, then at least two following non-empty rows must be numeric in
    at least two of those columns. Known geochemical/identity headers use the
    separate vocabulary path and do not need this fallback.
    """
    row = rows[index]
    populated = [(column, value) for column, value in enumerate(row) if value not in (None, "")]
    if len(populated) < 3:
        return False
    if any(_number(value) is not None for _, value in populated):
        return False
    if any(len(str(value).strip()) > 120 for _, value in populated):
        return False

    following: list[list[str | None]] = []
    for candidate in rows[index + 1:index + 8]:
        if any(value not in (None, "") for value in candidate):
            following.append(candidate)
        if len(following) == 3:
            break
    if len(following) < 2:
        return False

    numeric_rows = 0
    threshold = min(3, max(2, len(populated) // 2))
    for candidate in following:
        numeric = sum(
            1 for column, _ in populated
            if column < len(candidate) and _number(candidate[column]) is not None
        )
        if numeric >= threshold:
            numeric_rows += 1
    return numeric_rows >= 2


def _header_candidates(rows: list[list[str | None]]) -> tuple[int, ...]:
    result: list[int] = []
    for index, row in enumerate(rows):
        matches = sum(
            any(_header_token(value).startswith(token) for token in KNOWN_HEADER_TOKENS)
            for value in row if value
        )
        if matches >= 2 or _looks_like_generic_header(rows, index):
            result.append(index + 1)
    return tuple(result)


def _unit_from_text(text: str) -> str | None:
    lowered = text.lower().replace("\u00a0", " ")
    compact = re.sub(r"\s+", "", lowered)
    if "ppb" in compact:
        return "ppb"
    if "ppm" in compact or "мкг/г" in compact:
        return "ppm"
    if "apfu" in compact or "а.е.ф." in lowered:
        return "apfu"
    if any(marker in compact for marker in ("at.%", "at%", "atomic%", "атом.%", "атом%", "ат.%", "ат%")):
        return "at.%"
    if any(marker in compact for marker in ("mol%", "мол.%", "мол%")):
        return "mol%"
    if any(marker in compact for marker in ("wt.%", "wt%", "mass%", "мас.%", "мас%", "weight%", "вес%")):
        return "wt.%"
    return None


def _unit_context(rows: tuple[tuple[str | None, ...], ...], header_row: int) -> dict[str, Any] | None:
    for number in range(header_row, max(0, header_row - 6), -1):
        text = " | ".join(str(value).strip() for value in rows[number - 1] if value not in (None, ""))
        if not text:
            continue
        unit = _unit_from_text(text)
        if unit:
            return {"unit": unit, "row_number": number, "text": text[:240]}
    return None


def _next_nonempty_row(rows: tuple[tuple[str | None, ...], ...], start: int, stop: int) -> int | None:
    for row_number in range(start, min(stop, len(rows) + 1)):
        if any(value not in (None, "") for value in rows[row_number - 1]):
            return row_number
    return None


def _last_nonempty_row(rows: tuple[tuple[str | None, ...], ...], start: int, end: int) -> int:
    for row_number in range(min(end, len(rows)), start - 1, -1):
        if any(value not in (None, "") for value in rows[row_number - 1]):
            return row_number
    return start


def candidate_blocks(sheet: SheetInspection) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    headers = list(sheet.header_rows)
    for position, header_row in enumerate(headers):
        next_header = headers[position + 1] if position + 1 < len(headers) else len(sheet.rows) + 1
        data_start = _next_nonempty_row(sheet.rows, header_row + 1, next_header)
        if data_start is None:
            continue
        data_end = _last_nonempty_row(sheet.rows, data_start, next_header - 1)
        blocks.append({
            "block_id": f"{sheet.name}:{header_row}",
            "header_row": header_row,
            "data_start_row": data_start,
            "data_end_row": data_end,
            "orientation": "rows_are_analyses",
            "unit_context": _unit_context(sheet.rows, header_row),
        })
    return blocks


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
        targets = {relation.attrib["Id"]: relation.attrib["Target"].lstrip("/") for relation in rels.findall("pr:Relationship", NS)}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(item.itertext()) for item in root.findall("x:si", NS)]
        inspections: list[SheetInspection] = []
        for sheet in workbook.findall("x:sheets/x:sheet", NS):
            relation_id = sheet.attrib.get(f"{{{XLSX_REL}}}id")
            target = targets.get(relation_id or "")
            if not target:
                raise ImportCommandError("SOURCE_UNREADABLE", "Worksheet relationship is missing.")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            try:
                root = ET.fromstring(archive.read(sheet_path))
            except (KeyError, ET.ParseError) as exc:
                raise ImportCommandError("SOURCE_UNREADABLE", "Worksheet XML is invalid.") from exc
            rows: list[list[str | None]] = []
            warnings: list[dict[str, Any]] = []
            hidden_rows: list[int] = []
            uncached_formula_cells: list[str] = []
            merged_ranges = [item.attrib.get("ref") for item in root.findall("x:mergeCells/x:mergeCell", NS)]
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
                    value = value_node.text if value_node is not None else None
                    cell_type = cell.attrib.get("t")
                    if cell_type == "inlineStr":
                        inline = cell.find("x:is", NS)
                        value = "".join(inline.itertext()) if inline is not None else None
                    elif cell_type == "s" and value is not None:
                        value = shared[int(value)]
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
    if suffix == ".xls":
        with path.open("rb") as source:
            signature = source.read(8)
        if signature == OLE_COMPOUND_SIGNATURE:
            raise ImportCommandError(
                "LEGACY_XLS_REQUIRES_CONVERSION",
                "Legacy Excel .xls is detected, but native BIFF import is not enabled yet. Keep the original and save a copy as .xlsx for this build.",
                {"suffix": suffix},
            )
    readers = {
        ".xlsx": ("xlsx", _read_xlsx),
        ".csv": ("csv", lambda file: _read_delimited(file, ",")),
        ".tsv": ("tsv", lambda file: _read_delimited(file, "\t")),
    }
    if suffix not in readers:
        raise ImportCommandError("SOURCE_UNREADABLE", "Only XLSX, CSV and TSV are supported by this import build.", {"suffix": suffix})
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


def preview_source_window(source_path: str | Path, sheet_name: str, start_row: int, row_count: int = 12, start_column: int = 0, column_count: int = 24) -> dict[str, Any]:
    sheet = _sheet(inspect_source(source_path), sheet_name)
    start_row = max(1, int(start_row))
    row_count = max(1, min(int(row_count), 60))
    start_column = max(0, int(start_column))
    column_count = max(1, min(int(column_count), 80))
    end_row = min(len(sheet.rows), start_row + row_count - 1)
    max_columns = max((len(row) for row in sheet.rows), default=0)
    rows = []
    for row_number in range(start_row, end_row + 1):
        row = sheet.rows[row_number - 1]
        rows.append({
            "row_number": row_number,
            "values": [row[column] if column < len(row) else None for column in range(start_column, start_column + column_count)],
        })
    end_column = min(max_columns, start_column + column_count)
    return {
        "sheet_name": sheet.name,
        "start_row": start_row,
        "end_row": end_row,
        "start_column": start_column,
        "end_column": end_column,
        "column_labels": [_column_letters(index) for index in range(start_column, end_column)],
        "rows": rows,
        "used_range": {"rows": len(sheet.rows), "columns": max_columns},
    }


def _mapping_axis(mapping: dict[str, Any]) -> str:
    axis = mapping.get("source_axis")
    if axis in {"column", "row"}:
        return str(axis)
    return "column" if "source_column_index" in mapping else "row"


def _mapping_index(mapping: dict[str, Any]) -> int:
    axis = _mapping_axis(mapping)
    key = "source_column_index" if axis == "column" else "source_row_index"
    index = mapping.get(key)
    if not isinstance(index, int) or index < 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source mapping index is invalid.", {"axis": axis})
    return index


def _observed_header(sheet: SheetInspection, section: dict[str, Any], mapping: dict[str, Any]) -> str | None:
    index = _mapping_index(mapping)
    if section.get("orientation", "rows_are_analyses") == "rows_are_analyses":
        row = sheet.rows[int(section["header_row"]) - 1]
        return row[index] if index < len(row) else None
    header_column = int(section.get("header_column", 1)) - 1
    return sheet.rows[index][header_column] if index < len(sheet.rows) and header_column < len(sheet.rows[index]) else None


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
    enabled_count = 0
    for section in sections:
        if not isinstance(section, dict):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe section must be an object.")
        sheet = _sheet(inspection, str(section.get("sheet_name", "")))
        enabled = section.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Block enabled state must be boolean.")
        orientation = section.get("orientation", "rows_are_analyses")
        if orientation not in VALID_ORIENTATIONS:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Unknown block orientation.", {"orientation": orientation})
        if enabled:
            enabled_count += 1

        header_row = section.get("header_row")
        if not isinstance(header_row, int) or header_row < 1 or header_row > len(sheet.rows):
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe header row is outside the inspected sheet.")
        if orientation == "rows_are_analyses":
            start = section.get("data_start_row")
            end = section.get("data_end_row")
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > len(sheet.rows):
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe data rows are outside the inspected sheet.")
        else:
            max_columns = max((len(row) for row in sheet.rows), default=0)
            header_column = section.get("header_column", 1)
            start_column = section.get("data_start_column", 2)
            end_column = section.get("data_end_column", max_columns)
            field_start = section.get("data_start_row")
            field_end = section.get("data_end_row")
            if not isinstance(header_column, int) or header_column < 1 or header_column > max_columns:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Transposed block header column is outside the sheet.")
            if not isinstance(start_column, int) or not isinstance(end_column, int) or start_column < 1 or end_column < start_column or end_column > max_columns:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Transposed block analysis columns are outside the sheet.")
            if not isinstance(field_start, int) or not isinstance(field_end, int) or field_start < 1 or field_end < field_start or field_end > len(sheet.rows):
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Transposed block field rows are outside the sheet.")

        mappings = section.get("mappings")
        if not isinstance(mappings, list) or not mappings:
            raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe section has no mappings.")
        seen: set[tuple[str, int]] = set()
        for mapping in mappings:
            axis = _mapping_axis(mapping)
            index = _mapping_index(mapping)
            expected_axis = "column" if orientation == "rows_are_analyses" else "row"
            if axis != expected_axis:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping axis does not match block orientation.")
            if (axis, index) in seen:
                raise ImportCommandError("DUPLICATE_MAPPING", "A source field can be mapped only once per block.")
            seen.add((axis, index))
            source_header = mapping.get("source_header")
            observed = _observed_header(sheet, section, mapping)
            if observed != source_header:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Source header differs from recipe.", {"expected": source_header, "observed": observed})
            role = mapping.get("target_role")
            if role not in ROLE_SEMANTICS:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe mapping role is unknown.", {"role": role})
            semantics = mapping.get("measurement_semantics")
            if semantics not in ROLE_SEMANTICS[role]:
                raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Mapping semantics do not match its role.", {"target_role": role, "measurement_semantics": semantics})
            if enabled and role == "measurement":
                unit = mapping.get("unit")
                if unit not in VALID_UNITS:
                    raise ImportCommandError("UNKNOWN_UNIT", "Every mapped measurement needs an explicit recognized unit.", {"header": source_header, "unit": unit})
                if not isinstance(mapping.get("canonical_field"), str) or not mapping["canonical_field"]:
                    raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Every imported measurement needs a canonical field.")
                iron_found = iron_found or _header_token(mapping.get("canonical_field")) in IRON_FIELDS

        normalized_sections.append({
            "sheet_name": sheet.name,
            "block_id": section.get("block_id"),
            "enabled": enabled,
            "orientation": orientation,
            "header_row": header_row,
            "mapping_count": len(mappings),
        })

    if enabled_count == 0:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "At least one logical block must be enabled.")
    if iron_found and decisions.get("fe_semantics") in (None, "not_present"):
        raise ImportCommandError("IRON_SEMANTICS_REQUIRED", "Mapped iron measurements need an explicit Fe decision.")
    if decisions.get("censored_value_policy") != "preserve_original_token_and_detection_limit":
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Import must preserve censored tokens and limits.")
    if decisions.get("duplicate_policy") not in {"review_each", "keep_all", "skip_exact_after_review"}:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Duplicate policy is required.")
    if decisions.get("unit_policy") != "explicit_per_measurement_column":
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Each measurement field must declare its unit.")
    calculated = semantic_fingerprint(recipe)
    if recipe.get("semantic_fingerprint") != calculated:
        raise ImportCommandError("RECIPE_SCHEMA_INCOMPATIBLE", "Recipe semantic fingerprint does not match its current decisions.", {"expected": calculated, "observed": recipe.get("semantic_fingerprint")})
    return {"source_fingerprint": inspection.fingerprint, "sections": normalized_sections, "warnings": []}


def _qualifier(token: str | None) -> tuple[str | None, float | None]:
    if token is None or token == "":
        return "missing", None
    match = re.fullmatch(r"\s*<\s*([0-9]+(?:[.,][0-9]+)?)\s*", token)
    if match:
        return "below_detection_limit", float(match.group(1).replace(",", "."))
    return None, None


def _preview_id(fingerprint: str, sheet_name: str, primary: int, block_id: str, orientation: str) -> str:
    raw = f"{fingerprint}:{sheet_name}:{orientation}:{primary}:{block_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _row_value(row: tuple[str | None, ...], index: int) -> str | None:
    return row[index] if index < len(row) else None


def _is_repeated_header(sheet: SheetInspection, section: dict[str, Any], row_number: int) -> bool:
    header = sheet.rows[int(section["header_row"]) - 1]
    row = sheet.rows[row_number - 1]
    return bool(_header_signature(header)) and _header_signature(row) == _header_signature(header)


def _measurement(mapping: dict[str, Any], token: str | None, physical_row: int, physical_column: int) -> dict[str, Any]:
    qualifier, detection_limit = _qualifier(token)
    return {
        "field": mapping["canonical_field"],
        "unit": mapping["unit"],
        "raw_token": token,
        "qualifier": qualifier,
        "detection_limit": detection_limit,
        "source_header": mapping["source_header"],
        "source_column_index": _mapping_index(mapping),
        "physical_source_row_number": physical_row,
        "physical_source_column_index": physical_column,
        "source_cell": f"{_column_letters(physical_column)}{physical_row}",
        "measurement_set": mapping.get("measurement_set"),
        "method": mapping.get("method"),
    }


def _plan_rows(inspection: SourceInspection, sheet: SheetInspection, section: dict[str, Any], duplicate_keys: dict[tuple[str, ...], list[str]]) -> list[dict[str, Any]]:
    mappings = section["mappings"]
    identities = [item for item in mappings if item["target_role"] == "identity"]
    result: list[dict[str, Any]] = []
    for row_number in range(int(section["data_start_row"]), int(section["data_end_row"]) + 1):
        if _is_repeated_header(sheet, section, row_number):
            continue
        row = sheet.rows[row_number - 1]
        relevant = [_row_value(row, _mapping_index(item)) for item in mappings if item["target_role"] != "ignore"]
        if not any(value not in (None, "") for value in relevant):
            continue
        identity = tuple(str(_row_value(row, _mapping_index(item)) or "") for item in identities)
        measurements = [
            _measurement(item, _row_value(row, _mapping_index(item)), row_number, _mapping_index(item))
            for item in mappings if item["target_role"] == "measurement"
        ]
        preview_id = _preview_id(inspection.fingerprint, sheet.name, row_number, section["block_id"], "rows_are_analyses")
        duplicate_keys.setdefault(identity, []).append(preview_id)
        result.append({
            "preview_id": preview_id,
            "sheet_name": sheet.name,
            "row_number": row_number,
            "source_column_number": None,
            "orientation": "rows_are_analyses",
            "block_id": section["block_id"],
            "identity": identity,
            "measurements": measurements,
        })
    return result


def _plan_columns(inspection: SourceInspection, sheet: SheetInspection, section: dict[str, Any], duplicate_keys: dict[tuple[str, ...], list[str]]) -> list[dict[str, Any]]:
    mappings = section["mappings"]
    header_row = int(section["header_row"])
    result: list[dict[str, Any]] = []
    for column_number in range(int(section["data_start_column"]), int(section["data_end_column"]) + 1):
        column_index = column_number - 1
        axis_value = _row_value(sheet.rows[header_row - 1], column_index)
        values = [_row_value(sheet.rows[_mapping_index(item)], column_index) for item in mappings]
        if axis_value in (None, "") and not any(value not in (None, "") for value in values):
            continue
        identity_values: list[str] = []
        if section.get("analysis_axis_role", "Analysis") != "Ignore":
            identity_values.append(str(axis_value or ""))
        identity_values.extend(
            str(_row_value(sheet.rows[_mapping_index(item)], column_index) or "")
            for item in mappings if item["target_role"] == "identity"
        )
        identity = tuple(identity_values)
        measurements = [
            _measurement(item, _row_value(sheet.rows[_mapping_index(item)], column_index), _mapping_index(item) + 1, column_index)
            for item in mappings if item["target_role"] == "measurement"
        ]
        preview_id = _preview_id(inspection.fingerprint, sheet.name, column_number, section["block_id"], "columns_are_analyses")
        duplicate_keys.setdefault(identity, []).append(preview_id)
        result.append({
            "preview_id": preview_id,
            "sheet_name": sheet.name,
            "row_number": header_row,
            "source_column_number": column_number,
            "orientation": "columns_are_analyses",
            "block_id": section["block_id"],
            "identity": identity,
            "identity_axis_field": section.get("analysis_axis_field", "Analysis"),
            "measurements": measurements,
        })
    return result


def create_import_plan(inspection: SourceInspection, recipe: dict[str, Any]) -> dict[str, Any]:
    validation = validate_recipe(inspection, recipe)
    entries: list[dict[str, Any]] = []
    duplicate_keys: dict[tuple[str, ...], list[str]] = {}
    block_summaries: list[dict[str, Any]] = []
    for section in recipe["sections"]:
        if not section.get("enabled", True):
            block_summaries.append({"block_id": section["block_id"], "enabled": False, "analysis_count": 0, "measurement_count": 0})
            continue
        sheet = _sheet(inspection, section["sheet_name"])
        if section.get("orientation", "rows_are_analyses") == "rows_are_analyses":
            block_entries = _plan_rows(inspection, sheet, section, duplicate_keys)
        else:
            block_entries = _plan_columns(inspection, sheet, section, duplicate_keys)
        entries.extend(block_entries)
        block_summaries.append({
            "block_id": section["block_id"],
            "enabled": True,
            "analysis_count": len(block_entries),
            "measurement_count": sum(len(record["measurements"]) for record in block_entries),
        })
    duplicates = [ids for key, ids in duplicate_keys.items() if key and any(key) and len(ids) > 1]
    warnings = []
    if duplicates:
        warnings.append({"code": "DUPLICATE_CANDIDATES", "preview_ids": duplicates, "policy": recipe["global_decisions"]["duplicate_policy"]})
    return {
        "source_fingerprint": inspection.fingerprint,
        "validation": validation,
        "planned_records": entries,
        "summary": {
            "planned_analysis_count": len(entries),
            "planned_measurement_count": sum(len(record["measurements"]) for record in entries),
            "duplicate_candidate_groups": len(duplicates),
            "enabled_block_count": sum(1 for section in recipe["sections"] if section.get("enabled", True)),
        },
        "block_summaries": block_summaries,
        "warnings": warnings,
    }


def _run(operation: Any) -> dict[str, Any]:
    try:
        return {"result": operation()}
    except ImportCommandError as exc:
        return exc.projection()


def run_import_inspect_source(source_path: str | Path) -> dict[str, Any]:
    return _run(lambda: inspect_source(source_path).projection())


def run_import_preview_window(source_path: str | Path, sheet_name: str, start_row: int, row_count: int = 12, start_column: int = 0, column_count: int = 24) -> dict[str, Any]:
    return _run(lambda: preview_source_window(source_path, sheet_name, start_row, row_count, start_column, column_count))


def run_import_recipe_validate(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    return _run(lambda: validate_recipe(inspect_source(source_path), recipe))


def run_import_plan_create(source_path: str | Path, recipe: dict[str, Any]) -> dict[str, Any]:
    return _run(lambda: create_import_plan(inspect_source(source_path), recipe))
