from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from zipfile import ZipFile

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe
from petrolab.import_apply import apply_import_plan
from petrolab.import_preview import ImportCommandError
from petrolab.plot_data import plot_catalog, save_plot_specification
from petrolab.publication import export_publication, prepare_publication
from petrolab.work_groups import create_work_group


class PublicationPackageTests(unittest.TestCase):
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
