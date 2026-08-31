from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sys
import sqlite3
import tempfile
import shutil
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_preview import (  # noqa: E402
    inspect_source,
    run_import_inspect_source,
    run_import_plan_create,
    run_import_recipe_validate,
    semantic_fingerprint,
)
from petrolab.import_apply import apply_import_plan, check_linked_source, open_project, save_import_recipe_revision  # noqa: E402


FIXTURE = ROOT / "fixtures/import/m1_1_ambiguous_multisheet.xlsx"


def fixture_recipe() -> dict:
    """Legacy schema-v1 recipe with an already explicit keep-all decision.

    New Desktop recipes are schema v2 and require persisted duplicate-review
    evidence. This fixture models an older stored recipe so migration/apply
    compatibility can be tested independently from the new review UX.
    """
    fingerprint = inspect_source(FIXTURE).fingerprint
    recipe = {
        "source_file_sha256": fingerprint,
        "source_format": "xlsx",
        "ownership_mode": "linked_external",
        "sections": [
            {
                "sheet_name": "EPMA_analyses",
                "block_id": "epma-main",
                "header_row": 2,
                "data_start_row": 3,
                "data_end_row": 7,
                "mappings": [
                    {"source_column_index": 0, "source_header": "Analysis", "target_role": "identity", "canonical_field": "Analysis", "unit": None},
                    {"source_column_index": 1, "source_header": "Sample", "target_role": "identity", "canonical_field": "Sample", "unit": None},
                    {"source_column_index": 2, "source_header": "Point", "target_role": "identity", "canonical_field": "Point", "unit": None},
                    {"source_column_index": 3, "source_header": "Mineral", "target_role": "metadata", "canonical_field": "Mineral", "unit": None},
                    {"source_column_index": 4, "source_header": "SiO2 (wt.%)", "target_role": "measurement", "canonical_field": "SiO2", "unit": "wt.%"},
                    {"source_column_index": 5, "source_header": "MgO (wt.%)", "target_role": "measurement", "canonical_field": "MgO", "unit": "wt.%"},
                    {"source_column_index": 6, "source_header": "TiO2 (мас. %)", "target_role": "measurement", "canonical_field": "TiO2", "unit": "wt.%"},
                    {"source_column_index": 7, "source_header": "F (wt.%)", "target_role": "measurement", "canonical_field": "F", "unit": "wt.%"},
                    {"source_column_index": 8, "source_header": "FeOt (wt.%)", "target_role": "measurement", "canonical_field": "FeOt", "unit": "wt.%"},
                    {"source_column_index": 9, "source_header": "Fe2O3 (wt.%)", "target_role": "measurement", "canonical_field": "Fe2O3", "unit": "wt.%"},
                ],
            },
            {
                "sheet_name": "Trace_elements",
                "block_id": "trace-main",
                "header_row": 2,
                "data_start_row": 3,
                "data_end_row": 5,
                "mappings": [
                    {"source_column_index": 0, "source_header": "Analysis", "target_role": "identity", "canonical_field": "Analysis", "unit": None},
                    {"source_column_index": 1, "source_header": "Li (ppm)", "target_role": "measurement", "canonical_field": "Li", "unit": "ppm"},
                    {"source_column_index": 2, "source_header": "Rb (ppm)", "target_role": "measurement", "canonical_field": "Rb", "unit": "ppm"},
                    {"source_column_index": 3, "source_header": "Ba (ppm)", "target_role": "measurement", "canonical_field": "Ba", "unit": "ppm"},
                    {"source_column_index": 4, "source_header": "F (unknown unit)", "target_role": "measurement", "canonical_field": "F", "unit": "wt.%"},
                ],
            },
        ],
        "global_decisions": {
            "fe_semantics": "separate_fe2_fe3",
            "censored_value_policy": "preserve_original_token_and_detection_limit",
            "duplicate_policy": "keep_all",
            "unit_policy": "explicit_per_measurement_column",
        },
    }
    for section in recipe["sections"]:
        for mapping in section["mappings"]:
            role = mapping["target_role"]
            mapping["measurement_semantics"] = "measured" if role == "measurement" else role
    recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)
    return recipe


def refresh_recipe_fingerprint(recipe: dict) -> None:
    recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)


