"""Review, persist and reopen versioned mineral formula runs."""

from contextlib import closing
import json

from .desktop_workflow import _measurement_numeric_value
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError, value_status
from .mineral_formulae import (
    AMPHIBOLE, APATITE, CARBONATE_1CAT, CARBONATE_2CAT, FELDSPAR, GARNET, GARNET_DROOP, ILMENITE, ILMENITE_DROOP,
    MICA_11, MICA_22, NEPHELINE, PEROVSKITE, PYROXENE, PYROXENE_DROOP, SPINEL, SPINEL_DROOP, TITANITE, ZIRCON,
    calculate_mineral_formula,
)
from .olivine_formula import OLIVINE, calculate_olivine
from .plot_data import _selection
from .statistics_service import _fingerprint


_OXIDE_METHODS = {method["method_id"]: method for method in (
    FELDSPAR, PYROXENE, SPINEL, ILMENITE, ZIRCON, PEROVSKITE, CARBONATE_1CAT, CARBONATE_2CAT, GARNET, NEPHELINE,
    APATITE, TITANITE, MICA_11, MICA_22, AMPHIBOLE, PYROXENE_DROOP, GARNET_DROOP, SPINEL_DROOP, ILMENITE_DROOP,
)}
_DERIVED_UNITS = {
    "apfu": "APFU", "divalent_component_mol_percent": "mol.%", "end_member_mol_percent": "mol.%",
    "quadrilateral_apfu": "APFU", "site_sum_apfu": "APFU", "charge_per_formula": "e/f.u.",
    "anion_balance_apfu": "APFU", "estimated_anions_apfu": "APFU", "iron_partition_apfu": "APFU",
    "droop_diagnostics_apfu": "APFU",
    "indices": "1", "cation_fraction": "1",
}


def list_formula_methods():
    return [OLIVINE, *_OXIDE_METHODS.values()]


def _method(method_id):
    if method_id == OLIVINE["method_id"]:
        return OLIVINE
    if not isinstance(method_id, str) or method_id not in _OXIDE_METHODS:
        raise ImportCommandError("FORMULA_METHOD_UNAVAILABLE", "Метод расчёта формулы недоступен.")
    return _OXIDE_METHODS[method_id]


def _calculate(values, method):
    if method["method_id"] == OLIVINE["method_id"]:
        return calculate_olivine(values, method)
    return calculate_mineral_formula(values, method)


def review_import_formula(record, method_id):
    method = _method(method_id)
    inputs = []
    excluded = []
    values = {}
    contexts = set()
    for measurement in record["measurements"]:
        field = measurement["field"]
        value = _measurement_numeric_value(measurement)
        reason = None
        if field not in method["components"]:
            reason = "unsupported_component"
        elif measurement["unit"] != method["input_unit"]:
            reason = "incompatible_unit"
        elif value is None:
            reason = "non_quantitative"
        elif field in {"FeO", "Fe2O3", "FeOt"} and measurement["reported_fe_form"] != field:
            reason = "incompatible_iron_form"
        if reason:
            excluded.append({**measurement, "reason": reason})
            continue
        if field in values:
            raise ImportCommandError("FORMULA_AMBIGUOUS_COMPONENT", "В строке несколько измерений одного оксида.")
        contexts.add((measurement["method"], measurement["measurement_set"]))
        values[field] = value
        inputs.append({**measurement, "effective_value": value})
    if len(contexts) > 1:
        raise ImportCommandError("FORMULA_MIXED_INPUT", "Для пересчёта нужен один аналитический метод и набор.")
    fingerprint = _fingerprint({"preview_id": record["preview_id"], "method": method,
                                "measurements": record["measurements"]})
    try:
        result = _calculate(values, method)
    except ImportCommandError as error:
        missing = [field for field in method["required_components"] if field not in values]
        if not missing:
            raise
        unusable = [{key: row[key] for key in ("field", "source_cell", "raw_token", "value_status", "reason")}
                    for row in excluded if row["field"] in missing]
        raise ImportCommandError(error.code, error.message, {**error.details, "missing_components": missing,
                                                            "unusable_components": unusable}) from error
    return {"preview_id": record["preview_id"], "method_definition": method, "measurements": inputs,
            "excluded_measurements": excluded, "preview": result,
            "confirmation_fingerprint": fingerprint}


