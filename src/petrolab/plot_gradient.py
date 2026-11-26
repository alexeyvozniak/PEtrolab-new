"""Read-only values for concentration-based plot coloring, independent of axes."""
from collections import Counter, defaultdict
from contextlib import closing
from hashlib import sha256
import json

from .desktop_workflow import _measurement_numeric_value
from .import_apply import open_project
from .import_preview import ImportCommandError
from .plot_data import _ACTIVE_ANALYSES, _ACTIVE_MEASUREMENTS, _axis_key, _selection


def gradient_payload(axis, analysis_ids, rows):
    """Keep exact provenance; do not impute censored/ambiguous observations."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["analysis_id"]].append(row)
    forms = {row["reported_fe_form"] for records in grouped.values() for row in records}
    if len(forms) > 1:
        raise ImportCommandError("PLOT_GRADIENT_IRON_FORM", "Поле содержит разные формы представления железа. Выберите однозначное поле.")
    counts = Counter()
    entries = []
    numeric = []
    for analysis_id in sorted(analysis_ids):
        records = grouped.get(analysis_id, [])
        value = _measurement_numeric_value(records[0]) if len(records) == 1 else None
        if not records:
            status = "missing"
        elif len(records) > 1:
            status = "duplicate"
        elif value is None:
            status = "censored" if records[0]["qualifier"] else "excluded"
        else:
            status = "numeric"
            numeric.append(value)
        counts[status] += 1
        entries.append({"analysis_id": analysis_id, "status": status, "value": value,
                        "measurements": [{key: row[key] for key in ("measurement_id", "raw_token", "qualifier",
                            "value_status", "reported_fe_form")} for row in records]})
    payload = {"axis": axis, "entries": entries, "counts": {key: counts[key] for key in
               ("numeric", "missing", "duplicate", "censored", "excluded")},
               "minimum": min(numeric) if numeric else None, "maximum": max(numeric) if numeric else None}
    payload["fingerprint"] = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                              allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    return payload


def plot_gradient_values(database_path, axis, analysis_ids=None):
    key = _axis_key(axis)
    parameters = _selection(analysis_ids)
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        ids = [row[0] for row in connection.execute(
            f"SELECT a.analysis_id {_ACTIVE_ANALYSES} ORDER BY a.analysis_id LIMIT 50001", parameters)]
        if len(ids) > 50000:
            raise ImportCommandError("PLOT_GRADIENT_SCOPE_LIMIT", "Для градиента выберите не более 50 000 анализов.")
        if analysis_ids is not None and len(ids) != len(analysis_ids):
            raise ImportCommandError("PLOT_GRADIENT_SCOPE_CHANGED", "Часть входных анализов недоступна.")
        rows = connection.execute(f"""
            SELECT a.analysis_id, m.measurement_id, m.raw_token, m.qualifier, m.value_status, m.reported_fe_form
            {_ACTIVE_MEASUREMENTS}
            AND m.canonical_field = ? AND m.unit = ? AND m.measurement_set IS ? AND m.method IS ?
            ORDER BY a.analysis_id, m.rowid
        """, (*parameters, *key))
        return gradient_payload(axis, ids, rows)
