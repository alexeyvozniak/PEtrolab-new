from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_preview import inspect_source  # noqa: E402


CORPUS_DIR = ROOT / "fixtures" / "import"


def load_cases() -> list[tuple[Path, dict]]:
    cases: list[tuple[Path, dict]] = []
    for expectation_path in sorted(CORPUS_DIR.glob("*.expected.json")):
        expectation = json.loads(expectation_path.read_text(encoding="utf-8"))
        cases.append((expectation_path, expectation))
    return cases


class ImportRegressionCorpusTests(unittest.TestCase):
    def test_corpus_is_not_empty(self) -> None:
        self.assertTrue(load_cases(), "Import regression corpus must contain at least one *.expected.json case")

    def test_every_corpus_case_preserves_source_and_matches_inspection_contract(self) -> None:
        for expectation_path, expectation in load_cases():
            with self.subTest(case=expectation_path.name):
                self.assertEqual(expectation.get("fixture_version"), 1)
                source_name = expectation.get("source_file")
                self.assertIsInstance(source_name, str)
                self.assertTrue(source_name)
                source_path = expectation_path.with_name(source_name)
                self.assertTrue(source_path.is_file(), f"Missing source fixture for {expectation_path.name}: {source_name}")

                before = hashlib.sha256(source_path.read_bytes()).hexdigest()
                inspection = inspect_source(source_path)
                after = hashlib.sha256(source_path.read_bytes()).hexdigest()

                self.assertEqual(after, before, "Inspection must never mutate the source fixture")
                self.assertEqual(inspection.fingerprint, before)
                self.assertEqual([sheet.name for sheet in inspection.sheets], expectation.get("sheets"))

                projection = inspection.projection()
                self.assertEqual(
                    len(projection.get("candidate_blocks", [])),
                    expectation.get("expected_candidate_blocks"),
                )

                outcome = expectation.get("required_outcome", {}).get("inspect_source")
                self.assertIn(outcome, {"success", "success_with_warnings"})
                if outcome == "success_with_warnings":
                    self.assertTrue(projection.get("warnings"), "Expected import inspection warnings were not emitted")

                self.assertIsInstance(expectation.get("required_detection", {}), dict)


if __name__ == "__main__":
    unittest.main()
