"""Pure numeric projections of stored Measurements for scientific plots."""

from bisect import bisect_right
from collections import defaultdict
from contextlib import closing, nullcontext
from hashlib import sha256
import json
from math import fsum, isfinite
import re
from uuid import UUID

from .desktop_workflow import _measurement_numeric_value
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .plot_fields import clip_to_plot_rectangle, convex_hull, normal_probability_ellipse
from .statistics_core import feature_domain, review_feature_domains
from .trace_patterns import PATTERN_ORDERS, normalized_pattern_value, pattern_catalog, pattern_coordinates, pattern_reference


_ACTIVE_MEASUREMENTS = """
    FROM measurement m JOIN analysis a USING (analysis_id)
    JOIN import_batch b ON b.import_batch_id = a.import_batch_id
    JOIN source_file s ON s.source_id = a.source_id
    LEFT JOIN import_batch_retraction r ON r.import_batch_id = b.import_batch_id
    WHERE b.status = 'applied' AND r.import_batch_id IS NULL
      AND (? IS NULL OR a.analysis_id IN (SELECT value FROM json_each(?)))
"""
_AXIS_FIELDS = ("field", "unit", "measurement_set", "method")
_COORDINATE_AXIS_COUNTS = {"binary": 2, "ternary": 3, "histogram": 1}
_HISTOGRAM_BINNING = "sturges_v1"
_AXIS_PROJECTION = "m.canonical_field AS field, m.unit, m.measurement_set, m.method"
_ACTIVE_ANALYSES = """
    FROM analysis a JOIN import_batch b USING (import_batch_id)
    JOIN source_file s ON s.source_id = a.source_id
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


def plot_catalog(database_path, analysis_ids=None, *, include_formula=False):
    if type(include_formula) is not bool:
        raise ValueError('include_formula')
    with closing(open_project(database_path)) as connection:
        connection.execute('BEGIN')
        parameters = _selection(analysis_ids)
        rows = connection.execute(
            f"SELECT DISTINCT {_AXIS_PROJECTION} {_ACTIVE_MEASUREMENTS} ORDER BY field, unit, measurement_set, method",
            parameters,
        ).fetchall()
        sources = connection.execute(
            f"SELECT DISTINCT s.source_id, s.display_name AS source_name {_ACTIVE_MEASUREMENTS} ORDER BY source_name, s.source_id",
            parameters,
        ).fetchall()
        result = {"axes": [dict(row) for row in rows], "sources": [dict(row) for row in sources],
                  "patterns": pattern_catalog()}
        if include_formula:
            result['formula_series'] = _plot_formula_series(connection, parameters)
        return result


def _plot_formula_series(connection, selection):
    series = {}
    rows = connection.execute(f"""
        WITH active AS (SELECT a.analysis_id {_ACTIVE_ANALYSES})
        SELECT r.id, r.created_at, active.analysis_id,
               json_extract(r.definition_json, '$.method_id') AS method_id,
               json_extract(r.definition_json, '$.method_version') AS method_version,
               json_extract(r.definition_json, '$.method_definition_fingerprint') AS method_fingerprint,
               json_extract(r.definition_json, '$.method_definition') AS method_definition,
               json_extract(r.definition_json, '$.result_manifest.apfu') AS apfu
        FROM calculation_run r JOIN active ON active.analysis_id = json_extract(r.definition_json, '$.analysis_id')
        WHERE json_extract(r.definition_json, '$.method_id') LIKE 'formula.%'
          AND json_type(r.definition_json, '$.result_manifest.apfu') = 'object'
        ORDER BY method_id, method_version, method_fingerprint, r.created_at DESC, r.id
    """, selection)
    for row in rows:
        definition = json.loads(row['method_definition'])
        key = row['method_id'], row['method_version'], row['method_fingerprint']
        group = series.setdefault(key, {
            'method_id': key[0], 'method_version': key[1], 'method_definition_fingerprint': key[2],
            'name': definition['name'], 'oxygen_basis': definition.get('oxygen_basis'),
            'cation_basis': definition.get('cation_basis'), 'runs': [],
        })
        group['runs'].append({'run_id': row['id'], 'analysis_id': row['analysis_id'], 'created_at': row['created_at'],
                              'fields': sorted(f'apfu.{item}' for item in json.loads(row['apfu']))})
    return list(series.values())


def _axis_key(axis):
    if not isinstance(axis, dict) or set(axis) != set(_AXIS_FIELDS):
        raise ValueError("axes")
    if not all(isinstance(axis[key], str) and axis[key] for key in ("field", "unit")):
        raise ValueError("axes")
    if not all(axis[key] is None or isinstance(axis[key], str) for key in ("measurement_set", "method")):
        raise ValueError("axes")
    return tuple(axis[key] for key in _AXIS_FIELDS)


def _coordinate_axis(axis):
    if isinstance(axis, dict) and 'formula' in axis:
        key = _axis_key({field: value for field, value in axis.items() if field != 'formula'})
        binding = axis['formula']
        if (not key[0].startswith('apfu.') or key[0] == 'apfu.' or key[1:] != ('APFU', None, None)
                or not isinstance(binding, dict) or set(binding) != {'version', 'method_id', 'method_version', 'method_definition_fingerprint', 'run_ids'}
                or type(binding['version']) is not int or binding['version'] != 1
                or not isinstance(binding['method_id'], str) or not binding['method_id'].startswith('formula.')
                or not isinstance(binding['method_version'], str) or not binding['method_version']
                or not isinstance(binding['method_definition_fingerprint'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', binding['method_definition_fingerprint'])
                or binding['run_ids'] is None):
            raise ValueError('axis_formula')
        _selection(binding['run_ids'])
        return key, 'apfu', (binding['method_id'], binding['method_version'],
                             binding['method_definition_fingerprint'], tuple(sorted(binding['run_ids'])))
    if not isinstance(axis, dict) or 'calculation' not in axis:
        return _axis_key(axis), None, ()
    key = _axis_key({field: value for field, value in axis.items() if field != 'calculation'})
    definition = axis['calculation']
    if not isinstance(definition, dict) or set(definition) != {'operation', 'version', 'operands'}:
        raise ValueError('axis_calculation')
    operation, operands = definition['operation'], definition['operands']
    if (operation not in ('sum', 'ratio') or type(definition['version']) is not int or definition['version'] != 1
            or not isinstance(operands, list) or not 2 <= len(operands) <= (2 if operation == 'ratio' else 16)):
        raise ValueError('axis_calculation')
    inputs = tuple(map(_axis_key, operands))
    domains = {feature_domain(item) for item in operands}
    allowed = {'wt.%'} if domains == {'oxide_wt_percent'} else {'ppm', 'ppb'} if domains == {'trace_concentration'} else set()
    if (not allowed or len({item[0] for item in inputs}) != len(inputs)
            or any(item[2:] != key[2:] for item in inputs)
            or review_feature_domains(operands)['overlapping_iron']
            or (key[1] != 'ratio' if operation == 'ratio' else key[1] not in allowed)):
        raise ImportCommandError('PLOT_CALCULATION_INCOMPATIBLE_OPERANDS',
                                 'Выберите совместимые компоненты одного аналитического набора без двойного учёта железа.')
    return key, operation, inputs


def _plot_keys(kind, axes):
    if not isinstance(kind, str) or not isinstance(axes, list):
        raise ValueError("plot")
    if kind in PATTERN_ORDERS:
        if not 2 <= len(axes) <= len(PATTERN_ORDERS[kind]):
            raise ValueError("plot")
    elif len(axes) != _COORDINATE_AXIS_COUNTS.get(kind):
        raise ValueError("plot")
    definitions = [_coordinate_axis(axis) for axis in axes]
    keys = [definition[0] for definition in definitions]
    calculated = any(operation is not None for _, operation, _ in definitions)
    if len(set(keys)) != len(keys):
        raise ValueError("axes")
    if calculated and kind not in {"binary", "ternary"}:
        raise ImportCommandError('PLOT_CALCULATION_UNSUPPORTED', 'Расчётные оси доступны на бинарных и тройных диаграммах.')
    if kind == "ternary" and (len({key[1:] for key in keys}) != 1 or keys[0][1] not in ({"wt.%", "ppm", "ppb", "ratio", "APFU"} if calculated else {"wt.%", "ppm", "ppb"})):
        raise ImportCommandError("PLOT_TERNARY_INCOMPATIBLE_AXES", "Для тройной диаграммы выберите компоненты в одной единице и одном аналитическом наборе.")
    if kind == 'ternary' and calculated:
        if keys[0][1] == 'APFU':
            compatible = all(operation == 'apfu' for _, operation, _ in definitions) and len({binding for _, _, binding in definitions}) == 1
        elif keys[0][1] == 'ratio':
            ratio_inputs = [inputs for _, operation, inputs in definitions if operation == 'ratio']
            combined = [dict(zip(_AXIS_FIELDS, item)) for inputs in ratio_inputs for item in inputs]
            compatible = (len(ratio_inputs) == 3 and len({inputs[1] for inputs in ratio_inputs}) == 1
                          and len({inputs[0][0] for inputs in ratio_inputs}) == 3
                          and not review_feature_domains(combined)['overlapping_iron'])
        else:
            operands = [item for key, _, inputs in definitions for item in (inputs or (key,))]
            features = [dict(zip(_AXIS_FIELDS, item)) for item in operands]
            compatible = (len({item[0] for item in operands}) == len(operands)
                          and len({feature_domain(feature) for feature in features}) == 1
                          and not review_feature_domains(features)['overlapping_iron'])
        if not compatible:
            raise ImportCommandError('PLOT_TERNARY_INCOMPATIBLE_AXES', 'Для тройной диаграммы выберите одну основу APFU, неперекрывающиеся компоненты одного домена или отношения с общим знаменателем.')
    if kind in PATTERN_ORDERS and (len({key[2:] for key in keys}) != 1 or any(key[1] not in {"ppm", "ppb"} for key in keys)):
        raise ImportCommandError("PLOT_PATTERN_INCOMPATIBLE_AXES", "Для спектра выберите концентрации в ppm или ppb из одного аналитического набора и метода.")
    return keys


def _required_axis_keys(axes):
    required = set()
    for axis in axes:
        key, operation, operands = _coordinate_axis(axis)
        if operation != 'apfu':
            required.update(operands or (key,))
    return required


def _formula_axis_runs(connection, bindings):
    from .formula_service import _open_formula_run

    runs, results = {}, {}
    for binding in dict.fromkeys(bindings):
        method, version, fingerprint, ids = binding
        by_analysis = {}
        for run_id in ids:
            if run_id not in runs:
                runs[run_id] = _open_formula_run(connection, run_id)
            run = runs[run_id]
            if (run['method_id'], run['method_version'], run['method_definition_fingerprint']) != (method, version, fingerprint):
                raise ImportCommandError('PLOT_FORMULA_METHOD_MISMATCH', 'Выбранный расчёт APFU имеет другое определение метода.')
            analysis_id = run['analysis_id']
            if analysis_id in by_analysis:
                raise ImportCommandError('PLOT_FORMULA_AMBIGUOUS', 'Выберите один сохранённый расчёт APFU для каждого анализа.')
            by_analysis[analysis_id] = run
        results[binding] = by_analysis
    return results


def _formula_axis_value(field, run):
    if run is None:
        return None, {'field': field, 'reason': 'formula_run_missing'}
    evidence = {'field': field, 'reason': None, 'run_id': run['id'], 'method_id': run['method_id'],
                'method_version': run['method_version'], 'method_definition_fingerprint': run['method_definition_fingerprint'],
                'input_fingerprint': run['input_fingerprint'], 'input_measurement_ids': run['input_measurement_ids']}
    evidence['oxygen_basis'] = run['method_definition'].get('oxygen_basis')
    evidence['cation_basis'] = run['method_definition'].get('cation_basis')
    if run['status'] != 'current':
        return None, {**evidence, 'reason': 'formula_run_stale', 'stale_reasons': run['stale_reasons']}
    derived = next((item for item in run['result_manifest']['derived_values'] if item['field'] == field and item['unit'] == 'APFU'), None)
    if derived is None:
        return None, {**evidence, 'reason': 'formula_component_missing'}
    return derived['value'], {**evidence, 'derived_value_id': derived['id']}


def _coordinate_value(record, definition):
    key, operation, inputs = definition
    measurements, values = [], []
    for item in inputs or (key,):
        rows = record[item]
        measurements.extend({field: row[field] for field in ('measurement_id', 'raw_token', 'unit', 'value_status', 'reported_fe_form')}
                            for row in rows)
        if len(rows) != 1:
            return None, 'duplicate_measurements' if rows else 'missing', measurements
        row = rows[0]
        if item[0] in {'FeO', 'Fe2O3', 'FeOt', 'Fe2O3t'} and row['reported_fe_form'] != item[0]:
            return None, 'incompatible_iron_form', measurements
        value = _measurement_numeric_value(row)
        if value is None:
            status = row['value_status']
            return None, status if status and status != 'numeric' else 'unusable_measurement', measurements
        values.append(value)
    if operation is None:
        return values[0], None, measurements
    if any(value < 0 for value in values):
        return None, 'negative_operand', measurements
    if operation == 'ratio' and values[1] == 0:
        return None, 'zero_denominator', measurements
    try:
        if operation == 'ratio':
            value = values[0] / values[1]
            if inputs[0][1] != inputs[1][1]:
                value *= 1000 if inputs[0][1] == 'ppm' else .001
        else:
            value = fsum(number * (1 if item[1] == key[1] else 1000 if key[1] == 'ppb' else .001)
                         for item, number in zip(inputs, values))
    except (OverflowError, ValueError):
        return None, 'calculation_out_of_range', measurements
    return (value, None, measurements) if isfinite(value) else (None, 'calculation_out_of_range', measurements)


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


def _histogram(points):
    if not points:
        return [], [[], []]
    values = [point["values"][0] for point in points]
    low, high = min(values), max(values)
    intervals = (len(values) - 1).bit_length() + 1
    edges = [low]
    if low < high:
        for index in range(1, intervals):
            fraction = index / intervals
            edge = low * (1 - fraction) + high * fraction
            if edges[-1] < edge < high:
                edges.append(edge)
    edges.append(high)
    positions, x_ticks = _linear_coordinates(edges)
    if low == high:
        positions = [0, 1]
    bins = [defaultdict(list) for _ in range(len(edges) - 1)]
    for point, value in zip(points, values):
        index = min(bisect_right(edges, value) - 1, len(bins) - 1)
        bins[index][point["source_id"]].append(point["analysis_id"])
    counts = [sum(map(len, bin_sources.values())) for bin_sources in bins]
    maximum = max(counts)
    bars = []
    for index, (bin_sources, count) in enumerate(zip(bins, counts)):
        series, base = [], 0
        for source_id, ids in sorted(bin_sources.items()):
            series.append({"source_id": source_id, "analysis_ids": ids, "base": base / maximum,
                           "height": len(ids) / maximum})
            base += len(ids)
        bars.append({"lower": edges[index], "upper": edges[index + 1], "left": positions[index],
                     "right": positions[index + 1], "count": count, "series": series})
    y_ticks = [{"at": count / maximum, "label": str(count)} for count in sorted({0, maximum // 2, maximum})]
    return bars, [x_ticks, y_ticks]


def _alternate_concentration_key(key):
    element, unit, measurement_set, method = key
    return element, "ppb" if unit == "ppm" else "ppm", measurement_set, method


def _pattern_vertices(record, keys, concentrations):
    vertices = []
    for index, key in enumerate(keys):
        element, unit, _, _ = key
        rows = record[key] + record[_alternate_concentration_key(key)]
        value = _measurement_numeric_value(rows[0]) if len(rows) == 1 else None
        ratio = normalized_pattern_value(value, rows[0]["unit"] if rows else unit, concentrations[element])
        status = "missing"
        if len(rows) > 1:
            status = "duplicate_measurements"
        elif rows:
            if value is None:
                status = rows[0]["value_status"] or "unusable_measurement"
                if status == "numeric":
                    status = "unusable_measurement"
            elif ratio is None:
                status = "nonpositive" if value <= 0 else "ratio_out_of_range"
            else:
                status = "numeric"
        measurements = [{field: row[field] for field in ("measurement_id", "unit", "raw_token", "qualifier", "detection_limit")}
                        for row in rows]
        vertices.append({"element": element, "u": index / (len(keys) - 1), "v": None, "ratio": ratio,
                         "status": status, "measurements": measurements})
    return vertices


def query_plot_data(database_path, kind, axes, analysis_ids=None, hidden_analysis_ids=None, hidden_source_ids=None,
                    layers=None, *, normalization=None):
    keys = _plot_keys(kind, axes)
    calculated = any('calculation' in axis or 'formula' in axis for axis in axes)
    definitions = [_coordinate_axis(axis) for axis in axes] if calculated else []
    formula_bindings = [binding for _, operation, binding in definitions if operation == 'apfu']
    reference = pattern_reference(kind, [key[0] for key in keys], normalization) if kind in PATTERN_ORDERS else None
    layers = _validated_layers(layers)
    parameter, selection = _selection(analysis_ids)
    if any(value is not None and not isinstance(value, list) for value in (hidden_analysis_ids, hidden_source_ids)):
        raise ValueError("plot_visibility")
    _selection(hidden_analysis_ids or None)
    _selection(hidden_source_ids or None)
    hidden_analyses = set(hidden_analysis_ids or [])
    hidden_sources = set(hidden_source_ids or [])
    key_set = _required_axis_keys(axes) if calculated else set(keys)
    if reference is not None:
        key_set.update(map(_alternate_concentration_key, keys))
    fields = json.dumps(sorted({key[0] for key in key_set}))
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        active_analyses = connection.execute(
            f"SELECT a.analysis_id, a.source_id, a.identity_json, s.display_name AS source_name {_ACTIVE_ANALYSES}", (parameter, selection),
        ).fetchall()
        visible = {row["analysis_id"] for row in active_analyses
                   if row["analysis_id"] not in hidden_analyses and row["source_id"] not in hidden_sources}
        rows = connection.execute(f"""
            SELECT {_AXIS_PROJECTION}, a.analysis_id, a.identity_json, s.source_id, s.display_name AS source_name,
                   m.raw_token, m.qualifier, m.value_status, m.measurement_id, m.detection_limit, m.reported_fe_form
            {_ACTIVE_MEASUREMENTS} AND m.canonical_field IN (SELECT value FROM json_each(?))
            ORDER BY a.analysis_id, m.rowid
        """, (parameter, selection, fields))
        metadata = {row['analysis_id']: row for row in active_analyses if row['analysis_id'] in visible} if formula_bindings else {}
        observed = {analysis_id: defaultdict(list) for analysis_id in sorted(metadata)}
        for row in rows:
            key = tuple(row[field] for field in _AXIS_FIELDS)
            if key not in key_set:
                continue
            analysis_id = row["analysis_id"]
            if analysis_id not in visible:
                continue
            value = row if reference is not None or calculated else _measurement_numeric_value(row)
            observed.setdefault(analysis_id, defaultdict(list))[key].append(value)
            metadata[analysis_id] = row
        formula_runs = _formula_axis_runs(connection, formula_bindings) if formula_bindings else {}

    points = []
    pattern_exclusions = []
    coordinate_exclusions = []
    for analysis_id, record in observed.items():
        row = metadata[analysis_id]
        identity = " · ".join(token for token in json.loads(row["identity_json"]) if token)
        point = {"analysis_id": analysis_id, "label": identity, "source_id": row["source_id"],
                 "source_name": row["source_name"]}
        if reference is not None:
            vertices = _pattern_vertices(record, keys, reference["concentrations"])
            if any(vertex["ratio"] is not None for vertex in vertices):
                points.append({**point, "vertices": vertices})
            else:
                pattern_exclusions.append({"analysis_id": analysis_id, "reason": "no_positive_ratio", "vertices": vertices})
            continue
        if calculated:
            values, evidence = [], []
            for definition in definitions:
                key, operation, binding = definition
                if operation == 'apfu':
                    value, provenance = _formula_axis_value(key[0], formula_runs[binding].get(analysis_id))
                else:
                    value, status, measurements = _coordinate_value(record, definition)
                    provenance = {'field': key[0], 'reason': status, 'measurements': measurements}
                values.append(value)
                evidence.append(provenance)
            failure = next((item['reason'] for item in evidence if item['reason'] is not None), None)
            if failure:
                coordinate_exclusions.append({'analysis_id': analysis_id, 'reason': failure, 'axes': evidence})
                continue
            point['axis_inputs'] = evidence
        else:
            values = [record[key][0] if len(record[key]) == 1 else None for key in keys]
        if any(value is None or not isfinite(value) for value in values):
            continue
        point["values"] = values
        if kind == "ternary":
            magnitude = max(values)
            if magnitude <= 0 or min(values) < 0:
                if calculated:
                    coordinate_exclusions.append({'analysis_id': analysis_id, 'axes': evidence,
                        'reason': 'negative_component' if min(values) < 0 else 'zero_component_sum'})
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
    if kind == "histogram":
        histogram_bins, ticks = _histogram(points)
    if reference is not None:
        ticks = [[{"at": index / (len(keys) - 1), "label": key[0]} for index, key in enumerate(keys)],
                 pattern_coordinates(points)]
        pattern_exclusions.extend({"analysis_id": analysis_id, "reason": "no_matching_axes", "vertices": []}
                                  for analysis_id in sorted(visible - observed.keys()))
    by_id = {point["analysis_id"]: point for point in points}
    fields = []
    for layer in layers:
        field = layer["field"]
        if field is None or not field["visible"]:
            continue
        if kind not in ("binary", "ternary"):
            fields.append({"layer_id": layer["id"], "analysis_ids": [], "vertices": [],
                           "message": "Поля доступны для бинарных и тройных диаграмм."})
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
    if reference is not None:
        result.update(normalization=reference, exclusions=pattern_exclusions)
    if calculated:
        coordinate_exclusions.extend({'analysis_id': analysis_id, 'reason': 'no_matching_axes', 'axes': []}
                                     for analysis_id in sorted(visible - observed.keys()))
        result['exclusions'] = sorted(coordinate_exclusions, key=lambda item: item['analysis_id'])
    if kind == "histogram":
        result.update(binning=_HISTOGRAM_BINNING, bins=histogram_bins)
    result["projection_sha256"] = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                                     allow_nan=False).encode()).hexdigest()
    return result


def _write_visibility_entry(connection, analysis_ids, hidden, session_id, *, reverses_operation_id=None,
                            actor="Локальный пользователь"):
    action = "hide_plot_points" if hidden else "restore_plot_points"
    inverse = "restore_plot_points" if hidden else "hide_plot_points"
    parameters = {"analysis_ids": analysis_ids, "hidden": hidden}
    if session_id is not None:
        parameters["session_id"] = session_id
    if reverses_operation_id is not None:
        parameters["reverses_operation_id"] = reverses_operation_id
    reversible = reverses_operation_id is None
    entry = {
        "id": _id(), "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
        "action": action, "category": "view_only",
        "scope": [{"entity_type": "analysis", "entity_id": analysis_id, "expected_revision": None, "result_revision": None}
                  for analysis_id in analysis_ids],
        "parameters": parameters, "reversible": reversible,
        "inverse_action": {"action": inverse, "parameters": {"analysis_ids": analysis_ids}} if reversible else None,
        "state": "applied", "actor": actor, "created_at": _now(),
    }
    connection.execute("INSERT INTO operation_journal (id, entry_json) VALUES (?, ?)",
                       (entry["id"], json.dumps(entry, ensure_ascii=False)))
    return entry


def record_plot_visibility(database_path, analysis_ids, hidden, *, session_id=None):
    if analysis_ids is None:
        raise ValueError("analysis_ids")
    if session_id is not None and (not isinstance(session_id, str) or str(UUID(session_id)) != session_id):
        raise ValueError("session_id")
    _, encoded = _selection(analysis_ids)
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        known = connection.execute("""
            SELECT COUNT(*) FROM analysis WHERE analysis_id IN (SELECT value FROM json_each(?))
        """, (encoded,)).fetchone()[0]
        if known != len(analysis_ids):
            raise ImportCommandError("PLOT_ANALYSIS_UNAVAILABLE", "Часть анализов недоступна. Видимость не изменена.")
        return _write_visibility_entry(connection, analysis_ids, hidden, session_id)


def undo_plot_visibility(database_path, operation_id, session_id, hidden_analysis_ids, *, actor="Локальный пользователь"):
    if not isinstance(session_id, str) or str(UUID(session_id)) != session_id:
        raise ValueError("session_id")
    if not isinstance(hidden_analysis_ids, list):
        raise ValueError("hidden_analysis_ids")
    if not isinstance(actor, str) or not 1 <= len(actor.strip()) <= 120:
        raise ValueError("actor")
    _selection(hidden_analysis_ids or None)
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        stored = connection.execute("SELECT rowid, entry_json FROM operation_journal WHERE id = ?", (operation_id,)).fetchone()
        entry = json.loads(stored["entry_json"]) if stored else {}
        parameters = entry.get("parameters", {})
        if (entry.get("action") not in {"hide_plot_points", "restore_plot_points"}
                or entry.get("state") != "applied" or not entry.get("reversible")
                or parameters.get("session_id") != session_id):
            raise ImportCommandError("PLOT_VISIBILITY_UNDO_UNAVAILABLE", "Эта операция недоступна для отмены в текущем виде.")
        ids = parameters["analysis_ids"]
        hidden = parameters["hidden"]
        later = connection.execute("""
            SELECT DISTINCT affected.value
            FROM operation_journal j, json_each(j.entry_json, '$.parameters.analysis_ids') affected
            WHERE j.rowid > ? AND json_extract(j.entry_json, '$.state') = 'applied'
              AND json_extract(j.entry_json, '$.category') = 'view_only'
              AND json_extract(j.entry_json, '$.reversible') = 1
              AND json_extract(j.entry_json, '$.parameters.session_id') = ?
              AND affected.value IN (SELECT value FROM json_each(?))
        """, (stored["rowid"], session_id, json.dumps(ids))).fetchall()
        current = set(hidden_analysis_ids)
        conflicts = {row[0] for row in later} | {item for item in ids if (item in current) != hidden}
        if conflicts:
            raise ImportCommandError("PLOT_VISIBILITY_UNDO_CONFLICT", "Видимость части точек изменилась после этой операции.",
                                     {"analysis_ids": [item for item in ids if item in conflicts]})
        entry["state"] = "undone"
        connection.execute("UPDATE operation_journal SET entry_json = ? WHERE id = ?",
                           (json.dumps(entry, ensure_ascii=False), operation_id))
        return _write_visibility_entry(connection, ids, not hidden, session_id, reverses_operation_id=operation_id,
                                       actor=actor.strip())


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


def save_plot_specification(database_path, name, analysis_ids, panels, colors, hidden_analyses, hidden_sources, layers=None, *, transaction=None):
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
        if not isinstance(panel, dict) or set(panel) - {"normalization", "binning"} != {"id", "kind", "axes"}:
            raise ValueError("panels")
        panel_ids.append(panel["id"])
        kind = panel["kind"]
        keys = _plot_keys(kind, panel["axes"])
        panel_keys.update(_required_axis_keys(panel["axes"]))
        normalization = "sum_of_three_components" if kind == "ternary" else None
        if kind in PATTERN_ORDERS:
            normalization = pattern_reference(kind, [key[0] for key in keys], panel.get("normalization"))["id"]
        if "binning" in panel and (kind != "histogram" or panel["binning"] != _HISTOGRAM_BINNING):
            raise ImportCommandError("PLOT_HISTOGRAM_BINNING_UNSUPPORTED", "Версия интервалов гистограммы не поддерживается.")
        saved_panels.append({
            **panel, "title": " / ".join(axis["field"] for axis in panel["axes"]),
            "axes": [{**axis, "scale": "linear", "manual_range": None} for axis in panel["axes"]],
            "normalization": normalization,
        })
        if kind == "histogram":
            saved_panels[-1]["binning"] = _HISTOGRAM_BINNING
    _selection(panel_ids)
    with (closing(open_project(database_path)) if transaction is None else nullcontext(transaction)) as connection:
        with (connection if transaction is None else nullcontext()):
            if transaction is None:
                connection.execute("BEGIN IMMEDIATE")
            return _insert_plot_specification(connection, name, analysis_ids, saved_panels, panel_keys, colors,
                                              hidden_analyses, hidden_sources, layers)


def _insert_plot_specification(connection, name, analysis_ids, saved_panels, panel_keys, colors, hidden_analyses, hidden_sources, layers):
    rows, available = _layout_input(connection, analysis_ids)
    if not panel_keys <= available:
        raise ImportCommandError("PLOT_LAYOUT_AXES_UNAVAILABLE", "Часть полей раскладки недоступна для выбранного набора.")
    name = name.strip()
    if connection.execute("SELECT 1 FROM plot_specification WHERE name = ?", (name,)).fetchone():
        raise ImportCommandError("PLOT_LAYOUT_NAME_EXISTS", "Раскладка с таким названием уже есть.")
    scope = {row["analysis_id"] for row in rows}
    bindings = [_coordinate_axis({key: value for key, value in axis.items() if key not in {'scale', 'manual_range'}})[2]
                for panel in saved_panels for axis in panel['axes'] if 'formula' in axis]
    if bindings:
        for bound_runs in _formula_axis_runs(connection, bindings).values():
            if not bound_runs.keys() <= scope:
                raise ImportCommandError('PLOT_FORMULA_SCOPE', 'Формулы раскладки должны относиться к выбранным анализам.')
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
        if any(panel["kind"] == "histogram" and panel.get("binning") != _HISTOGRAM_BINNING for panel in spec["panels"]):
            raise ImportCommandError("PLOT_HISTOGRAM_BINNING_UNSUPPORTED", "Версия интервалов гистограммы не поддерживается.")
        _, available = _layout_input(connection, spec["input"]["analysis_ids"])
        keys = set()
        for panel in spec['panels']:
            axes = [{key: value for key, value in axis.items() if key not in {'scale', 'manual_range'}} for axis in panel['axes']]
            _plot_keys(panel['kind'], axes)
            keys.update(_required_axis_keys(axes))
        if not keys <= available:
            raise ImportCommandError("PLOT_LAYOUT_AXES_UNAVAILABLE", "Часть сохранённых полей недоступна. Раскладка не изменилась.")
        return spec
