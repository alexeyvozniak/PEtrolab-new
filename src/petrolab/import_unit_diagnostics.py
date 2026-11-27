"""Read-only numeric evidence for unresolved composition units.

Never assigns a unit or changes a recipe. A sum near 100 cannot distinguish
mass, atomic or molar percent. A small sum is not proof of APFU.
"""
from math import isfinite
from statistics import median

from .analyte_dictionary import ELEMENTS, COMPONENTS
from .import_preview import _number, value_status

# Do not add totals, LOI, water aliases, isotope ratios or derived indices.
_EXCLUDED = {"Total", "LOI", "H2O+", "H2O-"}
_ELEMENTS = set(ELEMENTS)
_OXIDES = set(COMPONENTS) - _EXCLUDED


def _family(field):
    if field in _ELEMENTS:
        return "element"
    if field in _OXIDES:
        return "oxide"
    return None


def composition_unit_hint(sheet, section):
    if not section.get("enabled", True):
        return None
    fields = []
    for mapping in section["mappings"]:
        field = (mapping.get("suggested_canonical_field") if mapping.get("target_role") == "ignore"
                 else mapping.get("canonical_field") if mapping.get("target_role") == "measurement" else None)
        family = _family(field)
        if family:
            fields.append((field, family, mapping))
    if not 4 <= len(fields) <= 64 or len({family for _, family, _ in fields}) != 1:
        return None
    # No mixing of known units, contexts, duplicates or overlapping Fe forms.
    if any(m.get("target_role") != "ignore" or m.get("review_decision") != "unresolved" or
           m.get("suggested_target") != "measurement" or m.get("unit") or m.get("header_unit") or
           m.get("adjacent_unit") for _, _, m in fields):
        return None
    names = [field for field, _, _ in fields]
    if len(set(names)) != len(names) or len({(m.get("method"), m.get("measurement_set")) for _, _, m in fields}) != 1:
        return None
    if len(set(names) & {"FeO", "FeOt", "Fe2O3", "Fe2O3t"}) > 1:
        return None
    transposed = section.get("orientation") == "columns_are_analyses"
    index_key = "source_row_index" if transposed else "source_column_index"
    indices = [mapping.get(index_key) for _, _, mapping in fields]
    if any(type(index) is not int or index < 0 for index in indices):
        return None
    start = section["data_start_column"] if transposed else section["data_start_row"]
    end = section["data_end_column"] if transposed else section["data_end_row"]
    extent = end - start + 1
    if extent < 3:
        return None
    sample = sorted({start + i * (extent - 1) // max(1, min(32, extent) - 1) for i in range(min(32, extent))})
    sums = []
    for position in sample:
        values = []
        for index in indices:
            row, col = (index, position - 1) if transposed else (position - 1, index)
            token = sheet.rows[row][col] if row < len(sheet.rows) and col < len(sheet.rows[row]) else None
            if value_status(token) != "numeric":
                break
            number = _number(token)
            if number is None or not isfinite(number) or number < 0 or number > 1e9:
                break
            values.append(number)
        if len(values) == len(indices):
            sums.append(sum(values))
    if len(sums) < 3 or len(sums) / len(sample) < .75:
        return None
    near100 = sum(95 <= value <= 105 for value in sums)
    small = sum(0 < value <= 30 for value in sums)
    if near100 / len(sums) >= .8:
        kind = "near_100"
    elif small / len(sums) >= .8 and fields[0][1] == "element":
        kind = "small_element_sum"
    else:
        return None
    return {"code": "UNIT_NUMERIC_HINT", "blocking": False, "severity": "info",
            "block_id": section["block_id"], "sheet_name": section["sheet_name"],
            "hint_kind": kind, "field_family": fields[0][1], "field_count": len(fields),
            "complete_count": len(sums), "sample_count": len(sample),
            "median_sum": round(median(sums), 4), "min_sum": round(min(sums), 4), "max_sum": round(max(sums), 4)}