def _read_input(connection, analysis_id, measurement_ids, method):
    _selection([analysis_id])
    _, encoded = _selection(measurement_ids)
    if not encoded or len(measurement_ids) > len(method["components"]):
        raise ValueError("measurement_ids")
    source = connection.execute("""SELECT a.source_id, a.import_batch_id, b.recipe_revision_id, b.source_fingerprint_sha256
        FROM analysis a JOIN import_batch b USING (import_batch_id)
        LEFT JOIN import_batch_retraction x USING (import_batch_id)
        WHERE a.analysis_id = ? AND b.status = 'applied' AND x.import_batch_id IS NULL""", (analysis_id,)).fetchone()
    if not source:
        raise ImportCommandError("FORMULA_INPUT_UNAVAILABLE", "Исходный анализ недоступен.")
    rows = connection.execute("""SELECT m.measurement_id, m.canonical_field, m.unit, m.measurement_set, m.method, m.raw_token,
            m.value_status, m.qualifier, m.detection_limit, m.reported_fe_form, m.fe_handling
        FROM measurement m JOIN json_each(?) requested ON requested.value = m.measurement_id
        WHERE m.analysis_id = ? ORDER BY m.measurement_id""", (encoded, analysis_id)).fetchall()
    if len(rows) != len(measurement_ids):
        raise ImportCommandError("FORMULA_INPUT_UNAVAILABLE", "Часть измерений недоступна для этого анализа.")
    if len({(row["method"], row["measurement_set"]) for row in rows}) != 1 or any(row["unit"] != method["input_unit"] for row in rows):
        raise ImportCommandError("FORMULA_MIXED_INPUT", "Выберите измерения одного метода и набора в wt.%.")
    if len({row["canonical_field"] for row in rows}) != len(rows):
        raise ImportCommandError("FORMULA_AMBIGUOUS_COMPONENT", "Для каждого оксида выберите одно измерение.")

    corrections = {}
    for row in connection.execute("""SELECT d.measurement_id, j.entry_json
        FROM edit_draft d JOIN operation_journal j ON j.edit_draft_id = d.id
        JOIN json_each(?) requested ON requested.value = d.measurement_id
        WHERE json_extract(j.entry_json, '$.action') = 'commit_edit_draft'
          AND json_extract(j.entry_json, '$.state') = 'applied'
          AND json_extract(j.entry_json, '$.parameters.phase') = 'completed'""", (encoded,)):
        if row["measurement_id"] in corrections:
            raise ImportCommandError("FORMULA_AMBIGUOUS_CORRECTION", "Для измерения найдено несколько подтверждённых поправок.")
        edit = json.loads(row["entry_json"])
        corrections[row["measurement_id"]] = {"operation_id": edit["id"], "raw_token": edit["parameters"]["change"]["new_value"],
                                               "source_sha256": edit["parameters"]["after_sha256"]}

    inputs = []
    values = {}
    for row in rows:
        measurement = dict(row)
        oxide = row["canonical_field"]
        if oxide in {"FeO", "Fe2O3", "FeOt"} and row["reported_fe_form"] != oxide:
            raise ImportCommandError("FORMULA_UNRESOLVED_IRON", "Форма железа в источнике не соответствует выбранному оксиду.")
        correction = corrections.get(row["measurement_id"])
        effective = measurement if correction is None else {**measurement, "raw_token": correction["raw_token"],
            "qualifier": None, "value_status": value_status(correction["raw_token"])}
        number = _measurement_numeric_value(effective)
        if number is None:
            raise ImportCommandError("FORMULA_INVALID_MEASUREMENT", f"{oxide}: требуется определённое числовое измерение.")
        inputs.append({**measurement, "correction": correction, "effective_value": number})
        values[oxide] = number
    fingerprint = _fingerprint({"analysis_id": analysis_id, "source": dict(source), "measurements": inputs})
    return {"analysis_id": analysis_id, "source": dict(source), "measurements": inputs, "input_fingerprint": fingerprint}, values


def review_formula(database_path, method_id, analysis_id, measurement_ids):
    method = _method(method_id)
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        review, values = _read_input(connection, analysis_id, measurement_ids, method)
        result = _calculate(values, method)
    return {**review, "method_definition": method, "method_definition_fingerprint": _fingerprint(method), "preview": result}


def run_formula(database_path, method_id, analysis_id, measurement_ids, input_fingerprint, method_fingerprint):
    method = _method(method_id)
    if method_fingerprint != _fingerprint(method):
        raise ImportCommandError("FORMULA_REVIEW_STALE", "Версия метода изменилась. Повторите проверку.")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        reviewed, values = _read_input(connection, analysis_id, measurement_ids, method)
        if reviewed["input_fingerprint"] != input_fingerprint:
            raise ImportCommandError("FORMULA_REVIEW_STALE", "Входные измерения изменились. Повторите проверку.")
        return _persist_formula_run(connection, reviewed, values, method)


