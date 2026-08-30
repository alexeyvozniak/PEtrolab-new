"""Versioned NDJSON boundary between the desktop shell and application services."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable, Mapping
from typing import Any, TextIO

from .desktop_workflow import list_project_analyses, suggest_import_recipe
from .import_apply import (
    apply_import_plan,
    check_linked_source,
    retract_latest_import,
    rollback_incomplete_batch,
    save_import_recipe_revision,
)
from .import_preview import (
    ImportCommandError,
    run_import_inspect_source,
    run_import_plan_create,
    run_import_preview_window,
    run_import_recipe_validate,
)
from .manual_mapping import revise_import_mapping, revise_import_mappings, revise_import_sections
from .media_import import apply_media_import_plan, create_analytical_point, create_media_import_plan, inspect_media_sources


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


def _dispatch_recipe_validate(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_recipe_validate(_source_path(params), _recipe(params))


def _dispatch_plan_create(params: Mapping[str, Any]) -> dict[str, Any]:
    return run_import_plan_create(_source_path(params), _recipe(params))


def _dispatch_plan_apply(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_import_plan(_project_database_path(params), _source_path(params), _recipe(params))}


def _dispatch_project_analyses_list(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_limit = params.get("limit", 500)
    if not isinstance(raw_limit, int):
        raise ValueError("limit")
    return {"result": list_project_analyses(_project_database_path(params), raw_limit)}


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
    return {"result": create_analytical_point(
        _project_database_path(params),
        _string(params, "sample_name"),
        _string(params, "point_name"),
        _string_list(params, "analysis_ids"),
        _string(params, "link_type"),
    )}


def _dispatch_media_inspect(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": inspect_media_sources(_string_list(params, "source_paths"))}


def _dispatch_media_plan(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": create_media_import_plan(_project_database_path(params), _object_list(params, "assignments"))}


def _dispatch_media_apply(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"result": apply_media_import_plan(_project_database_path(params), _object(params, "plan"))}


COMMANDS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "import.inspect_source": _dispatch_import_inspect,
    "import.preview.window": _dispatch_import_preview_window,
    "import.recipe.suggest": _dispatch_recipe_suggest,
    "import.recipe.revise_mapping": _dispatch_recipe_revise_mapping,
    "import.recipe.revise_mappings": _dispatch_recipe_revise_mappings,
    "import.recipe.revise_sections": _dispatch_recipe_revise_sections,
    "import.recipe.validate": _dispatch_recipe_validate,
    "import.plan.create": _dispatch_plan_create,
    "import.plan.apply": _dispatch_plan_apply,
    "project.analyses.list": _dispatch_project_analyses_list,
    "project.last_import.retract": _dispatch_project_last_import_retract,
    "source.check_linked": _dispatch_linked_source_check,
    "import.batch.rollback": _dispatch_batch_rollback,
    "import.recipe.save_revision": _dispatch_recipe_save_revision,
    "analytical_point.create": _dispatch_analytical_point_create,
    "media.inspect_sources": _dispatch_media_inspect,
    "media.import.plan": _dispatch_media_plan,
    "media.import.apply": _dispatch_media_apply,
}


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
