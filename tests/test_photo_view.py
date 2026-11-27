import sqlite3
import unittest
from petrolab.plot_data import _validate_photo_view
from petrolab.import_preview import ImportCommandError

class PhotoViewTests(unittest.TestCase):
    def test_exact_media_and_panel_ids_and_unavailable_photo(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE media_asset(media_asset_id TEXT)")
        media = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        db.execute("INSERT INTO media_asset VALUES (?)", (media,))
        panels = [{"id": "one"}, {"id": "two"}]
        view = {"media_asset_id": media, "panel_ids": ["two", "one"]}
        self.assertEqual(_validate_photo_view(db, view, panels), view)
        for ids in ([], ["one", "one"], ["missing"], ["one", "two", "three", "four"]):
            with self.assertRaises(ValueError):
                _validate_photo_view(db, {**view, "panel_ids": ids}, panels)
        db.execute("DELETE FROM media_asset")
        with self.assertRaises(ImportCommandError):
            _validate_photo_view(db, view, panels)
