from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.ndjson_service import handle_request  # noqa: E402
from real_world_fixtures import write_xlsx  # noqa: E402


FIXTURE = ROOT / "fixtures/import/m1_1_ambiguous_multisheet.xlsx"


def request(command: str, payload: dict) -> dict:
    return handle_request({
        "protocol_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "command": command,
        "payload": payload,
    })


class ImportWorkflowV2TransportTests(unittest.TestCase):
    def test_repeated_unrecognized_fields_can_be_explicitly_ignored_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = write_xlsx(Path(directory) / "repeated-unknown.xlsx", {
                "Data": [
                    ["Analysis", "SiO2 (wt.%)", "Operator code"],
                    ["A-1", 40.1, "x"],
                    ["A-2", 40.2, "y"],
                    [None, None, None],
                    ["Analysis", "SiO2 (wt.%)", "Operator code"],
                    ["B-1", 39.9, "z"],
                    ["B-2", 40.0, "q"],
                ],
            })
            recipe = suggest_import_recipe(source)["recipe"]
            scopes = request("import.recipe.bulk_ignore_scopes", {
                "source_path": str(source),
                "recipe": recipe,
            })["result"]["scopes"]
            self.assertEqual(len(scopes), 1)
            self.assertEqual(scopes[0]["block_count"], 2)
            self.assertEqual(scopes[0]["field_count"], 2)

            applied = request("import.recipe.apply_bulk_ignore", {
                "source_path": str(source),
                "recipe": recipe,
                "bulk_scope_id": scopes[0]["bulk_scope_id"],
            })
            self.assertEqual(applied["result"]["applied_decision_count"], 2)
            self.assertFalse(request("import.recipe.bulk_ignore_scopes", {
                "source_path": str(source),
                "recipe": applied["result"]["recipe"],
            })["result"]["scopes"])

            stale = request("import.recipe.apply_bulk_ignore", {
                "source_path": str(source),
                "recipe": applied["result"]["recipe"],
                "bulk_scope_id": scopes[0]["bulk_scope_id"],
            })
            self.assertEqual(stale["error"]["code"], "STALE_BULK_SCOPE")

    def test_bulk_mapping_revision_is_available_through_transport(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        trace = next(section for section in recipe["sections"] if section["sheet_name"] == "Trace_elements")
        mapping = next(item for item in trace["mappings"] if item["source_header"] == "F (unknown unit)")
        response = request("import.recipe.revise_mappings", {
            "source_path": str(FIXTURE),
            "recipe": recipe,
            "decisions": [{
                "sheet_name": "Trace_elements",
                "source_column_index": mapping["source_column_index"],
                "target": "Measurement",
                "canonical_field": "F",
                "unit": "ppm",
            }],
        })
        self.assertEqual(response["result"]["applied_decision_count"], 1)

    def test_server_issued_bulk_unit_scope_is_exact_and_becomes_stale_after_use(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        scopes = request("import.recipe.bulk_scopes", {
            "source_path": str(FIXTURE),
            "recipe": recipe,
        })
        self.assertNotIn("error", scopes)
        scope = next(item for item in scopes["result"]["scopes"] if item["decision_kind"] == "measurement_unit")
        self.assertTrue(scope["targets"])

        applied = request("import.recipe.apply_bulk_unit", {
            "source_path": str(FIXTURE),
            "recipe": recipe,
            "bulk_scope_id": scope["bulk_scope_id"],
            "unit": "ppm",
        })
        self.assertEqual(applied["result"]["bulk_scope_id"], scope["bulk_scope_id"])
        self.assertEqual(applied["result"]["applied_decision_count"], scope["field_count"])

        stale = request("import.recipe.apply_bulk_unit", {
            "source_path": str(FIXTURE),
            "recipe": applied["result"]["recipe"],
            "bulk_scope_id": scope["bulk_scope_id"],
            "unit": "ppm",
        })
        self.assertEqual(stale["error"]["code"], "STALE_BULK_SCOPE")

    def test_latest_import_retraction_is_available_through_transport(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
        scopes = request("import.recipe.bulk_scopes", {
            "source_path": str(FIXTURE),
            "recipe": recipe,
        })
        self.assertNotIn("error", scopes)
        for scope in scopes["result"]["scopes"]:
            recipe = request("import.recipe.apply_bulk_unit", {
                "source_path": str(FIXTURE),
                "recipe": recipe,
                "bulk_scope_id": scope["bulk_scope_id"],
                "unit": "ppm",
            })["result"]["recipe"]
        reviewed = request("import.recipe.review_duplicates", {
            "source_path": str(FIXTURE),
            "recipe": recipe,
            "decision": "keep_all",
        })
        self.assertNotIn("error", reviewed)
        recipe = reviewed["result"]["recipe"]
        self.assertEqual(recipe["global_decisions"]["duplicate_policy"], "keep_all")

        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "petrolab.sqlite")
            for _ in range(2):
                applied = request("import.plan.apply", {
                    "project_database_path": database,
                    "source_path": str(FIXTURE),
                    "recipe": recipe,
                })
                self.assertNotIn("error", applied)
            before = request("project.analyses.list", {"project_database_path": database, "limit": 500})["result"]
            retracted = request("project.last_import.retract", {
                "project_database_path": database,
                "reason": "test_retraction",
            })["result"]
            after = request("project.analyses.list", {"project_database_path": database, "limit": 500})["result"]

        self.assertEqual(before["import_batch_count"], 2)
        self.assertEqual(after["import_batch_count"], 1)
        self.assertEqual(after["total"], before["total"] - retracted["analysis_count"])


if __name__ == "__main__":
    unittest.main()
