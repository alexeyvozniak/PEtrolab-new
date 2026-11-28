"""Export a checked photo and zoning profile with a shared point index."""

from base64 import b64decode
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .import_preview import ImportCommandError
from .media_display import _publish_new_file, preview_project_media
from .plot_data import query_zoning_profile


def export_profile(database_path, media_id, points, axis, reference_px, reference_um, output_path):
    if not isinstance(output_path, str) or Path(output_path).suffix.lower() != ".pdf":
        raise ImportCommandError("PLOT_EXPORT_EXTENSION", "Выберите файл с расширением PDF.")
    destination = Path(output_path)
    temporary = None
    try:
        if destination.exists():
            raise FileExistsError(destination)
        profile = query_zoning_profile(database_path, media_id, points, axis, reference_px, reference_um)
        photo = preview_project_media(database_path, media_id)
        target = BytesIO()
        _draw_profile(target, photo, profile)
        data = target.getvalue()
        with NamedTemporaryFile(dir=destination.parent, suffix=".profile.tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        _publish_new_file(temporary, destination)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите другое имя.") from error
    except OSError as error:
        raise ImportCommandError("EXPORT_FAILED", "Не удалось сохранить фото и профиль.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "sha256": sha256(data).hexdigest()}


def _draw_profile(target, photo, profile):
    font = "PetroLabProfile"
    pdfmetrics.registerFont(TTFont(font, str(Path(__file__).with_name("assets") / "DejaVuSans.ttf")))
    canvas = Canvas(target, pagesize=(842, 595), invariant=1)
    canvas.setTitle("PetroLab — профиль зональности")
    canvas.setFont(font, 15)
    canvas.drawString(28, 568, "Фото и профиль зональности")
    canvas.setFont(font, 9)
    scale = f"{profile['reference_px']:.7g} px = {profile['reference_um']:.7g} мкм"
    canvas.drawString(28, 551, scale)

    raster = ImageReader(BytesIO(b64decode(photo["preview_url"].split(",", 1)[1])))
    width, height = photo["width_px"], photo["height_px"]
    factor = min(360 / width, 220 / height)
    image_x, image_y = 28, 530 - height * factor
    canvas.drawImage(raster, image_x, image_y, width * factor, height * factor)

    points = profile["points"]
    shown = [point["value"] for point in points if point["value"] is not None]
    axis = profile["axis"]
    canvas.drawString(418, 530, " · ".join(str(axis[key]) for key in ("field", "unit", "method") if axis.get(key)))
    canvas.line(445, 330, 805, 330)
    canvas.line(445, 330, 445, 505)
    end = points[-1]["distance_um"]
    canvas.drawString(445, 316, "0")
    canvas.drawRightString(805, 316, f"{end:.7g} мкм")
    if shown:
        low, high = min(shown), max(shown)
        canvas.drawRightString(441, 500, f"{high:.5g}")
        if low != high:
            canvas.drawRightString(441, 330, f"{low:.5g}")
    else:
        canvas.drawString(460, 420, "Нет пригодных значений")
    previous = None
    for index, point in enumerate(points, 1):
        marker_x = image_x + point["x_px"] * factor
        marker_y = image_y + (height - point["y_px"]) * factor
        canvas.setFillColorRGB(1, 1, 1)
        canvas.circle(marker_x, marker_y, 3, fill=1)
        canvas.setFillColorRGB(0.05, 0.25, 0.14)
        label_x = min(image_x + width * factor - 7, marker_x + 6)
        canvas.drawString(max(image_x, label_x), min(534, marker_y + 5), str(index))
        value = point["value"]
        if value is None:
            previous = None
            continue
        x = 445 + 360 * (point["distance_um"] / end if end else 0)
        magnitude = max(abs(low), abs(high))
        y = 415 if low == high else 330 + 170 * ((value / magnitude - low / magnitude) / (high / magnitude - low / magnitude))
        if previous is not None:
            canvas.line(*previous, x, y)
        canvas.circle(x, y, 3, fill=1)
        canvas.drawString(min(x + 4, 812), y + 4, str(index))
        previous = (x, y)

    canvas.setFillColorRGB(0, 0, 0)
    row_y = 284
    for index, point in enumerate(points, 1):
        if row_y < 32:
            canvas.showPage()
            canvas.setFont(font, 9)
            row_y = 556
        if index == 1 or row_y == 556:
            for x, label in ((28, "№"), (62, "Расстояние, мкм"), (190, "Значение"), (410, "Analysis ID")):
                canvas.drawString(x, row_y, label)
            row_y -= 16
        value = point["value"]
        entry = f"{value:.8g}" if value is not None else f"— ({point['reason']})"
        for x, label in ((28, str(index)), (62, f"{point['distance_um']:.8g}"), (190, entry), (410, point["analysis_id"])):
            canvas.drawString(x, row_y, label)
        row_y -= 14
    canvas.save()
