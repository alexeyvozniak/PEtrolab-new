from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.clean_table import classify_clean_table  # noqa: E402
from petrolab.import_apply import apply_import_plan  # noqa: E402
from petrolab.import_preview import inspect_source, validate_recipe  # noqa: E402


class CleanTableTests(unittest.TestCase):
    def _csv(self, directory: Path, text: str, name: str = "clean.csv") -> Path:
        path = directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_strict_clean_table_builds_valid_fast_recipe_and_applies(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,Point,Mineral,Generation,Source,SiO2 [wt.%],MgO [wt.%],Li [ppm]\n"
                "A-1,KIV-2,P1,Phlogopite,core,Lab,40.1,20.2,15\n"
                "A-2,KIV-2,P2,Phlogopite,rim,Lab,39.8,19.7,<0.5\n",
            )
            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "clean_table_fast")
            self.assertEqual(classification["reasons"], [])
            self.assertEqual(classification["plan_summary"]["planned_analysis_count"], 2)
            self.assertEqual(classification["plan_summary"]["planned_measurement_count"], 6)
            recipe = classification["recipe"]
            validate_recipe(inspect_source(source), recipe)
            result = apply_import_plan(directory / "project.sqlite", source, recipe)
            self.assertEqual(result["analysis_count"], 2)
            self.assertEqual(result["measurement_count"], 6)
            self.assertGreater(result["source_metadata_count"], 0)

    def test_explicit_unknown_measurement_name_is_allowed_when_unit_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,87Sr/86Sr [ratio],Zr/Hf [ratio]\n"
                "A-1,S1,0.70321,35.2\n"
                "A-2,S2,0.70318,34.8\n",
            )
            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "clean_table_fast")
            measurements = classification["sections"][0]["measurements"]
            self.assertEqual([(item["field"], item["unit"]) for item in measurements], [
                ("87Sr/86Sr", "ratio"),
                ("Zr/Hf", "ratio"),
            ])

    def test_missing_measurement_unit_falls_back_to_raw_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,SiO2\nA-1,S1,40.1\nA-2,S2,39.8\n",
            )
            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "raw_review")
            self.assertTrue(any(reason["code"] == "UNRECOGNIZED_CLEAN_FIELD" for reason in classification["reasons"]))

    def test_unknown_text_column_falls_back_instead_of_being_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,Operator note,SiO2 [wt.%]\nA-1,S1,ok,40.1\nA-2,S2,ok,39.8\n",
            )
            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "raw_review")
            reason = next(reason for reason in classification["reasons"] if reason["code"] == "UNRECOGNIZED_CLEAN_FIELD")
            self.assertEqual(reason["source_header"], "Operator note")

    def test_duplicate_identity_falls_back_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,SiO2 [wt.%]\nA-1,S1,40.1\nA-1,S1,39.8\n",
            )
            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "raw_review")
            self.assertTrue(any(reason["code"] == "CLEAN_TABLE_DUPLICATE_IDENTITIES" for reason in classification["reasons"]))

    def test_internal_blank_row_and_blank_header_are_not_fast_imported(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = self._csv(
                directory,
                "Analysis,Sample,,SiO2 [wt.%]\nA-1,S1,x,40.1\n,,,\nA-2,S2,y,39.8\n",
            )
            classification = classify_clean_table(inspect_source(source))
            codes = {reason["code"] for reason in classification["reasons"]}
            self.assertEqual(classification["mode"], "raw_review")
            self.assertIn("CLEAN_TABLE_BLANK_HEADER", codes)
            self.assertIn("CLEAN_TABLE_INTERNAL_BLANK_ROW", codes)


if __name__ == "__main__":
    unittest.main()
