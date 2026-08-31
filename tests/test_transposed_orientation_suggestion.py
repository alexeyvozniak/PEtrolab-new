from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source  # noqa: E402
from real_world_fixtures import long_preamble_weight_percent, repeated_headers, transposed_weight_percent  # noqa: E402


class TransposedOrientationSuggestionTests(unittest.TestCase):
    def test_clear_transposed_table_is_suggested_and_plans_without_manual_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = transposed_weight_percent(Path(directory) / "transposed.xlsx")
            suggestion = suggest_import_recipe(source)
            self.assertEqual(len(suggestion["recipe"]["sections"]), 1)
            section = suggestion["recipe"]["sections"][0]

            self.assertEqual(section["orientation"], "columns_are_analyses")
            self.assertEqual(section["header_row"], 2)
            self.assertEqual(section["header_column"], 1)
            self.assertEqual(section["data_start_column"], 2)
            self.assertEqual(section["data_end_column"], 3)
            self.assertEqual(section["analysis_axis_role"], "Analysis")
            self.assertTrue(any(warning["code"] == "TRANSPOSED_TABLE_LIKELY" for warning in suggestion["warnings"]))

            plan = create_import_plan(inspect_source(source), suggestion["recipe"])
            self.assertEqual(plan["summary"]["planned_analysis_count"], 2)
            self.assertEqual(plan["summary"]["planned_measurement_count"], 6)
            self.assertEqual(plan["planned_records"][0]["identity"], ("A-1",))
            self.assertEqual(plan["planned_records"][0]["measurements"][0]["source_cell"], "B3")

    def test_ordinary_row_table_is_not_falsely_transposed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = long_preamble_weight_percent(Path(directory) / "ordinary.xlsx")
            suggestion = suggest_import_recipe(source)
            self.assertTrue(all(section["orientation"] == "rows_are_analyses" for section in suggestion["recipe"]["sections"]))
            self.assertFalse(any(warning["code"] == "TRANSPOSED_TABLE_LIKELY" for warning in suggestion["warnings"]))

    def test_repeated_row_headers_remain_separate_row_oriented_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = repeated_headers(Path(directory) / "repeated.xlsx")
            suggestion = suggest_import_recipe(source)
            self.assertEqual(len(suggestion["recipe"]["sections"]), 2)
            self.assertEqual([section["orientation"] for section in suggestion["recipe"]["sections"]], ["rows_are_analyses", "rows_are_analyses"])
            self.assertFalse(any(warning["code"] == "TRANSPOSED_TABLE_LIKELY" for warning in suggestion["warnings"]))


if __name__ == "__main__":
    unittest.main()
