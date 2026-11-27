from types import SimpleNamespace
import unittest
from petrolab.import_unit_diagnostics import composition_unit_hint


class NumericUnitHintsTests(unittest.TestCase):
    def mapping(self, field, index, axis="column"):
        return {"target_role":"ignore","review_decision":"unresolved","suggested_target":"measurement",
                "suggested_canonical_field":field, "source_"+axis+"_index":index}

    def section(self, fields, transposed=False):
        axis="row" if transposed else "column"
        return {"block_id":"b","sheet_name":"s","orientation":"columns_are_analyses" if transposed else "rows_are_analyses",
                "data_start_row":2,"data_end_row":5,"data_start_column":2,"data_end_column":5,
                "mappings":[self.mapping(field,i+1,axis) for i,field in enumerate(fields)]}

    def test_near_100_is_hint_only_and_transposition_invariant(self):
        names=["SiO2","MgO","Al2O3","CaO"]
        rows=[["Analysis",*names],["P1","40","30","20","10"],["P2","41","30","20","9"],
              ["P3","42","29","20","9"],["P4","<DL","30","20","10"]]
        for transposed in (False,True):
            sheet=SimpleNamespace(rows=tuple(zip(*rows)) if transposed else rows)
            section=self.section(names,transposed)
            hint=composition_unit_hint(sheet,section)
            self.assertEqual(hint["hint_kind"],"near_100")
            self.assertEqual(hint["complete_count"],3)
            self.assertEqual(hint["median_sum"],100)
            self.assertFalse(hint["blocking"])
            self.assertNotIn("unit",hint)
            self.assertTrue(all("unit" not in m for m in section["mappings"]))

    def test_small_elements_and_exclusions(self):
        names=["Si","Mg","Al","Ca"]
        rows=[["Analysis",*names]]+[[str(i),"3","2","1","1"] for i in range(4)]
        sheet=SimpleNamespace(rows=rows)
        section=self.section(names)
        self.assertEqual(composition_unit_hint(sheet,section)["hint_kind"],"small_element_sum")
        section["mappings"][0]["unit"]="apfu"
        self.assertIsNone(composition_unit_hint(sheet,section))
        section=self.section(["SiO2","Mg","Al","Ca"])
        self.assertIsNone(composition_unit_hint(sheet,section))
        section=self.section(names)
        rows[1][1]="<DL"; rows[2][1]=""
        self.assertIsNone(composition_unit_hint(sheet,section))
