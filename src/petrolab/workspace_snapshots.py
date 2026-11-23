"""Named references to project state with explicit restore compatibility."""

from contextlib import closing
from hashlib import sha256
import json
from uuid import UUID

from .desktop_workflow import analysis_identity
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .plot_data import _layout_input, open_plot_specification, plot_catalog, save_plot_specification
from .trace_patterns import PATTERN_ORDERS
from .statistics_core import feature_domain
from .statistics_service import _METHOD, open_calculation_run, review_statistics
from .table_views import _fingerprint as table_universe_fingerprint
from .table_views import save_table_view


_SURFACES = {"overview", "import", "analyses", "samples", "thin_sections", "search", "plotting", "statistics", "publication"}
_CONTENT = {"data_universe", "table_view_id", "plot_specification_ids", "source_visibility", "selection_restore_policy",
            "selection_analysis_ids", "active_calculation_run_id", "active_surface"}


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("snapshot_id")
    return value


def _ids(values):
    if not isinstance(values, list) or len({_uuid(value) for value in values}) != len(values):
        raise ValueError("snapshot_ids")


def _payload(state):
    serialized = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode()).hexdigest()


def _state(state):
    if not isinstance(state, dict) or set(state) != _CONTENT:
        raise ValueError("snapshot_state")
    universe = state["data_universe"]
    if not isinstance(universe, dict) or set(universe) != {"dataset_ids", "work_group_ids", "analysis_ids"} or universe["dataset_ids"] != []:
        raise ValueError("snapshot_data_universe")
    for ids in (universe["work_group_ids"], universe["analysis_ids"], state["plot_specification_ids"], state["selection_analysis_ids"]):
        _ids(ids)
    for value in (state["table_view_id"], state["active_calculation_run_id"]):
        if value is not None:
            _uuid(value)
    visibility = state["source_visibility"]
    if not isinstance(visibility, list) or any(not isinstance(item, dict) or set(item) != {"source_id", "visible"}
                                               or type(item["visible"]) is not bool for item in visibility):
        raise ValueError("snapshot_source_visibility")
    _ids([item["source_id"] for item in visibility])
    if state["selection_restore_policy"] not in ("clear", "restore_exact_if_available"):
        raise ValueError("snapshot_selection")
    if state["selection_restore_policy"] == "clear" and state["selection_analysis_ids"]:
        raise ValueError("snapshot_selection")
    if not isinstance(state["active_surface"], str) or state["active_surface"] not in _SURFACES:
        raise ValueError("snapshot_surface")
    return state


def _report(database_path, connection, state):
    report = []

    def unavailable(field, reason):
        report.append({"field": field, "action": "blocked", "reason": reason})

    universe = state["data_universe"]
    if missing := connection.execute("""
        SELECT requested.value FROM json_each(?) requested
        LEFT JOIN analysis a ON a.analysis_id = requested.value
        LEFT JOIN import_batch b ON b.import_batch_id = a.import_batch_id
        LEFT JOIN import_batch_retraction r ON r.import_batch_id = a.import_batch_id
        WHERE b.status IS NOT 'applied' OR r.import_batch_id IS NOT NULL
    """, (json.dumps(list(dict.fromkeys(universe["analysis_ids"] + state["selection_analysis_ids"]))),)).fetchall():
        unavailable("analysis_ids", "Недоступные анализы: " + ", ".join(row[0] for row in missing))
    for group_id in universe["work_group_ids"]:
        group = connection.execute("""
            SELECT COUNT(*), SUM(b.status = 'applied' AND r.import_batch_id IS NULL)
            FROM work_group_analysis ga JOIN analysis a USING (analysis_id)
            JOIN import_batch b USING (import_batch_id) LEFT JOIN import_batch_retraction r USING (import_batch_id)
            WHERE ga.work_group_id = ?
        """, (group_id,)).fetchone()
        if not group[0] or group[0] != group[1]:
            unavailable("work_group_ids", f"Рабочая группа недоступна целиком или частично: {group_id}.")
    for item in state["source_visibility"]:
        if not connection.execute("SELECT 1 FROM source_file WHERE source_id = ?", (item["source_id"],)).fetchone():
            unavailable("source_visibility", f"Недоступен источник {item['source_id']}.")
    if state["table_view_id"] is not None:
        view = connection.execute("SELECT definition_json FROM table_view WHERE id = ?", (state["table_view_id"],)).fetchone()
        if not view or json.loads(view[0])["data_universe_fingerprint"] != table_universe_fingerprint(connection):
            unavailable("table_view_id", "Набор данных представления таблицы изменился.")
    for plot_id in state["plot_specification_ids"]:
        try:
            open_plot_specification(database_path, plot_id)
        except ImportCommandError as error:
            unavailable("plot_specification_ids", f"{plot_id}: {error.message}")
    if state["active_calculation_run_id"] is not None:
        try:
            run = open_calculation_run(database_path, state["active_calculation_run_id"])
            for reason in run["stale_reasons"]:
                unavailable("active_calculation_run_id", reason)
        except ImportCommandError as error:
            unavailable("active_calculation_run_id", error.message)
    return report


