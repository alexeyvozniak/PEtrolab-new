"""Pure numeric projections of stored Measurements for scientific plots."""

from collections import defaultdict
from contextlib import closing
from hashlib import sha256
import json
from math import isfinite
import re
from uuid import UUID

from .desktop_workflow import _measurement_numeric_value
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .plot_fields import clip_to_plot_rectangle, convex_hull, normal_probability_ellipse


_ACTIVE_MEASUREMENTS = """
    FROM measurement m JOIN analysis a USING (analysis_id)
    JOIN import_batch b ON b.import_batch_id = a.import_batch_id
    JOIN source_file s ON s.source_id = a.source_id
    LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
    WHERE b.status = 'applied' AND r.import_batch_id IS NULL
      AND (? IS NULL OR a.analysis_id IN (SELECT value FROM json_each(?)))
"""
_AXIS_FIELDS = ("field", "unit", "measurement_set", "method")
_AXIS_PROJECTION = "m.canonical_field AS field, m.unit, m.measurement_set, m.method"
_ACTIVE_ANALYSES = """
    FROM analysis a JOIN import_batch b USING (import_batch_id)
    LEFT JOIN import_batch_retraction r USING (import_batch_id)
    WHERE b.status = 'applied' AND r.import_batch_id IS NULL
      AND (? IS NULL OR a.analysis_id IN (SELECT value FROM json_each(?)))
"""


def _selection(ids):
    if ids is None:
        return None, None
    if (not isinstance(ids, list) or not ids
            or not all(isinstance(item, str) and str(UUID(item)) == item for item in ids)
            or len(ids) != len(set(ids))):
        raise ValueError("analysis_ids")
    return 1, json.dumps(ids)


def plot_catalog(database_path, analysis_ids=None):
    with closing(open_project(database_path)) as connection:
        parameters = _selection(analysis_ids)
        rows = connection.execute(
            f"SELECT DISTINCT {_AXIS_PROJECTION} {_ACTIVE_MEASUREMENTS} ORDER BY field, unit, measurement_set, method",
            parameters,
        ).fetchall()
        sources = connection.execute(
            f"SELECT DISTINCT s.source_id, s.display_name AS source_name {_ACTIVE_MEASUREMENTS} ORDER BY source_name, s.source_id",
            parameters,
        ).fetchall()
        return {"axes": [dict(row) for row in rows], "sources": [dict(row) for row in sources]}


def _axis_key(axis):
    if not isinstance(axis, dict) or set(axis) != set(_AXIS_FIELDS):
        raise ValueError("axes")
    if not all(isinstance(axis[key], str) and axis[key] for key in ("field", "unit")):
        raise ValueError("axes")
    if not all(axis[key] is None or isinstance(axis[key], str) for key in ("measurement_set", "method")):
        raise ValueError("axes")
    return tuple(axis[key] for key in _AXIS_FIELDS)


def _plot_keys(kind, axes):
    if kind not in ("binary", "ternary") or not isinstance(axes, list) or len(axes) != (2 if kind == "binary" else 3):
        raise ValueError("plot")
    keys = [_axis_key(axis) for axis in axes]
    if len(set(keys)) != len(keys):
        raise ValueError("axes")
    if kind == "ternary" and (len({key[1:] for key in keys}) != 1 or keys[0][1] not in {"wt.%", "ppm", "ppb"}):
        raise ImportCommandError("PLOT_TERNARY_INCOMPATIBLE_AXES", "Для тройной диаграммы выберите компоненты в одной единице и одном аналитическом наборе.")
    return keys


def _linear_coordinates(values):
    if not values:
        return [], []
    low, high = min(values), max(values)
    if low == high:
        return [0.5] * len(values), [{"at": 0.5, "label": f"{low:.6g}"}]
    magnitude = max(abs(low), abs(high))
    minimum, maximum = low / magnitude, high / magnitude
    span = maximum - minimum
    if span == 0:
        return [(value - low) / (high - low) for value in values], [
            {"at": 0, "label": repr(low)}, {"at": 1, "label": repr(high)},
        ]
    return [(value / magnitude - minimum) / span for value in values], [
        {"at": 0, "label": f"{low:.6g}"},
        {"at": 0.5, "label": f"{low / 2 + high / 2:.6g}"},
        {"at": 1, "label": f"{high:.6g}"},
    ]


