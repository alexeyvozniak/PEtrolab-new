"""Local publication snapshots and deterministic ZIP export."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .import_apply import open_project
from .import_preview import ImportCommandError
from .media_display import _publish_new_file
from .plot_data import list_plot_specifications, open_plot_specification
from .statistics_service import list_calculation_runs, open_calculation_run
from .work_groups import list_work_groups


_SVG = "{http://www.w3.org/2000/svg}"
_SVG_ELEMENTS = {"svg", "g", "path", "line", "polygon", "rect", "circle", "text"}
_SVG_ATTRIBUTES = {
    "id", "width", "height", "viewBox", "transform", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r",
    "d", "text-anchor", "points", "fill", "fill-opacity", "stroke", "stroke-width", "opacity", "font-size", "font-family",
}


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def publication_catalog(database_path):
    return {"groups": list_work_groups(database_path)["groups"], "layouts": list_plot_specifications(database_path),
            "runs": list_calculation_runs(database_path)}


def _read_vector(path):
    if not isinstance(path, str) or not path or Path(path).suffix.lower() != ".svg":
        raise ImportCommandError("PUBLICATION_FIGURE_FORMAT", "Выберите фигуру в SVG.")
    try:
        with Path(path).open("rb") as file:
            data = file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ImportCommandError("PUBLICATION_FIGURE_TOO_LARGE", "SVG превышает 20 МиБ.")
        content = data.decode("utf-8-sig")
        if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
            raise ElementTree.ParseError("declaration")
        root = ElementTree.fromstring(content)
        if root.tag != _SVG + "svg":
            raise ElementTree.ParseError("namespace")
        for node in root.iter():
            if (node.tag not in {_SVG + tag for tag in _SVG_ELEMENTS} or set(node.attrib) - _SVG_ATTRIBUTES
                    or any("url(" in value.casefold().replace(" ", "") for value in node.attrib.values())):
                raise ElementTree.ParseError("element or attribute")
        if any(child.tag not in {_SVG + "g", _SVG + "text"} for child in root) or any(
                child.tag in {_SVG + "g", _SVG + "svg"} for group in root for child in group):
            raise ElementTree.ParseError("nested groups")
    except (OSError, UnicodeDecodeError, ElementTree.ParseError) as error:
        raise ImportCommandError("PUBLICATION_FIGURE_UNSUPPORTED", "SVG не соответствует редактируемому векторному профилю PetroLab.") from error
    return data


def _supplementary_data(database_path, ids):
    encoded = json.dumps(ids)
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        analysis_rows = connection.execute("""
            SELECT a.analysis_id, a.source_id, a.identity_json, s.display_name AS source_name,
                   b.source_fingerprint_sha256 AS source_sha256, a.sheet_name, a.source_row_number, a.source_column_number,
                   a.block_id, b.recipe_revision_id, recipe.semantic_fingerprint_sha256 AS recipe_sha256
            FROM json_each(?) requested JOIN analysis a ON a.analysis_id = requested.value
            JOIN source_file s USING (source_id)
            JOIN import_batch b USING (import_batch_id)
            JOIN import_recipe_revision recipe USING (recipe_revision_id)
            LEFT JOIN import_batch_retraction r USING (import_batch_id)
            WHERE b.status = 'applied' AND r.import_batch_id IS NULL ORDER BY requested.key
        """, (encoded,)).fetchall()
        if len(analysis_rows) != len(ids):
            raise ImportCommandError("PUBLICATION_INPUT_UNAVAILABLE", "Часть исходных анализов недоступна.")
        measurements = connection.execute("""
            SELECT m.analysis_id, m.measurement_id, m.canonical_field AS field, m.unit, m.raw_token, m.value_status,
                   m.qualifier, m.detection_limit, m.source_cell, m.measurement_set, m.method, m.reported_fe_form, m.fe_handling
            FROM json_each(?) requested JOIN measurement m ON m.analysis_id = requested.value
            ORDER BY requested.key, m.source_cell, m.measurement_id
        """, (encoded,))
        def as_lines(rows):
            return b"".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, allow_nan=False).encode() + b"\n"
                            for row in rows)

        return {"data/analyses.jsonl": as_lines(analysis_rows), "data/measurements.jsonl": as_lines(measurements)}


def _build_package(database_path, name, items):
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
            or not isinstance(items, list) or not 1 <= len(items) <= 24):
        raise ValueError("publication_package")
    library = {item["group"]["id"]: item for item in list_work_groups(database_path)["groups"]}
    files = {}
    manifest_items = []
    warnings = []
    all_ids = {}
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) not in ({"kind", "id", "caption"}, {"kind", "id", "caption", "source_path"}):
            raise ValueError("publication_item")
        kind, identifier, caption = item["kind"], item["id"], item["caption"]
        if not isinstance(identifier, str) or not isinstance(caption, str) or len(caption) > 2000:
            raise ValueError("publication_item")
        if kind == "work_group":
            group = library.get(identifier)
            if group is None or group["unavailable_analysis_ids"]:
                raise ImportCommandError("PUBLICATION_INPUT_UNAVAILABLE", "Выбранная рабочая группа содержит недоступный вход.")
            result = group["group"]
            label, ids = result["name"], result["analysis_ids"]
        elif kind == "calculation_run":
            result = open_calculation_run(database_path, identifier)
            if result["status"] != "current":
                raise ImportCommandError("PUBLICATION_STALE_RESULT", "Сохранённый расчёт устарел. Повторите расчёт перед экспортом.")
            label, ids = "Расчёт " + result["method_id"], result["input"]["analysis_ids"]
        elif kind in ("plot_specification", "svg_figure"):
            result = open_plot_specification(database_path, identifier)
            label, ids = result["name"], result["input"]["analysis_ids"]
        else:
            raise ValueError("publication_item_kind")
        stem = f"{index:02d}-{kind}"
        paths = [f"materials/{stem}.json"]
        files[paths[0]] = _json_bytes(result)
        if kind == "svg_figure":
            paths.append(f"figures/{stem}.svg")
            files[paths[-1]] = _read_vector(item.get("source_path"))
        elif "source_path" in item:
            raise ValueError("publication_item_path")
        if not caption.strip():
            warnings.append(f"Материал {index} «{label}» без подписи.")
        manifest_items.append({"order": index, "kind": kind, "reference_id": identifier, "label": label,
                               "caption": caption.strip(), "paths": paths, "analysis_ids": ids})
        all_ids.update(dict.fromkeys(ids))
    if all_ids:
        files.update(_supplementary_data(database_path, list(all_ids)))
    with closing(open_project(database_path)) as connection:
        project_id = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
    files["README.md"] = (f"# {name.strip()}\n\n" + "\n".join(
        f"{item['order']}. {item['label']}\n\n{item['caption']}\n" for item in manifest_items
    )).encode()
    manifest = {
        "schema_version": 1, "project_id": project_id, "name": name.strip(), "profile": "neutral",
        "items": manifest_items, "warnings": warnings, "analysis_count": len(all_ids),
        "files": [{"path": path, "sha256": sha256(data).hexdigest(), "size": len(data)} for path, data in files.items()],
    }
    return files, manifest, sha256(_json_bytes(manifest)).hexdigest()


def prepare_publication(database_path, name, items):
    _, manifest, fingerprint = _build_package(database_path, name, items)
    return {"manifest": manifest, "fingerprint": fingerprint}


def export_publication(database_path, name, items, expected_fingerprint, output_path):
    if not isinstance(output_path, str) or not output_path or Path(output_path).suffix.lower() != ".zip":
        raise ValueError("publication_output_path")
    files, manifest, fingerprint = _build_package(database_path, name, items)
    if fingerprint != expected_fingerprint:
        raise ImportCommandError("PUBLICATION_CHANGED", "Содержимое изменилось после проверки. Проверьте пакет снова.")
    target = Path(output_path)
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".zip.tmp", delete=False) as stream:
            temporary = Path(stream.name)
        with ZipFile(temporary, "w") as archive:
            for path, data in [*files.items(), ("manifest.json", _json_bytes(manifest))]:
                member = ZipInfo(path)
                member.compress_type = ZIP_DEFLATED
                member.external_attr = 0o100644 << 16
                archive.writestr(member, data)
        _publish_new_file(temporary, target)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "ZIP уже существует. Выберите другое имя.") from error
    except OSError as error:
        raise ImportCommandError("EXPORT_FAILED", "Записать публикационный ZIP не удалось.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(target), "fingerprint": fingerprint, "manifest": manifest}
