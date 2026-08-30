from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_preview import inspect_source  # noqa: E402
from petrolab.ndjson_service import PROTOCOL_VERSION, handle_request, serve  # noqa: E402
from test_import_preview import FIXTURE, fixture_recipe  # noqa: E402


class NdjsonServiceTests(unittest.TestCase):
    def test_command_result_is_versioned_and_correlated(self) -> None:
        response = handle_request({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "command": "import.inspect_source",
            "payload": {"source_path": str(FIXTURE)},
        })
        self.assertIsNotNone(uuid.UUID(response["request_id"]))
        self.assertEqual(response["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(response["result"]["source_fingerprint"], inspect_source(FIXTURE).fingerprint)

    def test_error_is_structured_and_request_id_is_preserved(self) -> None:
        response = handle_request({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "command": "import.recipe.validate",
            "payload": {"source_path": str(FIXTURE), "recipe": {}},
        })
        self.assertIsNotNone(uuid.UUID(response["request_id"]))
        self.assertEqual(response["error"]["code"], "RECIPE_SCHEMA_INCOMPATIBLE")

    def test_protocol_unknown_command_and_invalid_request_do_not_raise(self) -> None:
        request_id = str(uuid.uuid4())
        self.assertEqual(handle_request({"protocol_version": "2.0", "request_id": request_id, "command": "import.inspect_source", "payload": {}})["error"]["code"], "PROTOCOL_VERSION_UNSUPPORTED")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": request_id, "command": "plot.query", "payload": {}})["error"]["code"], "UNKNOWN_COMMAND")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": request_id, "command": "import.inspect_source"})["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": "not-a-uuid", "command": "import.inspect_source"})["error"]["code"], "INVALID_REQUEST")

    def test_stream_writes_one_json_response_per_line_and_shutdowns(self) -> None:
        input_stream = io.StringIO("\n".join([
            json.dumps({"protocol_version": "1.0", "request_id": "6b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "import.plan.create", "payload": {"source_path": str(FIXTURE), "recipe": fixture_recipe()}}),
            json.dumps({"protocol_version": "1.0", "request_id": "7b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "shutdown", "payload": {}}),
        ]) + "\n")
        output_stream = io.StringIO()
        serve(input_stream, output_stream)
        responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["result"]["summary"]["planned_analysis_count"], 8)
        self.assertEqual(responses[1], {"protocol_version": "1.0", "request_id": "7b178581-aa86-4bb1-9742-4fd5324c22ed", "result": {"status": "shutting_down"}})

    def test_shutdown_obeys_protocol_version(self) -> None:
        input_stream = io.StringIO(json.dumps({"protocol_version": "2.0", "request_id": "8b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "shutdown", "payload": {}}) + "\n")
        output_stream = io.StringIO()
        serve(input_stream, output_stream)
        response = json.loads(output_stream.getvalue())
        self.assertEqual(response["request_id"], "8b178581-aa86-4bb1-9742-4fd5324c22ed")
        self.assertEqual(response["error"]["code"], "PROTOCOL_VERSION_UNSUPPORTED")

    def test_apply_and_linked_source_check_are_available_through_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            response = handle_request({
                "protocol_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "command": "import.plan.apply",
                "payload": {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()},
            })
            self.assertEqual(response["result"]["analysis_count"], 8)
            status = handle_request({
                "protocol_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "command": "source.check_linked",
                "payload": {"project_database_path": database, "source_id": response["result"]["source_id"]},
            })
            self.assertEqual(status["result"]["state"], "current")

    def test_recipe_revision_is_saved_as_a_new_transport_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            imported = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "import.plan.apply",
                "payload": {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()},
            })["result"]
            revised = fixture_recipe()
            revised["global_decisions"]["duplicate_policy"] = "keep_all"
            from test_import_preview import refresh_recipe_fingerprint
            refresh_recipe_fingerprint(revised)
            response = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "import.recipe.save_revision",
                "payload": {
                    "project_database_path": database, "source_id": imported["source_id"], "recipe": revised,
                    "supersedes_recipe_revision_id": imported["recipe_revision_id"],
                },
            })
            self.assertEqual(response["result"]["supersedes_recipe_revision_id"], imported["recipe_revision_id"])


if __name__ == "__main__":
    unittest.main()
