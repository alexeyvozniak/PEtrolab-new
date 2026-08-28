from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_contracts", ROOT / "scripts" / "validate_contracts.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ArchitectureContractTests(unittest.TestCase):
    def test_required_files_and_approved_screens_exist(self) -> None:
        VALIDATOR.validate_required_files()

    def test_architecture_names_all_mandatory_boundaries(self) -> None:
        VALIDATOR.validate_architecture_language()

    def test_json_contract_examples_are_valid(self) -> None:
        VALIDATOR.validate_schemas_and_examples()

    def test_product_contract_covers_all_approved_screens(self) -> None:
        master = (ROOT / "docs/product/PRODUCT_UX_MASTER_SPECIFICATION.md").read_text(encoding="utf-8")
        for screen in ("Анализы", "Построение", "Шлифы"):
            self.assertIn(screen, master)

    def test_acceptance_covers_recent_approved_behaviors(self) -> None:
        acceptance = (ROOT / "docs/product/UI_ACCEPTANCE.md").read_text(encoding="utf-8")
        for acceptance_id in ("AT-16", "AT-17", "AT-18", "AT-19", "AT-20", "AT-21"):
            self.assertIn(acceptance_id, acceptance)


if __name__ == "__main__":
    unittest.main()
