"""Exercise the packaged NDJSON service against an isolated temporary project."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))
from test_import_preview import FIXTURE, fixture_recipe  # noqa: E402
from petrolab.desktop_workflow import suggest_import_recipe  # noqa: E402
from petrolab.import_preview import semantic_fingerprint  # noqa: E402


def request(command: str, payload: dict) -> dict:
    return {"protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": command, "payload": payload}


def run(executable: Path, requests: list[dict]) -> list[dict]:
    data = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
    completed = subprocess.run([str(executable)], input=data, text=True, encoding="utf-8", capture_output=True, timeout=120, check=True)
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    if len(responses) != len(requests):
        raise RuntimeError(f"Expected {len(requests)} responses; got {len(responses)}: {completed.stderr}")
    for sent, received in zip(requests, responses):
        if received.get("request_id") != sent["request_id"] or "error" in received:
            raise RuntimeError(f"Unexpected service response: {received}")
    return responses


def archive_command(executable: Path, *args) -> dict:
    completed = subprocess.run([str(executable), "archive", *map(str, args)], text=True, encoding="utf-8",
                               capture_output=True, timeout=120, check=False)
    if completed.returncode:
        raise RuntimeError(f"Packaged archive command failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def check_lithos_package(executable: Path, directory: Path, database: str, analysis_ids: list[str]) -> None:
    project = {"project_database_path": database}
    catalog = run(executable, [request("plot_data.catalog", {**project, "analysis_ids": analysis_ids})])[0]["result"]
    layout = run(executable, [request("plot_spec.save", {
        **project, "name": "QA Lithos", "analysis_ids": analysis_ids, "colors": {},
        "panels": [{"id": str(uuid.uuid4()), "kind": "binary", "axes": catalog["axes"][:2]}],
    })])[0]["result"]
    figure = directory / "submission.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=90 * 72 / 25.4, height=100)
    writer.write(figure)
    params = {**project, "name": "QA Lithos", "profile": "lithos", "width_mm": 90, "items": [{
        "kind": "publication_figure", "id": layout["id"], "caption": "QA figure", "source_path": str(figure),
    }]}
    original_database = Path(database).read_bytes()
    snapshot = run(executable, [request("publication.prepare", params)])[0]["result"]
    destination = directory / "submission.zip"
    run(executable, [request("publication.export", {
        **params, "expected_fingerprint": snapshot["fingerprint"], "output_path": str(destination),
    })])
    if Path(database).read_bytes() != original_database:
        raise AssertionError("Packaged publication changed the project database")
    with ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        item = manifest["items"][0]
        if (manifest != snapshot["manifest"] or manifest["profile"] != "lithos"
                or item["reference_id"] != layout["id"] or item["analysis_ids"] != analysis_ids
                or item["figure"]["page_width_mm"] != 90):
            raise AssertionError("Packaged publication lost the checked figure or its provenance")
        if archive.read("figures/Figure_01.pdf") != figure.read_bytes():
            raise AssertionError("Packaged publication changed the attached PDF")
        for entry in manifest["files"]:
            if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["sha256"]:
                raise AssertionError(f"Packaged publication checksum mismatch: {entry['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "desktop/src-tauri/binaries/petrolab-service.exe")
    executable = parser.parse_args().executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"Build the packaged service first: {executable}")
    original_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="petrolab-packaged-qa-") as directory:
        mineral_source = Path(directory) / "mineral-underflow.csv"
        mineral_source.write_text(
            "Analysis,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%)\n"
            "A1,95,1e-999,0,0,0,0,0\nA2,94,1,0,0,0,0,0\n", encoding="utf-8")
        mineral_recipe = suggest_import_recipe(mineral_source)["recipe"]
        mineral_recipe["global_decisions"]["mineral_verification_enabled"] = True
        mineral_recipe["semantic_fingerprint"] = semantic_fingerprint(mineral_recipe)
        mineral_plan = run(executable, [request("import.plan.create", {"source_path": str(mineral_source), "recipe": mineral_recipe})])[0]["result"]
        verification = mineral_plan["planned_records"][0]["mineral_verification"]
        if verification["status"] != "insufficient_input" or "invalid_numeric_input" not in verification["issues"] or verification["prediction"] is not None:
            raise AssertionError(f"Packaged service accepted an underflowing mineral input: {verification}")
        scientific_source = Path(directory) / "limits.csv"
        scientific_source.write_text("Analysis,F (wt.%)\nA1,<1e-3\nA2,1\nA3,<1e-999\n", encoding="utf-8")
        scientific_database = str(Path(directory) / "limits.sqlite")
        scientific_recipe = suggest_import_recipe(scientific_source)["recipe"]
        run(executable, [request("import.plan.apply", {"project_database_path": scientific_database, "source_path": str(scientific_source), "recipe": scientific_recipe})])
        with closing(sqlite3.connect(scientific_database)) as connection:
            measurement = connection.execute("SELECT raw_token, value_status, detection_limit FROM measurement WHERE raw_token = ?", ("<1e-3",)).fetchone()
            if measurement != ("<1e-3", "below_detection_limit", 0.001):
                raise AssertionError(f"Packaged service lost detection limit semantics: {measurement}")
            underflow = connection.execute("SELECT raw_token, value_status, detection_limit FROM measurement WHERE raw_token = ?", ("<1e-999",)).fetchone()
            if underflow != ("<1e-999", "below_detection_limit", None):
                raise AssertionError(f"Packaged service incorrectly represented a tiny detection limit: {underflow}")
        database = str(Path(directory) / "project.sqlite")
        imported, listed = run(executable, [
            request("import.plan.apply", {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()}),
            request("project.analyses.list", {"project_database_path": database, "limit": 100}),
        ])
        reopened = run(executable, [request("project.analyses.list", {"project_database_path": database, "limit": 100})])[0]
        if imported["result"]["analysis_count"] != 8 or listed["result"] != reopened["result"] or reopened["result"]["total"] != 8:
            raise AssertionError("Imported analyses differ after service restart")
        if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != original_hash:
            raise AssertionError("Source workbook changed during packaged import")
        members = [row["analysis_id"] for row in reopened["result"]["analyses"][:2]]
        group = run(executable, [request("work_group.create", {
            "project_database_path": database, "name": "QA cohort", "created_by": "QA", "analysis_ids": members,
        })])[0]["result"]
        groups = run(executable, [request("work_group.list", {"project_database_path": database})])[0]["result"]["groups"]
        if group["analysis_ids"] != members or groups != [{"group": group, "unavailable_analysis_ids": []}]:
            raise AssertionError("Packaged service changed work group membership after restart")
        check_lithos_package(executable, Path(directory), database,
                             [row["analysis_id"] for row in reopened["result"]["analyses"]])
        image = Path(directory) / "thin-section.png"
        Image.new("RGB", (48, 32), "#627758").save(image)
        archive = Path(directory) / "portable.petrolab"
        restored = Path(directory) / "relocated"
        preview = run(executable, [request("media.preview_input", {"source_path": str(image)})])[0]
        exported = archive_command(executable, "export", database, archive, "--level", "project_sources")
        unpacked = archive_command(executable, "restore", archive, restored)
        reopened_copy = run(executable, [
            request("project.analyses.list", {"project_database_path": unpacked["project_database_path"], "limit": 100}),
        ])[0]
        if not preview["result"]["preview_url"].startswith("data:image/jpeg;base64,"):
            raise AssertionError("Packaged service failed to decode and preview an image")
        if (exported["manifest"] != unpacked["manifest"]
                or reopened_copy["result"]["analyses"] != reopened["result"]["analyses"]):
            raise AssertionError("Packaged service changed project data during archive round-trip")
        selection_book = Path(directory) / "selection.xlsx"
        run(executable, [request("analysis.selection.export_xlsx", {
            "project_database_path": database, "analysis_ids": members, "output_path": str(selection_book),
        })])
        with closing(load_workbook(selection_book, read_only=True)) as exported:
            if [row[0] for row in exported["Analyses"].iter_rows(min_row=2, values_only=True)] != members:
                raise AssertionError("Packaged export changed the selection")
        view = run(executable, [request("table_view.save", {
            "project_database_path": database, "name": "QA columns",
            "columns": [{"field": "source", "order": 0, "visible": True, "width_px": None}],
            "sort": [{"field": "source", "direction": "descending"}], "filters": [],
        })])[0]["result"]
        views = run(executable, [request("table_view.list", {"project_database_path": database})])[0]["result"]
        if views["views"] != [view] or views["data_universe_fingerprint"] != view["data_universe_fingerprint"]:
            raise AssertionError("Packaged table view changed after restart")
        incomplete = Path(directory) / "incomplete.sqlite"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(incomplete)) as copy:
            source.backup(copy)
            copy.execute("DELETE FROM schema_migration WHERE version = 8")
            copy.commit()
        before_incomplete = incomplete.read_bytes()
        incomplete_request = request("project.analyses.list", {"project_database_path": str(incomplete), "limit": 100})
        completed = subprocess.run([str(executable)], input=json.dumps(incomplete_request) + "\n", text=True, encoding="utf-8", capture_output=True, timeout=120, check=True)
        response = json.loads(completed.stdout)
        if (response.get("request_id") != incomplete_request["request_id"]
                or response.get("error", {}).get("code") != "PROJECT_SCHEMA_UNSUPPORTED"
                or response["error"]["details"].get("missing_migrations") != [8]):
            raise AssertionError(f"Incomplete migration history was not rejected: {response}")
        if incomplete.read_bytes() != before_incomplete or list(incomplete.parent.glob(f"{incomplete.name}.*.bak")):
            raise AssertionError("Incomplete project was modified or backed up during rejected open")
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("INSERT INTO schema_migration VALUES (?, ?)", (999, "future"))
            connection.commit()
        before = Path(database).read_bytes()
        future_request = request("project.analyses.list", {"project_database_path": database, "limit": 100})
        completed = subprocess.run([str(executable)], input=json.dumps(future_request) + "\n", text=True, encoding="utf-8", capture_output=True, timeout=120, check=True)
        response = json.loads(completed.stdout.splitlines()[0])
        if response.get("request_id") != future_request["request_id"] or response.get("error", {}).get("code") != "PROJECT_SCHEMA_UNSUPPORTED":
            raise AssertionError(f"Newer schema was not rejected: {response}")
        if Path(database).read_bytes() != before:
            raise AssertionError("Newer project changed during rejected open")
        unrelated = Path(directory) / "unrelated.sqlite"
        with closing(sqlite3.connect(unrelated)) as connection:
            connection.execute("CREATE TABLE original (value TEXT)")
            connection.execute("INSERT INTO original VALUES ('preserve')")
            connection.commit()
        before_unrelated = unrelated.read_bytes()
        unrelated_request = request("project.analyses.list", {"project_database_path": str(unrelated), "limit": 100})
        completed = subprocess.run([str(executable)], input=json.dumps(unrelated_request) + "\n", text=True, encoding="utf-8", capture_output=True, timeout=120, check=True)
        response = json.loads(completed.stdout.splitlines()[0])
        if response.get("request_id") != unrelated_request["request_id"] or response.get("error", {}).get("code") != "PROJECT_SCHEMA_UNSUPPORTED":
            raise AssertionError(f"Unrelated database was not rejected: {response}")
        if unrelated.read_bytes() != before_unrelated:
            raise AssertionError("Unrelated database changed during rejected open")

        draft_database = str(Path(directory) / "draft-project.sqlite")
        draft_source = Path(directory) / "draft.csv"
        draft_source.write_text("Analysis,SiO2 [wt.%]\nA1,40\nA2,41\n", encoding="utf-8")
        draft_request = {"project_database_path": draft_database}
        created = run(executable, [request("import.workspace.create", {
            **draft_request, "sources": [{"staged_path": str(draft_source)}],
        })])[0]["result"]["session"]
        restored = run(executable, [request("import.workspace.restore", draft_request)])[0]["result"]["workspace"]["session"]
        if restored != created:
            raise AssertionError("Import draft changed after packaged service restart")
        restored_again = run(executable, [
            request("import.workspace.restore", draft_request),
            request("import.workspace.commit", {
                "workspace_id": restored["workspace_id"], "expected_revision": restored["draft_revision"],
            }),
            request("import.workspace.restore", draft_request),
        ])
        if restored_again[1]["result"]["analysis_count"] != 2 or restored_again[2]["result"]["workspace"] is not None:
            raise AssertionError("Restored draft did not commit cleanly")
        sample_database = str(Path(directory) / "sample-project.sqlite")
        prepared = run(executable, [request("import.workspace.create", {
            "project_database_path": sample_database, "sources": [{"staged_path": str(draft_source)}],
        })])[0]["result"]
        session = prepared["session"]
        record = prepared["active"]["plan"]["planned_records"][0]
        workspace_request = {"workspace_id": session["workspace_id"], "expected_revision": session["draft_revision"]}
        assigned = run(executable, [
            request("import.workspace.restore", {"project_database_path": sample_database}),
            request("import.workspace.apply_decision", {
                **workspace_request, "source_id": session["active_source_id"],
                "decision": {"kind": "sample_assignment", "mode": "new", "sample_name": "QA Sample",
                             "preview_ids": [record["preview_id"]]},
            }),
            request("import.workspace.commit", {**workspace_request, "expected_revision": session["draft_revision"] + 1}),
            request("project.analyses.list", {"project_database_path": sample_database, "limit": 100}),
        ])[-1]["result"]["analyses"]
        if [row["sample_association"]["status"] for row in assigned] != ["linked", "unresolved"]:
            raise AssertionError("Packaged import lost the explicit Sample assignment")
        edit_database = str(Path(directory) / "edit-project.sqlite")
        edit_source = Path(directory) / "edit.xlsx"
        workbook = Workbook()
        workbook.active.append(["Analysis", "F (wt.%)"])
        workbook.active.append(["A1", 4.5])
        workbook.save(edit_source)
        workbook.close()
        original_edit_source = edit_source.read_bytes()
        edit_params = {"project_database_path": edit_database}
        listed = run(executable, [
            request("import.plan.apply", {**edit_params, "source_path": str(edit_source),
                "recipe": suggest_import_recipe(edit_source)["recipe"]}),
            request("project.analyses.list", edit_params),
        ])[-1]["result"]["analyses"]
        entry = run(executable, [request("edit_draft.save", {**edit_params,
            "measurement_id": listed[0]["measurement_list"][0]["measurement_id"], "new_value": "6.5"})])[0]["result"]
        changed = run(executable, [request("edit_draft.commit", {**edit_params, "draft_id": entry["id"],
            "actor": "QA", "reason": "Test reference correction"})])[0]["result"]
        if not changed["applied"] or Path(changed["operation"]["parameters"]["backup_path"]).read_bytes() != original_edit_source:
            raise AssertionError("Packaged service did not retain the XLSX backup")
        with closing(load_workbook(edit_source, read_only=True)) as checked:
            if checked.active["B2"].value != 6.5:
                raise AssertionError("Packaged service did not write the selected XLSX cell")
    print("Packaged service: import and draft restored, Lithos ZIP verified, unsupported databases rejected unchanged.")


if __name__ == "__main__":
    main()
