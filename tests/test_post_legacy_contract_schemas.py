from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class PostLegacyContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "validate_contracts", ROOT / "scripts" / "validate_contracts.py"
        )
        assert spec and spec.loader
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)
        cls.schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / "schemas").glob("*.schema.json")
        }

    def validate_example(self, name: str) -> dict:
        instance = load_json(f"examples/contracts/{name}.json")
        contract = instance.pop("$contract")
        self.validator._validate(
            instance,
            self.schemas[contract],
            self.schemas[contract],
            self.schemas,
        )
        return instance

    def assert_rejected(self, instance: dict, contract: str) -> None:
        with self.assertRaises(self.validator.ContractError):
            self.validator._validate(
                instance,
                self.schemas[contract],
                self.schemas[contract],
                self.schemas,
            )

    def test_import_recipe_has_explicit_iron_and_duplicate_semantics(self) -> None:
        recipe = self.validate_example("import-recipe")
        self.assertEqual(recipe["global_decisions"]["fe_semantics"], "total_as_feot")
        self.assertEqual(recipe["global_decisions"]["duplicate_policy"], "review_each")

        silent_merge = copy.deepcopy(recipe)
        silent_merge["global_decisions"]["duplicate_policy"] = "merge_first"
        self.assert_rejected(silent_merge, "import-recipe.schema.json")

    def test_scientific_method_requires_benchmark_and_forbids_pseudocount(self) -> None:
        method = self.validate_example("scientific-method-definition")
        self.assertEqual(method["input_domain"]["nonpositive_policy"], "reject")
        self.assertGreaterEqual(len(method["benchmark_ids"]), 1)

        without_benchmark = copy.deepcopy(method)
        without_benchmark["benchmark_ids"] = []
        self.assert_rejected(without_benchmark, "scientific-method-definition.schema.json")

        with_hidden_pseudocount = copy.deepcopy(method)
        with_hidden_pseudocount["input_domain"]["pseudocount"] = 1e-6
        self.assert_rejected(with_hidden_pseudocount, "scientific-method-definition.schema.json")

    def test_workspace_snapshot_cannot_embed_selection_or_measurements(self) -> None:
        snapshot = self.validate_example("workspace-snapshot")
        self.assertEqual(snapshot["selection_restore_policy"], "restore_exact_if_available")
        self.assertGreaterEqual(len(snapshot["selection_analysis_ids"]), 1)
        self.assertNotIn("selection_ids", snapshot)
        self.assertNotIn("measurements", snapshot)

        embedded_selection = copy.deepcopy(snapshot)
        embedded_selection["selection_ids"] = ["019c15f9-5d8a-7e31-89cf-86323913393f"]
        self.assert_rejected(embedded_selection, "workspace-snapshot.schema.json")

        embedded_measurements = copy.deepcopy(snapshot)
        embedded_measurements["measurements"] = [{"SiO2": 52.1}]
        self.assert_rejected(embedded_measurements, "workspace-snapshot.schema.json")

    def test_roadmap_keeps_rocks_and_streamlit_ui_out_of_current_release(self) -> None:
        roadmap = (ROOT / "docs/architecture/POST_LEGACY_IMPLEMENTATION_ROADMAP_2026-08-30.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("экран и классификационный workflow пород", roadmap)
        self.assertIn("копирование старого Streamlit UI", roadmap)
        self.assertIn("M1.1 `inspect → recipe validation → import plan`", roadmap)


if __name__ == "__main__":
    unittest.main()