def save_workspace_snapshot(database_path, name, state):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise ValueError("snapshot_name")
    _state(state)
    with closing(open_project(database_path)) as connection, connection:
        if report := _report(database_path, connection, state):
            raise ImportCommandError("SNAPSHOT_INCOMPATIBLE", "Состав рабочего состояния недоступен.", {"migration_report": report})
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM workspace_snapshot WHERE name = ?", (name.strip(),)).fetchone():
            raise ImportCommandError("SNAPSHOT_NAME_EXISTS", "Рабочее состояние с таким названием уже существует.")
        snapshot = {
            **state, "id": _id(), "name": name.strip(), "schema_version": 1,
            "semantic_fingerprint": _payload(state), "created_at": _now(),
            "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
            "migration_report": [],
        }
        connection.execute("INSERT INTO workspace_snapshot VALUES (?, ?, ?)",
                           (snapshot["id"], snapshot["name"], json.dumps(snapshot, ensure_ascii=False)))
        return snapshot


def list_workspace_snapshots(database_path):
    with closing(open_project(database_path)) as connection:
        return [dict(row) for row in connection.execute("SELECT id, name FROM workspace_snapshot ORDER BY name, id")]


def open_workspace_snapshot(database_path, snapshot_id):
    _uuid(snapshot_id)
    with closing(open_project(database_path)) as connection:
        row = connection.execute("SELECT definition_json FROM workspace_snapshot WHERE id = ?", (snapshot_id,)).fetchone()
        if not row:
            raise ImportCommandError("SNAPSHOT_UNAVAILABLE", "Сохранённое рабочее состояние недоступно.")
        snapshot = json.loads(row[0])
        if snapshot.get("schema_version") != 1:
            report = [{"field": "schema_version", "action": "blocked", "reason": "Версия рабочего состояния не поддерживается."}]
        else:
            content = _state({key: snapshot[key] for key in _CONTENT})
            if _payload(content) != snapshot["semantic_fingerprint"]:
                raise ImportCommandError("SNAPSHOT_DAMAGED", "Контрольная сумма рабочего состояния не совпадает.")
            report = _report(database_path, connection, content)
        return {"snapshot": None if report else snapshot, "migration_report": report}


_TEMPLATE_CONTENT = ("requirements", "table_columns", "panel_templates", "method_templates")
_METHOD_PARAMETERS = ("transform", "scaling", "clusters", "seed")
_TABLE_COLUMNS = {"source", "sheet", "origin", "mineral", "mineral-status", "generation"}


def list_analysis_templates(database_path):
    with closing(open_project(database_path)) as connection:
        return [dict(row) for row in connection.execute("SELECT id, name FROM analysis_template ORDER BY name, id")]


