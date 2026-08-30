from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.import_preview import ImportCommandError, create_import_plan, inspect_source  # noqa: E402
from petrolab.manual_mapping import revise_import_mapping  # noqa: E402


FIXTURE = ROOT / "fixtures/import/m1_1_ambiguous_multisheet.xlsx"


class ManualMappingTests(unittest.TestCase):
    def test_ignored_element_can_be_promoted_to_explicit_measurement(self) -> None:
        original = suggest_import_recipe(FIXTURE)["recipe"]
        trace = next(section for section in original["sections"] if section["sheet_name"] == "Trace_elements")
        mapping = next(item for item in trace["mappings"] if item["source_header"] == "F (unknown unit)")
        self.assertEqual(mapping["target_role"], "ignore")

        revised = revise_import_mapping(
            FIXTURE,
            original,
            "Trace_elements",
            mapping["source_column_index"],
            "Measurement",
            "F",
            "ppm",
        )["recipe"]

        revised_trace = next(section for section in revised["sections"] if section["sheet_name"] == "Trace_elements")
        revised_mapping = next(item for item in revised_trace["mappings"] if item["source_header"] == "F (unknown unit)")
        self.assertEqual(revised_mapping["target_role"], "measurement")
        self.assertEqual(revised_mapping["canonical_field"], "F")
        self.assertEqual(revised_mapping["unit"], "ppm")
        self.assertNotEqual(revised["semantic_fingerprint"], original["semantic_fingerprint"])
        self.assertEqual(mapping["target_role"], "ignore", "revision must not mutate the original recipe")

        plan = create_import_plan(inspect_source(FIXTURE), revised)
        self.assertTrue(any(
            measurement["field"] == "F" and measurement["unit"] == "ppm"
            for record in plan["planned_records"]
            for measurement in record["measurements"]
        ))

    def test_measurement_revision_requires_explicit_unit(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        trace = next(section for section in recipe["sections"] if section["sheet_name"] == "Trace_elements")
        mapping = next(item for item in trace["mappings"] if item["source_header"] == "F (unknown unit)")
        with self.assertRaises(ImportCommandError) as context:
            revise_import_mapping(
                FIXTURE,
                recipe,
                "Trace_elements",
                mapping["source_column_index"],
                "Measurement",
                "F",
                None,
            )
        self.assertEqual(context.exception.code, "UNKNOWN_UNIT")

    def test_identity_role_can_be_reassigned_explicitly(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        section = recipe["sections"][0]
        mapping = section["mappings"][0]
        revised = revise_import_mapping(
            FIXTURE,
            recipe,
            section["sheet_name"],
            mapping["source_column_index"],
            "Sample",
        )["recipe"]
        revised_section = next(item for item in revised["sections"] if item["sheet_name"] == section["sheet_name"])
        revised_mapping = next(item for item in revised_section["mappings"] if item["source_column_index"] == mapping["source_column_index"])
        self.assertEqual(revised_mapping["target_role"], "identity")
        self.assertEqual(revised_mapping["canonical_field"], "Sample")


if __name__ == "__main__":
    unittest.main()
