"""Deterministic structural recognition for import review.

This module proposes roles/fields from source headers. It never persists data and
never guesses an unstated unit from chemistry alone.
"""

from __future__ import annotations

import re
from typing import Any


IDENTITY_FIELDS = {
    "analysis": "Analysis",
    "анализ": "Analysis",
    "spectrum": "Analysis",
    "спектр": "Analysis",
    "sample": "Sample",
    "sampleid": "Sample",
    "образец": "Sample",
    "образецid": "Sample",
    "point": "Point",
    "spot": "Point",
    "точка": "Point",
    "analyticalno": "Analysis",
    "аналитическийномер": "Analysis",
}

METADATA_FIELDS = {
    "mineral": "Mineral",
    "минерал": "Mineral",
    "generation": "Generation",
    "генерация": "Generation",
    "zone": "Generation",
    "зона": "Generation",
}

MEASUREMENT_FIELDS = {
    "sio2": "SiO2", "tio2": "TiO2", "al2o3": "Al2O3", "feo": "FeO", "feot": "FeOt",
    "fe2o3": "Fe2O3", "fe2o3t": "Fe2O3t", "mno": "MnO", "mgo": "MgO", "cao": "CaO",
    "na2o": "Na2O", "k2o": "K2O", "p2o5": "P2O5", "cr2o3": "Cr2O3", "nio": "NiO",
    "f": "F", "cl": "Cl", "o": "O", "na": "Na", "mg": "Mg", "al": "Al", "si": "Si", "p": "P", "s": "S", "k": "K", "ca": "Ca", "ti": "Ti", "mn": "Mn", "fe": "Fe",
    "li": "Li", "rb": "Rb", "ba": "Ba", "sr": "Sr", "ni": "Ni", "cr": "Cr", "co": "Co",
    "sc": "Sc", "v": "V", "cu": "Cu", "zn": "Zn", "ga": "Ga", "y": "Y", "zr": "Zr", "nb": "Nb",
    "mo": "Mo", "cs": "Cs", "la": "La", "ce": "Ce", "pr": "Pr", "nd": "Nd", "sm": "Sm", "eu": "Eu",
    "gd": "Gd", "tb": "Tb", "dy": "Dy", "ho": "Ho", "er": "Er", "tm": "Tm", "yb": "Yb", "lu": "Lu",
    "hf": "Hf", "ta": "Ta", "w": "W", "pb": "Pb", "th": "Th", "u": "U",
}

IRON_FIELDS = {"FeO", "FeOt", "Fe2O3", "Fe2O3t", "Fe"}
VALID_UNITS = {"wt.%", "ppm", "ppb", "apfu", "mol%", "at.%", "ratio"}


def normalized(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().replace("₂", "2").replace("₃", "3")
    return "".join(character for character in value if character.isalnum())


def field_token(header: str) -> str:
    text = header.strip()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.split(r"\s+", text, maxsplit=1)[0]
    return normalized(text)


def unit_from_header(header: str) -> str | None:
    lowered = header.lower().replace("\u00a0", " ")
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


def mapping_for_header(
    source_index: int,
    header: str,
    *,
    source_axis: str = "column",
    context_unit: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized_header = normalized(header)
    token = field_token(header)
    identity = IDENTITY_FIELDS.get(normalized_header) or IDENTITY_FIELDS.get(token)
    index_key = "source_column_index" if source_axis == "column" else "source_row_index"
    base = {"source_axis": source_axis, index_key: source_index, "source_header": header}

    if identity:
        return ({
            **base,
            "target_role": "identity",
            "canonical_field": identity,
            "unit": None,
            "measurement_semantics": "identity",
        }, None)

    metadata = METADATA_FIELDS.get(normalized_header) or METADATA_FIELDS.get(token)
    if metadata:
        return ({
            **base,
            "target_role": "metadata",
            "canonical_field": metadata,
            "unit": None,
            "measurement_semantics": "metadata",
        }, None)

    measurement = MEASUREMENT_FIELDS.get(token)
    if measurement:
        unit = unit_from_header(header) or context_unit
        if unit:
            return ({
                **base,
                "target_role": "measurement",
                "canonical_field": measurement,
                "unit": unit,
                "measurement_semantics": "measured",
            }, None)
        return ({
            **base,
            "target_role": "ignore",
            "canonical_field": header,
            "unit": None,
            "measurement_semantics": "ignored",
        }, {
            "code": "UNIT_REQUIRES_REVIEW",
            "source_header": header,
            index_key: source_index,
            "source_axis": source_axis,
            "canonical_field": measurement,
        })

    return ({
        **base,
        "target_role": "ignore",
        "canonical_field": header,
        "unit": None,
        "measurement_semantics": "ignored",
    }, None)


def mappings_for_row_header(header: tuple[str | None, ...], context_unit: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for column, raw_header in enumerate(header):
        if raw_header in (None, ""):
            continue
        mapping, warning = mapping_for_header(column, str(raw_header), source_axis="column", context_unit=context_unit)
        mappings.append(mapping)
        if warning:
            warnings.append(warning)
    return mappings, warnings


def mappings_for_column_header(
    rows: tuple[tuple[str | None, ...], ...],
    header_column: int,
    field_start_row: int,
    field_end_row: int,
    context_unit: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mappings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    column_index = header_column - 1
    for row_number in range(field_start_row, field_end_row + 1):
        row = rows[row_number - 1]
        raw_header = row[column_index] if column_index < len(row) else None
        if raw_header in (None, ""):
            continue
        mapping, warning = mapping_for_header(row_number - 1, str(raw_header), source_axis="row", context_unit=context_unit)
        mappings.append(mapping)
        if warning:
            warnings.append(warning)
    return mappings, warnings
