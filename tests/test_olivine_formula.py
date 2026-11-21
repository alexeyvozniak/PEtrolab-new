from contextlib import closing
import csv
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.edit_drafts import commit_edit_draft, save_edit_draft
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_preview import ImportCommandError
from petrolab.ndjson_service import handle_request
from petrolab.olivine_formula import OLIVINE, calculate_olivine
from petrolab.publication import export_publication, prepare_publication, publication_catalog
from petrolab.statistics_service import list_calculation_runs
from real_world_fixtures import write_xlsx


# Gündüz and Asan, Mineralogical Magazine 87 (2023), Table 1, columns 1 and 5.
PUBLISHED_OXIDES = {"SiO2": 40.536, "TiO2": 0.009, "Al2O3": 0.019, "Cr2O3": 0.046,
                    "FeO": 10.998, "MnO": 0.174, "MgO": 47.971, "NiO": 0.292, "CaO": 0.123, "Na2O": 0.009}
PUBLISHED_APFU = {"Si": 0.998, "Ti": 0.000, "Al": 0.001, "Cr": 0.001, "Fe2+": 0.226,
                  "Mn": 0.004, "Mg": 1.761, "Ni": 0.006, "Ca": 0.003, "Na": 0.000}


class OlivineFormulaTests(unittest.TestCase):
    def test_published_epma_example_and_ideal_forsterite(self):
        result = calculate_olivine(PUBLISHED_OXIDES)
        for element, expected in PUBLISHED_APFU.items():
            self.assertAlmostEqual(result["apfu"][element], expected, delta=0.001, msg=element)
        self.assertEqual(result["warnings"], [])
        ideal = calculate_olivine({"SiO2": 42.7065, "MgO": 57.2935, "FeO": 0})
        self.assertAlmostEqual(ideal["apfu"]["Si"], 1, delta=0.0001)
        self.assertAlmostEqual(ideal["apfu"]["Mg"], 2, delta=0.0001)
        self.assertEqual(ideal["divalent_component_mol_percent"], {"Fo": 100, "Fa": 0})
        self.assertNotIn("Fe3+", ideal["apfu"])

    def test_input_restrictions_and_applicability_report(self):
        for values in ({"SiO2": 40, "MgO": 50, "FeOt": 10}, {"SiO2": 40, "MgO": 50}, {"SiO2": 40, "MgO": -1, "FeO": 10}):
            with self.subTest(values=values), self.assertRaises(ImportCommandError):
                calculate_olivine(values)
        result = calculate_olivine({"SiO2": 2, "MgO": 50, "FeO": 10, "Fe2O3": 1})
        self.assertGreater(result["apfu"]["Fe3+"], 0)
        self.assertEqual({warning["field"] for warning in result["warnings"]}, {"oxide_sum_wt_pct", "cation_sum_apfu"})

    def test_saved_run_detects_approved_workbook_correction_and_method_upgrade(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            database = path / "project.sqlite"
            source = write_xlsx(path / "published.xlsx", {"Olivine": [
                ["Analysis", *[f"{oxide} (wt.%)" for oxide in PUBLISHED_OXIDES]],
                ["O1", *PUBLISHED_OXIDES.values()],
            ]})
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            with closing(open_project(database)) as connection:
                analysis_id = connection.execute("SELECT analysis_id FROM analysis").fetchone()[0]
                measurements = {row["canonical_field"]: row["measurement_id"] for row in connection.execute("SELECT * FROM measurement")}
            fields = {"analysis_id": analysis_id, "method_id": OLIVINE["method_id"], "measurement_ids": list(measurements.values())}

            def call(command, **parameters):
                return handle_request({"request_id": str(uuid4()), "protocol_version": "1.0", "command": command,
                                       "payload": {"project_database_path": str(database), **parameters}})

            def fingerprints(review):
                return {name: review[name] for name in ("input_fingerprint", "method_definition_fingerprint")}

            checked = call("formula.review", **fields)["result"]
            old = call("formula.run", **fields, **fingerprints(checked))["result"]
            self.assertEqual(call("formula.run.open", run_id=old["id"])["result"]["status"], "current")
            self.assertEqual(list_calculation_runs(database), [])
            self.assertEqual(publication_catalog(database)["formula_runs"][0]["analysis_label"], "O1")
            materials = [{"kind": "formula_run", "id": old["id"], "caption": "Оливин"}]
            prepared = prepare_publication(database, "Формула", materials)
            destination = path / "formula.zip"
            export_publication(database, "Формула", materials, prepared["fingerprint"], str(destination))
            with ZipFile(destination) as archive:
                formula = json.loads(archive.read("materials/01-formula_run.json"))
                derived = list(csv.DictReader(StringIO(archive.read("data/derived_values.csv").decode())))
                measured = [json.loads(line) for line in archive.read("data/measurements.jsonl").splitlines()]
                self.assertEqual(formula["input_measurement_ids"], old["input_measurement_ids"])
                magnesium, = [row for row in derived if row["field"] == "apfu.Mg"]
                self.assertEqual(magnesium["input_fingerprint"], old["input_fingerprint"])
                self.assertEqual(magnesium["method_version"], OLIVINE["version"])
                original, = [row for row in measured if row["measurement_id"] == measurements["MgO"]]
                self.assertEqual((original["unit"], original["raw_token"]), ("wt.%", "47.971"))
            draft = save_edit_draft(database, measurements["MgO"], "46.5")
            self.assertEqual(call("formula.run.open", run_id=old["id"])["result"]["status"], "current")
            self.assertTrue(commit_edit_draft(database, draft["id"], "Проверка", "Контрольная поправка")['applied'])
            stale = call("formula.run.open", run_id=old["id"])["result"]
            self.assertEqual(stale["stale_reasons"], ["inputs_changed"])
            rejected_path = path / "stale.zip"
            with self.assertRaises(ImportCommandError) as reject:
                export_publication(database, "Формула", materials, prepared["fingerprint"], str(rejected_path))
            self.assertEqual(reject.exception.code, "PUBLICATION_STALE_RESULT")
            self.assertFalse(rejected_path.exists())
            self.assertEqual(call("formula.run", **fields, **fingerprints(checked))["error"]["code"], "FORMULA_REVIEW_STALE")
            with patch("petrolab.formula_service.OLIVINE", {**OLIVINE, "version": "1.1.0"}):
                refreshed = call("formula.review", **fields)["result"]
                new = call("formula.run", **fields, **fingerprints(refreshed))["result"]
                self.assertEqual(call("formula.run.open", run_id=old["id"])["result"]["stale_reasons"], ["method_changed", "inputs_changed"])
                self.assertEqual(call("formula.run.open", run_id=new["id"])["result"]["status"], "current")
            self.assertEqual(new["method_version"], "1.1.0")
            self.assertNotEqual(new["result_manifest"]["apfu"]["Mg"], old["result_manifest"]["apfu"]["Mg"])
            self.assertNotEqual(new["input_fingerprint"], old["input_fingerprint"])
            self.assertEqual([run["id"] for run in call("formula.runs.list", analysis_id=analysis_id)["result"]], [new["id"], old["id"]])
            self.assertEqual(call("formula.run.open", run_id=old["id"])["result"]["result_manifest"], old["result_manifest"])
            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute("SELECT raw_token FROM measurement WHERE measurement_id = ?", (measurements["MgO"],)).fetchone()[0], "47.971")


if __name__ == "__main__":
    unittest.main()
