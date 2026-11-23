"""Versioned NDJSON boundary between the desktop shell and application services."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable, Mapping
from typing import Any, TextIO

from .clean_table import classify_clean_table
from .import_workspace import ImportWorkspaceStore
from .work_groups import create_work_group, list_work_groups
from .selection_export import export_selection_csv, export_selection_xlsx
from .table_views import list_table_views, save_table_view
from .edit_drafts import check_edit_draft, commit_edit_draft, list_edit_drafts, save_edit_draft
from .project_navigation import project_overview, search_analyses
from .sample_workspace import add_sample_note, change_point_link, get_point_analyses, get_project_sample, list_project_samples, save_sample_context
from .manual_analysis import create_manual_analysis
from .media_links import change_media_link, create_media_region, import_linked_photo, list_media_links
from .plot_data import list_plot_specifications, open_plot_specification, plot_catalog, query_plot_data, record_plot_visibility, save_plot_specification
from .plot_export import export_plot
from .desktop_workflow import apply_bulk_ignore_scope, apply_bulk_unit_scope, bulk_ignore_scopes, bulk_unit_scopes, list_project_analyses, list_project_mineral_identifications, suggest_import_recipe
from .import_apply import (
    apply_import_plan,
    check_linked_source,
    retract_latest_import,
    rollback_incomplete_batch,
    save_import_recipe_revision,
)
from .import_preview import (
    ImportCommandError,
    inspect_source,
    run_import_inspect_source,
    run_import_plan_create,
    run_import_preview_window,
    run_import_recipe_validate,
)
from .manual_mapping import review_duplicate_candidates, revise_import_mapping, revise_import_mappings, revise_import_sections
from .media_import import (apply_media_import_plan, create_analytical_point, create_media_import_plan, inspect_media_folder,
                           inspect_media_sources, load_media_import_draft, save_media_import_draft)
from .media_display import export_media_batch, export_media_original, export_media_rendered, preview_input_media, preview_project_media
from .statistics_service import list_calculation_runs, open_calculation_run, review_statistics, run_clustering, save_calculated_cluster
from .formula_service import list_formula_runs, open_formula_run, review_formula, run_formula
from .olivine_formula import OLIVINE
from .publication import (
    capture_publication_media, capture_publication_plot, capture_publication_table, export_publication,
    prepare_publication, publication_catalog,
)
from .project_archive import export_project_archive, restore_project_archive
from .workspace_snapshots import apply_analysis_template, list_workspace_snapshots, open_workspace_snapshot, save_analysis_template, save_workspace_snapshot


PROTOCOL_VERSION = "1.0"


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _source_path(params: Mapping[str, Any]) -> str:
    path = params.get("source_path")
    if not isinstance(path, str) or not path:
        raise ValueError("source_path")
    return path


def _recipe(params: Mapping[str, Any]) -> dict[str, Any]:
    recipe = params.get("recipe")
    if not isinstance(recipe, dict):
        raise ValueError("recipe")
    return recipe


def _project_database_path(params: Mapping[str, Any]) -> str:
    path = params.get("project_database_path")
    if not isinstance(path, str) or not path:
        raise ValueError("project_database_path")
    return path


def _source_id(params: Mapping[str, Any]) -> str:
    source_id = params.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id")
    return source_id


def _import_batch_id(params: Mapping[str, Any]) -> str:
    import_batch_id = params.get("import_batch_id")
    if not isinstance(import_batch_id, str) or not import_batch_id:
        raise ValueError("import_batch_id")
    return import_batch_id


def _optional_supersedes_revision_id(params: Mapping[str, Any]) -> str | None:
    value = params.get("supersedes_recipe_revision_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("supersedes_recipe_revision_id")
    return value


def _string(params: Mapping[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value


def _integer(params: Mapping[str, Any], name: str) -> int:
    value = params.get(name)
    if not isinstance(value, int):
        raise ValueError(name)
    return value


def _optional_string(params: Mapping[str, Any], name: str) -> str | None:
    value = params.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(name)
    return value


def _string_list(params: Mapping[str, Any], name: str) -> list[str]:
    value = params.get(name)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(name)
    return value


def _object_list(params: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    value = params.get(name)
    if not isinstance(value, list) or not value or not all(isinstance(item, dict) for item in value):
        raise ValueError(name)
    return value


def _object(params: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = params.get(name)
    if not isinstance(value, dict):
        raise ValueError(name)
    return value


def _dispatch_import_inspect(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_inspect_source(_source_path(params))


def _dispatch_import_clean_table_classify(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": classify_clean_table(inspect_source(_source_path(params)))}


def _dispatch_import_preview_window(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_preview_window(
        _source_path(params),
        _string(params, "sheet_name"),
        _integer(params, "start_row"),
        int(params.get("row_count", 12)),
        int(params.get("start_column", 0)),
        int(params.get("column_count", 24)),
    )


def _dispatch_recipe_suggest(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": suggest_import_recipe(_source_path(params))}


def _dispatch_recipe_bulk_scopes(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": bulk_unit_scopes(_source_path(params), _recipe(params))}


def _dispatch_recipe_apply_bulk_unit(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_bulk_unit_scope(
        _source_path(params), _recipe(params), _string(params, "bulk_scope_id"), _string(params, "unit")
    )}


def _dispatch_recipe_bulk_ignore_scopes(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": bulk_ignore_scopes(_source_path(params), _recipe(params))}


def _dispatch_recipe_apply_bulk_ignore(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_bulk_ignore_scope(
        _source_path(params), _recipe(params), _string(params, "bulk_scope_id")
    )}


def _dispatch_recipe_revise_mapping(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": revise_import_mapping(
        _source_path(params),
        _recipe(params),
        _string(params, "sheet_name"),
        _integer(params, "source_column_index"),
        _string(params, "target"),
        _optional_string(params, "canonical_field"),
        _optional_string(params, "unit"),
    )}


def _dispatch_recipe_revise_mappings(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": revise_import_mappings(
        _source_path(params),
        _recipe(params),
        _object_list(params, "decisions"),
    )}


def _dispatch_recipe_revise_sections(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": revise_import_sections(
        _source_path(params),
        _recipe(params),
        _object_list(params, "decisions"),
    )}


def _dispatch_recipe_review_duplicates(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": review_duplicate_candidates(
        _source_path(params),
        _recipe(params),
        _string(params, "decision"),
    )}


def _dispatch_recipe_validate(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_recipe_validate(_source_path(params), _recipe(params))


def _dispatch_plan_create(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_plan_create(_source_path(params), _recipe(params))


def _dispatch_plan_apply(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_import_plan(_project_database_path(params), _source_path(params), _recipe(params))}


def _dispatch_project_analyses_list(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_limit = params.get("limit", 500)
    raw_offset = params.get("offset", 0)
    if not isinstance(raw_limit, int) or not isinstance(raw_offset, int):
        raise ValueError("limit")
    return {"result": list_project_analyses(_project_database_path(params), raw_limit, raw_offset)}


def _dispatch_analysis_get(params: Mapping[str, Any]) -> dict[str, Any]:
    analysis_id = params.get("analysis_id")
    if not isinstance(analysis_id, str) or str(uuid.UUID(analysis_id)) != analysis_id:
        raise ValueError("analysis_id")
    analyses = list_project_analyses(_project_database_path(params), 1, analysis_id=analysis_id)["analyses"]
    if not analyses:
        raise ImportCommandError("ANALYSIS_NOT_FOUND", "Анализ больше недоступен.")
    return {"result": analyses[0]}


def _dispatch_project_mineral_identification_list(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_limit = params.get("limit", 500)
    raw_offset = params.get("offset", 0)
    if not isinstance(raw_limit, int) or not isinstance(raw_offset, int):
        raise ValueError("limit")
    return {"result": list_project_mineral_identifications(_project_database_path(params), raw_limit, raw_offset)}


def _dispatch_project_last_import_retract(params: Mapping[str, Any]) -> dict[str, Any]:
    reason = params.get("reason", "user_retracted")
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason")
    return {"result": retract_latest_import(_project_database_path(params), reason)}


def _dispatch_linked_source_check(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": check_linked_source(_project_database_path(params), _source_id(params))}


def _dispatch_batch_rollback(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": rollback_incomplete_batch(_project_database_path(params), _import_batch_id(params))}


def _dispatch_recipe_save_revision(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": save_import_recipe_revision(
        _project_database_path(params), _source_id(params), _recipe(params), _optional_supersedes_revision_id(params)
    )}


def _dispatch_analytical_point_create(params: Mapping[str, Any]) -> dict[str, Any]:
    sample_id = params.get("sample_id")
    return {"result": create_analytical_point(
        _project_database_path(params),
        _string(params, "sample_name") if sample_id is None else "",
        _string(params, "point_name"),
        _string_list(params, "analysis_ids"),
        _string(params, "link_type"),
        sample_id=sample_id, actor=params.get("actor"),
    )}


def _dispatch_media_inspect(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": inspect_media_sources(_string_list(params, "source_paths"))}


def _dispatch_media_plan(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": create_media_import_plan(_project_database_path(params), _object_list(params, "assignments"))}


def _dispatch_media_apply(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_media_import_plan(_project_database_path(params), _object(params, "plan"),
                                              draft_fingerprint=params.get("draft_fingerprint"))}


COMMANDS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "workspace.snapshot.save": lambda params: {"result": save_workspace_snapshot(
        _project_database_path(params), params.get("name"), params.get("state"),
    )},
    "workspace.snapshot.list": lambda params: {"result": list_workspace_snapshots(_project_database_path(params))},
    "workspace.snapshot.open": lambda params: {"result": open_workspace_snapshot(
        _project_database_path(params), params.get("id"),
    )},
    "workspace.template.save": lambda params: {"result": save_analysis_template(
        _project_database_path(params), params.get("name"), params.get("plot_id"),
        params.get("table_view_id"), params.get("calculation_run_id"),
    )},
    "workspace.template.apply": lambda params: {"result": apply_analysis_template(
        _project_database_path(params), params.get("id"), params.get("analysis_ids"), params.get("name"),
    )},
    "project.archive.export": lambda params: {"result": export_project_archive(
        _project_database_path(params), params.get("output_path"), params.get("level"),
    )},
    "project.archive.restore": lambda params: {"result": restore_project_archive(
        params.get("archive_path"), params.get("destination_path"),
    )},
    "publication.catalog": lambda params: {"result": publication_catalog(_project_database_path(params))},
    "publication.capture_plot": lambda params: {"result": capture_publication_plot(
        _project_database_path(params), params.get("capture"), params.get("caption", ""),
    )},
    "publication.capture_table": lambda params: {"result": capture_publication_table(
        _project_database_path(params), params.get("analysis_ids"),
    )},
    "publication.capture_media": lambda params: {"result": capture_publication_media(
        _project_database_path(params), params.get("media_asset_id"), params.get("options"),
    )},
    "plot.export": lambda params: {"result": export_plot(
        params.get("svg"), params.get("format"), params.get("output_path"), params.get("width_mm"), params.get("dpi"),
    )},
    "publication.prepare": lambda params: {"result": prepare_publication(
        _project_database_path(params), params.get("name"), params.get("items"),
        params.get("profile", "neutral"), params.get("width_mm"),
    )},
    "publication.export": lambda params: {"result": export_publication(
        _project_database_path(params), params.get("name"), params.get("items"),
        params.get("expected_fingerprint"), params.get("output_path"),
        params.get("profile", "neutral"), params.get("width_mm"),
    )},
    "statistics.review": lambda params: {"result": review_statistics(
        _project_database_path(params), params.get("input"), params.get("features"),
    )},
    "statistics.cluster.run": lambda params: {"result": run_clustering(
        _project_database_path(params), params.get("input"), params.get("features"),
        params.get("review_fingerprint"), params.get("parameters"),
    )},
    "statistics.cluster.save_group": lambda params: {"result": save_calculated_cluster(
        _project_database_path(params), params.get("run_id"), params.get("cluster"), params.get("name"), params.get("actor"),
    )},
    "formula.methods.list": lambda _: {"result": [OLIVINE]},
    "formula.review": lambda params: {"result": review_formula(_project_database_path(params), params.get("method_id"),
        params.get("analysis_id"), params.get("measurement_ids"))},
    "formula.run": lambda params: {"result": run_formula(_project_database_path(params), params.get("method_id"),
        params.get("analysis_id"), params.get("measurement_ids"), params.get("input_fingerprint"), params.get("method_definition_fingerprint"))},
    "formula.run.open": lambda params: {"result": open_formula_run(_project_database_path(params), params.get("run_id"))},
    "formula.runs.list": lambda params: {"result": list_formula_runs(_project_database_path(params), params.get("analysis_id"))},
    "statistics.runs.list": lambda params: {"result": list_calculation_runs(_project_database_path(params))},
    "statistics.run.open": lambda params: {"result": open_calculation_run(_project_database_path(params), params.get("run_id"))},
    "plot_spec.save": lambda params: {"result": save_plot_specification(
        _project_database_path(params), params.get("name"), params.get("analysis_ids"), params.get("panels"),
        params.get("colors"), params.get("hidden_analysis_ids", []), params.get("hidden_source_ids", []),
        params.get("layers"),
    )},
    "plot_spec.list": lambda params: {"result": list_plot_specifications(_project_database_path(params))},
    "plot_spec.open": lambda params: {"result": open_plot_specification(_project_database_path(params), params.get("id"))},
    "plot_visibility.hide": lambda params: {"result": record_plot_visibility(
        _project_database_path(params), params.get("analysis_ids"), True,
    )},
    "plot_visibility.restore": lambda params: {"result": record_plot_visibility(
        _project_database_path(params), params.get("analysis_ids"), False,
    )},
    "plot_data.catalog": lambda params: {"result": plot_catalog(_project_database_path(params), params.get("analysis_ids"))},
    "plot_data.query": lambda params: {"result": query_plot_data(
        _project_database_path(params), params.get("kind"), params.get("axes"), params.get("analysis_ids"),
        params.get("hidden_analysis_ids"), params.get("hidden_source_ids"), params.get("layers"),
        normalization=params.get("normalization"),
    )},
    "project.overview": lambda params: {"result": project_overview(_project_database_path(params))},
    "project.samples.list": lambda params: {"result": list_project_samples(_project_database_path(params))},
    "project.sample.get": lambda params: {"result": get_project_sample(_project_database_path(params), params.get("sample_id"))},
    "project.sample.context.save": lambda params: {"result": save_sample_context(
        _project_database_path(params), params.get("sample_id"), params.get("context"), params.get("expected_revision"),
    )},
    "project.sample.note.add": lambda params: {"result": add_sample_note(
        _project_database_path(params), params.get("sample_id"), params.get("author"), params.get("body"),
    )},
    "analytical_point.analyses": lambda params: {"result": get_point_analyses(
        _project_database_path(params), params.get("point_id"),
    )},
    "analytical_point.analysis.create_manual": lambda params: {"result": create_manual_analysis(
        _project_database_path(params), params.get("point_id"), params.get("entry"),
    )},
    "analytical_point.link.set": lambda params: {"result": change_point_link(
        _project_database_path(params), params.get("point_id"), params.get("analysis_id"), params.get("actor"), params.get("link_type"),
        analysis_ids=params.get("analysis_ids"),
    )},
    "media.preview_input": lambda params: {"result": preview_input_media(
        _source_path(params), params.get("region"), params.get("expected_fingerprint"),
    )},
    "media.region.create": lambda params: {"result": create_media_region(
        _project_database_path(params), params.get("media_asset_id"), params.get("geometry"),
    )},
    "media.links.list": lambda params: {"result": list_media_links(_project_database_path(params), params.get("spatial_annotation_id"))},
    "media.link.set": lambda params: {"result": change_media_link(
        _project_database_path(params), params.get("spatial_annotation_id"), params.get("media_asset_id"), params.get("attached"),
    )},
    "media.link.import_photo": lambda params: {"result": import_linked_photo(
        _project_database_path(params), params.get("spatial_annotation_id"), _source_path(params), params.get("media_type"), params.get("expected_fingerprint"),
    )},
    "media.preview": lambda params: {"result": preview_project_media(
        _project_database_path(params), params.get("media_asset_id"), params.get("region"),
    )},
    "media.export_original": lambda params: {"result": export_media_original(
        _project_database_path(params), params.get("media_asset_id"), params.get("output_path"),
    )},
    "media.export_rendered": lambda params: {"result": export_media_rendered(
        _project_database_path(params), params.get("media_asset_id"), params.get("output_path"), params.get("options"),
    )},
    "media.export_batch": lambda params: {"result": export_media_batch(
        _project_database_path(params), params.get("media_asset_ids"), params.get("output_path"), params.get("options"),
    )},
    "analysis.query": lambda params: {"result": search_analyses(
        _project_database_path(params), **{key: params[key] for key in ("query", "mineral", "source", "method", "source_id", "sample_id", "limit", "offset") if key in params},
    )},
    "project.analysis.get": _dispatch_analysis_get,
    "edit_draft.commit": lambda params: {"result": commit_edit_draft(
        _project_database_path(params), params.get("draft_id"), params.get("actor"), params.get("reason"),
    )},
    "edit_draft.save": lambda params: {"result": save_edit_draft(
        _project_database_path(params), params.get("measurement_id"), params.get("new_value", {}),
    )},
    "edit_draft.list": lambda params: {"result": list_edit_drafts(_project_database_path(params), params.get("analysis_id"))},
    "edit_draft.check": lambda params: {"result": check_edit_draft(_project_database_path(params), params.get("draft_id"))},
    "table_view.save": lambda params: {"result": save_table_view(
        _project_database_path(params), params.get("name"), params.get("columns"),
        params.get("sort"), params.get("filters"),
    )},
    "table_view.list": lambda params: {"result": list_table_views(_project_database_path(params))},
    "analysis.selection.export_xlsx": lambda params: {"result": export_selection_xlsx(
        _project_database_path(params), params.get("analysis_ids"), params.get("output_path"),
    )},
    "analysis.selection.export_csv": lambda params: {"result": export_selection_csv(
        _project_database_path(params), params.get("analysis_ids"), params.get("output_path"),
    )},
    "work_group.create": lambda params: {"result": create_work_group(
        _project_database_path(params), params.get("name"), params.get("analysis_ids"),
        params.get("created_by"), params.get("description", ""),
    )},
    "work_group.list": lambda params: {"result": list_work_groups(_project_database_path(params))},
    "import.inspect_source": _dispatch_import_inspect,
    "import.clean_table.classify": _dispatch_import_clean_table_classify,
    "import.preview.window": _dispatch_import_preview_window,
    "import.recipe.suggest": _dispatch_recipe_suggest,
    "import.recipe.bulk_scopes": _dispatch_recipe_bulk_scopes,
    "import.recipe.apply_bulk_unit": _dispatch_recipe_apply_bulk_unit,
    "import.recipe.bulk_ignore_scopes": _dispatch_recipe_bulk_ignore_scopes,
    "import.recipe.apply_bulk_ignore": _dispatch_recipe_apply_bulk_ignore,
    "import.recipe.revise_mapping": _dispatch_recipe_revise_mapping,
    "import.recipe.revise_mappings": _dispatch_recipe_revise_mappings,
    "import.recipe.revise_sections": _dispatch_recipe_revise_sections,
    "import.recipe.review_duplicates": _dispatch_recipe_review_duplicates,
    "import.recipe.validate": _dispatch_recipe_validate,
    "import.plan.create": _dispatch_plan_create,
    "import.plan.apply": _dispatch_plan_apply,
    "project.analyses.list": _dispatch_project_analyses_list,
    "project.mineral_identification.list": _dispatch_project_mineral_identification_list,
    "project.last_import.retract": _dispatch_project_last_import_retract,
    "source.check_linked": _dispatch_linked_source_check,
    "import.batch.rollback": _dispatch_batch_rollback,
    "import.recipe.save_revision": _dispatch_recipe_save_revision,
    "analytical_point.create": _dispatch_analytical_point_create,
    "media.inspect_sources": _dispatch_media_inspect,
    "media.inspect_folder": lambda params: {"result": inspect_media_folder(_string(params, "folder"))},
    "media.import.plan": _dispatch_media_plan,
    "media.import.apply": _dispatch_media_apply,
    "media.import.draft.load": lambda params: {"result": load_media_import_draft(_project_database_path(params))},
    "media.import.draft.save": lambda params: {"result": save_media_import_draft(
        _project_database_path(params), _object(params, "plan"), params.get("expected_fingerprint"),
    )},
}

WORKSPACES = ImportWorkspaceStore()
for _operation in ('create', 'restore', 'add_sources', 'get', 'preview_window', 'apply_decision', 'apply_bulk_decision', 'replan', 'discard', 'commit'):
    COMMANDS[f'import.workspace.{_operation}'] = lambda params, operation=_operation: {'result': WORKSPACES.command(operation, params)}


def handle_request(request: object) -> dict[str, Any]:
    if not isinstance(request, dict):
        return _error("INVALID_REQUEST", "Request must be a JSON object.")
    unexpected = sorted(set(request) - {"protocol_version", "request_id", "command", "payload"})
    if unexpected:
        return _error("INVALID_REQUEST", "Request contains unsupported envelope fields.", {"fields": unexpected})
    if "payload" not in request or not isinstance(request["payload"], dict):
        return _error("INVALID_REQUEST", "payload must be a JSON object.")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return _error("INVALID_REQUEST", "request_id must be a non-empty string.")
    try:
        uuid.UUID(request_id)
    except ValueError:
        return _error("INVALID_REQUEST", "request_id must be a UUID.")
    envelope: dict[str, Any] = {"protocol_version": PROTOCOL_VERSION, "request_id": request_id}
    if request.get("protocol_version") != PROTOCOL_VERSION:
        return envelope | _error(
            "PROTOCOL_VERSION_UNSUPPORTED",
            "Request protocol version is not supported.",
            {"supported_protocol_version": PROTOCOL_VERSION},
        )
    command = request.get("command")
    params = request["payload"]
    if not isinstance(command, str) or command not in COMMANDS:
        return envelope | _error("UNKNOWN_COMMAND", "Command is not available.", {"command": command})
    try:
        return envelope | COMMANDS[command](params)
    except ImportCommandError as exc:
        return envelope | exc.projection()
    except ValueError as exc:
        return envelope | _error("INVALID_REQUEST", "Required command parameter is invalid.", {"parameter": str(exc)})
    except Exception:
        return envelope | _error("INTERNAL_ERROR", "Command failed unexpectedly.")


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
    for line in input_stream:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = _error("INVALID_REQUEST", "Request is not valid JSON.")
        else:
            if isinstance(request, dict) and request.get("command") == "shutdown":
                request_id = request.get("request_id")
                unexpected = sorted(set(request) - {"protocol_version", "request_id", "command", "payload"})
                if unexpected or "payload" not in request or not isinstance(request["payload"], dict):
                    response = _error("INVALID_REQUEST", "Shutdown request has an invalid envelope.")
                elif not isinstance(request_id, str) or not request_id:
                    response = _error("INVALID_REQUEST", "request_id must be a non-empty string.")
                else:
                    try:
                        uuid.UUID(request_id)
                    except ValueError:
                        response = _error("INVALID_REQUEST", "request_id must be a UUID.")
                    else:
                        response = None
                if response is None and request.get("protocol_version") != PROTOCOL_VERSION:
                    response = {
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": request_id,
                    } | _error(
                        "PROTOCOL_VERSION_UNSUPPORTED",
                        "Request protocol version is not supported.",
                        {"supported_protocol_version": PROTOCOL_VERSION},
                    )
                elif response is None:
                    response = {"protocol_version": PROTOCOL_VERSION, "request_id": request_id, "result": {"status": "shutting_down"}}
                output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                output_stream.flush()
                return
            response = handle_request(request)
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()


if __name__ == "__main__":
    serve()
