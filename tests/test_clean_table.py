from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


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

    def test_unused_header_only_template_sheet_does_not_block_fast_import(self) -> None:
        workbook = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
          <sheets>
            <sheet name=\"01_EPMA_WDS\" sheetId=\"1\" r:id=\"rId1\"/>
            <sheet name=\"03_LAICPMS_trace\" sheetId=\"2\" r:id=\"rId2\"/>
          </sheets>
        </workbook>"""
        relationships = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
          <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>
          <Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet2.xml\"/>
        </Relationships>"""
        used_sheet = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>
          <row r=\"1\">
            <c r=\"A1\" t=\"inlineStr\"><is><t>Analysis</t></is></c>
            <c r=\"B1\" t=\"inlineStr\"><is><t>Sample</t></is></c>
            <c r=\"C1\" t=\"inlineStr\"><is><t>SiO2 [wt.%]</t></is></c>
          </row>
          <row r=\"2\"><c r=\"A2\" t=\"inlineStr\"><is><t>A-1</t></is></c><c r=\"B2\" t=\"inlineStr\"><is><t>S1</t></is></c><c r=\"C2\"><v>40.1</v></c></row>
          <row r=\"3\"><c r=\"A3\" t=\"inlineStr\"><is><t>A-2</t></is></c><c r=\"B3\" t=\"inlineStr\"><is><t>S2</t></is></c><c r=\"C3\"><v>39.8</v></c></row>
        </sheetData></worksheet>"""
        unused_sheet = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>
          <row r=\"1\">
            <c r=\"A1\" t=\"inlineStr\"><is><t>Analysis</t></is></c>
            <c r=\"B1\" t=\"inlineStr\"><is><t>Sample</t></is></c>
            <c r=\"C1\" t=\"inlineStr\"><is><t>Li [ppm]</t></is></c>
          </row>
        </sheetData></worksheet>"""
        with tempfile.TemporaryDirectory() as directory_name:
            source = Path(directory_name) / "PetroLab_Clean_Table.xlsx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook)
                archive.writestr("xl/_rels/workbook.xml.rels", relationships)
                archive.writestr("xl/worksheets/sheet1.xml", used_sheet)
                archive.writestr("xl/worksheets/sheet2.xml", unused_sheet)
            classification = classify_clean_table(inspect_source(source))

        self.assertEqual(classification["mode"], "clean_table_fast")
        self.assertEqual(classification["ignored_empty_sheets"], ["03_LAICPMS_trace"])
        self.assertEqual([section["sheet_name"] for section in classification["sections"]], ["01_EPMA_WDS"])
        self.assertEqual(classification["plan_summary"]["planned_analysis_count"], 2)


if __name__ == "__main__":
    unittest.main()