def query_plot_data(database_path, kind, axes, analysis_ids=None, hidden_analysis_ids=None, hidden_source_ids=None, layers=None):
    keys = _plot_keys(kind, axes)
    layers = _validated_layers(layers)
    parameter, selection = _selection(analysis_ids)
    if any(value is not None and not isinstance(value, list) for value in (hidden_analysis_ids, hidden_source_ids)):
        raise ValueError("plot_visibility")
    _selection(hidden_analysis_ids or None)
    _selection(hidden_source_ids or None)
    hidden_analyses = set(hidden_analysis_ids or [])
    hidden_sources = set(hidden_source_ids or [])
    fields = json.dumps([axis["field"] for axis in axes])
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        active_analyses = connection.execute(
            f"SELECT a.analysis_id, a.source_id {_ACTIVE_ANALYSES}", (parameter, selection),
        ).fetchall()
        visible = {row["analysis_id"] for row in active_analyses
                   if row["analysis_id"] not in hidden_analyses and row["source_id"] not in hidden_sources}
        rows = connection.execute(f"""
            SELECT {_AXIS_PROJECTION}, a.analysis_id, a.identity_json, s.source_id, s.display_name AS source_name,
                   m.raw_token, m.qualifier, m.value_status
            {_ACTIVE_MEASUREMENTS} AND m.canonical_field IN (SELECT value FROM json_each(?))
            ORDER BY a.analysis_id, m.rowid
        """, (parameter, selection, fields))
        observed = {}
        metadata = {}
        for row in rows:
            key = tuple(row[field] for field in _AXIS_FIELDS)
            if key not in keys:
                continue
            analysis_id = row["analysis_id"]
            if analysis_id not in visible:
                continue
            observed.setdefault(analysis_id, defaultdict(list))[key].append(_measurement_numeric_value(row))
            metadata[analysis_id] = row

    points = []
    for analysis_id, record in observed.items():
        values = [record[key][0] if len(record[key]) == 1 else None for key in keys]
        if any(value is None or not isfinite(value) for value in values):
            continue
        row = metadata[analysis_id]
        identity = " · ".join(token for token in json.loads(row["identity_json"]) if token)
        point = {"analysis_id": analysis_id, "label": identity, "source_id": row["source_id"],
                 "source_name": row["source_name"], "values": values}
        if kind == "ternary":
            magnitude = max(values)
            if magnitude <= 0 or min(values) < 0:
                continue
            shares = [value / magnitude for value in values]
            total_shares = sum(shares)
            point["u"] = (shares[1] + shares[2] / 2) / total_shares
            point["v"] = shares[2] / total_shares
        points.append(point)

    ticks = []
    if kind == "binary":
        coordinates = []
        for axis_index in range(2):
            positions, axis_ticks = _linear_coordinates([point["values"][axis_index] for point in points])
            coordinates.append(positions)
            ticks.append(axis_ticks)
        for point, u, v in zip(points, *coordinates):
            point.update(u=u, v=v)
    by_id = {point["analysis_id"]: point for point in points}
    fields = []
    for layer in layers:
        field = layer["field"]
        if field is None or not field["visible"]:
            continue
        included = [by_id[analysis_id] for analysis_id in layer["analysis_ids"] if analysis_id in by_id]
        coordinates = [(point["u"], point["v"]) for point in included]
        message = None
        if field["method"] == "convex_hull":
            vertices = convex_hull(coordinates)
        elif kind == "binary":
            vertices = clip_to_plot_rectangle(normal_probability_ellipse(coordinates, field["probability"]))
        else:
            vertices = []
            message = "Эллипс вероятности поддерживается на бинарной диаграмме."
        if not vertices and message is None:
            message = "Для поля нужны как минимум три неколлинеарные точки."
        fields.append({"layer_id": layer["id"], "analysis_ids": [point["analysis_id"] for point in included],
                       "vertices": vertices, "message": message})
    result = {"kind": kind, "axes": axes, "points": points, "ticks": ticks, "fields": fields,
              "input_analysis_ids": sorted(row["analysis_id"] for row in active_analyses),
              "input_count": len(active_analyses), "hidden_count": len(active_analyses) - len(visible),
              "excluded_count": len(visible) - len(points)}
    result["projection_sha256"] = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                                     allow_nan=False).encode()).hexdigest()
    return result


