import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
from petrolab import media_display
from petrolab.media_import import _sha256
from petrolab.import_preview import ImportCommandError

class MediaPreviewCacheTests(unittest.TestCase):
    def setUp(self):
        media_display._PREVIEW_CACHE.clear()

    def tearDown(self):
        media_display._PREVIEW_CACHE.clear()

    def test_cache_reuses_pixels_but_checks_original(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            Image.new("RGB", (64, 48), "red").save(path)
            fingerprint = _sha256(path)
            original_open = Image.open
            with patch.object(media_display.Image, "open", wraps=original_open) as decode:
                first = media_display._preview_image(path, fingerprint)
                second = media_display._preview_image(path, fingerprint)
                self.assertEqual(first, second)
                self.assertEqual(decode.call_count, 1)
                region = {"left": 1, "top": 2, "width": 12, "height": 10}
                crop = media_display._preview_image(path, fingerprint, region)
                self.assertTrue(crop.startswith("data:image/png"))
                self.assertEqual(crop, media_display._preview_image(path, fingerprint, region))
                self.assertEqual(decode.call_count, 2)
                with self.assertRaises(ValueError):
                    media_display._preview_image(path, fingerprint, {**region, "left": True})
                Image.new("RGB", (64, 48), "blue").save(path)
                with self.assertRaises(ImportCommandError):
                    media_display._preview_image(path, fingerprint)
                self.assertNotEqual(first, media_display._preview_image(path, _sha256(path)))

    def test_cache_bounded_by_size_and_count(self):
        with patch.object(media_display, "_PREVIEW_CACHE_BYTES", 10), patch.object(media_display, "_PREVIEW_CACHE_COUNT", 2):
            media_display._preview_cache_put("a", "1234")
            media_display._preview_cache_put("b", "5678")
            self.assertEqual(media_display._preview_cache_get("a"), "1234")
            media_display._preview_cache_put("c", "90")
            self.assertIsNone(media_display._preview_cache_get("b"))
            media_display._preview_cache_put("oversize", "x" * 11)
            self.assertIsNone(media_display._preview_cache_get("oversize"))
            media_display._preview_cache_put("d", "x" * 9)
            self.assertLessEqual(sum(map(len, media_display._PREVIEW_CACHE.values())), 10)
