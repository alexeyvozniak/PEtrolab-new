from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.import_apply import apply_import_plan  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source  # noqa: E402
from petrolab.manual_mapping import revise_import_mappings  # noqa: E402
from real_world_fixtures import write_xlsx  # noqa: E402


class PhysicalFieldReviewTests(unittest.TestCase):
    def test_populated_blank_header_column_remains_reviewable_and_importable(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = write_xlsx(directory / "blank-header.xlsx", {
                "Data": [
                    ["Analysis", "SiO2", None, "Comment"],
                    ["A-1", 50.1, 101.0, "first"],
                    ["A-2", 51.2, 102.0, "second"],
                ]
            })

            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            by_index = {mapping["source_column_index"]: mapping for mapping in section["mappings"]}

            self.assertEqual(set(by_index), {0, 1, 2, 3})
            self.assertIsNone(by_index[2]["source_header"])
            self.assertEqual(by_index[2]["target_role"], "ignore")

            revised = revise_import_mappings(source, suggestion["recipe"], [{
                "block_id": section["block_id"],
                "source_axis": "column",
                "source_index": 2,
                "target": "Measurement",
                "canonical_field": "Mystery",
                "unit": "ppm",
            }])["recipe"]

            plan = create_import_plan(inspect_source(source), revised)
            self.assertEqual(plan["summary"]["planned_analysis_count"], 2)
            self.assertEqual(plan["summary"]["planned_measurement_count"], 2)
            self.assertEqual(plan["planned_records"][0]["measurements"][0]["source_cell"], "C2")
            self.assertIsNone(plan["planned_records"][0]["measurements"][0]["source_header"])

            applied = apply_import_plan(directory / "project.sqlite", source, revised)
            self.assertEqual(applied["analysis_count"], 2)
            self.assertEqual(applied["measurement_count"], 2)


if __name__ == "__main__":
    unittest.main()
