from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
from pypdf import PdfReader

from petrolab.import_preview import ImportCommandError
from petrolab.plot_export import export_plot
from petrolab.publication import _read_lithos_figure


PLOT = """<svg xmlns="http://www.w3.org/2000/svg" width="460" height="280" viewBox="0 0 460 280">
<g id="panel-b" transform="translate(0 0)">
<text x="10" y="17" font-size="13">Б SiO₂</text>
<path d="M 45 20 V 250 H 425" stroke="#76897b" fill="none"/>
<polygon points="100,100 300,100 300,200 100,200" fill="#ff3030" fill-opacity="0.5"/>
<circle cx="220" cy="140" r="7" fill="#103080"/>
</g></svg>"""


class PlotExportTests(unittest.TestCase):
    def test_pdf_keeps_editable_text_and_graphic_paths_and_matches_lithos_width(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "figure.pdf"
            export_plot(PLOT, "pdf", str(path), 90)
            page = PdfReader(path, strict=True).pages[0]
            self.assertIn("Б SiO₂", page.extract_text())
            self.assertIsNone(page["/Resources"].get("/XObject"))
            self.assertIn(b" l", page.get_contents().get_data())
            self.assertEqual(_read_lithos_figure(str(path), 90, "line_art")[1]["page_width_mm"], 90)

    def test_png_and_tiff_save_selected_resolution_and_match_the_same_rendering(self):
        with TemporaryDirectory() as folder:
            pixels = []
            for format_name in ("png", "tiff"):
                path = Path(folder) / f"figure.{format_name}"
                result = export_plot(PLOT, format_name, str(path), 90, 600)
                self.assertEqual(result["sha256"], sha256(path.read_bytes()).hexdigest())
                with Image.open(path) as image:
                    self.assertEqual(image.size, (2126, 1295))
                    self.assertAlmostEqual(image.info["dpi"][0], 600, places=1)
                    self.assertNotEqual(image.getpixel((1017, 647)), (255, 255, 255))
                    self.assertEqual(image.getpixel((1850, 500)), (255, 255, 255))
                    pixels.append(image.tobytes())
            self.assertEqual(*pixels)

    def test_external_content_and_overwrite_are_rejected_without_writing(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "figure.svg"
            with self.assertRaises(ImportCommandError):
                export_plot(PLOT.replace("<circle", '<circle onclick="example"'), "svg", str(path))
            self.assertFalse(path.exists())
            export_plot(PLOT, "svg", str(path))
            with self.assertRaises(ImportCommandError) as duplicate:
                export_plot(PLOT.replace("panel-b", "panel-c"), "svg", str(path))
            self.assertEqual(duplicate.exception.code, "EXPORT_FILE_EXISTS")
            self.assertEqual(path.read_bytes(), PLOT.encode())
            self.assertEqual(list(path.parent.iterdir()), [path])
