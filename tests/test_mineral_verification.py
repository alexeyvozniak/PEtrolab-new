from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.mineral_verification import verify_record  # noqa: E402


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
