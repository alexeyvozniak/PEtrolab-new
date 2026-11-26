from __future__ import annotations

from base64 import b64decode
import hashlib
from io import BytesIO
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_apply import MIGRATIONS, apply_import_plan, latest_active_import, open_project  # noqa: E402
from petrolab.import_preview import ImportCommandError  # noqa: E402
from petrolab.manual_analysis import create_manual_analysis  # noqa: E402
from petrolab.media_links import attach_media, change_media_link, create_media_region, import_linked_photo, list_media_links  # noqa: E402
from petrolab.media_display import export_media_batch, export_media_original, export_media_rendered, preview_input_media, preview_project_media  # noqa: E402
from petrolab.project_archive import export_project_archive, restore_project_archive  # noqa: E402
from PIL import Image  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from petrolab.publication import capture_publication_media, capture_publication_table, export_publication, prepare_publication  # noqa: E402
from petrolab.media_import import (  # noqa: E402
    _plan_fingerprint,
    apply_media_import_plan,
    create_analytical_point,
    create_media_import_plan,
    inspect_media_source,
    inspect_media_folder,
    inspect_media_sources,
    load_media_import_draft,
    save_media_import_draft,
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

    def test_folder_draft_detects_changes_and_is_consumed_by_one_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pictures = folder / "снимки"
            pictures.mkdir()
            first = pictures / "BSE.png"
            write_png(first)
            (pictures / "readme.txt").write_text("not an image", encoding="utf-8")
            (pictures / "subfolder").mkdir()
            write_png(pictures / "subfolder" / "nested.png")
            files = inspect_media_folder(str(pictures))["items"]
            self.assertEqual([item["display_name"] for item in files], ["BSE.png"])
            database, point, _ = self._project_with_points(folder)
            plan = create_media_import_plan(database, [self._assignment(first, point["analytical_point_id"])])
            saved = save_media_import_draft(database, plan)
            self.assertEqual(load_media_import_draft(database)["plan"], plan)
            with self.assertRaises(ImportCommandError) as stale:
                save_media_import_draft(database, plan)
            self.assertEqual(stale.exception.code, "MEDIA_DRAFT_CONFLICT")
            original = first.read_bytes()
            write_png(first, width=13)
            blocked = load_media_import_draft(database)
            self.assertIsNone(blocked["plan"])
            self.assertTrue(blocked["issue"])
            self.assertEqual(blocked["fingerprint"], saved["fingerprint"])
            with self.assertRaises(ImportCommandError):
                apply_media_import_plan(database, plan, draft_fingerprint=saved["fingerprint"])
            first.write_bytes(original)
            self.assertEqual(apply_media_import_plan(database, plan, draft_fingerprint=saved["fingerprint"])["spatial_annotation_count"], 1)
            self.assertIsNone(load_media_import_draft(database))
            with self.assertRaises(ImportCommandError) as replay:
                apply_media_import_plan(database, plan, draft_fingerprint=saved["fingerprint"])
            self.assertEqual(replay.exception.code, "MEDIA_DRAFT_CONFLICT")
            self.assertEqual(first.read_bytes(), original)

    def test_manual_analysis_preserves_tokens_and_creates_the_link_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            database, point, _ = self._project_with_points(folder)
            entry = {"identity": "EPMA-17", "measurement_date": "2026-08-28", "operator": "Иванов",
                     "method": "EPMA", "measurements": {"SiO2": "43,25", "FeO": "<0.05", "TiO2": "0"}}
            result = create_manual_analysis(database, point["analytical_point_id"], entry)
            analysis_id = result["analysis_id"]
            self.assertEqual(result["journal"]["parameters"]["analysis_ids"], [analysis_id])
            with closing(open_project(database)) as connection:
                rows = connection.execute("""SELECT canonical_field, unit, raw_token, detection_limit, value_status, reported_fe_form
                    FROM measurement WHERE analysis_id = ? ORDER BY canonical_field""", (analysis_id,)).fetchall()
                self.assertEqual([tuple(row) for row in rows], [
                    ("FeO", "wt.%", "<0.05", 0.05, "below_detection_limit", "FeO"),
                    ("SiO2", "wt.%", "43,25", None, "numeric", None), ("TiO2", "wt.%", "0", None, "numeric", None),
                ])
                source = connection.execute("SELECT * FROM source_file WHERE source_id = ?", (result["source_id"],)).fetchone()
                self.assertEqual(source["display_name"], "Ручной ввод.csv")
                self.assertEqual(source["source_fingerprint_sha256"], hashlib.sha256((folder / source["managed_relative_path"]).read_bytes()).hexdigest())
                self.assertNotEqual(latest_active_import(connection)["source_id"], result["source_id"])
                with connection:
                    connection.execute("""CREATE TRIGGER reject_point_link BEFORE INSERT ON analytical_point_analysis
                        BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "test failure"):
                create_manual_analysis(database, point["analytical_point_id"], {**entry, "identity": "EPMA-18"})
            with self.assertRaises(ImportCommandError) as duplicate:
                create_manual_analysis(database, point["analytical_point_id"], entry)
            self.assertEqual(duplicate.exception.code, "MANUAL_ANALYSIS_EXISTS")
            self.assertEqual(len(list((folder / "sources").glob("*.csv"))), 1)
            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_file WHERE display_name = 'Ручной ввод.csv'").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis WHERE json_extract(identity_json, '$[0]') = 'EPMA-18'").fetchone()[0], 0)

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

    def test_readable_formats_keep_original_bytes_and_header_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            with closing(open_project(database)):
                pass
            assignments = []
            for suffix, options in (("jpg", {}), ("bmp", {}), ("png", {}), ("tif", {"tiffinfo": {274: 6}})):
                source = root / f"image.{suffix}"
                Image.new("RGB", (24, 12)).save(source, **options)
                assignments.append({"source_path": str(source), "ownership_mode": "managed_copy", "media_type": "BSE",
                                    "sample_name": "KIV-2", "thin_section_name": "TS1", "placements": []})
            plan = create_media_import_plan(database, assignments)
            apply_media_import_plan(database, plan)
            for item in plan["items"]:
                source = Path(item["source_path"])
                self.assertEqual((item["width_px"], item["height_px"]), (24, 12))
                managed = root / "media" / f"{item['media_asset_id']}{source.suffix}"
                self.assertEqual(managed.read_bytes(), source.read_bytes())

    def test_corrupt_pixels_block_review_and_replay_of_a_legacy_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            with closing(open_project(database)):
                pass
            usable = root / "bse.png"
            damaged = root / "ppl.png"
            write_png(usable)
            write_png(damaged, width=16, height=10)

            def assignment(source, media_type):
                return {"source_path": str(source), "ownership_mode": "managed_copy", "media_type": media_type,
                        "sample_name": "KIV-2", "thin_section_name": "TS1", "placements": []}

            assignments = [assignment(usable, "BSE"), assignment(damaged, "PPL")]
            legacy_plan = create_media_import_plan(database, assignments)
            # Keep the header and valid chunk CRCs while breaking the pixel stream.
            corrupt = (damaged.read_bytes()[:33] + _png_chunk(b"IDAT", b"not a deflate stream")
                       + _png_chunk(b"IEND", b""))
            damaged.write_bytes(corrupt)
            legacy_plan["items"][1]["source_fingerprint"] = hashlib.sha256(corrupt).hexdigest()
            legacy_plan["semantic_fingerprint"] = _plan_fingerprint(legacy_plan)
            database_bytes = database.read_bytes()
            usable_bytes = usable.read_bytes()

            for attempt in (lambda: create_media_import_plan(database, assignments),
                            lambda: apply_media_import_plan(database, legacy_plan)):
                with self.assertRaises(ImportCommandError) as error:
                    attempt()
                self.assertEqual(error.exception.code, "MEDIA_UNREADABLE")
                self.assertEqual(Path(error.exception.details["path"]).resolve(), damaged.resolve())
            self.assertEqual(database.read_bytes(), database_bytes)
            self.assertEqual(usable.read_bytes(), usable_bytes)
            self.assertEqual(damaged.read_bytes(), corrupt)
            self.assertFalse((root / "media").exists())

    def test_batch_photo_links_resolve_against_reviewed_placements_and_commit_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, first, second = self._project_with_points(root)
            overview, detail = root / "overview.png", root / "detail.png"
            write_png(overview)
            write_png(detail, width=16)
            anchor = self._assignment(overview, first["analytical_point_id"])
            second_assignment = self._assignment(overview, second["analytical_point_id"], reason="Снимок охватывает оба образца")
            region = {**second_assignment["placements"][0],
                      "geometry": {"kind": "rectangle", "x_px": 1, "y_px": 2, "width_px": 6, "height_px": 4}}
            anchor["placements"].append(region)
            references = [{"source_fingerprint": hashlib.sha256(overview.read_bytes()).hexdigest(),
                           "analytical_point_id": point["analytical_point_id"]} for point in (first, second)]
            photo = {**anchor, "source_path": str(detail), "media_type": "Другое", "placements": [],
                     "attach_to_placements": references}
            for invalid, code in (
                ({**photo, "thin_section_name": "another section"}, "MEDIA_LINK_SCOPE"),
                ({**photo, "attach_to_placements": [references[0], references[0]]}, "INVALID_ASSIGNMENT"),
                ({**photo, "attach_to_placements": [{**references[0], "source_fingerprint": "0" * 64}]}, "MEDIA_LINK_UNAVAILABLE"),
            ):
                with self.assertRaises(ImportCommandError) as error:
                    create_media_import_plan(database, [anchor, invalid])
                self.assertEqual(error.exception.code, code)
            plan = create_media_import_plan(database, [photo, anchor])
            self.assertEqual(plan["schema_version"], 2)
            asset_id = plan["items"][0]["media_asset_id"]
            self.assertEqual(plan["media_links"], [
                {"media_asset_id": asset_id, "spatial_annotation_id": placement["spatial_annotation_id"]}
                for placement in plan["items"][1]["placements"]
            ])
            draft = save_media_import_draft(database, plan)
            self.assertEqual(load_media_import_draft(database)["plan"], plan)
            first_link, second_link = (link["spatial_annotation_id"] for link in plan["media_links"])

            def fail_second_link(connection, annotation_id, media_id):
                if annotation_id == second_link:
                    raise ImportCommandError("TEST_ROLLBACK", "Link insertion failed.")
                return attach_media(connection, annotation_id, media_id)

            originals = [overview.read_bytes(), detail.read_bytes()]
            with patch("petrolab.media_links.attach_media", side_effect=fail_second_link):
                with self.assertRaisesRegex(ImportCommandError, "Link insertion failed"):
                    apply_media_import_plan(database, plan, draft_fingerprint=draft["fingerprint"])
            self.assertEqual(load_media_import_draft(database)["plan"], plan)
            self.assertEqual(list((root / "media").glob("*")), [])
            with closing(open_project(database)) as connection:
                for table in ("media_asset", "media_import_batch", "spatial_annotation", "media_link"):
                    self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

            result = apply_media_import_plan(database, plan, draft_fingerprint=draft["fingerprint"])
            self.assertEqual(len(result["media_link_ids"]), 2)
            for annotation_id, link_id in zip((first_link, second_link), result["media_link_ids"], strict=True):
                links = list_media_links(database, annotation_id)
                self.assertEqual([(link["media_asset_id"], link["media_link_id"]) for link in links], [(asset_id, link_id)])
            self.assertIsNone(load_media_import_draft(database))
            self.assertEqual([overview.read_bytes(), detail.read_bytes()], originals)

    def test_photo_links_preserve_points_areas_and_originals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original, point_photo, region_photo, failed_photo = (folder / name for name in ("bse.png", "point.png", "region.png", "failed.png"))
            for index, path in enumerate((original, point_photo, region_photo, failed_photo)):
                write_png(path, width=12 + index, height=8)
            hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (original, point_photo, region_photo, failed_photo)}
            legacy_migrations = folder / "migrations-v18"
            legacy_migrations.mkdir()
            for migration in MIGRATIONS.glob("*.sql"):
                if int(migration.name.split("_", 1)[0]) <= 18:
                    (legacy_migrations / migration.name).write_bytes(migration.read_bytes())
            with patch("petrolab.import_apply.MIGRATIONS", legacy_migrations):
                database, point, _ = self._project_with_points(folder)
                plan = create_media_import_plan(database, [self._assignment(original, point["analytical_point_id"])])
                apply_media_import_plan(database, plan)
            item = plan["items"][0]
            asset_id = item["media_asset_id"]
            point_id = item["placements"][0]["spatial_annotation_id"]
            bounds = {"kind": "square", "x_px": 3.5, "y_px": 2, "width_px": 4, "height_px": 4}
            area = create_media_region(database, asset_id, bounds)
            backup, = folder.glob("project.sqlite.before-v19-*.bak")
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(connection.execute("SELECT project_schema_version FROM project_meta").fetchone()[0], 18)
                self.assertEqual(connection.execute("SELECT spatial_annotation_id FROM spatial_annotation").fetchone()[0], point_id)
            area_id = area["spatial_annotation_id"]
            point_link = import_linked_photo(database, point_id, point_photo, "PPL", hashes[point_photo])["media_link_ids"][0]
            area_link = import_linked_photo(database, area_id, region_photo, "XPL", hashes[region_photo])["media_link_ids"][0]
            saved_photo = list_media_links(database, point_id)[0]["media_asset_id"]
            self.assertEqual(list_media_links(database, area_id)[0]["media_link_id"], area_link)
            self.assertEqual(change_media_link(database, point_id, saved_photo, False)["media_link_id"], point_link)
            self.assertEqual(list_media_links(database, point_id), [])
            self.assertEqual(preview_project_media(database, saved_photo)["width_px"], 13)
            self.assertEqual(change_media_link(database, point_id, saved_photo, True)["media_link_id"], point_link)
            area_after = next(row for row in preview_project_media(database, asset_id)["annotations"] if row["spatial_annotation_id"] == area_id)
            self.assertEqual((area_after["geometry_kind"], area_after["x_px"], area_after["width_px"]), ("square", 3.5, 4))
            destination = folder / "publication.png"
            settings = {"points": True, "regions": True, "labels": True, "legend": True, "scale_bar": True,
                        "calibration": {"reference_pixels": 6, "reference_length": 30, "unit": "µm"}}
            publication = export_media_rendered(database, asset_id, str(destination), settings)
            self.assertEqual(set(publication["annotation_ids"]), {point_id, area_id})
            self.assertEqual(publication["rendered_scale"], {"pixels": 3, "length": 15.0, "unit": "µm"})
            self.assertEqual(publication["rendered_legend"], {"points": 1, "regions": 1})
            with Image.open(destination) as rendered:
                manifest = json.loads(rendered.info["PetroLab"])
                self.assertEqual(manifest["source_sha256"], hashes[original])
                self.assertEqual(manifest["options"], settings)
                self.assertGreater(rendered.height, 8)
            subset = export_media_rendered(database, asset_id, str(folder / "area-only.png"), {**settings, "annotation_ids": [area_id]})
            self.assertEqual(subset["annotation_ids"], [area_id])
            self.assertEqual(subset["rendered_legend"], {"points": 0, "regions": 1})
            selected_ids = point["analysis_ids"][::-1]
            items = [
                capture_publication_table(database, selected_ids),
                capture_publication_media(database, asset_id),
                capture_publication_media(database, asset_id, {**settings, "annotation_ids": [point_id]}),
                capture_publication_media(database, saved_photo),
            ]
            prepared = prepare_publication(database, "QA", items)
            package = folder / "publication.zip"
            export_publication(database, "QA", items, prepared["fingerprint"], str(package))
            with ZipFile(package) as archive:
                with closing(load_workbook(BytesIO(archive.read("tables/01-selection_table.xlsx")), read_only=True)) as workbook:
                    self.assertEqual([row[0] for row in list(workbook["Analyses"].values)[1:]], selected_ids)
                self.assertEqual(archive.read("images/02-media_capture.png"), original.read_bytes())
                rendered_metadata = json.loads(archive.read("materials/03-media_capture.json"))
                self.assertEqual(rendered_metadata["source_sha256"], hashes[original])
                self.assertEqual(rendered_metadata["rendition"]["annotation_ids"], [point_id])
                self.assertEqual({link["analysis_id"] for link in rendered_metadata["analysis_links"]}, set(selected_ids))
                with Image.open(BytesIO(archive.read("images/03-media_capture.png"))) as rendered:
                    self.assertEqual(json.loads(rendered.info["PetroLab"])["rendered_scale"]["length"], 15.0)
                self.assertEqual(archive.read("images/04-media_capture.png"), point_photo.read_bytes())
                attached_metadata = json.loads(archive.read("materials/04-media_capture.json"))
                self.assertEqual(attached_metadata["attachments"][0]["media_link_id"], point_link)
                self.assertEqual({link["analysis_id"] for link in attached_metadata["analysis_links"]}, set(selected_ids))
            change_media_link(database, point_id, saved_photo, False)
            with self.assertRaises(ImportCommandError) as stale:
                prepare_publication(database, "QA", items)
            self.assertEqual(stale.exception.code, "PUBLICATION_CAPTURE_CHANGED")
            change_media_link(database, point_id, saved_photo, True)
            with closing(open_project(database)) as connection, connection:
                connection.execute("CREATE TRIGGER reject_media_link BEFORE INSERT ON media_link BEGIN SELECT RAISE(ABORT, 'test link failure'); END")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "test link failure"):
                import_linked_photo(database, area_id, failed_photo, "PPL", hashes[failed_photo])
            self.assertEqual(len(list((folder / "media").glob("*.png"))), 3)
            self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in hashes}, hashes)

    def test_batch_inspection_reports_duplicate_physical_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            first, second = directory / "first.png", directory / "second.png"
            write_png(first)
            second.write_bytes(first.read_bytes())
            result = inspect_media_sources([first, second])
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(len(result["duplicate_groups"]), 1)

    def test_export_legend_and_scale_do_not_cover_selected_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            database, point, _ = self._project_with_points(folder)
            source = folder / "outcrop.png"
            Image.new("RGB", (720, 480), "#34423b").save(source)
            source_bytes = source.read_bytes()
            assignment = self._assignment(source, point["analytical_point_id"])
            assignment["placements"][0]["geometry"] = {"kind": "point", "x_px": 40, "y_px": 445}
            plan = create_media_import_plan(database, [assignment])
            apply_media_import_plan(database, plan)
            asset_id = plan["items"][0]["media_asset_id"]
            area = create_media_region(database, asset_id,
                                       {"kind": "rectangle", "x_px": 100, "y_px": 408, "width_px": 55, "height_px": 46})
            plain = str(folder / "annotations.png")
            decorated = str(folder / "annotations-and-key.png")
            settings = {"points": True, "regions": True, "labels": True}
            export_media_rendered(database, asset_id, plain, settings)
            result = export_media_rendered(database, asset_id, decorated, {**settings, "legend": True, "scale_bar": True})
            with Image.open(plain) as expected, Image.open(decorated) as actual:
                self.assertEqual(actual.width, expected.width)
                self.assertGreater(actual.height, expected.height)
                self.assertEqual(actual.crop((0, 0, *expected.size)).tobytes(), expected.tobytes())
            self.assertEqual(result["rendered_legend"], {"points": 1, "regions": 1})
            self.assertEqual(result["rendered_scale"], {"pixels": 180, "length": 180, "unit": "px"})
            self.assertIn(area["spatial_annotation_id"], result["annotation_ids"])
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_sample_photo_migration_preserves_v20_links_and_allows_no_thin_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            legacy = folder / "v20"
            legacy.mkdir()
            for migration in MIGRATIONS.glob("*.sql"):
                if int(migration.name.split("_", 1)[0]) <= 20:
                    (legacy / migration.name).write_bytes(migration.read_bytes())
            overview, detail, field = (folder / f"{name}.png" for name in ("overview", "detail", "outcrop"))
            for width, image in enumerate((overview, detail, field), start=12):
                write_png(image, width=width)
            tables = ("sample", "thin_section", "media_asset", "spatial_annotation", "analytical_point_annotation", "media_link")
            with patch("petrolab.import_apply.MIGRATIONS", legacy):
                database, point, _ = self._project_with_points(folder)
                assignment = self._assignment(overview, point["analytical_point_id"])
                plan = create_media_import_plan(database, [assignment])
                apply_media_import_plan(database, plan)
                annotation_id = plan["items"][0]["placements"][0]["spatial_annotation_id"]
                import_linked_photo(database, annotation_id, detail, "PPL", inspect_media_source(detail)["source_fingerprint"])
                legacy_draft = create_media_import_plan(database, [{**assignment, "source_path": str(field), "placements": []}])
                draft = save_media_import_draft(database, legacy_draft)
                with closing(open_project(database)) as connection:
                    before = {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}

            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual({table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}, before)
            backup, = folder.glob("project.sqlite.before-v21-*.bak")
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(connection.execute("SELECT project_schema_version FROM project_meta").fetchone()[0], 20)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(load_media_import_draft(database)["plan"], legacy_draft)
            standalone = {**assignment, "source_path": str(field), "media_type": "Полевое фото", "thin_section_name": None,
                          "placements": []}
            for invalid in ({**standalone, "media_type": "BSE"}, {**standalone, "placements": assignment["placements"]}):
                with self.assertRaises(ImportCommandError) as error:
                    create_media_import_plan(database, [invalid])
                self.assertEqual(error.exception.code, "MEDIA_SECTION_REQUIRED")

            plan = create_media_import_plan(database, [standalone])
            self.assertEqual((plan["schema_version"], plan["warnings"], plan["unplaced_points"]), (3, [], []))
            resaved = save_media_import_draft(database, plan, draft["fingerprint"])
            self.assertEqual(load_media_import_draft(database)["plan"], plan)
            apply_media_import_plan(database, plan, draft_fingerprint=resaved["fingerprint"])
            media_id = plan["items"][0]["media_asset_id"]
            with closing(open_project(database)) as connection:
                asset = connection.execute("SELECT sample_id, thin_section_id FROM media_asset WHERE media_asset_id = ?", (media_id,)).fetchone()
                self.assertEqual(tuple(asset), (point["sample_id"], None))
                self.assertEqual(connection.execute("SELECT * FROM thin_section").fetchall(), before["thin_section"])
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            output = folder / "outcrop-copy.png"
            export_media_original(database, media_id, str(output))
            self.assertEqual(output.read_bytes(), field.read_bytes())
            with self.assertRaises(ImportCommandError) as error:
                create_media_region(database, media_id, {"kind": "square", "x_px": 1, "y_px": 1, "width_px": 4, "height_px": 4})
            self.assertEqual(error.exception.code, "MEDIA_SECTION_REQUIRED")
            archive, restored = folder / "project.petrolab", folder / "restored"
            export_project_archive(database, str(archive), "full")
            restore_project_archive(str(archive), str(restored))
            restored_copy = folder / "restored-outcrop.png"
            export_media_original(restored / "project.sqlite", media_id, str(restored_copy))
            self.assertEqual(restored_copy.read_bytes(), field.read_bytes())
            self.assertEqual(list_media_links(restored / "project.sqlite", annotation_id), list_media_links(database, annotation_id))

    def test_batch_export_contains_exact_sources_and_never_publishes_a_partial_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            database, point, _ = self._project_with_points(folder)
            second_folder = folder / "other"
            second_folder.mkdir()
            first, second = folder / "scan.png", second_folder / "scan.png"
            write_png(first)
            write_png(second, width=18)
            annotated = self._assignment(first, point["analytical_point_id"])
            plan = create_media_import_plan(database, [annotated, {**annotated, "source_path": str(second), "placements": []}])
            apply_media_import_plan(database, plan)
            first_id, second_id = [item["media_asset_id"] for item in plan["items"]]
            originals = [second.read_bytes(), first.read_bytes()]
            archive = folder / "originals.zip"
            result = export_media_batch(database, [second_id, first_id], str(archive), None)
            self.assertEqual((result["image_count"], result["sha256"]), (2, hashlib.sha256(archive.read_bytes()).hexdigest()))
            with ZipFile(archive) as package:
                files = json.loads(package.read("manifest.json"))["files"]
                self.assertEqual([entry["media_asset_id"] for entry in files], [second_id, first_id])
                self.assertEqual([package.read(entry["path"]) for entry in files], originals)
                self.assertEqual(len(set(package.namelist())), 3)
            settings = {"points": True, "regions": True, "labels": True, "legend": True, "scale_bar": True}
            rendered_path = folder / "rendered.zip"
            export_media_batch(database, [first_id, second_id], str(rendered_path), settings)
            with ZipFile(rendered_path) as package:
                files = json.loads(package.read("manifest.json"))["files"]
                self.assertEqual([entry["rendered_legend"] for entry in files], [{"points": 1, "regions": 0}, {"points": 0, "regions": 0}])
                for entry in files:
                    data = package.read(entry["path"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                    with Image.open(BytesIO(data)) as output:
                        self.assertEqual(json.loads(output.info["PetroLab"])["source_sha256"], entry["source_sha256"])
            with self.assertRaises(ImportCommandError) as collision:
                export_media_batch(database, [first_id], str(archive), None)
            self.assertEqual(collision.exception.code, "EXPORT_FILE_EXISTS")
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result["sha256"])
            managed_second = folder / "media" / f"{second_id}.png"
            managed_second.write_bytes(b"changed")
            failed = folder / "failed.zip"
            with self.assertRaises(ImportCommandError) as changed:
                export_media_batch(database, [first_id, second_id], str(failed), None)
            self.assertEqual(changed.exception.code, "SOURCE_FINGERPRINT_MISMATCH")
            self.assertFalse(failed.exists())
            self.assertFalse(list(folder.glob(".petrolab-images-*")))
            self.assertEqual([second.read_bytes(), first.read_bytes()], originals)

    def test_preview_and_original_export_preserve_bytes_and_require_current_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database = directory / "project.sqlite"
            with closing(open_project(database)):
                pass
            image = directory / "original.png"
            write_png(image, width=64, height=40)
            with Image.open(image) as opened:
                edited_fixture = opened.copy()
            edited_fixture.putpixel((13, 8), (229, 76, 23, 255))
            edited_fixture.save(image)
            original = image.read_bytes()
            assignment = {"source_path": str(image), "sample_name": "KIV-2", "thin_section_name": "TS1",
                          "placements": [], "ownership_mode": "linked_external", "media_type": "PPL",
                          "sample_target": {"mode": "new", "sample_id": None},
                          "expected_source_fingerprint": hashlib.sha256(original).hexdigest()}
            plan = create_media_import_plan(database, [assignment])
            apply_media_import_plan(database, plan)
            media_id = plan["items"][0]["media_asset_id"]
            preview = preview_project_media(database, media_id)
            self.assertEqual((preview["width_px"], preview["height_px"], preview["annotations"]), (64, 40, []))
            self.assertTrue(preview["preview_url"].startswith("data:image/jpeg;base64,"))
            region = {"left": 10, "top": 5, "width": 7, "height": 6}
            detailed = preview_project_media(database, media_id, region)
            self.assertEqual(detailed["region"], region)
            self.assertEqual(preview_input_media(image, region, hashlib.sha256(original).hexdigest()), detailed)
            with Image.open(BytesIO(b64decode(detailed["preview_url"].split(",")[1]))) as cropped:
                self.assertEqual(cropped.size, (7, 6))
                self.assertEqual(cropped.getpixel((3, 3)), (229, 76, 23, 255))
            with self.assertRaises(ValueError):
                preview_project_media(database, media_id, {**region, "left": 60})
            with self.assertRaises(ImportCommandError) as wrong_fingerprint:
                preview_input_media(image, region, "0" * 64)
            self.assertEqual(wrong_fingerprint.exception.code, "SOURCE_FINGERPRINT_MISMATCH")
            destination = directory / "copy.png"
            result = export_media_original(database, media_id, str(destination))
            self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(destination.read_bytes(), original)
            with self.assertRaises(ImportCommandError) as overwrite:
                export_media_original(database, media_id, str(image))
            self.assertEqual(overwrite.exception.code, "EXPORT_FILE_EXISTS")
            self.assertEqual(image.read_bytes(), original)
            write_png(image, width=65, height=40)
            with self.assertRaises(ImportCommandError) as changed:
                export_media_original(database, media_id, str(directory / "changed.png"))
            self.assertEqual(changed.exception.code, "SOURCE_FINGERPRINT_MISMATCH")
            self.assertFalse((directory / "changed.png").exists())

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
                self.assertEqual(connection.execute("SELECT project_schema_version FROM project_meta").fetchone()[0], 24)
            self.assertEqual(result["spatial_annotation_count"], 1)
            media_id = plan["items"][0]["media_asset_id"]
            preview = preview_project_media(database, media_id)
            self.assertEqual([preview["annotations"][0][axis] for axis in ("x_px", "y_px")], [5.25, 3.5])
            rendered = export_media_rendered(database, media_id, str(directory / "rendered.png"),
                                             {"points": True, "regions": False, "labels": True})
            with Image.open(rendered["output_path"]) as exported:
                manifest = json.loads(exported.info["PetroLab"])
                self.assertEqual(manifest["source_sha256"], source_hash)
                self.assertEqual(manifest["annotation_ids"], rendered["annotation_ids"])
                self.assertEqual(len(manifest["annotation_ids"]), 1)
                self.assertEqual(exported.size, (12, 8))
                self.assertTrue(any(high > 0 for _, high in exported.convert("RGB").getextrema()))
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), source_hash)

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
