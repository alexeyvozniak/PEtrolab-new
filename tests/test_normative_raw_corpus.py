from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.clean_table import classify_clean_table  # noqa: E402
from petrolab.desktop_workflow import bulk_ignore_scopes, bulk_unit_scopes, suggest_import_recipe  # noqa: E402
from petrolab.import_preview import create_import_plan, inspect_source  # noqa: E402


CORPUS = ROOT / "fixtures" / "import" / "real-world"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))


class NormativeRawCorpusTests(unittest.TestCase):
    def test_every_owner_workbook_keeps_its_first_pass_projection(self) -> None:
        for expected in MANIFEST["files"]:
            with self.subTest(source=expected["name"]):
                source = CORPUS / expected["name"]
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertEqual(before, expected["sha256"])

                inspection = inspect_source(source)
                classification = classify_clean_table(inspection)
                self.assertEqual(classification["mode"], "raw_review")
                suggestion = suggest_import_recipe(source)
                recipe = suggestion["recipe"]
                plan = create_import_plan(inspection, recipe)
                scopes = bulk_unit_scopes(source, recipe)["scopes"]
                ignore_scopes = bulk_ignore_scopes(source, recipe)["scopes"]
                unresolved = sum(
                    warning.get("code") in {"UNIT_REQUIRES_REVIEW", "UNMAPPED_FIELD_REQUIRES_REVIEW"}
                    for warning in suggestion["warnings"]
                )

                observed = {
                    "source_format": inspection.source_format,
                    "sheets": len(inspection.sheets),
                    "blocks": len(recipe["sections"]),
                    "planned_analyses": plan["summary"]["planned_analysis_count"],
                    "planned_measurements": plan["summary"]["planned_measurement_count"],
                    "unresolved_fields": unresolved,
                    "bulk_unit_scopes": len(scopes),
                    "bulk_ignore_scopes": len(ignore_scopes),
                    "duplicate_groups": plan["summary"]["duplicate_candidate_groups"],
                }
                for field, value in observed.items():
                    self.assertEqual(value, expected[field], field)

                after = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertEqual(after, before, "import inspection must not rewrite the source")


if __name__ == "__main__":
    unittest.main()
