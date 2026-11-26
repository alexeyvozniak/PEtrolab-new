"""Local publication snapshots and deterministic ZIP export."""

from contextlib import closing
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from math import isfinite
from pathlib import Path
import re
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .import_apply import open_project
from .formula_service import list_formula_runs, open_formula_run
from .import_preview import ImportCommandError
from .media_display import _annotations, _asset_source, _publish_new_file, export_media_original, export_media_rendered
from .plot_data import list_plot_specifications, open_plot_specification, query_plot_data, validate_category_style, validate_point_style
from .plot_export import SVG_LIMIT, checked_svg, render_plot
from .selection_export import selection_xlsx_bytes
from .statistics_service import list_calculation_runs, open_calculation_run
from .work_groups import list_work_groups


_LITHOS_WIDTHS = (90, 180)
_LITHOS_RASTER_DPI = {"halftone": 300, "combination": 500, "line_art": 1000}
_LITHOS_FORMATS = {".pdf": "PDF", ".tif": "TIFF", ".tiff": "TIFF", ".png": "PNG"}
_CAPTURE_FORMATS = {"svg", "pdf", "tiff", "png"}


def _pdf_fonts_embedded(resources, visited):
    if not resources:
        return True
    resources = resources.get_object()
    if id(resources) in visited:
        return True
    visited.add(id(resources))
    fonts = resources.get("/Font")
    for reference in fonts.get_object().values() if fonts is not None else ():
        font = reference.get_object()
        if font.get("/Subtype") == "/Type3":
            if not _pdf_fonts_embedded(font.get("/Resources"), visited):
                return False
            continue
        for descendant in font.get("/DescendantFonts", [font]):
            descriptor = descendant.get_object().get("/FontDescriptor")
            if descriptor is None or not any(key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3")):
                return False
    objects = resources.get("/XObject")
    return objects is None or all(
        _pdf_fonts_embedded(reference.get_object().get("/Resources"), visited)
        for reference in objects.get_object().values()
    )


def _read_lithos_figure(path, width_mm, artwork):
    extension = Path(path).suffix.lower() if isinstance(path, str) else ""
    if extension not in _LITHOS_FORMATS:
        raise ImportCommandError("PUBLICATION_FIGURE_FORMAT", "Выберите файл PDF, TIFF или PNG.")
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(40 * 1024 * 1024 + 1)
    except OSError as error:
        raise ImportCommandError("PUBLICATION_FIGURE_UNSUPPORTED", "Не удалось прочитать файл фигуры.") from error
    checks, warnings = _check_lithos_figure(data, extension, width_mm, artwork)
    return data, checks, warnings


def _check_lithos_figure(data, extension, width_mm, artwork):
    try:
        if len(data) > 40 * 1024 * 1024:
            raise ImportCommandError("PUBLICATION_FIGURE_TOO_LARGE", "Фигура превышает 40 МиБ.")
        if extension == ".pdf":
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or len(reader.pages) != 1:
                raise ValueError("expected one unencrypted page")
            page = reader.pages[0]
            edge = page.cropbox.height if page.rotation % 180 else page.cropbox.width
            actual_width = float(edge * page.user_unit) * 25.4 / 72
            if not isfinite(actual_width) or abs(actual_width - width_mm) > 1:
                raise ImportCommandError("PUBLICATION_FIGURE_WIDTH", f"Ширина страницы PDF должна быть {width_mm} мм (±1 мм).")
            if not _pdf_fonts_embedded(page.get("/Resources"), set()):
                raise ImportCommandError("PUBLICATION_FIGURE_FONTS", "В PDF обнаружены невстроенные шрифты.")
            return {"format": "PDF", "page_width_mm": round(actual_width, 2)}, []
        with Image.open(BytesIO(data), formats=[_LITHOS_FORMATS[extension]]) as image:
            if image.n_frames != 1:
                raise ValueError("expected one raster frame")
            image.load()
            width, height = image.size
    except ImportCommandError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError,
            PdfReadError, Image.DecompressionBombError) as error:
        raise ImportCommandError("PUBLICATION_FIGURE_UNSUPPORTED", "Не удалось прочитать фигуру. Нужен одностраничный PDF или растровый файл с одним кадром.") from error
    minimum = _LITHOS_RASTER_DPI[artwork]
    actual_dpi = width * 25.4 / width_mm
    if actual_dpi < minimum:
        raise ImportCommandError("PUBLICATION_FIGURE_DPI", f"При ширине {width_mm} мм разрешение составляет {actual_dpi:.1f} dpi. Для выбранного типа нужно не менее {minimum} dpi.")
    warnings = ["PNG включён как копия для просмотра. Для подачи добавьте PDF или TIFF."] if extension == ".png" else []
    return {"format": _LITHOS_FORMATS[extension], "width_px": width, "height_px": height,
            "artwork": artwork, "effective_dpi": round(actual_dpi, 2), "minimum_dpi": minimum}, warnings


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _plot_capture(database_path, capture):
    if (not isinstance(capture, dict) or set(capture) - {"category_style"} != {
            "name", "svg", "format", "width_mm", "dpi", "include_csv", "panels",
            "analysis_ids", "colors", "hidden_analysis_ids", "hidden_source_ids", "layers",
    } or not isinstance(capture["name"], str) or not 1 <= len(capture["name"]) <= 120
            or not isinstance(capture["svg"], str) or not isinstance(capture["format"], str)
            or capture["format"] not in _CAPTURE_FORMATS or type(capture["include_csv"]) is not bool
            or capture["width_mm"] not in _LITHOS_WIDTHS or capture["dpi"] not in (300, 500, 600, 1000)
            or not isinstance(capture["panels"], list) or not 1 <= len(capture["panels"]) <= 32
            or not isinstance(capture["colors"], dict)
            or any(not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in capture["colors"].values())):
        raise ValueError("plot_capture")
    root = checked_svg(capture["svg"].encode())
    category_style = capture.get("category_style")
    nodes = list(root)
    if category_style is not None:
        if not nodes or nodes[-1].get("id") != "category-legend" or not any(panel["kind"] != "histogram" for panel in capture["panels"]):
            raise ValueError("plot_capture_category_legend")
        legend = nodes.pop()
        markers = [node for node in legend if node.tag.rsplit("}",1)[-1] in ("rect","circle","polygon")]
        expected = [(entry["color"], "circle" if entry.get("symbol") == "circle" else "polygon" if entry.get("symbol") else "rect") for entry in category_style["entries"]]
        if [(node.get("fill"),node.tag.rsplit("}",1)[-1]) for node in markers] != expected:
            raise ValueError("plot_capture_category_colors")
    if len(nodes) != len(capture["panels"]) or any(not node.tag.endswith("}g") for node in root):
        raise ValueError("plot_capture_panels")
    snapshots = []
    contributors = {}
    scope = capture["analysis_ids"]
    for panel, node in zip(capture["panels"], nodes):
        if not isinstance(panel, dict) or set(panel) - {"normalization", "point_style"} != {"id", "kind", "axes", "projection_sha256"}:
            raise ValueError("plot_capture_panel")
        validate_point_style(panel)
        projection = query_plot_data(database_path, panel["kind"], panel["axes"], scope,
                                     capture["hidden_analysis_ids"], capture["hidden_source_ids"], capture["layers"],
                                     normalization=panel.get("normalization"))
        if projection["projection_sha256"] != panel["projection_sha256"]:
            raise ImportCommandError("PUBLICATION_PLOT_CHANGED", "Данные диаграммы изменились. Обновите панели и добавьте фигуру заново.")
        scope = projection["input_analysis_ids"]
        ids = [point["analysis_id"] for point in projection["points"]]
        contributors.update(dict.fromkeys(ids))
        snapshot = {**panel, "svg_group": node.get("id"), "analysis_ids": ids, "points": projection["points"],
                    "ticks": projection["ticks"], "fields": projection["fields"]}
        if "normalization" in projection:
            snapshot['normalization'] = projection['normalization']
        if 'exclusions' in projection:
            snapshot['exclusions'] = projection['exclusions']
        if "bins" in projection:
            snapshot.update(binning=projection["binning"], bins=projection["bins"])
        snapshots.append(snapshot)
    if not contributors:
        raise ImportCommandError("PUBLICATION_EMPTY_PLOT", "В выбранных панелях нет анализов для публикации.")
    result = {key: value for key, value in capture.items() if key != "svg"}
    result["analysis_ids"] = scope
    result["panels"] = snapshots
    if category_style is not None:
        with closing(open_project(database_path)) as connection:
            connection.execute("BEGIN")
            validate_category_style(connection, scope, category_style)
    has_symbols = any("symbol" in panel.get("point_style", {}) for panel in snapshots) or any("symbol" in entry for entry in (category_style or {}).get("entries", []))
    result["schema_version"] = (5 if has_symbols else 4 if any("style" in (layer["field"] or {}) for layer in capture["layers"])
                                else 3 if any("point_style" in panel for panel in snapshots)
                                else 2 if category_style is not None else 1)
    return result, list(contributors)