class ImportPreviewTests(unittest.TestCase):
    def test_password_protected_xlsx_is_reported_without_read_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "locked.xlsx"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"not an ordinary xlsx")
            response = run_import_inspect_source(source)
        self.assertEqual(response["error"]["code"], "WORKBOOK_ENCRYPTED")

    def test_xlsx_preserves_inline_strings_physical_rows_and_preview_warnings(self) -> None:
        workbook = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
          <sheets><sheet name=\"inline\" sheetId=\"1\" r:id=\"rId1\"/></sheets>
        </workbook>"""
        relationships = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
          <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>
        </Relationships>"""
        sheet = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">
          <mergeCells count=\"1\"><mergeCell ref=\"A1:B1\"/></mergeCells>
          <sheetData>
            <row r=\"1\" hidden=\"1\"><c r=\"A1\" t=\"inlineStr\"><is><t>Analysis</t></is></c><c r=\"B1\" t=\"inlineStr\"><is><t>MgO</t></is></c></row>
            <row r=\"3\"><c r=\"A3\" t=\"inlineStr\"><is><t>KL-1</t></is></c><c r=\"B3\"><f>SUM(1,2)</f></c></row>
          </sheetData>
        </worksheet>"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "inline.xlsx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook)
                archive.writestr("xl/_rels/workbook.xml.rels", relationships)
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            inspection = inspect_source(source)
        self.assertEqual(inspection.sheets[0].rows[0], ("Analysis", "MgO"))
        self.assertEqual(inspection.sheets[0].rows[1], ())
        self.assertEqual(inspection.sheets[0].rows[2], ("KL-1", None))
        self.assertEqual(inspection.sheets[0].header_rows, (1,))
        self.assertEqual(
            [warning["code"] for warning in inspection.projection()["warnings"]],
            ["MERGED_HEADERS", "HIDDEN_ROWS", "FORMULA_WITHOUT_CACHED_VALUE"],
        )

    def test_inspect_multisheet_fixture_without_changing_bytes(self) -> None:
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        inspection = inspect_source(FIXTURE)
        after = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(inspection.fingerprint, before)
        self.assertEqual([sheet.name for sheet in inspection.sheets], ["EPMA_analyses", "Trace_elements", "Read_me"])
        self.assertEqual(len(inspection.projection()["candidate_blocks"]), 2)

    def test_recipe_requires_explicit_known_unit(self) -> None:
        recipe = fixture_recipe()
        recipe["sections"][1]["mappings"][4]["unit"] = None
        response = run_import_recipe_validate(FIXTURE, recipe)
        self.assertEqual(response["error"]["code"], "UNKNOWN_UNIT")

    def test_recipe_rejects_implicit_ownership_or_semantic_mismatch(self) -> None:
        recipe = fixture_recipe()
        recipe.pop("ownership_mode")
        self.assertEqual(run_import_recipe_validate(FIXTURE, recipe)["error"]["code"], "RECIPE_SCHEMA_INCOMPATIBLE")
        recipe = fixture_recipe()
        recipe["sections"][0]["mappings"][4]["measurement_semantics"] = "metadata"
        self.assertEqual(run_import_recipe_validate(FIXTURE, recipe)["error"]["code"], "RECIPE_SCHEMA_INCOMPATIBLE")

    def test_recipe_rejects_stale_semantic_fingerprint(self) -> None:
        recipe = fixture_recipe()
        recipe["global_decisions"]["duplicate_policy"] = "review_each"
        response = run_import_recipe_validate(FIXTURE, recipe)
        self.assertEqual(response["error"]["code"], "RECIPE_SCHEMA_INCOMPATIBLE")
        refresh_recipe_fingerprint(recipe)
        self.assertIn("result", run_import_recipe_validate(FIXTURE, recipe))

    def test_recipe_requires_iron_semantics(self) -> None:
        recipe = fixture_recipe()
        recipe["global_decisions"]["fe_semantics"] = "not_present"
        response = run_import_recipe_validate(FIXTURE, recipe)
        self.assertEqual(response["error"]["code"], "IRON_SEMANTICS_REQUIRED")

    def test_recipe_rejects_another_source_revision(self) -> None:
        recipe = fixture_recipe()
        recipe["source_file_sha256"] = "0" * 64
        response = run_import_recipe_validate(FIXTURE, recipe)
        self.assertEqual(response["error"]["code"], "SOURCE_FINGERPRINT_MISMATCH")

    def test_plan_preserves_censored_missing_decimal_and_duplicate_information(self) -> None:
        recipe = fixture_recipe()
        response = run_import_plan_create(FIXTURE, recipe)
        self.assertIn("result", response)
        plan = response["result"]
        self.assertEqual(plan["summary"]["planned_analysis_count"], 8)
        self.assertEqual(plan["summary"]["planned_measurement_count"], 42)
        self.assertEqual(plan["summary"]["duplicate_candidate_groups"], 1)
        self.assertEqual(plan["summary"]["enabled_block_count"], 2)
        epma_first = plan["planned_records"][0]
        self.assertEqual(epma_first["measurements"][2]["raw_token"], "0,95")
        censored = plan["planned_records"][1]["measurements"][3]
        self.assertEqual(censored["raw_token"], "<0.01")
        self.assertEqual(censored["qualifier"], "below_detection_limit")
        self.assertEqual(censored["detection_limit"], 0.01)
        missing = plan["planned_records"][2]["measurements"][3]
        self.assertEqual(missing["qualifier"], "missing")
        self.assertEqual(len(plan["warnings"][0]["preview_ids"][0]), 2)
        self.assertNotEqual(plan["planned_records"][0]["preview_id"], plan["planned_records"][4]["preview_id"])

    def test_apply_is_atomic_and_preserves_source_provenance(self) -> None:
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "project.sqlite"
            recipe = fixture_recipe()
            result = apply_import_plan(database, FIXTURE, recipe)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT status FROM import_batch").fetchone()[0], "applied")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis").fetchone()[0], 8)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM measurement").fetchone()[0], 42)
                censored = connection.execute(
                    "SELECT raw_token, qualifier, detection_limit FROM measurement WHERE raw_token = '<0.01'"
                ).fetchone()
                self.assertEqual(censored, ("<0.01", "below_detection_limit", 0.01))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_row_provenance").fetchone()[0], 42)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_cell_provenance").fetchone()[0], 42)
                self.assertEqual(
                    connection.execute("SELECT semantic_fingerprint_sha256 FROM import_recipe_revision").fetchone()[0],
                    recipe["semantic_fingerprint"],
                )
            self.assertEqual(result["analysis_count"], 8)
            self.assertEqual(result["measurement_count"], 42)
        self.assertEqual(before, hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_apply_rolls_back_every_insert_after_a_database_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "project.sqlite"
            connection = open_project(database)
            with connection:
                connection.execute(
                    """CREATE TRIGGER fail_measurement BEFORE INSERT ON measurement
                    BEGIN SELECT RAISE(ABORT, 'forced transactional failure'); END"""
                )
            connection.close()
            with self.assertRaises(sqlite3.IntegrityError):
                apply_import_plan(database, FIXTURE, fixture_recipe())
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_file").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis").fetchone()[0], 0)

    def test_managed_copy_is_preserved_separately_from_source(self) -> None:
        recipe = fixture_recipe()
        recipe["ownership_mode"] = "managed_copy"
        refresh_recipe_fingerprint(recipe)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "project.sqlite"
            result = apply_import_plan(database, FIXTURE, recipe)
            copied = Path(directory) / "sources" / f"{result['source_id']}.xlsx"
            self.assertTrue(copied.is_file())
            self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(), hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
            with closing(sqlite3.connect(database)) as connection:
                linked_path, managed_path = connection.execute(
                    "SELECT linked_path, managed_relative_path FROM source_file WHERE source_id = ?", (result["source_id"],)
                ).fetchone()
            self.assertIsNone(linked_path)
            self.assertEqual(managed_path, f"sources/{result['source_id']}.xlsx")

    def test_changed_linked_source_is_flagged_without_refreshing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            linked_source = directory / "linked.xlsx"
            shutil.copyfile(FIXTURE, linked_source)
            recipe = fixture_recipe()
            result = apply_import_plan(directory / "project.sqlite", linked_source, recipe)
            self.assertEqual(check_linked_source(directory / "project.sqlite", result["source_id"])["state"], "current")
            with linked_source.open("ab") as changed:
                changed.write(b"changed outside PetroLab")
            status = check_linked_source(directory / "project.sqlite", result["source_id"])
            self.assertEqual(status["state"], "source_changed")
            with closing(sqlite3.connect(directory / "project.sqlite")) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0], 1)

    def test_saving_recipe_revision_keeps_previous_snapshot_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "project.sqlite"
            first_recipe = fixture_recipe()
            imported = apply_import_plan(database, FIXTURE, first_recipe)
            revised_recipe = fixture_recipe()
            revised_recipe["global_decisions"]["duplicate_policy"] = "review_each"
            refresh_recipe_fingerprint(revised_recipe)
            revision = save_import_recipe_revision(
                database, imported["source_id"], revised_recipe, imported["recipe_revision_id"]
            )
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute(
                    "SELECT recipe_revision_id, supersedes_recipe_revision_id, recipe_json FROM import_recipe_revision ORDER BY created_at, rowid"
                ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][0], revision["recipe_revision_id"])
            self.assertEqual(rows[1][1], imported["recipe_revision_id"])
            self.assertEqual(json.loads(rows[0][2])["global_decisions"]["duplicate_policy"], "keep_all")
            self.assertEqual(json.loads(rows[1][2])["global_decisions"]["duplicate_policy"], "review_each")


if __name__ == "__main__":
    unittest.main()
