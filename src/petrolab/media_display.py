"""Read-only image previews and byte-preserving export."""

from base64 import b64encode
from contextlib import closing
from io import BytesIO
import json
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
                   p.point_name, apa.cross_sample_exception, apa.exception_reason
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


def export_media_rendered(database_path, media_id, output_path, options):
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("output_path")
    if (not isinstance(options, dict) or set(options) != {"points", "regions", "labels"}
            or any(type(value) is not bool for value in options.values())):
        raise ValueError("render_options")
    asset, source = _asset_source(database_path, media_id)
    destination = Path(output_path)
    if destination.suffix.lower() != ".png":
        _fail("INVALID_MEDIA_EXPORT_PATH", "Изображение с разметкой сохраняется как отдельный PNG.")
    annotations = [item for item in _annotations(database_path, media_id)
                   if options["points" if item["geometry_kind"] == "point" else "regions"]]
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
        for item in annotations:
            x, y = item["x_px"], item["y_px"]
            if item["geometry_kind"] == "point":
                draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                             outline="#a5edaf", width=line)
            else:
                draw.rectangle((x, y, x + item["width_px"], y + item["height_px"]),
                               outline="#a5edaf", width=line)
            if options["labels"] and item["point_name"]:
                draw.text((x + 2 * radius, y), item["point_name"], font=font, fill="#ffffff",
                          stroke_width=line, stroke_fill="#152318")
        manifest = {
            "version": 1, "media_asset_id": media_id, "source_sha256": asset["source_fingerprint_sha256"],
            "annotation_ids": [item["spatial_annotation_id"] for item in annotations], "options": options,
        }
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