def capture_publication_plot(database_path, capture, caption):
    if not isinstance(caption, str) or len(caption) > 2000:
        raise ValueError("publication_caption")
    snapshot, _ = _plot_capture(database_path, capture)
    capture = {**capture, "analysis_ids": snapshot["analysis_ids"]}
    return {"kind": "plot_capture", "id": sha256(_json_bytes(capture)).hexdigest(),
            "caption": caption.strip(), "capture": capture}


def _table_material(database_path, analysis_ids):
    workbook = selection_xlsx_bytes(database_path, analysis_ids)
    result = {"schema_version": 1, "name": "Таблица отбора", "analysis_ids": analysis_ids,
              "xlsx_sha256": sha256(workbook).hexdigest()}
    return result, analysis_ids, ".xlsx", workbook


def _media_material(database_path, media_id, options):
    asset, source = _asset_source(database_path, media_id)
    extension = source.suffix.lower() if options is None else ".png"
    with TemporaryDirectory(prefix="petrolab-publication-") as folder:
        path = Path(folder) / ("image" + extension)
        if options is None:
            exported = export_media_original(database_path, media_id, str(path))
        else:
            exported = export_media_rendered(database_path, media_id, str(path), options)
        with path.open("rb") as stream:
            data = stream.read(40 * 1024 * 1024 + 1)
    if len(data) > 40 * 1024 * 1024:
        raise ImportCommandError("PUBLICATION_FIGURE_TOO_LARGE", "Изображение превышает 40 МиБ.")
    selected = exported.get("annotation_ids")
    annotations = [item for item in _annotations(database_path, media_id)
                   if selected is None or item["spatial_annotation_id"] in selected]
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        attachments = [dict(row) for row in connection.execute("""
            SELECT ml.media_link_id, sa.spatial_annotation_id, sa.media_asset_id AS annotated_media_asset_id,
                   ma.source_fingerprint_sha256 AS annotated_source_sha256,
                   sa.geometry_kind, sa.x_px, sa.y_px, sa.width_px, sa.height_px, sa.label, apa.analytical_point_id
            FROM media_link ml JOIN spatial_annotation sa USING (spatial_annotation_id)
            JOIN media_asset ma ON ma.media_asset_id = sa.media_asset_id
            LEFT JOIN analytical_point_annotation apa USING (spatial_annotation_id)
            WHERE ml.media_asset_id = ? AND ml.detached_at IS NULL
            ORDER BY ml.media_link_id
        """, (media_id,))]
        points = list(dict.fromkeys(item["analytical_point_id"] for item in [*annotations, *attachments]
                                    if item["analytical_point_id"]))
        links = connection.execute("""
            SELECT l.analytical_point_id, l.analysis_id, l.link_type
            FROM analytical_point_analysis l JOIN json_each(?) points ON points.value = l.analytical_point_id
            ORDER BY l.analytical_point_id, l.analysis_id, l.link_type
        """, (json.dumps(points),)).fetchall()
    linked = [dict(row) for row in links]
    ids = list(dict.fromkeys(row["analysis_id"] for row in linked))
    result = {key: asset[key] for key in ("media_asset_id", "sample_id", "thin_section_id", "media_type", "mime_type",
                                         "width_px", "height_px")}
    result.update(schema_version=1, name=asset["display_name"], source_sha256=asset["source_fingerprint_sha256"],
                  rendition={key: value for key, value in exported.items() if key != "output_path"},
                  mode="original" if options is None else "annotated", annotations=annotations,
                  attachments=attachments, analysis_links=linked)
    return result, ids, extension, data


