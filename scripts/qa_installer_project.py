"""Seed and verify persistent project data across the Windows installer upgrade."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from qa_packaged_import import request, run
from petrolab.desktop_workflow import suggest_import_recipe


def project_state(executable, database):
    return [item["result"] for item in run(executable, [
        request(command, {"project_database_path": str(database)})
        for command in ("project.analyses.list", "work_group.list", "plot_spec.list")
    ])]


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
    from uuid import uuid4

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    parser.add_argument("executable", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    action = seed if args.action == "seed" else verify
    action(args.executable, args.database, args.state)


if __name__ == "__main__":
    main()
