"""Write a checked plot rendering as editable SVG/PDF or a raster image."""

from contextlib import closing
from hashlib import sha256
from io import BytesIO
from math import ceil, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

from .import_preview import ImportCommandError
from .media_display import _publish_new_file


SVG_LIMIT = 20 * 1024 * 1024
_SVG = "{http://www.w3.org/2000/svg}"
_SVG_TAGS = {_SVG + tag for tag in ("svg", "g", "path", "line", "polygon", "rect", "circle", "text")}
_SVG_ATTRIBUTES = {
    "id", "width", "height", "viewBox", "transform", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r",
    "d", "text-anchor", "points", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "opacity", "font-size", "font-family",
}
_EXTENSIONS = {"svg": {".svg"}, "pdf": {".pdf"}, "png": {".png"}, "tiff": {".tif", ".tiff"}}
_FONT = "PetroLabSans"


def checked_svg(data):
    if len(data) > SVG_LIMIT:
        raise ImportCommandError("PUBLICATION_FIGURE_TOO_LARGE", "SVG превышает 20 МиБ.")
    try:
        content = data.decode("utf-8-sig")
        if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
            raise ElementTree.ParseError("declaration")
        root = ElementTree.fromstring(content)
        if root.tag != _SVG + "svg":
            raise ElementTree.ParseError("namespace")
        for node in root.iter():
            if (node.tag not in _SVG_TAGS or set(node.attrib) - _SVG_ATTRIBUTES
                    or node.get("fill-rule") not in (None, "evenodd", "nonzero")
                    or any("url(" in "".join(value.casefold().split()) for value in node.attrib.values())):
                raise ElementTree.ParseError("element or attribute")
        if any(child.tag not in {_SVG + "g", _SVG + "text"} for child in root) or any(
                len(node) for group in root for node in group):
            raise ElementTree.ParseError("nested groups")
        if any(node.tag in {_SVG + "g", _SVG + "svg"} for group in root for node in group):
            raise ElementTree.ParseError("nested groups")
    except (UnicodeDecodeError, ElementTree.ParseError) as error:
        raise ImportCommandError("PUBLICATION_FIGURE_UNSUPPORTED", "SVG не соответствует редактируемому векторному профилю PetroLab.") from error
    return root


def _render_pdf(root, size):
    from reportlab.graphics import renderPDF
    from reportlab.pdfgen.canvas import Canvas
    from svglib.svglib import register_font, svg2rlg

    _, registered = register_font(_FONT, str(Path(__file__).with_name("assets") / "DejaVuSans.ttf"))
    if not registered:
        raise RuntimeError("Missing plot export font")
    for label in root.iter(_SVG + "text"):
        label.set("font-family", _FONT)
    ElementTree.register_namespace("", _SVG[1:-1])
    drawing = svg2rlg(BytesIO(ElementTree.tostring(root, encoding="utf-8")))
    drawing.initialFontName = _FONT
    target = BytesIO()
    canvas = Canvas(target, pagesize=size, invariant=1, pageCompression=1, initialFontName=_FONT, pdfVersion=(1, 4))
    canvas.scale(size[0] / drawing.width, size[1] / drawing.height)
    renderPDF.draw(drawing, canvas, 0, 0)
    canvas.showPage()
    canvas.save()
    return target.getvalue()


def _render_raster(pdf, target, format_name, dpi):
    from pypdfium2 import PdfDocument

    with PdfDocument(pdf) as document:
        with closing(document[0]) as page, closing(page.render(scale=dpi / 72)) as bitmap:
            with bitmap.to_pil() as image:
                options = {"compression": "tiff_lzw"} if format_name == "tiff" else {}
                image.save(target, format=format_name.upper(), dpi=(dpi, dpi), **options)


def _write_plot(target, svg, format_name, width_mm, dpi):
    if not isinstance(svg, str) or not isinstance(format_name, str) or format_name not in _EXTENSIONS:
        raise ValueError("plot_export")
    data = svg.encode("utf-8")
    root = checked_svg(data)
    raster = format_name in {"tiff", "png"}
    if format_name != "svg":
        if width_mm not in (90, 180) or (raster and dpi not in (300, 500, 600, 1000)):
            raise ValueError("plot_export_dimensions")
        try:
            origin_x, origin_y, width, height = map(float, root.get("viewBox", "").split())
        except ValueError as error:
            raise ImportCommandError("PLOT_EXPORT_DIMENSIONS", "Не удалось определить границы экспортируемых панелей.") from error
        if origin_x != 0 or origin_y != 0 or not (isfinite(width) and isfinite(height) and width > 0 and height > 0):
            raise ImportCommandError("PLOT_EXPORT_DIMENSIONS", "Не удалось определить границы экспортируемых панелей.")
        points = width_mm * 72 / 25.4
        size = (points, points * (height / width))
        if not isfinite(size[1]) or size[1] > 14_400 or (raster and ceil(points * dpi / 72) * ceil(size[1] * dpi / 72) > 45_000_000):
            raise ImportCommandError("PLOT_EXPORT_TOO_LARGE", "Фигура слишком велика. Уменьшите число панелей, ширину или dpi.")
        data = _render_pdf(root, size)
    if raster:
        _render_raster(data, target, format_name, dpi)
    else:
        target.write(data)


def render_plot(svg, format_name, width_mm=None, dpi=None):
    target = BytesIO()
    _write_plot(target, svg, format_name, width_mm, dpi)
    return target.getvalue()


def export_plot(svg, format_name, output_path, width_mm=None, dpi=None):
    if not isinstance(format_name, str) or format_name not in _EXTENSIONS:
        raise ValueError("plot_export")
    if not isinstance(output_path, str) or Path(output_path).suffix.lower() not in _EXTENSIONS[format_name]:
        raise ImportCommandError("PLOT_EXPORT_EXTENSION", "Расширение файла должно совпадать с выбранным форматом.")
    destination = Path(output_path)
    temporary = None
    try:
        if destination.exists():
            raise FileExistsError(destination)
        with NamedTemporaryFile(dir=destination.parent, suffix=".plot.tmp", delete=False) as stream:
            temporary = Path(stream.name)
            _write_plot(stream, svg, format_name, width_mm, dpi)
        digest = sha256()
        with temporary.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        _publish_new_file(temporary, destination)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите другое имя.") from error
    except ImportCommandError:
        raise
    except (OSError, RuntimeError, TypeError, AttributeError, ImportError) as error:
        raise ImportCommandError("EXPORT_FAILED", "Не удалось сохранить графики в выбранном формате.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "sha256": digest.hexdigest()}