def capture_publication_table(database_path, analysis_ids):
    result, _, _, _ = _table_material(database_path, analysis_ids)
    return {"kind": "selection_table", "id": sha256(_json_bytes(result)).hexdigest(), "caption": "",
            "capture": {"analysis_ids": analysis_ids}}


def capture_publication_media(database_path, media_id, options=None):
    result, _, _, _ = _media_material(database_path, media_id, options)
    return {"kind": "media_capture", "id": sha256(_json_bytes(result)).hexdigest(), "caption": "",
            "capture": {"media_asset_id": media_id, "options": options}}


def _plot_values_csv(panels):
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    headers = ["panel", "analysis_id", "field", "unit", "measurement_set", "method", "value"]
    has_patterns = any(isinstance(panel.get("normalization"), dict) for panel in panels)
    writer.writerow(headers + (["normalization_id", "status"] if has_patterns else []))
    for panel in panels:
        reference = panel.get("normalization")
        if isinstance(reference, dict):
            for point in [*panel["points"], *panel["exclusions"]]:
                writer.writerows((panel["svg_group"], point["analysis_id"], axis["field"], "1",
                                  axis["measurement_set"], axis["method"], vertex["ratio"],
                                  reference["id"], vertex["status"])
                                 for axis, vertex in zip(panel["axes"], point["vertices"]))
            continue
        for point in panel["points"]:
            writer.writerows((panel["svg_group"], point["analysis_id"], axis["field"], axis["unit"],
                              axis["measurement_set"], axis["method"], value) + ((None, None) if has_patterns else ())
                             for axis, value in zip(panel["axes"], point["values"]))
    return stream.getvalue().encode("utf-8")


