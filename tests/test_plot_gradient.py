import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from petrolab.plot_gradient import gradient_payload, plot_gradient_values
from petrolab.plot_data import plot_catalog
from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.import_apply import apply_import_plan
from petrolab.import_preview import ImportCommandError


class PlotGradientTests(unittest.TestCase):
    def test_exact_value_status_and_provenance(self):
        axis = {"field":"TiO2","unit":"wt.%","measurement_set":None,"method":None}
        def row(id, token, qualifier=None, form=None):
            return {"analysis_id":id,"measurement_id":id+token,"raw_token":token,
                    "qualifier":qualifier,"value_status":"numeric","reported_fe_form":form}
        rows = [row("a","0"),row("b","2.5"),row("c","<0.1","<"),row("d","1"),row("d","2"),
                row("e","invalid")]
        result = gradient_payload(axis,["f","e","d","c","b","a"],rows)
        self.assertEqual(result["counts"],{"numeric":2,"missing":1,"duplicate":1,"censored":1,"excluded":1})
        self.assertEqual((result["minimum"],result["maximum"]),(0,2.5))
        self.assertEqual(result["entries"][2]["measurements"][0]["raw_token"],"<0.1")
        self.assertEqual(result["fingerprint"],gradient_payload(axis,["a","b","c","d","e","f"],rows)["fingerprint"])
        self.assertNotEqual(result["fingerprint"],gradient_payload(axis,["a","b","c","d","e","f"],[row("a","0.0"),*rows[1:]])["fingerprint"])
        with self.assertRaises(ImportCommandError):
            gradient_payload(axis,["a","b"],[row("a","1",form="FeO"),row("b","2",form="FeOt")])

    def test_project_exact_field_and_unit(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"input.csv"
            source.write_text("Analysis,SiO2 [wt.%],MgO [wt.%]\nP1,40,50\nP2,50,20\n",encoding="utf-8")
            database=root/"project.sqlite"
            apply_import_plan(database,source,suggest_import_recipe(source)["recipe"])
            axis=next(item for item in plot_catalog(database)["axes"] if item["field"]=="MgO")
            result=plot_gradient_values(database,axis)
            self.assertEqual((result["minimum"],result["maximum"]),(20,50))
            self.assertEqual(result["counts"]["numeric"],2)
            self.assertEqual(len(result["entries"]),2)
            self.assertEqual(plot_gradient_values(database,{**axis,"unit":"ppm"})["counts"]["missing"],2)
            ids=[result["entries"][0]["analysis_id"]]
            self.assertEqual(len(plot_gradient_values(database,axis,ids)["entries"]),1)
