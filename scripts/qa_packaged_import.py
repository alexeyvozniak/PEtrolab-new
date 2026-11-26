"""Exercise the packaged NDJSON service against an isolated temporary project."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import closing
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from PIL import Image

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


def archive_command(executable: Path, *args, expected_error: str | None = None) -> dict | None:
    completed = subprocess.run([str(executable), "archive", *map(str, args)], text=True, encoding="utf-8",
                               capture_output=True, timeout=120, check=False)
    if expected_error is not None:
        if completed.returncode != 1 or not completed.stderr.startswith(expected_error + ":"):
            raise AssertionError(f"Expected {expected_error}, got {completed.returncode}: {completed.stderr.strip()}")
        return None
    if completed.returncode:
        raise RuntimeError(f"Packaged archive command failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def check_mineral_formulae(executable: Path, directory: Path) -> None:
    source = directory / "formulae.csv"
    original = (b"Analysis,SiO2 [wt.%],Al2O3 [wt.%],CaO [wt.%],Na2O [wt.%],K2O [wt.%]\n"
                b"F1,44.82,34.55,18.63,0.67,0.05\n")
    source.write_bytes(original)
    project = {"project_database_path": str(directory / "formulae.sqlite")}
    catalog, _, listed = [item["result"] for item in run(executable, [
        request("formula.methods.list", {}),
        request("import.plan.apply", {**project, "source_path": str(source), "recipe": suggest_import_recipe(source)["recipe"]}),
        request("project.analyses.list", project),
    ])]
    methods = {item["method_id"] for item in catalog}
    expected = {"formula.olivine.4o", "formula.feldspar.8o", "formula.pyroxene.6o", "formula.zircon.4o",
                "formula.spinel.4o", "formula.ilmenite.3o", "formula.perovskite.3o",
                "formula.carbonate.1cat", "formula.carbonate.2cat", "formula.garnet.12o", "formula.nepheline.32o",
                "formula.apatite.25oeq", "formula.titanite.2cat", "formula.mica.11oeq", "formula.mica.22oeq",
                "formula.amphibole.23oeq", "formula.pyroxene.6o.droop", "formula.garnet.12o.droop",
                "formula.spinel.4o.droop", "formula.ilmenite.3o.droop"}
    if not expected <= methods:
        raise AssertionError(f"Packaged formula catalog is missing methods: {methods}")
    analysis, = listed["analyses"]
    inputs = {**project, "method_id": "formula.feldspar.8o", "analysis_id": analysis["analysis_id"],
              "measurement_ids": [item["measurement_id"] for item in analysis["measurement_list"]]}
    review = run(executable, [request("formula.review", inputs)])[0]["result"]
    saved = run(executable, [request("formula.run", {**inputs, **{
        name: review[name] for name in ("input_fingerprint", "method_definition_fingerprint")
    }})])[0]["result"]
    reopened, after = [item["result"] for item in run(executable, [
        request("formula.run.open", {**project, "run_id": saved["id"]}),
        request("project.analyses.list", project),
    ])]
    anorthite = reopened["result_manifest"]["end_member_mol_percent"]["An"]
    if reopened != saved or reopened["status"] != "current" or not math.isclose(anorthite, 93.66, abs_tol=0.2):
        raise AssertionError("Packaged feldspar method did not restore the verified An result")
    fingerprint = reopened['method_definition_fingerprint']
    formula = {key: reopened[key] for key in ('method_id', 'method_version', 'method_definition_fingerprint')}
    formula.update(version=1, run_ids=[reopened['id']])
    axes = [{'field': f'apfu.{field}', 'unit': 'APFU', 'method': None, 'measurement_set': None, 'formula': formula}
            for field in ('Na', 'K', 'Ca')]
    panel = {'id': str(uuid.uuid4()), 'kind': 'ternary', 'axes': axes}
    layout = run(executable, [request('plot_spec.save', {**project, 'name': 'APFU original', 'panels': [panel], 'colors': {}})])[0]['result']
    template = run(executable, [request('workspace.template.save', {**project, 'name': 'APFU template', 'plot_id': layout['id']})])[0]['result']
    if reopened['id'] in json.dumps(template) or analysis['analysis_id'] in json.dumps(template):
        raise AssertionError('The APFU template retained concrete inputs')
    scope = {**project, 'id': template['id'], 'analysis_ids': [analysis['analysis_id']]}
    blocked, applied, projection = [response['result'] for response in run(executable, [
        request('workspace.template.apply', scope),
        request('workspace.template.apply', {**scope, 'name': 'APFU applied', 'formula_run_ids': {fingerprint: [reopened['id']]}}),
        request('plot_data.query', {**project, 'kind': panel['kind'], 'axes': axes}),
    ])]
    if (blocked['migration_report'][0].get('code') != 'TEMPLATE_FORMULA_REQUIRED' or applied['plot'] is None
            or not math.isclose(projection['points'][0]['v'], .9366, abs_tol=.002)):
        raise AssertionError('Packaged APFU template did not require exact binding and preserve the verified projection')
    if after != listed or source.read_bytes() != original:
        raise AssertionError("Packaged formula calculation changed source data")
    print("Packaged AT-31/33 service: feldspar calculation, pinned APFU axes and explicit template binding.")


def check_workspace_archive(executable: Path, directory: Path) -> None:
    source = directory / "workspace.csv"
    incoming = directory / "workspace-new.csv"
    incompatible = directory / "workspace-ppm.csv"
    originals = {
        source: b"Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nA,10,20\nB,12,21\nC,39,22\nD,45,24\n",
        incoming: b"Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nN1,14,29\nN2,48,26\n",
        incompatible: b"Analysis,SiO2 [ppm],Al2O3 [ppm]\nT1,140,29\nT2,480,26\n",
    }
    for path, data in originals.items():
        path.write_bytes(data)
    database = directory / "workspace.sqlite"
    project = {"project_database_path": str(database)}
    imported = run(executable, [
        *(request("import.plan.apply", {**project, "source_path": str(path), "recipe": suggest_import_recipe(path)["recipe"]})
          for path in originals),
        request("project.analyses.list", project),
    ])
    source_ids = [entry["result"]["source_id"] for entry in imported[:-1]]
    rows = imported[-1]["result"]["analyses"]
    ids, target_ids, incompatible_ids = [[row["analysis_id"] for row in rows if row["source_id"] == source_id]
                                        for source_id in source_ids]
    features = run(executable, [request("plot_data.catalog", {**project, "analysis_ids": ids})])[0]["result"]["axes"]
    calculation_input = {"kind": "analysis_snapshot", "analysis_ids": ids}
    review, table, plot = [entry["result"] for entry in run(executable, [
        request("statistics.review", {**project, "input": calculation_input, "features": features}),
        request("table_view.save", {**project, "name": "QA workspace table",
            "columns": [{"field": field, "order": index, "visible": True, "width_px": None}
                        for index, field in enumerate(("source", "generation", "measurement:SiO2"))],
            "sort": [{"field": "source", "direction": "descending"}],
            "filters": [{"id": str(uuid.uuid4()), "field": "source", "operator": "equals",
                         "value": source_ids[0], "enabled": True}]}),
        request("plot_spec.save", {**project, "name": "QA workspace plot", "analysis_ids": ids, "colors": {},
            "panels": [{"id": str(uuid.uuid4()), "kind": "binary", "axes": features} for _ in range(3)]}),
    ])]
    calculation = run(executable, [request("statistics.cluster.run", {
        **project, "input": calculation_input, "features": features, "review_fingerprint": review["input_fingerprint"],
        "parameters": {"transform": "euclidean", "scaling": "standard", "clusters": 2, "seed": 42},
    })])[0]["result"]
    state = {
        "data_universe": {"dataset_ids": [], "work_group_ids": [], "analysis_ids": ids},
        "table_view_id": table["id"], "plot_specification_ids": [plot["id"]],
        "source_visibility": [{"source_id": source_ids[0], "visible": False},
                              {"source_id": source_ids[1], "visible": True}],
        "selection_restore_policy": "restore_exact_if_available", "selection_analysis_ids": ids[:2],
        "active_calculation_run_id": calculation["id"], "active_surface": "statistics",
    }
    snapshot, template = [entry["result"] for entry in run(executable, [
        request("workspace.snapshot.save", {**project, "name": "QA workspace", "state": state}),
        request("workspace.template.save", {**project, "name": "QA template",
            "plot_id": plot["id"], "table_view_id": table["id"], "calculation_run_id": calculation["id"]}),
    ])]
    if any(identifier in json.dumps(template) for identifier in [*ids, *source_ids, calculation["id"]]):
        raise AssertionError("Analysis template retained concrete IDs")
    total = {**features[0], 'field': 'Oxides sum', 'calculation': {'version': 1, 'operation': 'sum', 'operands': features}}
    calculated_layout = run(executable, [request('plot_spec.save', {
        **project, 'name': 'QA calculated layout', 'analysis_ids': ids, 'colors': {},
        'panels': [{'id': str(uuid.uuid4()), 'kind': 'binary', 'axes': [total, features[0]]}],
    })])[0]['result']
    calculated_template = run(executable, [request('workspace.template.save', {
        **project, 'name': 'QA calculated template', 'plot_id': calculated_layout['id'],
    })])[0]['result']
    original_database = database.read_bytes()
    archive = directory / "workspace.petrolab"
    archive_command(executable, "export", database, archive, "--level", "full")
    restored = archive_command(executable, "restore", archive, directory / "workspace-restored")
    destination = {"project_database_path": restored["project_database_path"]}
    opened, reopened_plot, reopened_run, listed_templates = [entry["result"] for entry in run(executable, [
        request("workspace.snapshot.open", {**destination, "id": snapshot["id"]}),
        request("plot_spec.open", {**destination, "id": plot["id"]}),
        request("statistics.run.open", {**destination, "run_id": calculation["id"]}),
        request("workspace.template.list", destination),
    ])]
    if opened != {"snapshot": snapshot, "migration_report": []} or reopened_plot != plot or reopened_run != calculation:
        raise AssertionError("Restored workspace differs from the saved state")
    if listed_templates != [{"id": item["id"], "name": item["name"]} for item in (calculated_template, template)]:
        raise AssertionError("Template disappeared from the restored project")
    database_before_rejection = Path(destination["project_database_path"]).read_bytes()
    rejected = run(executable, [request("workspace.template.apply", {**destination, "id": template["id"],
        "name": "QA incompatible", "analysis_ids": incompatible_ids})])[0]["result"]
    if any(rejected[key] for key in ("plot", "table_view", "method_plans")):
        raise AssertionError("Template partially applied to incompatible units")
    rejected_fields = {item["field"] for item in rejected["migration_report"]
                       if item["action"] == "blocked" and "ppm" in item["reason"] and "wt.%" in item["reason"]}
    if rejected_fields != {"SiO2", "Al2O3"} or Path(destination["project_database_path"]).read_bytes() != database_before_rejection:
        raise AssertionError("Incompatible template changed the project or lost the expected and observed units")
    applied = run(executable, [request("workspace.template.apply", {**destination, "id": template["id"],
        "name": "QA applied", "analysis_ids": target_ids})])[0]["result"]
    if (len(applied["plot"]["panels"]) != 3 or applied["table_view"]["sort"] != table["sort"]
            or applied["plot"]["input"]["analysis_ids"] != target_ids
            or applied["table_view"]["columns"] != table["columns"] or applied["table_view"]["filters"]
            or not any(item["field"] == "table_filters" and item["action"] == "omitted" for item in applied["migration_report"])):
        raise AssertionError("Restored template did not preserve the transferable layout")
    rerun = run(executable, [request("statistics.cluster.run", {**destination, **applied["method_plans"][0]})])[0]["result"]
    if rerun["input"]["analysis_ids"] != target_ids or rerun["id"] == calculation["id"]:
        raise AssertionError("Template did not start a separate calculation on the new selection")
    new_layout = run(executable, [request('workspace.template.apply', {**destination, 'id': calculated_template['id'],
        'name': 'QA applied calculated', 'analysis_ids': target_ids})])[0]['result']['plot']
    rebound = [{key: value for key, value in axis.items() if key not in {'scale', 'manual_range'}}
               for axis in new_layout['panels'][0]['axes']]
    sum_projection = run(executable, [request('plot_data.query', {
        **destination, 'kind': 'binary', 'axes': rebound, 'analysis_ids': target_ids,
    })])[0]['result']
    if {point['label']: point['values'][0] for point in sum_projection['points']} != {'N1': 43, 'N2': 74}:
        raise AssertionError('The restored calculated template produced unexpected values on the new input')
    if any(path.read_bytes() != data for path, data in originals.items()) or database.read_bytes() != original_database:
        raise AssertionError("Workspace archive operations changed the original files")
    print("Packaged AT-33 service: exact workspace restored, template applied to a different source, incompatible units rejected.")


def check_lithos_package(executable: Path, directory: Path, database: str, analysis_ids: list[str]) -> None:
    project = {"project_database_path": database}
    catalog = run(executable, [request("plot_data.catalog", {**project, "analysis_ids": analysis_ids})])[0]["result"]
    panel = {"id": str(uuid.uuid4()), "kind": "binary", "axes": catalog["axes"][:2]}
    saved, projected = run(executable, [request("plot_spec.save", {
        **project, "name": "QA Lithos", "analysis_ids": analysis_ids, "colors": {},
        "panels": [panel],
    }), request("plot_data.query", {
        **project, "analysis_ids": analysis_ids, "kind": panel["kind"], "axes": panel["axes"],
    })])
    layout, projection = saved["result"], projected["result"]
    figure = directory / "submission.pdf"
    raster = directory / "submission.tiff"
    photo = directory / "supplement.png"
    Image.new("RGB", (64, 48), "#69727e").save(photo)
    point = run(executable, [request("analytical_point.create", {
        **project, "sample_name": "KIV-2", "point_name": "QA publication",
        "analysis_ids": analysis_ids[:2], "link_type": "same_point",
    })])[0]["result"]
    plan = run(executable, [request("media.import.plan", {**project, "assignments": [{
        "source_path": str(photo), "ownership_mode": "managed_copy", "media_type": "BSE",
        "sample_name": "KIV-2", "thin_section_name": "QA publication",
        "placements": [{"analytical_point_id": point["analytical_point_id"],
                        "geometry": {"kind": "point", "x_px": 12, "y_px": 14}, "cross_sample_exception_reason": None}],
    }]})])[0]["result"]
    run(executable, [request("media.import.apply", {**project, "plan": plan})])
    media_id = plan["items"][0]["media_asset_id"]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60" viewBox="0 0 100 60">'
           '<g id="panel-a"><text x="10" y="17" font-size="8">QA · Б</text>'
           '<line x1="5" y1="40" x2="95" y2="40" stroke="#202020"/></g></svg>')
    params = {**project, "name": "QA Lithos", "profile": "lithos", "width_mm": 90, "items": [{
        "kind": "publication_figure", "id": layout["id"], "caption": "QA figure", "source_path": str(figure),
    }, {
        "kind": "publication_figure", "id": layout["id"], "caption": "QA raster", "source_path": str(raster),
        "artwork": "combination",
    }]}
    original_database = Path(database).read_bytes()
    _, _, *captured = run(executable, [
        request("plot.export", {"svg": svg, "width_mm": 90, "format": "pdf", "output_path": str(figure)}),
        request("plot.export", {"svg": svg, "width_mm": 90, "dpi": 600, "format": "tiff", "output_path": str(raster)}),
        request("publication.capture_plot", {**project, "caption": "QA direct plot", "capture": {
            "name": "QA direct plot", "svg": svg, "format": "pdf", "width_mm": 90, "dpi": 600, "include_csv": True,
            "analysis_ids": analysis_ids, "colors": {}, "hidden_analysis_ids": [], "hidden_source_ids": [], "layers": [],
            "panels": [{**panel, "projection_sha256": projection["projection_sha256"]}],
        }}),
        request("publication.capture_table", {**project, "analysis_ids": analysis_ids[:2][::-1]}),
        request("publication.capture_media", {**project, "media_asset_id": media_id,
            "options": {"points": True, "regions": False, "labels": True, "legend": True}}),
    ])
    params["items"].extend(item["result"] for item in captured)
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
        if archive.read("figures/Figure_02.tiff") != raster.read_bytes() or manifest["items"][1]["figure"]["effective_dpi"] < 600:
            raise AssertionError("Packaged publication changed the attached TIFF or its resolution")
        direct = manifest["items"][2]
        exact_ids = [point["analysis_id"] for point in projection["points"]]
        if (direct["analysis_ids"] != exact_ids or archive.read("figures/Figure_03.pdf") != figure.read_bytes()
                or not all(identifier in archive.read("data/03-plot_capture.csv").decode() for identifier in exact_ids)):
            raise AssertionError("Packaged publication lost direct plot content or analysis IDs")
        with closing(load_workbook(BytesIO(archive.read("tables/04-selection_table.xlsx")), read_only=True)) as book:
            if [row[0] for row in list(book["Analyses"].values)[1:]] != analysis_ids[:2][::-1]:
                raise AssertionError("Packaged publication changed the selection table")
        with Image.open(BytesIO(archive.read("images/05-media_capture.png"))) as annotated:
            media = json.loads(annotated.info["PetroLab"])
            if media["source_sha256"] != hashlib.sha256(photo.read_bytes()).hexdigest() or len(media["annotation_ids"]) != 1:
                raise AssertionError("Packaged publication lost source identity or annotation")
        if set(manifest["items"][4]["analysis_ids"]) != set(analysis_ids[:2]):
            raise AssertionError("Packaged publication lost linked analyses")
        for entry in manifest["files"]:
            if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["sha256"]:
                raise AssertionError(f"Packaged publication checksum mismatch: {entry['path']}")


def check_portable_archive(executable: Path, directory: Path) -> None:
    directory.mkdir()
    database = str(directory / "project.sqlite")
    project = {"project_database_path": database}
    image, photo = directory / "thin-section.png", directory / "plane-light.png"
    Image.new("RGB", (48, 32), "#627758").save(image)
    Image.new("RGB", (48, 32), "#7d9c71").save(photo)
    original_files = {path: path.read_bytes() for path in (FIXTURE, image, photo)}
    _, listed, preview = [item["result"] for item in run(executable, [
        request("import.plan.apply", {**project, "source_path": str(FIXTURE), "recipe": fixture_recipe()}),
        request("project.analyses.list", {**project, "limit": 100}),
        request("media.preview_input", {"source_path": str(image)}),
    ])]
    if not preview["preview_url"].startswith("data:image/jpeg;base64,"):
        raise AssertionError("Packaged service failed to decode and preview an image")
    analyses = listed["analyses"]
    point = run(executable, [request("analytical_point.create", {**project, "sample_name": "Archive QA", "point_name": "P-01",
        "analysis_ids": [row["analysis_id"] for row in analyses[:2]], "link_type": "same_point"})])[0]["result"]
    point_id = point["analytical_point_id"]
    assignment = {"ownership_mode": "linked_external", "sample_name": point["sample_name"], "thin_section_name": "TS-01"}
    plan = run(executable, [request("media.import.plan", {**project, "assignments": [
        {**assignment, "source_path": str(image), "media_type": "BSE", "placements": [
            {"analytical_point_id": point_id, "geometry": {"kind": "point", "x_px": 16, "y_px": 8},
             "cross_sample_exception_reason": None}]},
        {**assignment, "source_path": str(photo), "media_type": "PPL", "placements": [],
         "attach_to_placements": [{"analytical_point_id": point_id,
                                   "source_fingerprint": hashlib.sha256(original_files[image]).hexdigest()}]},
    ]})])[0]["result"]
    run(executable, [request("media.import.apply", {**project, "plan": plan})])

    def content(path):
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or connection.execute("PRAGMA foreign_key_check").fetchone():
                raise AssertionError(f"Integrity check failed for {path.name}")
            tables = ("analysis", "measurement", "source_cell_provenance", "import_recipe_revision",
                      "analytical_point_analysis", "spatial_annotation", "analytical_point_annotation", "media_link")
            return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}

    expected = content(Path(database))
    if not all(expected.values()):
        raise AssertionError("Portable archive fixture has missing scientific records or links")
    database_bytes = Path(database).read_bytes()
    levels = {"project": 1, "project_sources": 2, "full": 4}
    source_hash, image_hash, photo_hash = (hashlib.sha256(original_files[path]).hexdigest() for path in (FIXTURE, image, photo))
    expected_hashes = {"project": set(), "project_sources": {source_hash}, "full": {source_hash, image_hash, photo_hash}}
    archives = {level: directory / f"portable-{level}.petrolab" for level in levels}
    destinations = {level: directory / f"relocated-{level}" for level in levels}
    exported = run(executable, [request("project.archive.export", {**project, "output_path": str(path), "level": level})
                                for level, path in archives.items()])
    restored = run(executable, [request("project.archive.restore", {"archive_path": str(archives[level]),
                              "destination_path": str(destination)}) for level, destination in destinations.items()])
    for (level, count), output, opened in zip(levels.items(), exported, restored, strict=True):
        manifest = opened["result"]["manifest"]
        destination = destinations[level]
        if output["result"]["manifest"] != manifest or len(manifest["files"]) != count or manifest["level"] != level:
            raise AssertionError(f"Wrong manifest for archive level {level}")
        if content(destination / "project.sqlite") != expected:
            raise AssertionError(f"Scientific records or links changed in archive level {level}")
        for entry in manifest["files"]:
            payload = (destination / entry["path"]).read_bytes()
            if len(payload) != entry["size"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise AssertionError(f"Manifest differs from the restored file: {entry['path']}")
        included = {hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.rglob("*")
                    if path.is_file() and path.name != "project.sqlite"}
        if included != expected_hashes[level]:
            raise AssertionError(f"Unexpected files in archive level {level}")

    full = archives["full"]
    destination = destinations["full"]
    relocated_project = {"project_database_path": str(destination / "project.sqlite")}
    reopened, restored_preview = [item["result"] for item in run(executable, [
        request("project.analyses.list", {**relocated_project, "limit": 100}),
        request("media.preview", {**relocated_project, "media_asset_id": plan["items"][0]["media_asset_id"]}),
    ])]
    if reopened["analyses"] != analyses or restored_preview["annotations"][0]["analytical_point_id"] != point_id:
        raise AssertionError("Restored project lost an analysis or the image point")
    previous_file = destination / "original-notes.txt"
    previous_file.write_bytes(b"Original workspace")
    previous_database = (destination / "project.sqlite").read_bytes()
    archive_command(executable, "restore", full, destination, expected_error="PROJECT_ARCHIVE_DESTINATION_EXISTS")
    corrupted = directory / "damaged.petrolab"
    with ZipFile(full) as original, ZipFile(corrupted, "w") as altered:
        for name in original.namelist():
            payload = original.read(name)
            altered.writestr(name, b"!" + payload[1:] if name == "project.sqlite" else payload)
    archive_command(executable, "restore", corrupted, destination, "--replace", expected_error="PROJECT_ARCHIVE_INVALID")
    invalid_path = directory / "invalid-path.petrolab"
    with ZipFile(full) as original, ZipFile(invalid_path, "w") as altered:
        manifest = json.loads(original.read("manifest.json"))
        for entry in manifest["files"]:
            name = entry["path"]
            if name.startswith("media/"):
                entry["path"] = "../" + Path(name).name
            altered.writestr(entry["path"], original.read(name))
        altered.writestr("manifest.json", json.dumps(manifest))
    invalid_destination = directory / "invalid-restore"
    archive_command(executable, "restore", invalid_path, invalid_destination, expected_error="PROJECT_ARCHIVE_INVALID")
    if invalid_destination.exists():
        raise AssertionError("Invalid archive path created a destination")
    if (previous_file.read_bytes() != b"Original workspace" or (destination / "project.sqlite").read_bytes() != previous_database
            or list(directory.glob(f"{destination.name}.backup-*"))):
        raise AssertionError("Rejected restore changed or backed up the destination")
    replacement = archive_command(executable, "restore", full, destination, "--replace")
    backup = Path(replacement["backup_path"])
    if (previous_file.exists() or (backup / previous_file.name).read_bytes() != b"Original workspace"
            or (backup / "project.sqlite").read_bytes() != previous_database or content(destination / "project.sqlite") != expected):
        raise AssertionError("Replacing the workspace did not preserve the complete previous directory or restore the archive")
    if Path(database).read_bytes() != database_bytes or any(path.read_bytes() != data for path, data in original_files.items()):
        raise AssertionError("Archive verification changed an original")
    print("Packaged AT-34 service: all archive levels, original bytes, exact links, rejected replacement and backup verified.")


def check_operation_journal(executable: Path, directory: Path) -> None:
    source = directory / "journal.csv"
    original = b"Analysis,SiO2 [wt.%]\nJ1,39\nJ2,41\nJ3,43\n"
    source.write_bytes(original)
    project = {"project_database_path": str(directory / "journal.sqlite")}

    def exchange(*commands):
        return [item["result"] for item in run(executable, [
            request(command, {**project, **payload}) for command, payload in commands
        ])]

    prepared, = exchange(("import.workspace.create", {"sources": [{"staged_path": str(source)}]}))
    workspace = prepared["session"]
    review = {"workspace_id": workspace["workspace_id"], "expected_revision": workspace["draft_revision"]}
    _, _, _, before = exchange(
        ("import.workspace.restore", {}),
        ("import.workspace.apply_decision", {
            **review, "source_id": workspace["active_source_id"],
            "decision": {"kind": "sample_assignment", "mode": "new", "sample_name": "QA Journal",
                         "preview_ids": [row["preview_id"] for row in prepared["active"]["plan"]["planned_records"]]},
        }),
        ("import.workspace.commit", {**review, "expected_revision": workspace["draft_revision"] + 1}),
        ("project.analyses.list", {}),
    )
    ids = [row["analysis_id"] for row in before["analyses"]]
    sample_id = before["analyses"][0]["sample_association"]["sample_id"]
    session_id = str(uuid.uuid4())
    assigned, point, hidden, page = exchange(
        ("generation.assign", {"analysis_ids": ids[:2], "new_name": "Rim", "actor": "QA"}),
        ("analytical_point.create", {"analysis_ids": ids[:2], "sample_id": sample_id,
                                     "point_name": "P-01", "link_type": "same_point", "actor": "QA"}),
        ("plot_visibility.hide", {"analysis_ids": ids[:1], "session_id": session_id}),
        ("operation_journal.list", {"limit": 2}),
    )
    if [entry["category"] for entry in page["entries"]] != ["view_only", "domain"]:
        raise AssertionError("Packaged journal lost its operation categories")
    point_entry = point["journal"]["id"]
    point_args = {"point_id": point["analytical_point_id"]}
    opened, restored_view, removed, links_after_remove, undo_generation, after, undone_entry = exchange(
        ("operation_journal.open", {"operation_id": point_entry}),
        ("operation_journal.undo", {"operation_id": hidden["id"], "actor": "QA",
                                    "session_id": session_id, "hidden_analysis_ids": ids[:1]}),
        ("analytical_point.link.set", {**point_args, "analysis_id": ids[0], "actor": "QA"}),
        ("analytical_point.analyses", point_args),
        ("operation_journal.undo", {"operation_id": assigned["id"], "actor": "QA"}),
        ("project.analyses.list", {}),
        ("operation_journal.open", {"operation_id": assigned["id"]}),
    )
    inverse, links_after_restore, cancelled_point, links_after_cancel = exchange(
        ("operation_journal.undo", {"operation_id": removed["id"], "actor": "QA"}),
        ("analytical_point.analyses", point_args),
        ("operation_journal.undo", {"operation_id": point_entry, "actor": "QA"}),
        ("analytical_point.analyses", point_args),
    )
    if opened != point["journal"] or restored_view["parameters"]["analysis_ids"] != ids[:1]:
        raise AssertionError("Packaged journal lost the original scope")
    if ([row["analysis_id"] for row in links_after_remove] != ids[1:2]
            or inverse["parameters"]["reverses_operation_id"] != removed["id"]):
        raise AssertionError("Packaged journal reversed the wrong removal")
    if ({row["analysis_id"] for row in links_after_restore} != set(ids[:2])
            or cancelled_point["parameters"]["analysis_ids"] != ids[:2] or links_after_cancel):
        raise AssertionError("Packaged journal restored or cancelled the wrong point links")
    if (undo_generation["parameters"]["assignment_operation_id"] != assigned["id"] or undone_entry["state"] != "undone"
            or after != before or source.read_bytes() != original):
        raise AssertionError("Packaged journal lost its inverse or changed the source evidence")
    print("Packaged AT-37 service: generation, point links, visibility and journal round-trip verified.")


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
        check_workspace_archive(executable, Path(directory))
        check_mineral_formulae(executable, Path(directory))
        check_operation_journal(executable, Path(directory))
        check_portable_archive(executable, Path(directory) / "archive-qa")
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