def publication_catalog(database_path):
    return {"groups": list_work_groups(database_path)["groups"], "layouts": list_plot_specifications(database_path),
            "runs": list_calculation_runs(database_path), "formula_runs": list_formula_runs(database_path)}


def _derived_values_csv(runs):
    fields = ["id", "run_id", "analysis_id", "field", "unit", "value", "method_id", "method_version", "input_fingerprint"]
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for run in runs.values():
        definition = {key: run[key] for key in ("method_id", "method_version", "input_fingerprint")}
        writer.writerows({**value, **definition} for value in run["result_manifest"]["derived_values"])
    return stream.getvalue().encode("utf-8")


def _read_vector(path):
    if not isinstance(path, str) or not path or Path(path).suffix.lower() != ".svg":
        raise ImportCommandError("PUBLICATION_FIGURE_FORMAT", "Выберите фигуру в SVG.")
    try:
        with Path(path).open("rb") as file:
            data = file.read(SVG_LIMIT + 1)
    except OSError as error:
        raise ImportCommandError("PUBLICATION_FIGURE_UNSUPPORTED", "Не удалось прочесть SVG.") from error
    checked_svg(data)
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


def _build_package(database_path, name, items, profile, width_mm):
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
            or not isinstance(items, list) or not 1 <= len(items) <= 24
            or profile not in ("neutral", "lithos") or (profile == "lithos" and width_mm not in _LITHOS_WIDTHS)):
        raise ValueError("publication_package")
    library = {item["group"]["id"]: item for item in list_work_groups(database_path)["groups"]}
    files = {}
    manifest_items = []
    warnings = []
    all_ids = {}
    formulas = {}
    figures = []
    for index, item in enumerate(items, 1):
        if (not isinstance(item, dict) or not {"kind", "id", "caption"} <= item.keys()
                or item.keys() - {"kind", "id", "caption", "source_path", "artwork", "capture"}):
            raise ValueError("publication_item")
        kind, identifier, caption = item["kind"], item["id"], item["caption"]
        if not isinstance(identifier, str) or not isinstance(caption, str) or len(caption) > 2000:
            raise ValueError("publication_item")
        material_file = None
        if kind == "work_group":
            group = library.get(identifier)
            if group is None or group["unavailable_analysis_ids"]:
                raise ImportCommandError("PUBLICATION_INPUT_UNAVAILABLE", "Выбранная рабочая группа содержит недоступный вход.")
            result = group["group"]
            label, ids = result["name"], result["analysis_ids"]
        elif kind in {"calculation_run", "formula_run"}:
            result = (open_formula_run if kind == "formula_run" else open_calculation_run)(database_path, identifier)
            if result["status"] != "current":
                raise ImportCommandError("PUBLICATION_STALE_RESULT", "Сохранённый расчёт устарел. Повторите расчёт перед экспортом.")
            if kind == "formula_run":
                label, ids = result["method_definition"]["name"], [result["analysis_id"]]
                formulas[identifier] = result
            else:
                label, ids = "Расчёт " + result["method_id"], result["input"]["analysis_ids"]
        elif kind in ("plot_specification", "svg_figure", "publication_figure"):
            result = open_plot_specification(database_path, identifier)
            label, ids = result["name"], result["input"]["analysis_ids"]
        elif kind == "plot_capture":
            capture = item.get("capture")
            result, ids = _plot_capture(database_path, capture)
            if identifier != sha256(_json_bytes(capture)).hexdigest():
                raise ImportCommandError("PUBLICATION_PLOT_CHANGED", "Снимок фигуры изменился. Добавьте фигуру заново.")
            label = result["name"]
        elif kind in ("selection_table", "media_capture"):
            capture = item.get("capture")
            if not isinstance(capture, dict):
                raise ValueError("publication_capture")
            if kind == "selection_table" and set(capture) == {"analysis_ids"}:
                result, ids, extension, data = _table_material(database_path, capture["analysis_ids"])
            elif kind == "media_capture" and set(capture) == {"media_asset_id", "options"}:
                result, ids, extension, data = _media_material(database_path, capture["media_asset_id"], capture["options"])
            else:
                raise ValueError("publication_capture")
            if identifier != sha256(_json_bytes(result)).hexdigest():
                raise ImportCommandError("PUBLICATION_CAPTURE_CHANGED", "Исходные данные материала изменились. Добавьте его в пакет заново.")
            label = result["name"]
            material_file = extension, data
        else:
            raise ValueError("publication_item_kind")
        has_capture = kind in ("plot_capture", "selection_table", "media_capture")
        if ("capture" in item) != has_capture or (has_capture and "source_path" in item):
            raise ValueError("publication_item_capture")
        stem = f"{index:02d}-{kind}"
        paths = [f"materials/{stem}.json"]
        files[paths[0]] = _json_bytes(result)
        figure = None
        figure_data = None
        if material_file is not None:
            extension, data = material_file
            directory = "tables" if kind == "selection_table" else "images"
            paths.append(f"{directory}/{stem}{extension}")
            files[paths[-1]] = data
            if profile == "lithos" and kind == "media_capture":
                warnings.append(f"Материал {index} · изображение включено в дополнительные материалы. Для проверки журнальной фигуры приложите PDF или TIFF.")
        elif kind == "svg_figure":
            if "artwork" in item:
                raise ValueError("publication_item_artwork")
            paths.append(f"figures/{stem}.svg")
            files[paths[-1]] = _read_vector(item.get("source_path"))
            if profile == "lithos":
                warnings.append(f"Материал {index} · SVG включён для редактирования. Для подачи добавьте PDF или TIFF.")
        elif kind == "plot_capture":
            format_name = capture["format"]
            target_width = capture["width_mm"]
            artwork = item.get("artwork", "line_art")
            if not isinstance(artwork, str) or artwork not in _LITHOS_RASTER_DPI:
                raise ValueError("publication_figure_artwork")
            if profile == "lithos" and format_name != "svg" and target_width != width_mm:
                raise ImportCommandError("PUBLICATION_FIGURE_WIDTH", f"Материал {index} сохранён с другой шириной. Выберите {width_mm} мм в окне выгрузки графиков.")
            try:
                data = render_plot(capture["svg"], format_name, capture["width_mm"], capture["dpi"])
            except ImportCommandError:
                raise
            except (OSError, RuntimeError, TypeError, AttributeError, ImportError) as error:
                raise ImportCommandError("EXPORT_FAILED", "Не удалось построить фигуру для пакета.") from error
            if format_name == "svg":
                paths.append(f"figures/{stem}.svg")
                files[paths[-1]] = data
                if profile == "lithos":
                    warnings.append(f"Материал {index} · SVG включён для редактирования. Для подачи добавьте PDF или TIFF.")
            else:
                checks = {"format": format_name.upper()}
                notices = []
                if profile == "lithos":
                    checks, notices = _check_lithos_figure(data, "." + format_name, width_mm, artwork)
                elif format_name in {"png", "tiff"}:
                    checks["effective_dpi"] = capture["dpi"]
                figure_data = data, target_width, checks, notices
            if capture["include_csv"]:
                paths.append(f"data/{stem}.csv")
                files[paths[-1]] = _plot_values_csv(result["panels"])
        elif kind == "publication_figure":
            artwork = item.get("artwork", "line_art")
            if profile != "lithos" or not isinstance(artwork, str) or artwork not in _LITHOS_RASTER_DPI:
                raise ValueError("publication_figure_profile")
            if not caption.strip():
                raise ImportCommandError("PUBLICATION_FIGURE_CAPTION", f"Добавьте подпись к фигуре в строке {index}.")
            data, checks, notices = _read_lithos_figure(item.get("source_path"), width_mm, artwork)
            figure_data = data, width_mm, checks, notices
        elif "source_path" in item or "artwork" in item:
            raise ValueError("publication_item_path")
        if figure_data is not None:
            data, target_width, checks, notices = figure_data
            if profile == "lithos" and not caption.strip():
                raise ImportCommandError("PUBLICATION_FIGURE_CAPTION", f"Добавьте подпись к фигуре в строке {index}.")
            number = len(figures) + 1
            extension = {"PDF": "pdf", "TIFF": "tiff", "PNG": "png"}[checks["format"]]
            paths.append(f"figures/Figure_{number:02d}.{extension}")
            files[paths[-1]] = data
            warnings.extend(f"Figure {number} · {notice}" for notice in notices)
            figure = {"number": number, "target_width_mm": target_width, **checks}
            figures.append((figure, caption.strip()))
        if not caption.strip():
            warnings.append(f"Материал {index} «{label}» без подписи.")
        manifest_items.append({"order": index, "kind": kind, "reference_id": identifier, "label": label,
                               "caption": caption.strip(), "paths": paths, "analysis_ids": ids})
        if figure:
            manifest_items[-1]["figure"] = figure
        all_ids.update(dict.fromkeys(ids))
    if profile == "lithos":
        if not any(figure["format"] in {"PDF", "TIFF"} for figure, _ in figures):
            warnings.append("В пакете пока нет PDF или TIFF для подачи.")
    if figures:
        files["figures/captions.txt"] = ("\n\n".join(
            f"Figure {figure['number']}. {caption}" for figure, caption in figures
        ) + "\n").encode()
    if all_ids:
        files.update(_supplementary_data(database_path, list(all_ids)))
    if formulas:
        files["data/derived_values.csv"] = _derived_values_csv(formulas)
    with closing(open_project(database_path)) as connection:
        project_id = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
    files["README.md"] = (f"# {name.strip()}\n\n" + "\n".join(
        f"{item['order']}. {item['label']}\n\n{item['caption']}\n" for item in manifest_items
    )).encode()
    manifest = {
        "schema_version": 1, "project_id": project_id, "name": name.strip(), "profile": profile,
        "items": manifest_items, "warnings": warnings, "analysis_count": len(all_ids),
        "files": [{"path": path, "sha256": sha256(data).hexdigest(), "size": len(data)} for path, data in files.items()],
    }
    if profile == "lithos":
        manifest["figure_width_mm"] = width_mm
    return files, manifest, sha256(_json_bytes(manifest)).hexdigest()


def prepare_publication(database_path, name, items, profile="neutral", width_mm=None):
    _, manifest, fingerprint = _build_package(database_path, name, items, profile, width_mm)
    return {"manifest": manifest, "fingerprint": fingerprint}


def export_publication(database_path, name, items, expected_fingerprint, output_path, profile="neutral", width_mm=None):
    if not isinstance(output_path, str) or not output_path or Path(output_path).suffix.lower() != ".zip":
        raise ValueError("publication_output_path")
    files, manifest, fingerprint = _build_package(database_path, name, items, profile, width_mm)
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