def record_plot_visibility(database_path, analysis_ids, hidden):
    if analysis_ids is None:
        raise ValueError("analysis_ids")
    _, encoded = _selection(analysis_ids)
    action = "hide_plot_points" if hidden else "restore_plot_points"
    inverse = "restore_plot_points" if hidden else "hide_plot_points"
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        known = connection.execute("""
            SELECT COUNT(*) FROM analysis WHERE analysis_id IN (SELECT value FROM json_each(?))
        """, (encoded,)).fetchone()[0]
        if known != len(analysis_ids):
            raise ImportCommandError("PLOT_ANALYSIS_UNAVAILABLE", "Часть анализов недоступна. Видимость не изменена.")
        entry = {
            "id": _id(), "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
            "action": action, "category": "view_only",
            "scope": [{"entity_type": "analysis", "entity_id": analysis_id, "expected_revision": None, "result_revision": None}
                      for analysis_id in analysis_ids],
            "parameters": {"analysis_ids": analysis_ids, "hidden": hidden}, "reversible": True,
            "inverse_action": {"action": inverse, "parameters": {"analysis_ids": analysis_ids}},
            "state": "applied", "actor": "Локальный пользователь", "created_at": _now(),
        }
        connection.execute("INSERT INTO operation_journal (id, entry_json) VALUES (?, ?)",
                           (entry["id"], json.dumps(entry, ensure_ascii=False)))
        return entry


def _layout_input(connection, analysis_ids):
    parameters = _selection(analysis_ids)
    rows = connection.execute(f"SELECT a.analysis_id, a.source_id {_ACTIVE_ANALYSES} ORDER BY a.analysis_id", parameters).fetchall()
    if not rows or (analysis_ids is not None and len(rows) != len(analysis_ids)):
        raise ImportCommandError("PLOT_LAYOUT_INPUT_UNAVAILABLE", "Часть входных анализов недоступна. Раскладку нельзя открыть или сохранить с изменённым составом.")
    axes = connection.execute(f"SELECT DISTINCT {_AXIS_PROJECTION} {_ACTIVE_MEASUREMENTS}", parameters)
    return rows, {tuple(row) for row in axes}


def _validated_layers(layers):
    if layers is None:
        return []
    if not isinstance(layers, list) or len(layers) > 32:
        raise ValueError("layers")
    ids = []
    for layer in layers:
        if not isinstance(layer, dict) or set(layer) != {"id", "name", "analysis_ids", "show_points", "opacity", "field"}:
            raise ValueError("layers")
        ids.append(layer["id"])
        _selection(layer["analysis_ids"])
        if (not isinstance(layer["name"], str) or not 1 <= len(layer["name"].strip()) <= 120
                or layer["analysis_ids"] is None or type(layer["show_points"]) is not bool
                or type(layer["opacity"]) not in (float, int) or not 0 <= layer["opacity"] <= 1):
            raise ValueError("layers")
        field = layer["field"]
        if field is None:
            continue
        if (not isinstance(field, dict) or set(field) != {"method", "visible", "probability"}
                or type(field["visible"]) is not bool):
            raise ValueError("field")
        if field["method"] == "convex_hull" and field["probability"] is None:
            continue
        if (field["method"] != "normal_probability_ellipse" or type(field["probability"]) not in (int, float)
                or not 0 < field["probability"] < 1):
            raise ValueError("field")
    _selection(ids or None)
    return layers


