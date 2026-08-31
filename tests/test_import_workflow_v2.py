from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.ndjson_service import handle_request  # noqa: E402


FIXTURE = ROOT / "fixtures/import/m1_1_ambiguous_multisheet.xlsx"


def request(command: str, payload: dict) -> dict:
    return handle_request({
        "protocol_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "command": command,
        "payload": payload,
    })


class ImportWorkflowV2TransportTests(unittest.TestCase):
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

    def test_latest_import_retraction_is_available_through_transport(self) -> None:
        recipe = suggest_import_recipe(FIXTURE)["recipe"]
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
