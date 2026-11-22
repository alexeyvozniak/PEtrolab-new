"""Project-bound table view settings, independent of analysis selection."""

from contextlib import closing, nullcontext
from hashlib import sha256
import json
from uuid import UUID

from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError


def _fingerprint(connection):
    rows = connection.execute("""
        SELECT b.import_batch_id, b.source_fingerprint_sha256, b.recipe_revision_id
        FROM import_batch b LEFT JOIN import_batch_retraction r USING (import_batch_id)
        WHERE b.status = 'applied' AND r.import_batch_id IS NULL ORDER BY b.import_batch_id
    """)
    return sha256(json.dumps([tuple(row) for row in rows], separators=(",", ":")).encode()).hexdigest()


def _validate_layout(columns, sort, filters):
    if not isinstance(columns, list) or not columns:
        raise ValueError("columns")
    fields = []
    for position, column in enumerate(columns):
        if (not isinstance(column, dict) or set(column) != {"field", "order", "visible", "width_px"}
                or not isinstance(column["field"], str) or not column["field"]
                or type(column["order"]) is not int or column["order"] != position
                or type(column["visible"]) is not bool or column["width_px"] is not None):
            raise ValueError("columns")
        fields.append(column["field"])
    if len(set(fields)) != len(fields) or not any(column["visible"] for column in columns):
        raise ValueError("columns")
    if (not isinstance(sort, list) or len(sort) != 1 or not isinstance(sort[0], dict)
            or set(sort[0]) != {"field", "direction"} or sort[0]["field"] not in fields
            or sort[0]["direction"] not in ("ascending", "descending")):
        raise ValueError("sort")
    if not isinstance(filters, list):
        raise ValueError("filters")
    operators = {"query": "contains", "source": "equals", "sheet": "equals",
                 "mineral-status": "in", "sample-link": "equals"}
    seen = set()
    for rule in filters:
        if not isinstance(rule, dict) or set(rule) != {"id", "field", "operator", "value", "enabled"}:
            raise ValueError("filters")
        field, value = rule["field"], rule["value"]
        if (not isinstance(field, str) or field in seen or rule["enabled"] is not True
                or not isinstance(rule["id"], str) or str(UUID(rule["id"])) != rule["id"]):
            raise ValueError("filters")
        if field.startswith("column:") and field[7:] in fields:
            accepted = ("contains", "measurement_expression") if field[7:].startswith("measurement:") else ("contains",)
        else:
            accepted = (operators.get(field),) if field in operators else ()
        if rule["operator"] not in accepted:
            raise ValueError("filters")
        if field == "mineral-status":
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                raise ValueError("filters")
        elif not isinstance(value, str) or not value.strip() or (field == "sample-link" and value not in ("linked", "unlinked")):
            raise ValueError("filters")
        seen.add(field)


def save_table_view(database_path, name, columns, sort, filters, *, transaction=None):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ImportCommandError("TABLE_VIEW_NAME_INVALID", "Введите название представления до 120 символов.")
    _validate_layout(columns, sort, filters)
    with (closing(open_project(database_path)) if transaction is None else nullcontext(transaction)) as connection:
        with (connection if transaction is None else nullcontext()):
            if transaction is None:
                connection.execute("BEGIN IMMEDIATE")
            return _insert_table_view(connection, name, columns, sort, filters)


def _insert_table_view(connection, name, columns, sort, filters):
    if connection.execute("SELECT 1 FROM table_view WHERE name = ?", (name.strip(),)).fetchone():
        raise ImportCommandError("TABLE_VIEW_NAME_EXISTS", "Представление с таким названием уже есть.")
    view = {
        "id": _id(), "name": name.strip(), "data_universe_fingerprint": _fingerprint(connection),
        "project_id": connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0],
        "columns": columns, "sort": sort, "filters": filters, "group_by": None,
        "created_at": _now(), "updated_at": _now(),
    }
    connection.execute("INSERT INTO table_view (id, name, definition_json) VALUES (?, ?, ?)",
                       (view["id"], view["name"], json.dumps(view, ensure_ascii=False)))
    return view


def list_table_views(database_path):
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        fingerprint = _fingerprint(connection)
        views = [json.loads(row[0]) for row in connection.execute("SELECT definition_json FROM table_view ORDER BY name, id")]
        return {"views": views, "data_universe_fingerprint": fingerprint}
