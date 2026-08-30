from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_apply import apply_import_plan, open_project  # noqa: E402
from petrolab.import_preview import ImportCommandError  # noqa: E402
from petrolab.media_import import (  # noqa: E402
    apply_media_import_plan,
    create_analytical_point,
    create_media_import_plan,
    inspect_media_source,
    inspect_media_sources,
)
from test_import_preview import FIXTURE, fixture_recipe  # noqa: E402


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_png(path: Path, width: int = 12, height: int = 8) -> None:
    pixels = b"".join(b"\x00" + b"\x00\x00\x00\xff" * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(pixels))
        + _png_chunk(b"IEND", b"")
    )


def write_tiff(path: Path, width: int = 640, height: int = 480) -> None:
    path.write_bytes(
        b"II" + struct.pack("<H", 42) + struct.pack("<I", 8)
        + struct.pack("<H", 2)
        + struct.pack("<HHI", 256, 4, 1) + struct.pack("<I", width)
        + struct.pack("<HHI", 257, 4, 1) + struct.pack("<I", height)
        + struct.pack("<I", 0)
    )


class MediaImportTests(unittest.TestCase):
    def _project_with_points(self, directory: Path) -> tuple[Path, dict, dict]:
        database = directory / "project.sqlite"
        apply_import_plan(database, FIXTURE, fixture_recipe())
        with closing(sqlite3.connect(database)) as connection:
            ids = [row[0] for row in connection.execute("SELECT analysis_id FROM analysis ORDER BY rowid").fetchall()]
        first = create_analytical_point(database, "KIV-2", "P-07", ids[:2], "same_point")
        second = create_analytical_point(database, "OTHER", "P-08", ids[2:4], "same_grain")
        return database, first, second

    def _assignment(self, image: Path, point_id: str, sample_name: str = "KIV-2", reason: str | None = None) -> dict:
        return {
            "source_path": str(image),
            "ownership_mode": "managed_copy",
            "media_type": "BSE",
            "sample_name": sample_name,
            "thin_section_name": f"{sample_name}-TS1",
            "placements": [
                {
                    "analytical_point_id": point_id,
                    "geometry": {"kind": "point", "x_px": 5.25, "y_px": 3.5},
                    "cross_sample_exception_reason": reason,
                }
            ],
        }

    def test_png_and_tiff_metadata_are_inspected_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            png, tiff = directory / "image.png", directory / "bse.tif"
            write_png(png)
            write_tiff(tiff)
            self.assertEqual((inspect_media_source(png)["width_px"], inspect_media_source(png)["height_px"]), (12, 8))
            tiff_result = inspect_media_source(tiff)
            self.assertEqual((tiff_result["mime_type"], tiff_result["width_px"], tiff_result["height_px"]), ("image/tiff", 640, 480))

    def test_batch_inspection_reports_duplicate_physical_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            first, second = directory / "first.png", directory / "second.png"
            write_png(first)
            second.write_bytes(first.read_bytes())
            result = inspect_media_sources([first, second])
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(len(result["duplicate_groups"]), 1)

    def test_windows_batch_file_is_not_treated_as_an_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            script = Path(directory_name) / "images.bat"
            script.write_text("echo unsafe", encoding="utf-8")
            with self.assertRaises(ImportCommandError) as raised:
                inspect_media_source(script)
            self.assertEqual(raised.exception.code, "MEDIA_FORMAT_UNSUPPORTED")

    def test_media_batch_preserves_source_and_source_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database, point, _ = self._project_with_points(directory)
            image = directory / "KIV-2_BSE.png"
            write_png(image)
            source_hash = hashlib.sha256(image.read_bytes()).hexdigest()
            plan = create_media_import_plan(database, [self._assignment(image, point["analytical_point_id"])])
            self.assertEqual(plan["items"][0]["media_type"], "BSE")
            result = apply_media_import_plan(database, plan)
            copied = directory / "media" / f"{plan['items'][0]['media_asset_id']}.png"
            self.assertTrue(copied.is_file())
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), source_hash)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_asset").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM spatial_annotation").fetchone()[0], 1)
                row = connection.execute("SELECT geometry_kind, x_px, y_px, image_width_px, image_height_px FROM spatial_annotation").fetchone()
                self.assertEqual(row, ("point", 5.25, 3.5, 12, 8))
                self.assertEqual(connection.execute("SELECT project_schema_version FROM project_meta").fetchone()[0], 4)
            self.assertEqual(result["spatial_annotation_count"], 1)

    def test_cross_sample_placement_requires_and_preserves_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database, _, other_point = self._project_with_points(directory)
            image = directory / "KIV-2_BSE.png"
            write_png(image)
            with self.assertRaises(ImportCommandError) as raised:
                create_media_import_plan(database, [self._assignment(image, other_point["analytical_point_id"])])
            self.assertEqual(raised.exception.code, "CROSS_SAMPLE_CONFIRMATION_REQUIRED")
            assignment = self._assignment(image, other_point["analytical_point_id"], reason="Legacy label verified in lab notebook")
            result = apply_media_import_plan(database, create_media_import_plan(database, [assignment]))
            self.assertEqual(result["spatial_annotation_count"], 1)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute("SELECT cross_sample_exception, exception_reason FROM analytical_point_annotation").fetchone(),
                    (1, "Legacy label verified in lab notebook"),
                )

    def test_unplaced_image_is_allowed_but_visible_in_review_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database, _, _ = self._project_with_points(directory)
            image = directory / "overview.png"
            write_png(image)
            assignment = self._assignment(image, "unused")
            assignment["placements"] = []
            plan = create_media_import_plan(database, [assignment])
            self.assertEqual(plan["warnings"][0]["code"], "UNPLACED_MEDIA")
            result = apply_media_import_plan(database, plan)
            self.assertEqual(result["spatial_annotation_count"], 0)

    def test_database_failure_rolls_back_rows_and_removes_managed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database, point, _ = self._project_with_points(directory)
            image = directory / "KIV-2_BSE.png"
            write_png(image)
            plan = create_media_import_plan(database, [self._assignment(image, point["analytical_point_id"])])
            connection = open_project(database)
            with connection:
                connection.execute("""CREATE TRIGGER fail_media_annotation BEFORE INSERT ON spatial_annotation
                    BEGIN SELECT RAISE(ABORT, 'forced media failure'); END""")
            connection.close()
            with self.assertRaises(sqlite3.IntegrityError):
                apply_media_import_plan(database, plan)
            self.assertFalse((directory / "media" / f"{plan['items'][0]['media_asset_id']}.png").exists())
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_import_batch").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_asset").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM spatial_annotation").fetchone()[0], 0)

    def test_changed_source_and_changed_reviewed_plan_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database, point, _ = self._project_with_points(directory)
            image = directory / "KIV-2_BSE.png"
            write_png(image)
            plan = create_media_import_plan(database, [self._assignment(image, point["analytical_point_id"])])
            altered_plan = json.loads(json.dumps(plan))
            altered_plan["items"][0]["placements"][0]["geometry"]["x_px"] = 6
            with self.assertRaises(ImportCommandError) as plan_error:
                apply_media_import_plan(database, altered_plan)
            self.assertEqual(plan_error.exception.code, "PLAN_FINGERPRINT_MISMATCH")
            image.write_bytes(image.read_bytes() + b"changed")
            with self.assertRaises(ImportCommandError) as source_error:
                apply_media_import_plan(database, plan)
            self.assertEqual(source_error.exception.code, "SOURCE_FINGERPRINT_MISMATCH")


if __name__ == "__main__":
    unittest.main()
