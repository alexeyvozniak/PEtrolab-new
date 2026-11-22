"""Seed and verify persistent project data across the Windows installer upgrade."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

from qa_packaged_import import request, run
from petrolab.desktop_workflow import suggest_import_recipe


def project_state(executable, database):
    state = [item["result"] for item in run(executable, [
        request(command, {"project_database_path": str(database)})
        for command in ("project.analyses.list", "work_group.list", "plot_spec.list")
    ])]
    layouts = run(executable, [
        request("plot_spec.open", {"project_database_path": str(database), "id": layout["id"]})
        for layout in state[2]
    ])
    return [*state[:2], [item["result"] for item in layouts]]


def seed(executable, database, state_file):
    if state_file.exists():
        raise RuntimeError("Upgrade verification evidence already exists")
    source = state_file.with_suffix(".csv")
    source.write_text("Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\n"
                      "P1,11,22,67\nP2,23,41,36\nP3,25,35,40\nP4,29,35,36\nP5,31,12,57\n", encoding="utf-8")
    scope = {"project_database_path": str(database)}
    _, listed, catalog = run(executable, [
        request("import.plan.apply", {**scope, "source_path": str(source), "recipe": suggest_import_recipe(source)["recipe"]}),
        request("project.analyses.list", scope),
        request("plot_data.catalog", scope),
    ])
    ids = [row["analysis_id"] for row in listed["result"]["analyses"]]
    axes = catalog["result"]["axes"]
    archive = state_file.with_suffix(".petrolab")
    run(executable, [
        request("work_group.create", {**scope, "name": "Upgrade QA", "analysis_ids": ids, "created_by": "QA"}),
        request("plot_spec.save", {**scope, "name": "Upgrade QA", "analysis_ids": ids, "colors": {}, "panels": [
            {"id": str(uuid4()), "kind": "binary", "axes": axes[:2]},
            {"id": str(uuid4()), "kind": "ternary", "axes": axes},
        ]}),
        request("project.archive.export", {**scope, "output_path": str(archive), "level": "project_sources"}),
    ])
    with ZipFile(archive) as package:
        manifest = json.loads(package.read("manifest.json"))
    expected = {"data": project_state(executable, database), "source_sha256": sha256(source.read_bytes()).hexdigest(),
                "sources": [relative for relative in manifest["files"] if relative["path"].startswith("sources/")]}
    state_file.write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")


def verify(executable, database, state_file):
    expected = json.loads(state_file.read_text(encoding="utf-8"))
    if project_state(executable, database) != expected["data"]:
        raise AssertionError("Upgrade changed persisted analysis, group or plot records")
    if sha256(state_file.with_suffix(".csv").read_bytes()).hexdigest() != expected["source_sha256"]:
        raise AssertionError("Upgrade changed the original source")
    for entry in expected["sources"]:
        managed = database.parent / entry["path"]
        if sha256(managed.read_bytes()).hexdigest() != entry["sha256"]:
            raise AssertionError(f"Upgrade changed a managed source: {managed.name}")


def verify_historical(executable, historical_source):
    historical_source = historical_source.resolve(strict=True)
    with TemporaryDirectory(prefix="petrolab-historical-") as directory:
        root = Path(directory)
        database = root / "project.sqlite"
        source = root / "source.csv"
        original_source = b"Analysis,SiO2 (wt.%),Al2O3 (wt.%)\nA1,40,21\nA2,41,22\nA3,42,23\nA4,43,24\n"
        source.write_bytes(original_source)
        subprocess.run([sys.executable, "-c", """
import sys
from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.import_apply import apply_import_plan
database, source = sys.argv[1:]
apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
""", str(database), str(source)], cwd=historical_source,
            env={**os.environ, "PYTHONPATH": str(historical_source / "src")}, check=True, timeout=60)

        def read_project(path):
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise AssertionError(f"SQLite integrity check failed: {path.name}")
                version = connection.execute("SELECT MAX(version) FROM schema_migration").fetchone()[0]
                rows = connection.execute("""
                    SELECT a.analysis_id, a.identity_json, a.source_id, a.sheet_name, a.source_row_number,
                           m.measurement_id, m.canonical_field, m.raw_token, m.unit, m.source_cell
                    FROM analysis a JOIN measurement m USING (analysis_id)
                    ORDER BY a.analysis_id, m.measurement_id
                """).fetchall()
                return version, rows

        old_version, old_rows = read_project(database)
        if old_version != 8 or len(old_rows) != 8:
            raise AssertionError("The historical 0.1.6 source did not produce the expected schema and measurements")
        result = run(executable, [request("project.analyses.list", {"project_database_path": str(database)})])[0]["result"]
        new_version, new_rows = read_project(database)
        if result["total"] != 4 or new_version <= old_version or new_rows != old_rows:
            raise AssertionError("The installed candidate changed or lost historical analyses")
        backups = list(root.glob("project.sqlite.before-v9-*.bak"))
        if len(backups) != 1 or read_project(backups[0]) != (old_version, old_rows) or source.read_bytes() != original_source:
            raise AssertionError("The historical database backup or original source was not preserved")
    print("The candidate migrated a historical 0.1.6 project and preserved its measurements and backup.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify", "historical"))
    parser.add_argument("executable", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("state", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "historical":
        verify_historical(args.executable, args.database)
    else:
        if args.state is None:
            parser.error("seed and verify require the state file")
        action = seed if args.action == "seed" else verify
        action(args.executable, args.database, args.state)


if __name__ == "__main__":
    main()
