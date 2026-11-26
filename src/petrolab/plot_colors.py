"""Explicit project-scoped view preferences, never scientific data."""
from contextlib import closing
import json
import re
from uuid import UUID
from .import_apply import open_project
from .import_preview import ImportCommandError

_MODES = {"source", "sample", "mineral", "generation"}

def _validate(scheme):
    if not isinstance(scheme, dict) or set(scheme) != {"mode", "colors"} or scheme["mode"] not in _MODES:
        raise ValueError("plot_color_scheme")
    colors = scheme["colors"]
    if not isinstance(colors, list) or len(colors) > 4000:
        raise ValueError("plot_colors")
    seen = set()
    for entry in colors:
        if not isinstance(entry, dict) or set(entry) != {"mode", "key", "color"}:
            raise ValueError("plot_color_entry")
        mode, key, color = entry["mode"], entry["key"], entry["color"]
        if mode not in _MODES or not isinstance(key, str) or not 1 <= len(key) <= 512:
            raise ValueError("plot_color_key")
        if mode != "mineral" and str(UUID(key)) != key:
            raise ValueError("plot_color_id")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color) or (mode,key) in seen:
            raise ValueError("plot_color_value")
        seen.add((mode,key))
    return {"mode": scheme["mode"], "colors": [{**entry,"color":entry["color"].lower()} for entry in colors]}

def _read(connection):
    row = connection.execute("SELECT definition_json, revision FROM project_plot_colors WHERE singleton=1").fetchone()
    return {"scheme": _validate(json.loads(row[0])), "revision": row[1]} if row else {"scheme":{"mode":"source","colors":[]},"revision":0}

def get_project_plot_colors(database_path):
    with closing(open_project(database_path)) as connection:
        return _read(connection)

def save_project_plot_colors(database_path, scheme, expected_revision):
    scheme = _validate(scheme)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("plot_color_revision")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _read(connection)
        if current["revision"] != expected_revision:
            raise ImportCommandError("PLOT_COLOR_REVISION_CONFLICT", "Цветовая схема уже изменена. Загрузите сохранённую схему повторно.")
        revision = expected_revision + 1
        connection.execute("""INSERT INTO project_plot_colors VALUES (1, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET definition_json=excluded.definition_json,revision=excluded.revision""",
            (json.dumps(scheme, ensure_ascii=False),revision))
        return {"scheme":scheme,"revision":revision}