def save_analysis_template(database_path, name, plot_id=None, table_view_id=None, calculation_run_id=None):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        raise ValueError("template_name")
    if all(identifier is None for identifier in (plot_id, table_view_id, calculation_run_id)):
        raise ValueError("template_components")
    plot = open_plot_specification(database_path, plot_id) if plot_id is not None else None
    version = 1 if table_view_id is None and calculation_run_id is None else 2
    requirements = {}

    def fields(axes):
        names = []
        for axis in axes:
            key = axis["field"]
            requirement = {"field": key, "semantic_domain": feature_domain(axis), "allowed_units": [axis["unit"]], "required": True}
            if version == 2:
                requirement.update(measurement_set=axis["measurement_set"], method=axis["method"])
            if requirement["semantic_domain"] == "other" or (key in requirements and requirements[key] != requirement):
                raise ImportCommandError("TEMPLATE_FIELD_AMBIGUOUS", f"Домен или единица признака {key} неоднозначны.")
            requirements[key] = requirement
            names.append(key)
        return names

    panels = []
    for panel in (plot["panels"] if plot else []):
        definition = {"kind": panel["kind"], "title": panel["title"], "axes": fields(panel["axes"])}
        if panel["kind"] in PATTERN_ORDERS:
            definition["normalization"] = panel["normalization"]
        panels.append(definition)
    columns, sort, methods, filters_omitted = [], [], [], False
    if calculation_run_id is not None:
        run = open_calculation_run(database_path, calculation_run_id)
        if run.get("status") != "current":
            raise ImportCommandError("TEMPLATE_METHOD_UNAVAILABLE", "Исходный расчёт устарел.")
        params = run["parameters"]
        methods.append({"method_id": run["method_id"], "method_version": run["method_version"],
                        "parameters": {**{key: params[key] for key in _METHOD_PARAMETERS}, "features": fields(params["features"])}})
    if table_view_id is not None:
        _uuid(table_view_id)
        with closing(open_project(database_path)) as connection:
            row = connection.execute("SELECT definition_json FROM table_view WHERE id = ?", (table_view_id,)).fetchone()
        if row is None:
            raise ImportCommandError("TEMPLATE_TABLE_UNAVAILABLE", "Представление таблицы недоступно.")
        view = json.loads(row[0])
        columns = [{key: column[key] for key in ("field", "order", "visible")} for column in view["columns"]]
        sort = view["sort"]
        filters_omitted = bool(view["filters"])
        catalog = plot_catalog(database_path)["axes"]
        for column in columns:
            kind, _, key = column["field"].partition(":")
            # A panel or calculation can establish the context for a shared table field.
            if kind == "measurement" and key not in requirements:
                matches = [axis for axis in catalog if axis["field"] == key]
                if not matches:
                    raise ImportCommandError("TEMPLATE_FIELD_AMBIGUOUS", f"Измерение {key} недоступно.")
                fields(matches)
    content = {"requirements": list(requirements.values()), "table_columns": columns,
               "panel_templates": panels, "method_templates": methods}
    if version == 2:
        content["table_sort"] = sort
        content["table_filters_omitted"] = filters_omitted
    template = {**content, "id": _id(), "name": name.strip(), "schema_version": version,
                "semantic_fingerprint": _payload(content), "created_at": _now()}
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM analysis_template WHERE name = ?", (template["name"],)).fetchone():
            raise ImportCommandError("TEMPLATE_NAME_EXISTS", "Шаблон с таким названием уже существует.")
        connection.execute("INSERT INTO analysis_template VALUES (?, ?, ?)",
                           (template["id"], template["name"], json.dumps(template, ensure_ascii=False)))
    return template


def _template_table_columns(connection, analysis_ids, axes):
    available = _TABLE_COLUMNS | {f"measurement:{axis['field']}" for axis in axes}
    rows = connection.execute("""
        SELECT a.analysis_id, a.identity_json, a.sheet_name, a.block_id, r.recipe_json
        FROM json_each(?) ids JOIN analysis a ON a.analysis_id = ids.value
        JOIN import_batch b USING (import_batch_id)
        JOIN import_recipe_revision r ON r.recipe_revision_id = b.recipe_revision_id
    """, (json.dumps(analysis_ids),))
    for row in rows:
        available.update(f"identity:{field}" for field in analysis_identity(row))
    seen = set()
    for row in connection.execute("""
        SELECT m.analysis_id, m.canonical_field, m.source_header
        FROM json_each(?) ids JOIN analysis_source_metadata m ON m.analysis_id = ids.value
        ORDER BY m.analysis_id, m.source_column_index, m.rowid
    """, (json.dumps(analysis_ids),)):
        key = row["analysis_id"], row["canonical_field"]
        field = row["canonical_field"] if key not in seen else f"{row['canonical_field']} · {row['source_header']}"
        seen.add(key)
        available.add(f"metadata:{field}")
    return available


