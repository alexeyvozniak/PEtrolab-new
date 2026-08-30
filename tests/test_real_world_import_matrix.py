from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe  # noqa: E402
from petrolab.import_apply import apply_import_plan  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source, preview_source_window  # noqa: E402
from petrolab.manual_mapping import revise_import_mappings, revise_import_sections  # noqa: E402
from real_world_fixtures import (  # noqa: E402
    atomic_percent,
    complementary_duplicate_blocks,
    duplicate_field_methods,
    generic_isotope,
    long_preamble_weight_percent,
    multiple_blocks,
    repeated_headers,
    transposed_weight_percent,
)


class RealWorldImportMatrixTests(unittest.TestCase):
    def test_generic_numeric_table_does_not_require_known_geochemistry_headers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = generic_isotope(Path(directory) / "MORB-like.xlsx")
            inspection = inspect_source(source)
            self.assertEqual(inspection.sheets[0].header_rows, (1,))
            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            self.assertEqual(section["header_row"], 1)
            self.assertTrue(all(mapping["target_role"] == "ignore" for mapping in section["mappings"]))
            decisions = [
                {
                    "block_id": section["block_id"],
                    "source_axis": "column",
                    "source_index": mapping["source_column_index"],
                    "target": "Measurement",
                    "canonical_field": mapping["source_header"],
                    "unit": "ratio",
                }
                for mapping in section["mappings"]
            ]
            revised = revise_import_mappings(source, suggestion["recipe"], decisions)["recipe"]
            plan = create_import_plan(inspection, revised)
            self.assertEqual(plan["summary"]["planned_analysis_count"], 3)
            self.assertEqual(plan["summary"]["planned_measurement_count"], 9)

    def test_long_preamble_supplies_explicit_weight_percent_context_and_skips_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = long_preamble_weight_percent(Path(directory) / "instrument.xlsx")
            suggestion = suggest_import_recipe(source)
            self.assertEqual(len(suggestion["recipe"]["sections"]), 1)
            section = suggestion["recipe"]["sections"][0]
            self.assertEqual(section["header_row"], 5)
            self.assertEqual(section["data_start_row"], 7)
            self.assertEqual(section["unit_context"]["unit"], "wt.%")
            mapped = {mapping["canonical_field"]: mapping for mapping in section["mappings"]}
            self.assertEqual(mapped["SiO2"]["unit"], "wt.%")
            self.assertEqual(mapped["MgO"]["unit"], "wt.%")
            self.assertFalse(any(warning["code"] == "UNIT_REQUIRES_REVIEW" for warning in suggestion["warnings"]))

    def test_repeated_headers_create_separate_blocks_and_never_become_analysis_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = repeated_headers(Path(directory) / "repeated.xlsx")
            suggestion = suggest_import_recipe(source)
            sections = suggestion["recipe"]["sections"]
            self.assertEqual([section["header_row"] for section in sections], [1, 5])
            plan = create_import_plan(inspect_source(source), suggestion["recipe"])
            self.assertEqual(plan["summary"]["planned_analysis_count"], 4)
            self.assertEqual([record["row_number"] for record in plan["planned_records"]], [2, 3, 6, 7])
            revised = revise_import_sections(source, suggestion["recipe"], [{"block_id": sections[1]["block_id"], "enabled": False}])["recipe"]
            reduced = create_import_plan(inspect_source(source), revised)
            self.assertEqual(reduced["summary"]["planned_analysis_count"], 2)
            self.assertEqual(reduced["summary"]["enabled_block_count"], 1)

    def test_two_tables_on_one_sheet_are_exposed_as_two_reviewable_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = multiple_blocks(Path(directory) / "two-blocks.xlsx")
            suggestion = suggest_import_recipe(source)
            sections = suggestion["recipe"]["sections"]
            self.assertEqual(len(sections), 2)
            self.assertEqual([section["header_row"] for section in sections], [1, 5])
            self.assertEqual([section["data_end_row"] for section in sections], [3, 7])

    def test_complementary_blocks_with_same_identity_are_warned_not_silently_merged(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = complementary_duplicate_blocks(directory / "complementary.xlsx")
            suggestion = suggest_import_recipe(source)
            plan = create_import_plan(inspect_source(source), suggestion["recipe"])
            self.assertEqual(plan["summary"]["planned_analysis_count"], 4)
            self.assertEqual(plan["summary"]["duplicate_candidate_groups"], 2)
            self.assertEqual(len(plan["warnings"]), 1)
            self.assertEqual(plan["warnings"][0]["code"], "DUPLICATE_CANDIDATES")
            self.assertEqual(sorted(len(group) for group in plan["warnings"][0]["preview_ids"]), [2, 2])
            first_block_fields = {item["field"] for item in plan["planned_records"][0]["measurements"]}
            second_block_fields = {item["field"] for item in plan["planned_records"][2]["measurements"]}
            self.assertEqual(first_block_fields, {"SiO2", "MgO"})
            self.assertEqual(second_block_fields, {"La", "Ce"})

            applied = apply_import_plan(directory / "project.sqlite", source, suggestion["recipe"])
            self.assertEqual(applied["analysis_count"], 4)
            with closing(sqlite3.connect(directory / "project.sqlite")) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis").fetchone()[0], 4)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM measurement").fetchone()[0], 8)

    def test_transposed_block_is_normalized_in_memory_and_preserves_physical_cells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = transposed_weight_percent(directory / "transposed.xlsx")
            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            revised = revise_import_sections(source, suggestion["recipe"], [{
                "block_id": section["block_id"],
                "orientation": "columns_are_analyses",
                "header_column": 1,
                "data_start_column": 2,
                "data_end_column": 3,
                "analysis_axis_role": "Analysis",
                "analysis_axis_field": "Analysis",
                "rebuild_mappings": True,
            }])["recipe"]
            plan = create_import_plan(inspect_source(source), revised)
            self.assertEqual(plan["summary"]["planned_analysis_count"], 2)
            self.assertEqual(plan["summary"]["planned_measurement_count"], 6)
            first = plan["planned_records"][0]
            self.assertEqual(first["orientation"], "columns_are_analyses")
            self.assertEqual(first["identity"], ("A-1",))
            self.assertEqual(first["measurements"][0]["field"], "SiO2")
            self.assertEqual(first["measurements"][0]["unit"], "wt.%")
            self.assertEqual(first["measurements"][0]["source_cell"], "B3")
            self.assertEqual(first["measurements"][1]["source_cell"], "B4")

            database = directory / "project.sqlite"
            applied = apply_import_plan(database, source, revised)
            self.assertEqual(applied["analysis_count"], 2)
            self.assertEqual(applied["measurement_count"], 6)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_cell_provenance").fetchone()[0], 6)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_row_provenance").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis WHERE source_orientation = 'columns_are_analyses'").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT source_cell FROM measurement ORDER BY rowid LIMIT 2").fetchall(), [("B3",), ("B4",)])

    def test_atomic_percent_is_not_collapsed_into_mol_percent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = atomic_percent(Path(directory) / "atomic.xlsx")
            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            self.assertEqual(section["unit_context"]["unit"], "at.%")
            units = {
                mapping["unit"]
                for mapping in section["mappings"]
                if mapping["target_role"] == "measurement"
            }
            self.assertEqual(units, {"at.%"})

    def test_same_canonical_field_from_two_methods_stays_distinguishable(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = duplicate_field_methods(directory / "mixed-methods.xlsx")
            suggestion = suggest_import_recipe(source)
            section = suggestion["recipe"]["sections"][0]
            mappings = {item["source_header"]: item for item in section["mappings"]}
            decisions = []
            for header, method in (("SiO2 EPMA (wt.%)", "EPMA"), ("SiO2 SIMS (wt.%)", "SIMS")):
                mapping = mappings[header]
                decisions.append({
                    "block_id": section["block_id"],
                    "source_axis": "column",
                    "source_index": mapping["source_column_index"],
                    "target": "Measurement",
                    "canonical_field": "SiO2",
                    "unit": "wt.%",
                    "method": method,
                    "measurement_set": method,
                })
            revised = revise_import_mappings(source, suggestion["recipe"], decisions)["recipe"]
            plan = create_import_plan(inspect_source(source), revised)
            self.assertEqual([item["method"] for item in plan["planned_records"][0]["measurements"]], ["EPMA", "SIMS"])

            database = directory / "project.sqlite"
            applied = apply_import_plan(database, source, revised)
            projection = list_project_analyses(database)
            first = projection["analyses"][0]
            self.assertEqual(applied["source_metadata_count"], 4)
            self.assertEqual(first["source_metadata"]["Mineral"], "Phlogopite")
            self.assertIn(first["source_metadata"]["Generation"], {"core", "rim"})
            self.assertEqual(set(first["measurements"]), {"SiO2 · EPMA", "SiO2 · SIMS"})
            self.assertEqual({item["method"] for item in first["measurement_list"]}, {"EPMA", "SIMS"})
            self.assertTrue(all(item["source_cell"] for item in first["source_metadata_list"]))

    def test_raw_preview_returns_physical_rows_without_normalizing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = long_preamble_weight_percent(Path(directory) / "preview.xlsx")
            preview = preview_source_window(source, "EPMA", 4, 4, 0, 4)
            self.assertEqual(preview["rows"][0]["values"][0], "All results in weight%")
            self.assertEqual(preview["rows"][1]["values"], ["Analysis", "SiO2", "MgO", "FeO"])
            self.assertEqual(preview["rows"][2]["values"], [None, None, None, None])

    def test_legacy_xls_is_identified_honestly_instead_of_called_encrypted_xlsx(self) -> None:
        from petrolab.import_preview import ImportCommandError
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.xls"
            source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"synthetic-biff")
            with self.assertRaises(ImportCommandError) as raised:
                inspect_source(source)
            self.assertEqual(raised.exception.code, "LEGACY_XLS_REQUIRES_CONVERSION")


if __name__ == "__main__":
    unittest.main()
