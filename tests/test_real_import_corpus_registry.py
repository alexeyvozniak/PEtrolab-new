from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_real_import_corpus import snapshot_workbook  # noqa: E402


REGISTRY = ROOT / "fixtures" / "import" / "real-corpus.registry.json"
PRIVATE_DIR = ROOT / "fixtures" / "import" / "real-private"
PUBLIC_REGRESSION_FIXTURE = ROOT / "fixtures" / "import" / "m1_1_ambiguous_multisheet.xlsx"


class RealImportCorpusRegistryTests(unittest.TestCase):
    def test_registry_is_normative_and_contains_real_anchor_cases(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["corpus_version"], 1)
        self.assertEqual(registry["authority"], "real_source_workbooks")
        self.assertEqual(registry["storage"], "external_private")
        cases = registry["cases"]
        self.assertGreaterEqual(len(cases), 9)
        self.assertTrue(all(case["required"] is True for case in cases))
        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))

    def test_public_repository_does_not_contain_private_raw_workbooks(self) -> None:
        if not PRIVATE_DIR.exists():
            return
        raw = [
            path
            for path in PRIVATE_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        ]
        self.assertEqual(raw, [], f"Private real workbooks must not be committed: {raw}")

    def test_manifest_only_runner_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_real_import_corpus.py"), "--manifest-only"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("required workbooks", completed.stdout)

    def test_snapshot_protects_semantic_recognition_without_mutating_source(self) -> None:
        before = hashlib.sha256(PUBLIC_REGRESSION_FIXTURE.read_bytes()).hexdigest()
        snapshot = snapshot_workbook(PUBLIC_REGRESSION_FIXTURE)
        after = hashlib.sha256(PUBLIC_REGRESSION_FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(snapshot["sha256"], before)
        self.assertEqual(len(snapshot["recognition"]["semantic_fingerprint"]), 64)
        self.assertTrue(snapshot["recognition"]["sections"])
        self.assertTrue(any(section["mappings"] for section in snapshot["recognition"]["sections"]))


if __name__ == "__main__":
    unittest.main()
