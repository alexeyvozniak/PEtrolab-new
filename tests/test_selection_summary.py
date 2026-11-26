import unittest
from petrolab.selection_summary import summarize_measurements

def row(id, value, unit="wt.%", field="MgO", method="EPMA", measurement_set="A", qualifier=None, status="numeric", iron=None):
    return {"analysis_id":id,"field":field,"unit":unit,"measurement_set":measurement_set,"method":method,
            "reported_fe_form":iron,"raw_token":value,"qualifier":qualifier,"value_status":status}

class SelectionSummaryTests(unittest.TestCase):
    def test_exact_group_and_pair(self):
        rows=[row("a","10"),row("b","15"),row("a","1","ppm"),row("b","<2","ppm",qualifier="<"),
              row("a","0",field="CaO"),row("b","2",field="CaO")]
        out=summarize_measurements(rows,["a","b"])
        mg=next(x for x in out if x["field"]=="MgO" and x["unit"]=="wt.%")
        self.assertEqual((mg["n"],mg["mean"],mg["median"],mg["delta"],mg["relative_percent"]),(2,12.5,12.5,5,50))
        self.assertAlmostEqual(mg["sd"],3.5355339059)
        ppm=next(x for x in out if x["unit"]=="ppm")
        self.assertEqual((ppm["n"],ppm["excluded"],ppm["delta"]),(1,1,None))
        self.assertEqual(ppm["pair"][1]["raw_tokens"],["<2"])
        ca=next(x for x in out if x["field"]=="CaO")
        self.assertEqual((ca["delta"],ca["relative_percent"]),(2,None))

    def test_duplicates_missing_and_fe_separation(self):
        rows=[row("a","1"),row("a","2"),row("b","0"),row("a","10",field="FeO",iron="FeO"),row("b","15",field="FeO",iron="FeOT")]
        out=summarize_measurements(rows,["a","b","c"])
        mg=next(x for x in out if x["field"]=="MgO")
        self.assertEqual((mg["n"],mg["missing"],mg["duplicate"],mg["mean"]),(1,1,1,0))
        self.assertEqual(len([x for x in out if x["field"]=="FeO"]),2)
