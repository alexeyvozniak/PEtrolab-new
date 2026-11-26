import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from petrolab.plot_colors import get_project_plot_colors, save_project_plot_colors
from petrolab.import_preview import ImportCommandError

class PlotColorTests(unittest.TestCase):
    def test_project_isolation_persistence_revision_validation(self):
        with TemporaryDirectory() as folder:
            a,b=Path(folder)/"a.sqlite",Path(folder)/"b.sqlite"
            self.assertEqual(get_project_plot_colors(a)["revision"],0)
            scheme={"mode":"mineral","colors":[{"mode":"mineral","key":"phlogopite","color":"#AABBCC","symbol":"diamond"},
                {"mode":"sample","key":str(uuid4()),"color":"#112233"}]}
            saved=save_project_plot_colors(a,scheme,0)
            self.assertEqual(saved["revision"],1)
            self.assertEqual(saved["scheme"]["colors"][0]["color"],"#aabbcc")
            self.assertEqual(get_project_plot_colors(a),saved)
            self.assertEqual(saved["scheme"]["colors"][0]["symbol"],"diamond")
            with self.assertRaises(ValueError):
                save_project_plot_colors(a,{"mode":"mineral","colors":[{"mode":"mineral","key":"mica","color":"#112233","symbol":"unknown"}]},1)
            self.assertEqual(get_project_plot_colors(b)["revision"],0)
            with self.assertRaises(ImportCommandError):
                save_project_plot_colors(a,scheme,0)
            with self.assertRaises(ValueError):
                save_project_plot_colors(a,{"mode":"source","colors":[{"mode":"source","key":"bad","color":"#112233"}]},1)
            self.assertEqual(get_project_plot_colors(a),saved)

    def test_presets_roundtrip_isolation_and_revision(self):
        import json
        from petrolab.plot_colors import get_project_plot_presets, save_project_plot_presets
        with TemporaryDirectory() as folder:
            a,b=Path(folder)/"a.sqlite",Path(folder)/"b.sqlite"
            item={"kind":"binary","keys":[json.dumps(["MgO","wt.%",None,None]),json.dumps(["SiO2","wt.%",None,None])]}
            preferences={"favorites":[item],"recent":[item]}
            self.assertEqual(get_project_plot_presets(a)["revision"],0)
            saved=save_project_plot_presets(a,preferences,0)
            self.assertEqual(get_project_plot_presets(a),saved)
            self.assertEqual(get_project_plot_presets(b)["preferences"],{"favorites":[],"recent":[]})
            with self.assertRaises(ImportCommandError):
                save_project_plot_presets(a,preferences,0)
            with self.assertRaises(ValueError):
                save_project_plot_presets(a,{"favorites":[item,item],"recent":[]},1)
            self.assertEqual(get_project_plot_presets(a),saved)
