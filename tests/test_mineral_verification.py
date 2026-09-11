from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.mineral_verification import verify_record  # noqa: E402
from petrolab.mineral_verification import controlled_label, reported_target


def complete_silica_record(reported_mineral):
    values = {
        "SiO2": 95,
        "Al2O3": 0,
        "MgO": 0,
        "CaO": 0,
        "Na2O": 0,
        "K2O": 0,
        "FeO": 0,
    }
    measurements = [
        {
            "field": field,
            "unit": "wt.%",
            "raw_token": str(value),
            "value_status": "numeric",
            "reported_fe_form": None,
        }
        for field, value in values.items()
    ]
    return {
        "preview_id": "silica-1",
        "measurements": measurements,
        "reported_mineral": reported_mineral,
    }


class MineralVerificationTests(unittest.TestCase):
    def test_exact_aliases_preserve_species_and_separate_chemical_target(self):
        for text in ('Флогопит', 'Phl', 'phlogopite'):
            self.assertEqual(controlled_label(text), 'phlogopite')
            self.assertEqual(reported_target(text), 'trioctahedral mica')
        self.assertEqual(reported_target('Cpx'), 'clinopyroxene')
        self.assertIsNone(controlled_label('unknown label'))

    def test_unrecognized_manual_annotation_is_visible_not_stale(self):
        record = complete_silica_record('silica')
        record['mineral_assignment'] = {'value': 'unknown label', 'origin': 'user_assigned'}
        result = verify_record(record)
        self.assertEqual(result['status'], 'manual_unresolved')
        self.assertEqual(result['manual_assignment']['value'], 'unknown label')
        self.assertIsNone(result['accepted'])
        self.assertNotIn('accepted_assignment_stale', result['issues'])

    def test_missing_volatiles_only_allow_bounded_olivine_exception(self):
        from copy import deepcopy
        record = complete_silica_record('olivine')
        for measurement in record['measurements']:
            measurement['raw_token'] = str({'SiO2': 40, 'MgO': 50, 'FeO': 10}.get(measurement['field'], 0))
        for field in ('F', 'Cl'):
            for state, token in [('missing', None), ('below_detection_limit', '<DL')]:
                changed = deepcopy(record)
                changed['measurements'].append({'field': field, 'unit': 'wt.%', 'raw_token': token, 'value_status': state})
                result = verify_record(changed)
                self.assertEqual(result['prediction'], 'olivine')
                self.assertEqual(result['excluded_inputs'], [field])
                self.assertEqual(changed['measurements'][-1]['raw_token'], token)
        silica = complete_silica_record('silica')
        silica['measurements'].append({'field': 'F', 'unit': 'wt.%', 'raw_token': None, 'value_status': 'missing'})
        self.assertIsNone(verify_record(silica)['prediction'])
        record['measurements'] = [m for m in record['measurements'] if m['field'] != 'K2O']
        result = verify_record(record)
        self.assertIsNone(result['prediction'])
        self.assertIn('K2O', result['missing_components'])

    def test_legacy_string_reported_label_is_safe_and_compared(self) -> None:
        result = verify_record(complete_silica_record("silica"))

        self.assertEqual(result["reported_mineral"], "silica")
        self.assertEqual(result["prediction"], "silica")
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(result["confidence"], "high")

    def test_current_fingerprint_keeps_an_explicit_acceptance(self) -> None:
        record = complete_silica_record({"value": "silica", "origin": "source"})
        suggestion = verify_record(record)
        accepted = {
            "target": suggestion["prediction"],
            "input_fingerprint": suggestion["input_fingerprint"],
            "ruleset_version": suggestion["ruleset_version"],
        }

        result = verify_record(record, accepted=accepted)

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["accepted"]["target"], "silica")
        self.assertNotIn("accepted_assignment_stale", result["issues"])


if __name__ == "__main__":
    unittest.main()
