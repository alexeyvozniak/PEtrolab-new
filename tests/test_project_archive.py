from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from PIL import Image

from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.import_apply import MIGRATIONS, open_project
from petrolab.ndjson_service import handle_request
from petrolab.import_preview import ImportCommandError
from petrolab.project_archive import export_project_archive, replace_project_from_archive


class ProjectArchiveTests(unittest.TestCase):
    def test_archive_migrates_only_database_copy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "old-project.sqlite"
            old_migrations = root / "migrations"
            old_migrations.mkdir()
            for migration in MIGRATIONS.glob("*.sql"):
                if int(migration.name.split("_", 1)[0]) <= 17:
                    (old_migrations / migration.name).write_bytes(migration.read_bytes())
            with patch("petrolab.import_apply.MIGRATIONS", old_migrations), closing(open_project(database)):
                pass
            original = database.read_bytes()
            archived = export_project_archive(database, str(root / "portable.petrolab"), "project")
            self.assertGreater(archived["manifest"]["project_schema_version"], 17)
            self.assertEqual(database.read_bytes(), original)
            self.assertEqual(list(root.glob("old-project.sqlite.before-v*.bak")), [])

    def test_service_command_line_round_trip_and_missing_database(self):
        repo = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "проект.sqlite"
            archive = root / "архив.petrolab"
            restored = root / "восстановленный проект"
            command = [sys.executable, str(repo / "scripts" / "petrolab_service.py"), "archive"]
            environment = {**os.environ, "PYTHONPATH": str(repo / "src")}

            def cli(*args):
                return subprocess.run([*command, *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                                      env=environment, timeout=30)

            rejected = cli("export", database, archive, "--level", "project")
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse(database.exists())
            self.assertFalse(archive.exists())
            request = {"protocol_version": "1.0", "request_id": str(uuid4()), "command": "project.analyses.list",
                       "payload": {"project_database_path": str(database)}}
            self.assertIn("result", handle_request(request))
            readiness = cli("check-export", database, "--level", "full")
            self.assertEqual(readiness.returncode, 0, readiness.stderr)
            self.assertTrue(json.loads(readiness.stdout)["ready"])
            self.assertFalse(archive.exists())
            exported = cli("export", database, archive, "--level", "project")
            self.assertEqual(exported.returncode, 0, exported.stderr)
            inspected = cli("inspect", archive)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["manifest"], json.loads(exported.stdout)["manifest"])
            self.assertFalse(restored.exists())
            unpacked = cli("restore", archive, restored)
            self.assertEqual(unpacked.returncode, 0, unpacked.stderr)
            self.assertEqual(json.loads(exported.stdout)["manifest"], json.loads(unpacked.stdout)["manifest"])
            self.assertTrue((restored / "project.sqlite").is_file())
            second = cli("restore", archive, restored)
            self.assertEqual(second.returncode, 1)
            self.assertIn("PROJECT_ARCHIVE_DESTINATION_EXISTS", second.stderr)
            note = restored / "notes.txt"
            note.write_bytes(b"keep original")
            replaced = cli("restore", archive, restored, "--replace")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            backup = Path(json.loads(replaced.stdout)["backup_path"])
            self.assertEqual((backup / "notes.txt").read_bytes(), b"keep original")
            self.assertFalse(note.exists())

    def test_replace_validates_first_and_rolls_back_failed_promotion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "project"
            target.mkdir()
            database = target / "project.sqlite"
            with closing(open_project(database)):
                pass
            original = database.read_bytes()
            archive = root / "valid.petrolab"
            export_project_archive(database, str(archive), "project")
            broken = root / "broken.petrolab"
            broken.write_bytes(b"invalid zip")
            with self.assertRaises(ImportCommandError) as invalid:
                replace_project_from_archive(str(broken), str(target))
            self.assertEqual(invalid.exception.code, "PROJECT_ARCHIVE_INVALID")
            self.assertEqual(database.read_bytes(), original)
            self.assertEqual(list(root.glob("project.backup-*")), [])
            journal = target / "project.sqlite-wal"
            journal.touch()
            with self.assertRaises(ImportCommandError) as busy:
                replace_project_from_archive(str(archive), str(target))
            self.assertEqual(busy.exception.code, "PROJECT_ARCHIVE_PROJECT_IN_USE")
            journal.unlink()
            rename = Path.rename

            def fail_promotion(path, destination):
                if path.name == "verified":
                    raise PermissionError("injected promotion failure")
                return rename(path, destination)

            with patch.object(Path, "rename", fail_promotion), self.assertRaises(ImportCommandError) as failed:
                replace_project_from_archive(str(archive), str(target))
            self.assertEqual(failed.exception.code, "PROJECT_ARCHIVE_FAILED")
            self.assertEqual(database.read_bytes(), original)
            self.assertEqual(list(root.glob("project.backup-*")), [])

    def test_three_archive_levels_and_rejection_leave_original_untouched(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            source = root / "analyses.csv"
            source.write_text("Analysis,SiO2 [wt.%]\nP1,12\nP2,<1\n", encoding="utf-8")
            image = root / "ppl.png"
            Image.new("RGB", (16, 12), "#627758").save(image)
            originals = {path: path.read_bytes() for path in (source, image)}

            def call(command, **payload):
                return handle_request({"protocol_version": "1.0", "request_id": str(uuid4()), "command": command,
                    "payload": {"project_database_path": str(database), **payload}})

            imported = call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"])
            self.assertIn("result", imported)
            plan = call("media.import.plan", assignments=[{
                "source_path": str(image), "ownership_mode": "linked_external", "media_type": "PPL",
                "sample_name": "KIV-1", "thin_section_name": "TS-1", "placements": [],
            }])["result"]
            self.assertIn("result", call("media.import.apply", plan=plan))

            def scientific_rows(path):
                with closing(sqlite3.connect(path)) as connection:
                    return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                            for table in ("analysis", "measurement", "import_recipe_revision", "sample", "thin_section")}

            expected = scientific_rows(database)
            for level, file_count in (("project", 1), ("project_sources", 2), ("full", 3)):
                artifact = root / f"{level}.petrolab"
                report = call("project.archive.check_export", level=level)["result"]
                self.assertTrue(report["ready"])
                self.assertEqual(len(report["assets"]), file_count - 1)
                self.assertFalse(artifact.exists())
                exported = call("project.archive.export", output_path=str(artifact), level=level)
                self.assertIn("result", exported)
                manifest = exported["result"]["manifest"]
                self.assertEqual(len(manifest["files"]), file_count)
                with ZipFile(artifact) as archive:
                    for entry in manifest["files"]:
                        self.assertEqual(sha256(archive.read(entry["path"])).hexdigest(), entry["sha256"])
                destination = root / f"restored-{level}"
                original_archive = artifact.read_bytes()
                inspected = call("project.archive.inspect", archive_path=str(artifact))
                self.assertEqual(inspected.get("result"), {"manifest": manifest,
                    "unpacked_size": sum(entry["size"] for entry in manifest["files"])})
                self.assertEqual(artifact.read_bytes(), original_archive)
                self.assertFalse(destination.exists())
                restored = call("project.archive.restore", archive_path=str(artifact), destination_path=str(destination))
                self.assertIn("result", restored)
                self.assertEqual(scientific_rows(destination / "project.sqlite"), expected)
                for entry in manifest["files"]:
                    if entry["path"] != "project.sqlite":
                        self.assertEqual(sha256((destination / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
                denied = call("project.archive.restore", archive_path=str(artifact), destination_path=str(destination))
                self.assertEqual(denied["error"]["code"], "PROJECT_ARCHIVE_DESTINATION_EXISTS")
                self.assertEqual(scientific_rows(destination / "project.sqlite"), expected)

            good = root / "full.petrolab"
            for invalid in ("damaged", "damaged-media", "traversal"):
                bad = root / f"{invalid}.petrolab"
                with ZipFile(good) as archive, ZipFile(bad, "w") as out:
                    manifest = json.loads(archive.read("manifest.json"))
                    for entry in manifest["files"]:
                        path = entry["path"]
                        data = archive.read(path)
                        if invalid == "damaged" and path == "project.sqlite":
                            data = b"!" + data[1:]
                        if invalid == "damaged-media" and path.startswith("media/"):
                            data = b"!" + data[1:]
                        if invalid == "traversal" and path.startswith("media/"):
                            path = entry["path"] = "../escaped.png"
                        out.writestr(path, data)
                    out.writestr("manifest.json", json.dumps(manifest))
                destination = root / f"restored-{invalid}"
                before = bad.read_bytes()
                self.assertEqual(call("project.archive.inspect", archive_path=str(bad))["error"]["code"],
                                 "PROJECT_ARCHIVE_INVALID")
                self.assertEqual(call("project.archive.restore", archive_path=str(bad),
                    destination_path=str(destination))["error"]["code"], "PROJECT_ARCHIVE_INVALID")
                self.assertEqual(bad.read_bytes(), before)
                self.assertFalse(destination.exists())
                self.assertFalse((root / "escaped.png").exists())

            with closing(sqlite3.connect(database)) as connection:
                relative, = connection.execute("SELECT managed_relative_path FROM source_file").fetchone()
            managed = root / relative
            missing = managed.with_suffix(".moved")
            managed.rename(missing)
            image.write_bytes(b"changed linked photo")
            database_bytes = database.read_bytes()
            report = call("project.archive.check_export", level="full")["result"]
            self.assertFalse(report["ready"])
            self.assertEqual({(item["kind"], item["name"], item["status"]) for item in report["assets"]}, {
                ("sources", source.name, "unavailable"), ("media", image.name, "changed"),
            })
            sources_report = call("project.archive.check_export", level="project_sources")["result"]
            self.assertEqual([item["status"] for item in sources_report["assets"]], ["unavailable"])
            self.assertTrue(call("project.archive.check_export", level="project")["result"]["ready"])
            refused = root / "unavailable-full.petrolab"
            export = call("project.archive.export", level="full", output_path=str(refused))
            self.assertEqual(export["error"]["code"], "PROJECT_ARCHIVE_SOURCE_UNAVAILABLE")
            self.assertFalse(refused.exists())
            self.assertEqual(database.read_bytes(), database_bytes)
            self.assertFalse(managed.exists())
            self.assertEqual(image.read_bytes(), b"changed linked photo")
            missing.rename(managed)
            image.write_bytes(originals[image])
            self.assertEqual(scientific_rows(database), expected)
            self.assertEqual({path: path.read_bytes() for path in originals}, originals)
