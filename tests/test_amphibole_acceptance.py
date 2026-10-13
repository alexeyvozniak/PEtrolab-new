"""Run the AT-45/46 family scenarios that gate the packaged Windows service."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class AmphiboleServiceAcceptanceTests(unittest.TestCase):
    def test_real_ndjson_acceptance(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, str(root / 'scripts/qa_amphibole_service.py'), '--all-methods'],
                                   cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['service'], 'python')
        self.assertEqual(report['method'], 'amphibole.oxygen23/0.1.0')
        self.assertEqual(len(report['checks']), 7)
        self.assertEqual(set(report['additional_methods']), {'olivine.oxygen4', 'mica.charge22',
                         'clinopyroxene.oxygen6', 'orthopyroxene.oxygen6', 'garnet.structural12', 'clinopyroxene.structural6'})
