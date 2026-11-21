from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe
from petrolab.import_apply import apply_import_plan
from petrolab.import_preview import ImportCommandError
from petrolab.plot_data import plot_catalog, save_plot_specification
from petrolab.publication import export_publication, prepare_publication
from petrolab.work_groups import create_work_group


class PublicationPackageTests(unittest.TestCase):
    def test_lithos_figures_have_ordered_captions_and_verified_width_and_resolution(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.csv"
            source.write_text("Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP1,2,10\n", encoding="utf-8")
            database = root / "petrolab.sqlite"
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            ids = [row["analysis_id"] for row in list_project_analyses(database)["analyses"]]
            layout = save_plot_specification(database, "Композиции", ids,
                [{"id": str(uuid4()), "kind": "binary", "axes": plot_catalog(database)["axes"]}], {}, [], [])
            raster = root / "figure.tif"
            Image.new("RGB", (3600, 400), "white").save(raster, dpi=(72, 72))
            preview = root / "figure.png"
            Image.new("RGB", (3600, 400), "white").save(preview)
            pdf = root / "figure.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=90 * 72 / 25.4, height=100)
            writer.write(pdf)
            items = [{"kind": "publication_figure", "id": layout["id"], "caption": caption, "source_path": str(path)}
                     for path, caption in [(raster, "Растровая фигура"), (pdf, "Векторная фигура"), (preview, "Просмотр")]]
            prepared = prepare_publication(database, "Lithos", items, "lithos", 90)
            manifest = prepared["manifest"]
            self.assertEqual(manifest["profile"], "lithos")
            self.assertEqual(manifest["figure_width_mm"], 90)
            self.assertEqual(manifest["items"][0]["figure"]["effective_dpi"], 1016)
            self.assertEqual(manifest["items"][1]["figure"]["page_width_mm"], 90)
            self.assertTrue(any("PNG" in warning for warning in manifest["warnings"]))
            destination = root / "lithos.zip"
            export_publication(database, "Lithos", items, prepared["fingerprint"], str(destination), "lithos", 90)
            with ZipFile(destination) as archive:
                self.assertEqual(archive.read("figures/Figure_01.tiff"), raster.read_bytes())
                self.assertEqual(archive.read("figures/Figure_02.pdf"), pdf.read_bytes())
                self.assertEqual(archive.read("figures/Figure_03.png"), preview.read_bytes())
                self.assertEqual(archive.read("figures/captions.txt").decode(),
                                 "Figure 1. Растровая фигура\n\nFigure 2. Векторная фигура\n\nFigure 3. Просмотр\n")
                self.assertEqual(json.loads(archive.read("manifest.json")), manifest)
            for item, width, code in [
                (items[0], 180, "PUBLICATION_FIGURE_DPI"),
                (items[1], 180, "PUBLICATION_FIGURE_WIDTH"),
                ({**items[0], "caption": " "}, 90, "PUBLICATION_FIGURE_CAPTION"),
            ]:
                with self.subTest(code=code), self.assertRaises(ImportCommandError) as rejected:
                    prepare_publication(database, "Lithos", [item], "lithos", width)
                self.assertEqual(rejected.exception.code, code)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({NameObject("/Subtype"): NameObject("/Type1")}),
                }),
            })
            writer.write(pdf)
            with self.assertRaises(ImportCommandError) as fonts:
                prepare_publication(database, "Lithos", items, "lithos", 90)
            self.assertEqual(fonts.exception.code, "PUBLICATION_FIGURE_FONTS")

    def test_export_matches_manifest_and_rejects_changed_figure(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "petrolab.sqlite"
            source = root / "input.csv"
            rows = "Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP1,2,10\nP2,<1,11\n"
            source.write_text(rows, encoding="utf-8")
            dataset = suggest_import_recipe(source)["recipe"]
            apply_import_plan(database, source, dataset)
            ids = [row["analysis_id"] for row in list_project_analyses(database)["analyses"]]
            group = create_work_group(database, "Группа", ids, "Иванов")
            layout = save_plot_specification(database, "Композиции", ids,
                [{"id": str(uuid4()), "kind": "binary", "axes": plot_catalog(database)["axes"]}], {}, [], [])
            figure = root / "figure.svg"
            content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g id="panel-b"><text x="1" y="2">b</text></g></svg>'
            figure.write_text(content, encoding="utf-8")
            items = [{"kind": "svg_figure", "id": layout["id"], "caption": "Рисунок b", "source_path": str(figure)},
                     {"kind": "work_group", "id": group["id"], "caption": "Исходные анализы"}]
            prepared = prepare_publication(database, "Материалы", items)
            destinations = [root / "one.zip", root / "two.zip"]
            for path in destinations:
                export_publication(database, "Материалы", items, prepared["fingerprint"], str(path))
            self.assertEqual(destinations[0].read_bytes(), destinations[1].read_bytes())
            with ZipFile(destinations[0]) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest, prepared["manifest"])
                self.assertEqual([item["reference_id"] for item in manifest["items"]], [layout["id"], group["id"]])
                self.assertEqual(set(archive.namelist()), {"manifest.json", *(entry["path"] for entry in manifest["files"])})
                for entry in manifest["files"]:
                    self.assertEqual(sha256(archive.read(entry["path"])).hexdigest(), entry["sha256"])
                measurements = [json.loads(line) for line in archive.read("data/measurements.jsonl").splitlines()]
                self.assertEqual({item["analysis_id"] for item in measurements}, set(ids))
                self.assertIn("<1", [item["raw_token"] for item in measurements])
            figure.write_text(content.replace(">b<", ">c<"), encoding="utf-8")
            with self.assertRaises(ImportCommandError) as changed:
                export_publication(database, "Материалы", items, prepared["fingerprint"], str(root / "changed.zip"))
            self.assertEqual(changed.exception.code, "PUBLICATION_CHANGED")
            figure.write_text(content.replace("<text", "<foreignObject").replace("</text>", "</foreignObject>"), encoding="utf-8")
            with self.assertRaises(ImportCommandError) as unsupported:
                prepare_publication(database, "Материалы", items)
            self.assertEqual(unsupported.exception.code, "PUBLICATION_FIGURE_UNSUPPORTED")
            self.assertEqual(source.read_text(encoding="utf-8"), rows)
