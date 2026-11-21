"""Versioned, immutable Calculation Runs and exact analysis data review."""

from contextlib import closing
from hashlib import sha256
import json
import platform

import numpy as np

from .desktop_workflow import _measurement_numeric_value
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .plot_data import _axis_key, _selection
from .statistics_core import fit_kmeans, pca_projection, review_feature_domains, scale_values, transform_values
from .work_groups import create_work_group


_METHOD = {
    "method_id": "statistics.cluster.kmeans_lloyd", "version": "1.0.0",
    "name": "K-means (Ллойд)", "algorithm": "lloyd",
    "initializations": 8, "maximum_iterations": 100, "random_generator": "PCG64",
    "empty_cluster_policy": "discard_start", "tie_policy": "first_center", "label_order": "lexicographic_center",
    "missing_policy": "complete_cases", "censored_policy": "exclude",
    "clr_basis": "natural_log_centered", "ilr_basis": "ordered_helmert",
    "standard_scaling": "population_sd", "robust_scaling": "median_iqr_linear",
    "references": ["10.1109/TIT.1982.1056489", "10.1111/j.2517-6161.1982.tb01195.x"],
    "independent_benchmarks": ["two_part_logratio", "two_clusters_exact_inertia", "rank_one_pca"],
}


def _fingerprint(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return sha256(data).hexdigest()


def _resolve_input(connection, requested):
    if not isinstance(requested, dict):
        raise ValueError("statistics_input")
    kind = requested.get("kind")
    if kind == "analysis_snapshot" and set(requested) == {"kind", "analysis_ids"}:
        ids = requested["analysis_ids"]
        normalized = {"kind": "analysis_snapshot", "analysis_ids": ids}
    elif kind in {"work_group", "work_group_snapshot"} and set(requested) in ({"kind", "work_group_id"}, {"kind", "work_group_id", "analysis_ids"}):
        group_id = requested["work_group_id"]
        _selection([group_id])
        ids = [row[0] for row in connection.execute(
            "SELECT analysis_id FROM work_group_analysis WHERE work_group_id = ? ORDER BY position", (group_id,),
        )]
        if not ids or ("analysis_ids" in requested and requested["analysis_ids"] != ids):
            raise ImportCommandError("STATISTICS_INPUT_CHANGED", "Состав рабочей группы недоступен или изменился.")
        normalized = {"kind": "work_group_snapshot", "work_group_id": group_id, "analysis_ids": ids}
    else:
        raise ValueError("statistics_input")
    _, encoded = _selection(ids)
    if not encoded:
        raise ValueError("statistics_input")
    if len(ids) > 10000:
        raise ImportCommandError("STATISTICS_INPUT_TOO_LARGE", "Для расчёта выберите до 10 000 анализов.")
    return normalized, encoded


def _read_matrix(connection, requested, features):
    if not isinstance(features, list) or not 2 <= len(features) <= 24:
        raise ValueError("statistics_features")
    keys = [_axis_key(feature) for feature in features]
    if len(keys) != len(set(keys)):
        raise ValueError("statistics_features")
    resolved, encoded = _resolve_input(connection, requested)
    sources = connection.execute("""
        SELECT a.analysis_id, b.status, r.import_batch_id AS retracted, a.identity_json,
               b.source_fingerprint_sha256, b.recipe_revision_id
        FROM json_each(?) requested
        LEFT JOIN analysis a ON a.analysis_id = requested.value
        LEFT JOIN import_batch b ON b.import_batch_id = a.import_batch_id
        LEFT JOIN import_batch_retraction r ON r.import_batch_id = a.import_batch_id
        ORDER BY requested.key
    """, (encoded,)).fetchall()
    if any(row["status"] != "applied" or row["retracted"] for row in sources):
        raise ImportCommandError("STATISTICS_INPUT_CHANGED", "Часть входных анализов недоступна. Выберите другой входной набор.")
    rows = connection.execute("""
        SELECT m.analysis_id, m.measurement_id, m.canonical_field, m.unit, m.measurement_set, m.method,
               m.raw_token, m.value_status, m.qualifier, m.detection_limit
        FROM measurement m JOIN json_each(?) requested ON requested.value = m.analysis_id
        WHERE m.canonical_field IN (SELECT value FROM json_each(?))
        ORDER BY requested.key, m.measurement_id
    """, (encoded, json.dumps([item["field"] for item in features])))
    measurements = {analysis_id: {} for analysis_id in resolved["analysis_ids"]}
    evidence = []
    wanted = set(keys)
    for row in rows:
        feature_key = (row["canonical_field"], row["unit"], row["measurement_set"], row["method"])
        if feature_key not in wanted:
            continue
        measurements[row["analysis_id"]].setdefault(feature_key, []).append(row)
        evidence.append(tuple(row))
    fingerprint = _fingerprint({"sources": [tuple(row) for row in sources], "input": resolved,
                                "features": features, "measurements": evidence})
    matrix = []
    complete_ids = []
    euclidean_excluded = []
    logratio_excluded = []
    rows_for_review = []
    labels = {row["analysis_id"]: " · ".join(value for value in json.loads(row["identity_json"]) if value) for row in sources}
    for analysis_id in resolved["analysis_ids"]:
        record = measurements[analysis_id]
        values = []
        failures = []
        nonpositive = []
        raw_tokens = []
        for key in keys:
            candidates = record.get(key, [])
            value = _measurement_numeric_value(candidates[0]) if len(candidates) == 1 else None
            if value is None:
                reason = "calculation_policy" if len(candidates) > 1 else "missing"
                if len(candidates) == 1 and candidates[0]["qualifier"] == "below_detection_limit":
                    reason = "censored"
                failures.append({"analysis_id": analysis_id, "field": key[0], "reason": reason})
            elif value <= 0:
                nonpositive.append({"analysis_id": analysis_id, "field": key[0], "reason": "zero" if value == 0 else "negative"})
            values.append(value)
            raw_tokens.append(candidates[0]["raw_token"] if len(candidates) == 1 else None)
        rows_for_review.append({"analysis_id": analysis_id, "label": labels[analysis_id], "raw_tokens": raw_tokens})
        euclidean_excluded.extend(failures)
        logratio_excluded.extend(failures + nonpositive)
        if not failures:
            complete_ids.append(analysis_id)
            matrix.append(values)
    return {"input": resolved, "features": features, "domain": review_feature_domains(features), "labels": labels,
            "rows": rows_for_review,
            "input_fingerprint": fingerprint, "measurement_ids": [candidate[1] for candidate in evidence],
            "euclidean_excluded": euclidean_excluded, "logratio_excluded": logratio_excluded}, complete_ids, matrix


def review_statistics(database_path, requested, features):
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        review, complete_ids, _ = _read_matrix(connection, requested, features)
        return {**review, "complete_count": len(complete_ids),
                "positive_complete_count": len(review["input"]["analysis_ids"]) - len({item["analysis_id"] for item in review["logratio_excluded"]}),
                "method": _METHOD}


def run_clustering(database_path, requested, features, review_fingerprint, parameters):
    if not isinstance(parameters, dict) or set(parameters) != {"transform", "scaling", "clusters", "seed"}:
        raise ValueError("statistics_parameters")
    transform, scaling, clusters, seed = (parameters[key] for key in ("transform", "scaling", "clusters", "seed"))
    if (transform not in ("euclidean", "clr", "ilr") or scaling not in ("none", "standard", "robust")
            or type(clusters) is not int or not 2 <= clusters <= 12 or type(seed) is not int or not 0 <= seed < 2 ** 32):
        raise ValueError("statistics_parameters")
    if transform != "euclidean" and scaling != "none":
        raise ImportCommandError("STATISTICS_TRANSFORM_SCALING", "У CLR и ILR отдельное масштабирование меняет геометрию, поэтому выберите «Без масштабирования».")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        review, complete_ids, matrix = _read_matrix(connection, requested, features)
        if review["input_fingerprint"] != review_fingerprint:
            raise ImportCommandError("STATISTICS_INPUT_CHANGED", "Входные данные изменились. Повторите проверку перед расчётом.")
        domain = review["domain"]
        if transform != "euclidean" and not domain["logratio_available"]:
            raise ImportCommandError("STATISTICS_MIXED_COMPOSITION_DOMAIN", "CLR и ILR требуют одного подтверждённого состава, единицы и аналитического контекста.")
        if transform == "euclidean" and (not domain["euclidean_available"] or (domain["mixed_units"] and scaling == "none")):
            raise ImportCommandError("STATISTICS_INCOMPATIBLE_UNITS", "Для разведочного метода проверьте единицы. Разные единицы требуют явного масштабирования.")
        excluded = review["euclidean_excluded" if transform == "euclidean" else "logratio_excluded"]
        rejected_ids = {item["analysis_id"] for item in excluded}
        used = [(analysis_id, values) for analysis_id, values in zip(complete_ids, matrix) if analysis_id not in rejected_ids]
        if len(used) < clusters:
            raise ImportCommandError("STATISTICS_TOO_FEW_ROWS", "После исключений осталось недостаточно анализов для выбранного числа кластеров.")
        ids, values = zip(*used)
        transformed = transform_values(values, transform)
        data, scale = scale_values(transformed, scaling)
        fit = fit_kmeans(data, clusters, seed)
        pca = pca_projection(data)
        members = [{"analysis_id": analysis_id, "label": review["labels"][analysis_id], "cluster": cluster,
                    "scores": scores, "u": coordinates[0], "v": coordinates[1]}
                   for analysis_id, cluster, scores, coordinates in zip(ids, fit.pop("labels"), pca.pop("scores"), pca.pop("projection"))]
        project_id = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
        run = {
            "id": _id(), "project_id": project_id, "method_id": _METHOD["method_id"], "method_version": _METHOD["version"],
            "method_definition_fingerprint": _fingerprint(_METHOD), "input": review["input"],
            "input_measurement_ids": review["measurement_ids"], "input_fingerprint": review["input_fingerprint"],
            "parameters": {**parameters, "features": features, "feature_domains": domain["domains"],
                           "missing_and_censored": "exclude", "nonpositive": "exclude" if transform != "euclidean" else "keep",
                           "scaling_parameters": scale},
            "status": "current", "stale_reasons": [], "seed": seed,
            "excluded": excluded, "result_manifest": {"members": members, "fit": fit, "pca": pca},
            "software_versions": {"numpy": np.__version__, "python": platform.python_version()}, "created_at": _now(),
        }
        connection.execute("INSERT INTO calculation_run VALUES (?, ?, ?, ?)",
                           (run["id"], project_id, run["created_at"], json.dumps(run, ensure_ascii=False, allow_nan=False)))
        return run


def list_calculation_runs(database_path):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT id, created_at, json_extract(definition_json, '$.parameters.scaling') AS scaling,
                   json_extract(definition_json, '$.parameters.transform') AS transform,
                   json_extract(definition_json, '$.parameters.clusters') AS clusters
            FROM calculation_run WHERE json_extract(definition_json, '$.method_id') = ? ORDER BY created_at DESC, rowid DESC
        """, (_METHOD["method_id"],))
        return [dict(row) for row in rows]


def open_calculation_run(database_path, run_id):
    _selection([run_id])
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        row = connection.execute("""SELECT definition_json FROM calculation_run
            WHERE id = ? AND json_extract(definition_json, '$.method_id') = ?""", (run_id, _METHOD["method_id"])).fetchone()
        if not row:
            raise ImportCommandError("CALCULATION_RUN_UNAVAILABLE", "Сохранённый расчёт недоступен.")
        run = json.loads(row[0])
        reasons = []
        if run["method_definition_fingerprint"] != _fingerprint(_METHOD):
            reasons.append("Версия метода или его параметры по умолчанию изменились.")
        try:
            current, _, _ = _read_matrix(connection, run["input"], run["parameters"]["features"])
            if current["input_fingerprint"] != run["input_fingerprint"]:
                reasons.append("Входные измерения или аналитический контекст изменились.")
        except ImportCommandError as error:
            if error.code != "STATISTICS_INPUT_CHANGED":
                raise
            reasons.append("Часть входного набора недоступна.")
        return {**run, "status": "stale" if reasons else "current", "stale_reasons": reasons}


def save_calculated_cluster(database_path, run_id, cluster, name, author):
    if type(cluster) is not int or cluster < 0:
        raise ValueError("cluster")
    run = open_calculation_run(database_path, run_id)
    if run["status"] != "current":
        raise ImportCommandError("CALCULATION_RUN_STALE", "Вход или метод изменился. Выполните новый расчёт перед сохранением группы.")
    ids = [member["analysis_id"] for member in run["result_manifest"]["members"] if member["cluster"] == cluster]
    if not ids:
        raise ImportCommandError("STATISTICS_CLUSTER_UNAVAILABLE", "Кластер недоступен в этом расчёте.")
    return create_work_group(database_path, name, ids, author,
                             calculation_origin={"calculation_run_id": run_id, "cluster": cluster})
