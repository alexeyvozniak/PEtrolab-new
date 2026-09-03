"""Deterministic structural recognition for import review.

This module proposes roles/fields from source headers. It never persists data and
never guesses an unstated unit from chemistry alone. Automatic recognition may
suggest Ignore, but populated physical source fields remain reviewable.
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
    "образца": "Sample",
    "образецid": "Sample",
    "point": "Point",
    "spot": "Point",
    "точка": "Point",
    "analyticalno": "Analysis",
    "аналитическийномер": "Analysis",
    "меткаспектра": "Analysis",
    "анализаepma": "Analysis",
    "анализаэпма": "Analysis",
    "epma": "Analysis",
    "epmanumber": "Analysis",
    "epmaanalysis": "Analysis",
    "epmaanalysisnumber": "Analysis",
    "epmaномер": "Analysis",
    "epmaанализа": "Analysis",
    "epmaanalyzis": "Analysis",
    "анализа": "Analysis",
    "dotno": "Point",
    "точкасims": "Point",
    "точкассимс": "Point",
    "номеробразца": "Sample",
    "образцаномер": "Sample",
}

METADATA_FIELDS = {
    "mineral": "Mineral",
    "минерал": "Mineral",
    "generation": "Generation",
    "генерация": "Generation",
    "zone": "Generation",
    "зона": "Generation",
    "порода": "Rock",
    "rock": "Rock",
    "источник": "Source",
    "source": "Source",
    "comment": "Comment",
    "commentlena": "Comment",
    "commentgalya": "Comment",
    "position": "Position",
    "photono": "Photo number",
    "sizeµm": "Size (µm)",
    "sizeum": "Size (µm)",
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
    "br": "Br", "b": "B", "as": "As", "se": "Se", "be": "Be", "bi": "Bi",
    "feot": "FeOt", "feotot": "FeOt", "feototal": "FeOt", "feotot": "FeOt",
    "total": "Total", "всего": "Total",
}

DIMENSIONLESS_FIELDS = {
    "87sr86sr0": ("87Sr/86Sr(0)", "ratio"),
    "esrt": ("εSr(t)", "epsilon"),
    "endt": ("εNd(t)", "epsilon"),
}

IRON_FIELDS = {"FeO", "FeOt", "Fe2O3", "Fe2O3t", "Fe"}
VALID_UNITS = {"wt.%", "ppm", "ppb", "apfu", "mol%", "at.%", "ratio", "epsilon"}


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
    if compact in {"атом", "атом.", "atomic"}:
        return "at.%"
    return None


def _index_key(source_axis: str) -> str:
    return "source_column_index" if source_axis == "column" else "source_row_index"


def ignored_mapping(source_index: int, *, source_axis: str, source_header: str | None) -> dict[str, Any]:
    """Return an explicit reversible Ignore mapping for a physical source field."""
    return {
        "source_axis": source_axis,
        _index_key(source_axis): source_index,
        "source_header": source_header,
        "target_role": "ignore",
        "canonical_field": source_header or "",
        "unit": None,
        "measurement_semantics": "ignored",
        "review_decision": "unresolved",
    }


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
    index_key = _index_key(source_axis)
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

    dimensionless = DIMENSIONLESS_FIELDS.get(normalized_header) or DIMENSIONLESS_FIELDS.get(token)
    if dimensionless:
        field, unit = dimensionless
        return ({
            **base,
            "target_role": "measurement",
            "canonical_field": field,
            "unit": unit,
            "measurement_semantics": "measured",
            "review_decision": "recognized",
        }, None)

    measurement = MEASUREMENT_FIELDS.get(normalized_header) or MEASUREMENT_FIELDS.get(token)
    if measurement:
        unit = unit_from_header(header) or context_unit
        if unit:
            return ({
                **base,
                "target_role": "measurement",
                "canonical_field": measurement,
                "unit": unit,
                "measurement_semantics": "measured",
                "review_decision": "recognized",
            }, None)
        ignored = ignored_mapping(source_index, source_axis=source_axis, source_header=header)
        ignored["suggested_target"] = "measurement"
        ignored["suggested_canonical_field"] = measurement
        return (ignored, {
            "code": "UNIT_REQUIRES_REVIEW",
            "source_header": header,
            index_key: source_index,
            "source_axis": source_axis,
            "canonical_field": measurement,
        })

    return (ignored_mapping(source_index, source_axis=source_axis, source_header=header), None)


def mappings_for_row_header(header: tuple[str | None, ...], context_unit: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compatibility helper for a header row only.

    New block-based code should use `mappings_for_row_block` so populated blank-
    header columns remain visible.
    """
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


def mappings_for_row_block(
    rows: tuple[tuple[str | None, ...], ...],
    header_row: int,
    data_start_row: int,
    data_end_row: int,
    context_unit: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build mappings for every populated physical column in a row-oriented block."""
    header = rows[header_row - 1]
    bounded_end = min(len(rows), data_end_row)
    max_columns = max(
        [len(header), *(len(rows[index - 1]) for index in range(data_start_row, bounded_end + 1))],
        default=0,
    )
    mappings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for column in range(max_columns):
        raw_header = header[column] if column < len(header) else None
        has_data = any(
            column < len(rows[row_number - 1]) and rows[row_number - 1][column] not in (None, "")
            for row_number in range(data_start_row, bounded_end + 1)
        )
        if raw_header in (None, "") and not has_data:
            continue
        if raw_header in (None, ""):
            mappings.append(ignored_mapping(column, source_axis="column", source_header=None))
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
    """Compatibility helper for transposed field labels only."""
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


def mappings_for_column_block(
    rows: tuple[tuple[str | None, ...], ...],
    header_column: int,
    field_start_row: int,
    field_end_row: int,
    data_start_column: int,
    data_end_column: int,
    context_unit: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build mappings for every populated physical field row in a transposed block."""
    mappings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    header_column_index = header_column - 1
    first_data_index = max(0, data_start_column - 1)
    last_data_index = max(first_data_index, data_end_column - 1)
    for row_number in range(field_start_row, min(field_end_row, len(rows)) + 1):
        row = rows[row_number - 1]
        raw_header = row[header_column_index] if header_column_index < len(row) else None
        has_data = any(
            column < len(row) and row[column] not in (None, "")
            for column in range(first_data_index, last_data_index + 1)
        )
        if raw_header in (None, "") and not has_data:
            continue
        source_index = row_number - 1
        if raw_header in (None, ""):
            mappings.append(ignored_mapping(source_index, source_axis="row", source_header=None))
            continue
        mapping, warning = mapping_for_header(source_index, str(raw_header), source_axis="row", context_unit=context_unit)
        mappings.append(mapping)
        if warning:
            warnings.append(warning)
    return mappings, warnings
