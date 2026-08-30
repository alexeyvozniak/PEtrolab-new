from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.manual_mapping import revise_import_mapping  # noqa: E402
from petrolab.oriented_apply import apply_oriented_import_plan  # noqa: E402
from petrolab.oriented_import import create_oriented_import_plan  # noqa: E402
from petrolab.import_preview import inspect_source  # noqa: E402


TRANSPOSED = """Field,A-01,A-02
Analysis,A-01,A-02
Sample,S-01,S-02
Si,45.1,46.2
Mg,10.2,11.3
Fe,5.0,6.0
"""


class OrientedImportTests(unittest.TestCase):
    def test_transposed_element_table_is_suggested_and_planned_by_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "transposed.csv"
            source.write_text(TRANSPOSED, encoding="utf-8")
            suggestion = suggest_import_recipe(source)
            recipe = suggestion["recipe"]

            self.assertEqual(recipe["sections"][0]["orientation"], "columns")
            self.assertTrue(any(item["code"] == "TRANSPOSED_TABLE_SUGGESTED" for item in suggestion["warnings"]))

            section = recipe["sections"][0]
            si = next(item for item in section["mappings"] if item["source_header"] == "Si")
            mg = next(item for item in section["mappings"] if item["source_header"] == "Mg")
            self.assertEqual(si["target_role"], "ignore")
            self.assertEqual(mg["target_role"], "ignore")

            recipe = revise_import_mapping(source, recipe, source.stem, si["source_column_index"], "Measurement", "Si", "wt.%")["recipe"]
            recipe = revise_import_mapping(source, recipe, source.stem, mg["source_column_index"], "Measurement", "Mg", "wt.%")["recipe"]
            plan = create_oriented_import_plan(inspect_source(source), recipe)

            self.assertEqual(plan["summary"]["planned_analysis_count"], 2)
            self.assertEqual(plan["planned_records"][0]["source_orientation"], "columns")
            self.assertEqual(plan["planned_records"][0]["source_record_label"], "B")
            refs = {item["source_cell_reference"] for item in plan["planned_records"][0]["measurements"]}
            self.assertEqual(refs, {"B4", "B5"})

    def test_transposed_apply_persists_real_cell_coordinates_without_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "transposed.csv"
            database = root / "project.sqlite"
            source.write_text(TRANSPOSED, encoding="utf-8")
            recipe = suggest_import_recipe(source)["recipe"]
            section = recipe["sections"][0]
            for field in ("Si", "Mg"):
                mapping = next(item for item in section["mappings"] if item["source_header"] == field)
                recipe = revise_import_mapping(source, recipe, source.stem, mapping["source_column_index"], "Measurement", field, "wt.%")["recipe"]
                section = recipe["sections"][0]

            result = apply_oriented_import_plan(database, source, recipe)
            self.assertEqual(result["analysis_count"], 2)
            self.assertEqual(result["measurement_count"], 4)

            with closing(sqlite3.connect(database)) as connection:
                analyses = connection.execute(
                    "SELECT source_orientation, source_record_index FROM analysis ORDER BY source_record_index"
                ).fetchall()
                provenance = connection.execute(
                    "SELECT row_number, source_column_index, source_cell_reference FROM source_row_provenance ORDER BY source_cell_reference"
                ).fetchall()

            self.assertEqual(analyses, [("columns", 2), ("columns", 3)])
            self.assertEqual({row[2] for row in provenance}, {"B4", "B5", "C4", "C5"})
            self.assertIn((4, 1, "B4"), provenance)
            self.assertIn((4, 2, "C4"), provenance)


if __name__ == "__main__":
    unittest.main()