def _persist_formula_run(connection, reviewed, values, method):
    result = _calculate(values, method)
    run_id = _id()
    derived = [{"id": _id(), "run_id": run_id, "analysis_id": reviewed["analysis_id"],
                "field": f"{series}.{key}", "unit": unit, "value": value}
               for series, unit in _DERIVED_UNITS.items() for key, value in result.get(series, {}).items()]
    project_id = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
    record = {**reviewed, "id": run_id, "project_id": project_id, "method_id": method["method_id"],
              "method_version": method["version"], "method_definition": method,
              "method_definition_fingerprint": _fingerprint(method),
              "input_measurement_ids": [row["measurement_id"] for row in reviewed["measurements"]],
              "result_manifest": {**result, "derived_values": derived}, "created_at": _now(), "status": "current", "stale_reasons": []}
    connection.execute("INSERT INTO calculation_run VALUES (?, ?, ?, ?)",
                       (run_id, project_id, record["created_at"], json.dumps(record, ensure_ascii=False, allow_nan=False)))
    return record


def persist_import_formulae(connection, batch_id, plan, acceptances):
    records = {row["preview_id"]: row for row in plan["planned_records"]}
    run_ids = []
    for preview_id, acceptance in acceptances.items():
        record = records.get(preview_id)
        review = check_import_formula_acceptance(record, acceptance)
        analysis = connection.execute("SELECT analysis_id FROM analysis WHERE import_batch_id = ? AND preview_id = ?",
                                      (batch_id, preview_id)).fetchone()
        if analysis is None:
            raise ImportCommandError("FORMULA_INPUT_UNAVAILABLE", "Подтверждённый анализ отсутствует в импорте.")
        analysis_id = analysis["analysis_id"]
        fields = {(row["source_cell"], row["field"]) for row in review["measurements"]}
        measurement_ids = [row["measurement_id"] for row in connection.execute(
            "SELECT measurement_id, source_cell, canonical_field FROM measurement WHERE analysis_id = ?", (analysis_id,)
        ) if (row["source_cell"], row["canonical_field"]) in fields]
        if len(measurement_ids) != len(fields):
            raise ImportCommandError("FORMULA_INPUT_UNAVAILABLE", "Не найдены точные измерения для подтверждённого расчёта.")
        method = review["method_definition"]
        reviewed, values = _read_input(connection, analysis_id, measurement_ids, method)
        if values != {row["field"]: row["effective_value"] for row in review["measurements"]}:
            raise ImportCommandError("FORMULA_REVIEW_STALE", "Измерения отличаются от подтверждённого расчёта.")
        run_ids.append(_persist_formula_run(connection, reviewed, values, method)["id"])
    return run_ids


def check_import_formula_acceptance(record, acceptance):
    try:
        if record is not None:
            review = review_import_formula(record, acceptance["method_id"])
            if review["confirmation_fingerprint"] == acceptance["confirmation_fingerprint"]:
                return review
    except ImportCommandError as error:
        raise ImportCommandError("FORMULA_REVIEW_STALE", "Повторите или снимите подтверждение формулы.") from error
    raise ImportCommandError("FORMULA_REVIEW_STALE", "Повторите или снимите подтверждение формулы.")


def open_formula_run(database_path, run_id):
    _selection([run_id])
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        return _open_formula_run(connection, run_id)


def _open_formula_run(connection, run_id):
    row = connection.execute("""SELECT definition_json FROM calculation_run
        WHERE id = ? AND json_extract(definition_json, '$.method_id') LIKE 'formula.%'""", (run_id,)).fetchone()
    if not row:
        raise ImportCommandError("FORMULA_RUN_UNAVAILABLE", "Сохранённый расчёт формулы недоступен.")
    run = json.loads(row[0])
    reasons = []
    try:
        method = _method(run["method_id"])
    except ImportCommandError:
        reasons.append("method_unavailable")
        method = run["method_definition"]
    if _fingerprint(method) != run["method_definition_fingerprint"]:
        reasons.append("method_changed")
    try:
        review, _ = _read_input(connection, run["analysis_id"], run["input_measurement_ids"], run["method_definition"])
        if review["input_fingerprint"] != run["input_fingerprint"]:
            reasons.append("inputs_changed")
    except ImportCommandError:
        reasons.append("inputs_unavailable")
    return {**run, "status": "stale" if reasons else "current", "stale_reasons": reasons}


def list_formula_runs(database_path, analysis_id=None):
    if analysis_id is not None:
        _selection([analysis_id])
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""SELECT r.id, r.created_at, json_extract(r.definition_json, '$.method_id') AS method_id,
                   json_extract(r.definition_json, '$.method_version') AS method_version,
                   json_extract(r.definition_json, '$.method_definition.name') AS method_name,
                   a.analysis_id, a.identity_json
            FROM calculation_run r JOIN analysis a ON a.analysis_id = json_extract(r.definition_json, '$.analysis_id')
            WHERE json_extract(r.definition_json, '$.method_id') LIKE 'formula.%' AND (? IS NULL OR a.analysis_id = ?)
            ORDER BY r.created_at DESC, r.rowid DESC""", (analysis_id, analysis_id))
        results = []
        for row in rows:
            item = dict(row)
            item["analysis_label"] = " · ".join(value for value in json.loads(item.pop("identity_json")) if value) or item["analysis_id"]
            results.append(item)
        return results
