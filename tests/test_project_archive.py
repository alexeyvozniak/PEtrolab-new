from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from zipfile import ZipFile

from PIL import Image

from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.ndjson_service import handle_request


class ProjectArchiveTests(unittest.TestCase):
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
                exported = call("project.archive.export", output_path=str(artifact), level=level)
                self.assertIn("result", exported)
                manifest = exported["result"]["manifest"]
                self.assertEqual(len(manifest["files"]), file_count)
                with ZipFile(artifact) as archive:
                    for entry in manifest["files"]:
                        self.assertEqual(sha256(archive.read(entry["path"])).hexdigest(), entry["sha256"])
                destination = root / f"restored-{level}"
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
            for invalid in ("damaged", "traversal"):
                bad = root / f"{invalid}.petrolab"
                with ZipFile(good) as archive, ZipFile(bad, "w") as out:
                    manifest = json.loads(archive.read("manifest.json"))
                    for entry in manifest["files"]:
                        path = entry["path"]
                        data = archive.read(path)
                        if invalid == "damaged" and path == "project.sqlite":
                            data = b"!" + data[1:]
                        if invalid == "traversal" and path.startswith("media/"):
                            path = entry["path"] = "../escaped.png"
                        out.writestr(path, data)
                    out.writestr("manifest.json", json.dumps(manifest))
                destination = root / f"restored-{invalid}"
                self.assertEqual(call("project.archive.restore", archive_path=str(bad),
                    destination_path=str(destination))["error"]["code"], "PROJECT_ARCHIVE_INVALID")
                self.assertFalse(destination.exists())
                self.assertFalse((root / "escaped.png").exists())
            self.assertEqual(scientific_rows(database), expected)
            self.assertEqual({path: path.read_bytes() for path in originals}, originals)