def save_plot_specification(database_path, name, analysis_ids, panels, colors, hidden_analyses, hidden_sources, layers=None):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ImportCommandError("PLOT_LAYOUT_NAME_INVALID", "Введите название раскладки до 120 символов.")
    if not isinstance(panels, list) or not 1 <= len(panels) <= 32:
        raise ValueError("panels")
    layers = _validated_layers(layers)
    if not isinstance(colors, dict) or any(not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
                                           for color in colors.values()):
        raise ValueError("colors")
    for mask in (hidden_analyses, hidden_sources):
        if not isinstance(mask, list):
            raise ValueError("visibility")
        _selection(mask or None)
    panel_ids = []
    panel_keys = set()
    saved_panels = []
    for panel in panels:
        if not isinstance(panel, dict) or set(panel) != {"id", "kind", "axes"}:
            raise ValueError("panels")
        panel_ids.append(panel["id"])
        panel_keys.update(_plot_keys(panel["kind"], panel["axes"]))
        saved_panels.append({
            **panel, "title": " / ".join(axis["field"] for axis in panel["axes"]),
            "axes": [{**axis, "scale": "linear", "manual_range": None} for axis in panel["axes"]],
            "normalization": "sum_of_three_components" if panel["kind"] == "ternary" else None,
        })
    _selection(panel_ids)
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        rows, available = _layout_input(connection, analysis_ids)
        if not panel_keys <= available:
            raise ImportCommandError("PLOT_LAYOUT_AXES_UNAVAILABLE", "Часть полей раскладки недоступна для выбранного набора.")
        name = name.strip()
        if connection.execute("SELECT 1 FROM plot_specification WHERE name = ?", (name,)).fetchone():
            raise ImportCommandError("PLOT_LAYOUT_NAME_EXISTS", "Раскладка с таким названием уже есть.")
        scope = {row["analysis_id"] for row in rows}
        if any(not set(layer["analysis_ids"]) <= scope for layer in layers):
            raise ImportCommandError("PLOT_LAYER_INPUT_UNAVAILABLE", "Часть анализов слоя находится вне входного набора раскладки.")
        sources = {row["source_id"] for row in rows}
        source_rows = connection.execute("""
            SELECT source_id, display_name FROM source_file WHERE source_id IN (SELECT value FROM json_each(?))
            ORDER BY display_name, source_id
        """, (json.dumps(sorted(sources)),))
        legend = [{"value": row["source_id"], "label": row["display_name"],
                   "color": colors.get(row["source_id"], "#527eac"), "symbol": "circle"} for row in source_rows]
        now = _now()
        spec = {
            "id": _id(), "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
            "name": name, "schema_version": 1,
            "input": {"kind": "analysis_snapshot", "analysis_ids": list(analysis_ids or sorted(scope))},
            "panels": saved_panels, "legend": {"group_by": "source", "entries": legend}, "filters": [],
            "layers": layers,
            "hidden_analysis_ids": [item for item in hidden_analyses if item in scope],
            "hidden_source_ids": [item for item in hidden_sources if item in sources], "created_at": now, "updated_at": now,
        }
        connection.execute("INSERT INTO plot_specification (id, name, definition_json) VALUES (?, ?, ?)",
                           (spec["id"], name, json.dumps(spec, ensure_ascii=False)))
        return spec


def list_plot_specifications(database_path):
    with closing(open_project(database_path)) as connection:
        return [dict(row) for row in connection.execute("SELECT id, name FROM plot_specification ORDER BY name, id")]


def open_plot_specification(database_path, spec_id):
    _selection([spec_id])
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        row = connection.execute("SELECT definition_json FROM plot_specification WHERE id = ?", (spec_id,)).fetchone()
        if not row:
            raise ImportCommandError("PLOT_LAYOUT_UNAVAILABLE", "Раскладка недоступна.")
        spec = json.loads(row[0])
        if spec.get("schema_version") != 1:
            raise ImportCommandError("PLOT_LAYOUT_VERSION_UNSUPPORTED", "Версия раскладки несовместима с этой версией PetroLab.")
        _, available = _layout_input(connection, spec["input"]["analysis_ids"])
        keys = {tuple(axis[key] for key in _AXIS_FIELDS) for panel in spec["panels"] for axis in panel["axes"]}
        if not keys <= available:
            raise ImportCommandError("PLOT_LAYOUT_AXES_UNAVAILABLE", "Часть сохранённых полей недоступна. Раскладка не изменилась.")
        return spec