def apply_analysis_template(database_path, template_id, analysis_ids, name=None):
    _uuid(template_id)
    _ids(analysis_ids)
    if not analysis_ids:
        raise ValueError("template_analysis_ids")
    with closing(open_project(database_path)) as connection:
        row = connection.execute("SELECT definition_json FROM analysis_template WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise ImportCommandError("TEMPLATE_UNAVAILABLE", "Шаблон недоступен.")
    template = json.loads(row[0])
    version = template.get("schema_version")
    if version not in (1, 2):
        return {"plot": None, "migration_report": [
            {"field": "schema_version", "action": "blocked", "reason": "Версия шаблона не поддерживается."}
        ]}
    keys = _TEMPLATE_CONTENT + (("table_sort", "table_filters_omitted") if version == 2 else ())
    content = {key: template[key] for key in keys}
    if _payload(content) != template["semantic_fingerprint"]:
        raise ImportCommandError("TEMPLATE_DAMAGED", "Контрольная сумма шаблона не совпадает.")
    axes = plot_catalog(database_path, analysis_ids)["axes"]
    compatible = {}
    report = []
    for requirement in template["requirements"]:
        field = requirement["field"]
        candidates = [axis for axis in axes if axis["field"] == field]
        matches = [axis for axis in candidates if axis["unit"] in requirement["allowed_units"]
                   and feature_domain(axis) == requirement["semantic_domain"]
                   and all(axis[key] == requirement[key] for key in ("measurement_set", "method") if key in requirement)]
        if len(matches) == 1:
            compatible[field] = matches[0]
            report.append({"field": field, "action": "unchanged",
                           "reason": f"Единица {matches[0]['unit']}, домен и аналитический контекст совместимы."})
        else:
            expected_units = ", ".join(requirement["allowed_units"])
            observed_units = ", ".join(sorted({axis["unit"] for axis in candidates}))
            if not candidates:
                reason = f"Поле отсутствует в выбранном наборе. Требуемые единицы — {expected_units}."
            elif not matches:
                reason = (f"Требуемые единицы — {expected_units}. Найденные единицы — {observed_units}. "
                          "Совместимое сочетание единицы, домена и аналитического контекста отсутствует.")
            else:
                reason = "Есть несколько совместимых аналитических контекстов."
            report.append({"field": field, "action": "blocked", "reason": reason})
    table = None
    methods = []
    plot = None
    if version == 2:
        with closing(open_project(database_path)) as connection:
            try:
                _layout_input(connection, analysis_ids)
            except ImportCommandError as error:
                report.append({"field": "analysis_ids", "action": "blocked", "reason": error.message})
            available = _template_table_columns(connection, analysis_ids, axes)
        for column in template["table_columns"]:
            field = column["field"]
            if field not in available:
                report.append({"field": field, "action": "blocked", "reason": "Колонка отсутствует в выбранном наборе."})
        if template["table_filters_omitted"]:
            report.append({"field": "table_filters", "action": "omitted", "reason": "Фильтры исходного представления не входят в переносимый шаблон."})
        if not any(item["action"] == "blocked" for item in report):
            for method in template["method_templates"]:
                plan, issue = _review_template_method(database_path, method, analysis_ids, compatible)
                if issue:
                    report.append({"field": "method_templates", "action": "blocked", "reason": issue})
                else:
                    methods.append(plan)
    if name is not None and not any(item["action"] == "blocked" for item in report):
        panels = []
        for panel in template["panel_templates"]:
            definition = {"id": _id(), "kind": panel["kind"], "axes": [compatible[field] for field in panel["axes"]]}
            if "normalization" in panel:
                definition["normalization"] = panel["normalization"]
            panels.append(definition)
        try:
            with closing(open_project(database_path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                if panels:
                    plot = save_plot_specification(database_path, name, analysis_ids, panels, {}, [], [], transaction=connection)
                elif version == 2:
                    _layout_input(connection, analysis_ids)
                if template["table_columns"]:
                    columns = [{**column, "width_px": None} for column in template["table_columns"]]
                    table = save_table_view(database_path, name, columns, template["table_sort"], [], transaction=connection)
        except ImportCommandError as error:
            if error.code not in {"PLOT_TERNARY_INCOMPATIBLE_AXES", "PLOT_PATTERN_INCOMPATIBLE_AXES",
                                  "PLOT_LAYOUT_AXES_UNAVAILABLE", "PLOT_LAYOUT_INPUT_UNAVAILABLE"}:
                raise
            field = "analysis_ids" if error.code == "PLOT_LAYOUT_INPUT_UNAVAILABLE" else "panel_templates"
            report.append({"field": field, "action": "blocked", "reason": error.message})
    result = {"plot": plot, "migration_report": report}
    if version == 2:
        result.update(table_view=table, method_plans=methods if not any(item["action"] == "blocked" for item in report) else [])
    return result


def _review_template_method(database_path, method, analysis_ids, compatible):
    if (method["method_id"], method["method_version"]) != (_METHOD["method_id"], _METHOD["version"]):
        return None, "Версия статистического метода несовместима."
    settings = method["parameters"]
    features = [compatible[field] for field in settings["features"]]
    requested = {"kind": "analysis_snapshot", "analysis_ids": analysis_ids}
    try:
        review = review_statistics(database_path, requested, features)
    except ImportCommandError as error:
        return None, error.message
    domain = review["domain"]
    if settings["transform"] == "euclidean":
        if not domain["euclidean_available"] or (domain["mixed_units"] and settings["scaling"] == "none"):
            return None, "Единицы несовместимы с выбранным масштабированием."
        count = review["complete_count"]
    else:
        if not domain["logratio_available"]:
            return None, "Выбранные поля не образуют совместимый состав для CLR или ILR."
        count = review["positive_complete_count"]
    if count < settings["clusters"]:
        return None, "После исключений недостаточно анализов для выбранного числа кластеров."
    return {"method_id": method["method_id"], "method_version": method["method_version"], "input": requested,
            "features": features, "parameters": {key: settings[key] for key in _METHOD_PARAMETERS},
            "review_fingerprint": review["input_fingerprint"]}, None
