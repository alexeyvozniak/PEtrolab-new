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
            scheme={"mode":"mineral","colors":[{"mode":"mineral","key":"phlogopite","color":"#AABBCC"},
                {"mode":"sample","key":str(uuid4()),"color":"#112233"}]}
            saved=save_project_plot_colors(a,scheme,0)
            self.assertEqual(saved["revision"],1)
            self.assertEqual(saved["scheme"]["colors"][0]["color"],"#aabbcc")
            self.assertEqual(get_project_plot_colors(a),saved)
            self.assertEqual(get_project_plot_colors(b)["revision"],0)
            with self.assertRaises(ImportCommandError):
                save_project_plot_colors(a,scheme,0)
            with self.assertRaises(ValueError):
                save_project_plot_colors(a,{"mode":"source","colors":[{"mode":"source","key":"bad","color":"#112233"}]},1)
            self.assertEqual(get_project_plot_colors(a),saved)
