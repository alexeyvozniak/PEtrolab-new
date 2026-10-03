from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe  # noqa: E402
from petrolab.import_apply import apply_import_plan  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source  # noqa: E402
from real_world_fixtures import long_preamble_weight_percent, repeated_headers, transposed_weight_percent, write_xlsx  # noqa: E402


class TransposedOrientationSuggestionTests(unittest.TestCase):
    def test_wide_table_with_spectrum_identity_is_not_false_positive_transposed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = write_xlsx(Path(directory) / "wide-spectra.xlsx", {
                "summary": [
                    ["in oxides", None, None, None],
                    ["Метка спектра", "Si", "Ca", "Fe"],
                    ["Спектр 1", 30.47, 31.45, 22.8],
                    ["Спектр 2", 35.05, 6.6, 12.1],
                ],
            })
            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            self.assertEqual(section["orientation"], "rows_are_analyses")
            self.assertEqual(section["mappings"][0]["target_role"], "identity")
            self.assertEqual(
                [mapping["suggested_canonical_field"] for mapping in section["mappings"][1:]],
                ["Si", "Ca", "Fe"],
            )

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

    def test_saved_projection_keeps_column_origin_for_transposed_analyses(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = transposed_weight_percent(directory / "transposed.xlsx")
            recipe = suggest_import_recipe(source)["recipe"]
            database = directory / "project.sqlite"

            applied = apply_import_plan(database, source, recipe)
            projection = list_project_analyses(database)

            self.assertEqual(applied["analysis_count"], 2)
            self.assertEqual(projection["total"], 2)
            origins = {
                (analysis["source_orientation"], analysis["source_column_number"], analysis["source_row_number"])
                for analysis in projection["analyses"]
            }
            self.assertEqual(origins, {("columns_are_analyses", 2, 2), ("columns_are_analyses", 3, 2)})
            self.assertEqual({analysis["identity"]["Analysis"] for analysis in projection["analyses"]}, {"A-1", "A-2"})

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
