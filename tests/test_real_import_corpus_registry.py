from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "fixtures" / "import" / "real-corpus.registry.json"
PRIVATE_DIR = ROOT / "fixtures" / "import" / "real-private"


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


if __name__ == "__main__":
    unittest.main()
