from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.import_preview import preview_source_window  # noqa: E402
from real_world_fixtures import write_xlsx  # noqa: E402


class InstrumentPreambleRegressionTests(unittest.TestCase):
    def test_service_metadata_before_eds_header_does_not_create_fake_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = write_xlsx(Path(directory) / "2019-like.xlsx", {
                "18KA-20": [
                    ["Project: synthetic"],
                    ["Owner: analyst"],
                    [None],
                    [None],
                    [None],
                    ["Sample: Sample 1", "Point: service metadata"],
                    ["Type: Default"],
                    ["ID:"],
                    [None],
                    ["Processing option : Oxygen by stoichiometry"],
                    [None],
                    ["All results in compound%"],
                    [None],
                    ["Spectrum", "In stats.", "F", "Na", "Mg", "Al", "Si", "P", "K", "Ca", "Ti", "V", "Cr"],
                    ["Spectrum 1", "Yes", 1.2, 0.4, 10.1, 8.4, 20.1, 0.2, 0.3, 12.1, 1.0, 0.1, 0.2],
                    ["Spectrum 2", "Yes", 1.0, 0.5, 9.9, 8.6, 20.3, 0.2, 0.3, 12.0, 1.1, 0.1, 0.2],
                ]
            })

            suggestion = suggest_import_recipe(source)
            sections = suggestion["recipe"]["sections"]
            self.assertEqual(len(sections), 1)
            self.assertEqual(sections[0]["sheet_name"], "18KA-20")
            self.assertEqual(sections[0]["header_row"], 14)
            self.assertEqual(sections[0]["data_start_row"], 15)
            self.assertEqual(sections[0]["data_end_row"], 16)

    def test_raw_preview_can_jump_directly_to_later_physical_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rows = [[f"service row {index}"] for index in range(1, 80)]
            rows[59] = ["Analysis", "SiO2", "MgO"]
            rows[60] = ["A-1", 50.1, 10.2]
            source = write_xlsx(Path(directory) / "long-sheet.xlsx", {"Sheet1": rows})

            preview = preview_source_window(source, "Sheet1", 56, 12, 0, 6)
            self.assertEqual(preview["start_row"], 56)
            self.assertEqual(preview["end_row"], 67)
            self.assertEqual(preview["used_range"]["rows"], 79)
            self.assertEqual(preview["rows"][4]["values"][:3], ["Analysis", "SiO2", "MgO"])


if __name__ == "__main__":
    unittest.main()
