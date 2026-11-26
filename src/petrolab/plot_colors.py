"""Explicit project-scoped view preferences, never scientific data."""
from contextlib import closing
import json
import re
from uuid import UUID
from .import_apply import open_project
from .import_preview import ImportCommandError
from .plot_symbols import PLOT_SYMBOLS

_MODES = {"source", "sample", "mineral", "generation"}

def _validate(scheme):
    if not isinstance(scheme, dict) or set(scheme) != {"mode", "colors"} or scheme["mode"] not in _MODES:
        raise ValueError("plot_color_scheme")
    colors = scheme["colors"]
    if not isinstance(colors, list) or len(colors) > 4000:
        raise ValueError("plot_colors")
    seen = set()
    for entry in colors:
        if not isinstance(entry, dict) or set(entry) - {"symbol"} != {"mode", "key", "color"}:
            raise ValueError("plot_color_entry")
        mode, key, color = entry["mode"], entry["key"], entry["color"]
        if mode not in _MODES or not isinstance(key, str) or not 1 <= len(key) <= 512:
            raise ValueError("plot_color_key")
        if mode != "mineral" and str(UUID(key)) != key:
            raise ValueError("plot_color_id")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color) or (mode,key) in seen:
            raise ValueError("plot_color_value")
        if "symbol" in entry and entry["symbol"] not in PLOT_SYMBOLS:
            raise ValueError("plot_symbol")
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

def _validate_presets(preferences):
    from .plot_data import _AXIS_FIELDS, _plot_keys
    from .trace_patterns import PATTERN_ORDERS, pattern_reference
    if not isinstance(preferences, dict) or set(preferences) != {"favorites", "recent"}:
        raise ValueError("plot_presets")
    validated = {}
    for group, limit in (("favorites", 24), ("recent", 12)):
        items = preferences[group]
        if not isinstance(items, list) or len(items) > limit:
            raise ValueError("plot_presets")
        seen = set()
        validated[group] = []
        for item in items:
            if not isinstance(item, dict) or set(item) - {"normalization"} != {"kind", "keys"}:
                raise ValueError("plot_preset")
            if not isinstance(item["keys"], list) or not 1 <= len(item["keys"]) <= 64:
                raise ValueError("plot_preset_keys")
            if not isinstance(item["kind"], str):
                raise ValueError("plot_preset_kind")
            axes = []
            for key in item["keys"]:
                if not isinstance(key, str) or len(key) > 4096:
                    raise ValueError("plot_preset_key")
                values = json.loads(key)
                if not isinstance(values, list) or len(values) != 4:
                    raise ValueError("plot_preset_key")
                axes.append(dict(zip(_AXIS_FIELDS, values)))
            keys = _plot_keys(item["kind"], axes)
            normalization = item.get("normalization")
            if item["kind"] in PATTERN_ORDERS:
                if not isinstance(normalization, str):
                    raise ValueError("plot_preset_normalization")
                pattern_reference(item["kind"], [key[0] for key in keys], normalization)
            elif "normalization" in item:
                raise ValueError("plot_preset_normalization")
            signature = (item["kind"], tuple(keys), normalization)
            if signature in seen:
                raise ValueError("plot_preset_duplicate")
            seen.add(signature)
            validated[group].append(item)
    return validated


def _read_presets(connection):
    row = connection.execute("SELECT definition_json, revision FROM project_plot_presets WHERE singleton=1").fetchone()
    return {"preferences": _validate_presets(json.loads(row[0])), "revision": row[1]} if row else {
        "preferences": {"favorites": [], "recent": []}, "revision": 0}


def get_project_plot_presets(database_path):
    with closing(open_project(database_path)) as connection:
        return _read_presets(connection)


def save_project_plot_presets(database_path, preferences, expected_revision):
    preferences = _validate_presets(preferences)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("plot_preset_revision")
    with closing(open_project(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _read_presets(connection)
        if current["revision"] != expected_revision:
            raise ImportCommandError("PLOT_PRESET_REVISION_CONFLICT", "Избранное изменилось. Загрузите сохранённые комбинации повторно.")
        revision = expected_revision + 1
        connection.execute("""INSERT INTO project_plot_presets VALUES (1, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET definition_json=excluded.definition_json,revision=excluded.revision""",
            (json.dumps(preferences, ensure_ascii=False), revision))
        return {"preferences": preferences, "revision": revision}
