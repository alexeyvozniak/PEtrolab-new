from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LegacyAuditContractTests(unittest.TestCase):
    def test_report_pins_both_revisions_and_all_decisions(self) -> None:
        report = (ROOT / "docs/product/LEGACY_STREAMLIT_AUDIT_REPORT_2026-08-30.md").read_text(encoding="utf-8")
        self.assertIn("e7bf36f46a6c049bc0dfb767483611e892503e41", report)
        self.assertIn("4e200b7e9ca020e36a7ebcad7134074222a0bcba", report)
        for decision in ("Keep", "Rework", "Defer", "Reject"):
            self.assertIn(decision, report)

    def test_scientific_guards_are_normative(self) -> None:
        rules = (ROOT / "docs/product/SCIENTIFIC_RULES.md").read_text(encoding="utf-8")
        for required in ("CLR/ILR", "pseudocount", "fingerprint", "Mineral Recognition", "Operation Journal"):
            self.assertIn(required, rules)

    def test_workspace_snapshot_is_not_template_or_selection(self) -> None:
        model = (ROOT / "docs/product/DOMAIN_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("Workspace Snapshot", model)
        self.assertIn("Analysis Template", model)
        self.assertIn("не содержит конкретные Analysis ID", model)

    def test_acceptance_covers_each_new_contract_family(self) -> None:
        acceptance = (ROOT / "docs/product/UI_ACCEPTANCE.md").read_text(encoding="utf-8")
        for acceptance_id in range(30, 38):
            self.assertIn(f"AT-{acceptance_id}", acceptance)

    def test_approved_statistics_images_are_present(self) -> None:
        screens = ROOT / "docs/design/reference/screens"
        for name in (
            "statistics-task-approved-v1.png",
            "statistics-data-review-approved-v1.png",
            "statistics-comparison-result-approved-v1.png",
        ):
            self.assertGreater((screens / name).stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main()
