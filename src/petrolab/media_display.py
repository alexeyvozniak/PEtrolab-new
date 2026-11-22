"""Read-only image previews and byte-preserving export."""

from base64 import b64encode
from contextlib import closing
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, UnidentifiedImageError

from .import_apply import open_project
from .media_import import _fail, _sha256, _uuid, inspect_media_source


def _asset_source(database_path, media_id):
    _uuid(media_id, "media_asset_id")
    with closing(open_project(database_path)) as connection:
        asset = connection.execute("SELECT * FROM media_asset WHERE media_asset_id = ?", (media_id,)).fetchone()
    if asset is None:
        _fail("MEDIA_UNAVAILABLE", "Изображение недоступно в этом проекте.")
    if asset["source_kind"] == "managed_copy":
        media_root = (Path(database_path).parent / "media").resolve()
        source = (Path(database_path).parent / asset["managed_relative_path"]).resolve()
        if not source.is_relative_to(media_root):
            _fail("MEDIA_UNAVAILABLE", "Путь файла изображения находится за пределами каталога проекта.")
    else:
        source = Path(asset["linked_path"])
    if not source.is_file():
        _fail("MEDIA_UNAVAILABLE", "Файл изображения недоступен.")
    return asset, source


def _preview_image(source, expected_fingerprint, region=None):
    try:
        if _sha256(source) != expected_fingerprint:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Изображение изменилось. Предпросмотр остановлен.")
        with Image.open(source) as image:
            buffer = BytesIO()
            if region is None:
                image.thumbnail((1400, 1400))
                image.convert("RGB").save(buffer, format="JPEG", quality=88)
            else:
                left, top, width, height = _preview_region(region, image.width, image.height)
                crop = image.crop((left, top, left + width, top + height))
                if crop.mode not in {"L", "I;16", "RGB", "RGBA"}:
                    crop = crop.convert("RGBA")
                crop.save(buffer, format="PNG", compress_level=2)
        if _sha256(source) != expected_fingerprint:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Изображение изменилось во время предпросмотра.")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        _fail("MEDIA_PREVIEW_FAILED", "Создать предпросмотр изображения не удалось.")
    content_type = "jpeg" if region is None else "png"
    return f"data:image/{content_type};base64," + b64encode(buffer.getvalue()).decode("ascii")


def _preview_region(region, image_width, image_height):
    keys = ("left", "top", "width", "height")
    if not isinstance(region, dict) or set(region) != set(keys) or any(type(region[key]) is not int for key in keys):
        raise ValueError("Недопустимая область предпросмотра.")
    left, top, width, height = (region[key] for key in keys)
    if not (0 <= left < image_width and 0 <= top < image_height
            and 1 <= width <= min(1400, image_width - left)
            and 1 <= height <= min(1400, image_height - top)):
        raise ValueError("Область предпросмотра выходит за границы изображения.")
    return left, top, width, height


def preview_input_media(source_path, region=None, expected_fingerprint=None):
    image = inspect_media_source(source_path)
    if region is not None and expected_fingerprint != image["source_fingerprint"]:
        _fail("SOURCE_FINGERPRINT_MISMATCH", "Изображение изменилось. Добавьте файл заново.")
    preview = _preview_image(Path(image["source_path"]), image["source_fingerprint"], region)
    return {**image, "preview_url": preview} if region is None else {"region": region, "preview_url": preview}


def preview_project_media(database_path, media_id, region=None):
    asset, source = _asset_source(database_path, media_id)
    preview = _preview_image(source, asset["source_fingerprint_sha256"], region)
    if region is not None:
        return {"region": region, "preview_url": preview}
    return {"preview_url": preview,
            "width_px": asset["width_px"], "height_px": asset["height_px"],
            "annotations": _annotations(database_path, media_id)}


def _annotations(database_path, media_id):
    with closing(open_project(database_path)) as connection:
        rows = connection.execute("""
            SELECT sa.spatial_annotation_id, sa.geometry_kind, sa.x_px, sa.y_px, sa.width_px, sa.height_px,
                   p.analytical_point_id, p.sample_id AS point_sample_id, p.point_name, sa.label,
                   apa.cross_sample_exception, apa.exception_reason
            FROM spatial_annotation sa
            LEFT JOIN analytical_point_annotation apa USING (spatial_annotation_id)
            LEFT JOIN analytical_point p USING (analytical_point_id)
            WHERE sa.media_asset_id = ? ORDER BY sa.created_at, sa.spatial_annotation_id
        """, (media_id,))
        return [dict(row) for row in rows]


