from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe  # noqa: E402
from petrolab.import_apply import apply_import_plan, retract_latest_import  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source, validate_recipe  # noqa: E402


FIXTURE = ROOT / "fixtures/import/m1_1_ambiguous_multisheet.xlsx"


class DesktopWorkflowTests(unittest.TestCase):
    def test_suggested_recipe_is_conservative_and_valid(self) -> None:
        suggestion = suggest_import_recipe(FIXTURE)
        recipe = suggestion["recipe"]
        inspection = inspect_source(FIXTURE)

        validation = validate_recipe(inspection, recipe)
        self.assertEqual(len(validation["sections"]), 2)
        self.assertEqual(recipe["ownership_mode"], "managed_copy")
        self.assertEqual(recipe["global_decisions"]["fe_semantics"], "preserve_reported_form_for_review")

        trace = next(section for section in recipe["sections"] if section["sheet_name"] == "Trace_elements")
        unknown_f = next(mapping for mapping in trace["mappings"] if mapping["source_header"] == "F (unknown unit)")
        self.assertEqual(unknown_f["target_role"], "ignore")
        warning = next(warning for warning in suggestion["warnings"] if warning.get("source_header") == "F (unknown unit)")
        self.assertEqual(warning["code"], "UNIT_REQUIRES_REVIEW")
        self.assertEqual(warning["canonical_field"], "F")

        plan = create_import_plan(inspection, recipe)
        self.assertEqual(plan["summary"]["planned_analysis_count"], 8)

    def test_applied_import_is_visible_in_desktop_analysis_projection(self) -> None:
        suggestion = suggest_import_recipe(FIXTURE)
        recipe = suggestion["recipe"]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "petrolab.sqlite"
            applied = apply_import_plan(database, FIXTURE, recipe)
            projection = list_project_analyses(database)
            managed_sources = list((Path(directory) / "sources").glob("*.xlsx"))

        self.assertEqual(projection["total"], applied["analysis_count"])
        self.assertEqual(projection["source_count"], 1)
        self.assertEqual(projection["import_batch_count"], 1)
        self.assertEqual(projection["latest_import"]["import_batch_id"], applied["import_batch_id"])
        self.assertEqual(projection["analyses"][0]["source_name"], FIXTURE.name)
        self.assertTrue(any("Analysis" in row["identity"] for row in projection["analyses"]))
        self.assertTrue(any("SiO2" in row["measurements"] for row in projection["analyses"]))
        self.assertEqual(len(managed_sources), 1)

    def test_retracted_latest_import_is_preserved_but_hidden_from_active_projection(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "petrolab.sqlite"
            first = apply_import_plan(database, FIXTURE, recipe)
            second = apply_import_plan(database, FIXTURE, recipe)
            before = list_project_analyses(database)
            retracted = retract_latest_import(database)
            after = list_project_analyses(database)

            import sqlite3
            with closing(sqlite3.connect(database)) as connection:
                audit_rows = connection.execute(
                    "SELECT COUNT(*) FROM analysis WHERE import_batch_id = ?", (second["import_batch_id"],)
                ).fetchone()[0]
                retraction_rows = connection.execute(
                    "SELECT COUNT(*) FROM import_batch_retraction WHERE import_batch_id = ?", (second["import_batch_id"],)
                ).fetchone()[0]

        self.assertEqual(before["import_batch_count"], 2)
        self.assertEqual(retracted["import_batch_id"], second["import_batch_id"])
        self.assertEqual(after["import_batch_count"], 1)
        self.assertEqual(after["total"], first["analysis_count"])
        self.assertEqual(after["latest_import"]["import_batch_id"], first["import_batch_id"])
        self.assertEqual(audit_rows, second["analysis_count"])
        self.assertEqual(retraction_rows, 1)


if __name__ == "__main__":
    unittest.main()
