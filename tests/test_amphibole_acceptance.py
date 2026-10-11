"""Run the same AT-45 scenario that gates the packaged Windows service."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class AmphiboleServiceAcceptanceTests(unittest.TestCase):
    def test_real_ndjson_acceptance(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, str(root / 'scripts/qa_amphibole_service.py')],
                                   cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['service'], 'python')
        self.assertEqual(report['method'], 'amphibole.oxygen23/0.1.0')
        self.assertEqual(len(report['checks']), 7)