def export_media_original(database_path, media_id, output_path):
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path")
    asset, source = _asset_source(database_path, media_id)
    destination = Path(output_path)
    if destination.suffix.lower() != source.suffix.lower():
        _fail("INVALID_MEDIA_EXPORT_PATH", "Расширение копии должно совпадать с расширением исходного файла.")
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, suffix=".media.tmp", delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream)
        if _sha256(temporary) != asset["source_fingerprint_sha256"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Файл изменился. Экспорт исходного изображения остановлен.")
        _publish_new_file(temporary, destination)
    except FileExistsError:
        _fail("EXPORT_FILE_EXISTS", "Этот файл уже существует. Выберите другое имя для копии.")
    except OSError:
        _fail("EXPORT_FAILED", "Не удалось записать копию изображения.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "sha256": asset["source_fingerprint_sha256"]}


def _publish_new_file(temporary, destination):
    if os.name == "nt":
        temporary.rename(destination)
    else:
        os.link(temporary, destination)


def _export_scale(rendered, calibration):
    pixels = max(1, rendered.width // 4)
    if calibration is None:
        return {"pixels": pixels, "length": pixels, "unit": "px"}
    if (not isinstance(calibration, dict) or set(calibration) != {"reference_pixels", "reference_length", "unit"}
            or calibration["unit"] not in ("µm", "mm", "cm")):
        raise ValueError("scale_calibration")
    reference_pixels, reference_length = calibration["reference_pixels"], calibration["reference_length"]
    if (type(reference_pixels) not in (int, float) or type(reference_length) not in (int, float)
            or not (0 < reference_pixels <= rendered.width) or not (0 < reference_length < math.inf)):
        _fail("INVALID_MEDIA_CALIBRATION", "Введите положительную длину и ширину отрезка на оригинале в пикселях.")
    distance = pixels * (reference_length / reference_pixels)
    if not 0 < distance < math.inf:
        _fail("INVALID_MEDIA_CALIBRATION", "Заданная калибровка выходит за числовой диапазон.")
    return {"pixels": pixels, "length": distance, "unit": calibration["unit"]}


def _draw_export_key(rendered, font, line, scale, legend, protected_bounds):
    if not scale and legend is None:
        return rendered
    draw = ImageDraw.Draw(rendered)
    padding = max(4, line * 4)
    marker = max(5, line * 4)
    _, _, _, text_height = draw.textbbox((0, 0), "Аg", font=font)
    row_height = max(text_height, marker) + padding
    legend_rows = []
    if legend is not None:
        if legend["points"]:
            legend_rows.append(("point", f"Точки: {legend['points']}"))
        if legend["regions"]:
            legend_rows.append(("region", f"Области: {legend['regions']}"))
        if not legend_rows:
            legend_rows.append((None, "Без аннотаций"))
    scale_label = f"{scale['length']:.4g} {scale['unit']}" if scale else ""
    widths = [float(draw.textlength(label, font=font)) + (marker + padding if kind else 0) for kind, label in legend_rows]
    if scale:
        widths.append(max(scale["pixels"], float(draw.textlength(scale_label, font=font))))
    panel_width = math.ceil(max(widths)) + 2 * padding
    panel_height = len(legend_rows) * row_height + 2 * padding + (row_height + marker + padding if scale else 0)
    left, top = padding, rendered.height - panel_height - padding
    right, bottom = left + panel_width - 1, top + panel_height - 1
    overlaps_annotation = any(
        x0 <= right and x1 >= left and y0 <= bottom and y1 >= top
        for x0, y0, x1, y1 in protected_bounds
    )
    if panel_width + 2 * padding > rendered.width or panel_height * 2 > rendered.height or overlaps_annotation:
        left, top = 0, rendered.height
        extended = Image.new("RGB", (max(rendered.width, panel_width), rendered.height + panel_height), "#16231b")
        extended.paste(rendered, (0, 0))
        rendered = extended
        draw = ImageDraw.Draw(rendered)
    draw.rectangle((left, top, left + panel_width - 1, top + panel_height - 1), fill="#16231b")
    x, y = left + padding, top + padding
    for kind, label in legend_rows:
        if kind:
            shape = draw.ellipse if kind == "point" else draw.rectangle
            shape((x, y + padding, x + marker, y + padding + marker), outline="#a5edaf", width=line)
        draw.text((x + (marker + padding if kind else 0), y), label, font=font, fill="white")
        y += row_height
    if scale:
        draw.text((x, y), scale_label, font=font, fill="white")
        y += row_height
        end = x + scale["pixels"]
        draw.line((x, y, end, y), fill="white", width=line)
        for endpoint in (x, end):
            draw.line((endpoint, y - marker // 2, endpoint, y + marker // 2), fill="white", width=line)
    return rendered


def export_media_rendered(database_path, media_id, output_path, options):
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path")
    required = {"points", "regions", "labels"}
    switches = required | {"legend", "scale_bar"}
    if (not isinstance(options, dict) or not required <= options.keys() or options.keys() - switches - {"calibration", "annotation_ids"}
            or any(type(options[key]) is not bool for key in switches & options.keys())
            or (options.get("calibration") is not None and not options.get("scale_bar"))):
        raise ValueError("render_options")
    asset, source = _asset_source(database_path, media_id)
    destination = Path(output_path)
    if destination.suffix.lower() != ".png":
        _fail("INVALID_MEDIA_EXPORT_PATH", "Изображение с разметкой сохраняется как отдельный PNG.")
    available = _annotations(database_path, media_id)
    selected = options.get("annotation_ids", [item["spatial_annotation_id"] for item in available])
    if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
        raise ValueError("annotation_ids")
    selected = set(selected)
    if not selected <= {item["spatial_annotation_id"] for item in available}:
        _fail("MEDIA_ANNOTATION_UNAVAILABLE", "Набор меток изменился. Откройте изображение заново.")
    annotations = [item for item in available if item["spatial_annotation_id"] in selected
                   and options["points" if item["geometry_kind"] == "point" else "regions"]]
    temporary = None
    try:
        if _sha256(source) != asset["source_fingerprint_sha256"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Исходное изображение изменилось.")
        with Image.open(source) as original:
            rendered = original.convert("RGB")
        if _sha256(source) != asset["source_fingerprint_sha256"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH", "Исходное изображение изменилось во время чтения.")
        draw = ImageDraw.Draw(rendered)
        size = min(rendered.size)
        line = max(1, round(size / 500))
        radius = max(3, round(size / 100))
        font_size = max(12, round(size / 40))
        font = ImageFont.load_default(size=font_size)
        for name in ("arial.ttf", "DejaVuSans.ttf"):
            try:
                font = ImageFont.truetype(name, font_size)
                break
            except OSError:
                continue
        protected_bounds = []
        for item in annotations:
            x, y = item["x_px"], item["y_px"]
            if item["geometry_kind"] == "point":
                bounds = (x - radius, y - radius, x + radius, y + radius)
                draw.ellipse(bounds, outline="#a5edaf", width=line)
            else:
                bounds = (x, y, x + item["width_px"], y + item["height_px"])
                draw.rectangle(bounds, outline="#a5edaf", width=line)
            protected_bounds.append(bounds)
            label = item["point_name"] or item["label"]
            if options["labels"] and label:
                position = (x + 2 * radius, y)
                draw.text(position, label, font=font, fill="#ffffff",
                          stroke_width=line, stroke_fill="#152318")
                protected_bounds.append(draw.textbbox(position, label, font=font, stroke_width=line))
        scale = _export_scale(rendered, options.get("calibration")) if options.get("scale_bar") else None
        legend = None
        if options.get("legend"):
            count = sum(item["geometry_kind"] == "point" for item in annotations)
            legend = {"points": count, "regions": len(annotations) - count}
        rendered = _draw_export_key(rendered, font, line, scale, legend, protected_bounds)
        manifest = {
            "version": 1, "media_asset_id": media_id, "source_sha256": asset["source_fingerprint_sha256"],
            "annotation_ids": [item["spatial_annotation_id"] for item in annotations], "options": options,
        }
        if scale or legend is not None:
            manifest.update(version=2, rendered_scale=scale, rendered_legend=legend)
        metadata = PngImagePlugin.PngInfo()
        metadata.add_itxt("PetroLab", json.dumps(manifest, ensure_ascii=False))
        with NamedTemporaryFile(dir=destination.parent, suffix=".media.tmp", delete=False) as stream:
            temporary = Path(stream.name)
            rendered.save(stream, format="PNG", pnginfo=metadata)
        fingerprint = _sha256(temporary)
        _publish_new_file(temporary, destination)
    except FileExistsError:
        _fail("EXPORT_FILE_EXISTS", "Этот файл уже существует. Выберите другое имя для производного изображения.")
    except (OSError, Image.DecompressionBombError):
        _fail("EXPORT_FAILED", "Не удалось выгрузить изображение с разметкой.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "sha256": fingerprint, **manifest}
