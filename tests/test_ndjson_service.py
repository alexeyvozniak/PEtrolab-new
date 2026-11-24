from __future__ import annotations

import io
import json
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import shutil
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_preview import inspect_source  # noqa: E402
from petrolab.ndjson_service import PROTOCOL_VERSION, handle_request, serve  # noqa: E402
from test_import_preview import FIXTURE, fixture_recipe  # noqa: E402
from test_media_import import write_png  # noqa: E402


class NdjsonServiceTests(unittest.TestCase):
    def test_generation_assignment_undo_keeps_exact_scope_and_import_evidence(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            source_bytes = FIXTURE.read_bytes()

            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            def evidence():
                with closing(sqlite3.connect(database)) as connection:
                    return [connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                            for table in ("analysis", "measurement", "source_file", "source_cell_provenance")]

            self.assertIn("result", call("import.plan.apply", source_path=str(FIXTURE), recipe=fixture_recipe()))
            originals = evidence()
            rows = call("project.analyses.list")["result"]["analyses"]
            first, second, neighbor = [row["analysis_id"] for row in rows[:3]]
            assigned = call("generation.assign", analysis_ids=[first, second], new_name="Rim", actor="Reviewer")["result"]
            self.assertEqual(assigned["category"], "domain")
            self.assertEqual([row["entity_id"] for row in assigned["scope"]], [first, second])
            self.assertEqual([row["result_revision"] for row in assigned["scope"]], [1, 1])
            catalog = call("generation.list")["result"]["generations"]
            self.assertEqual([(item["name"], item["created_by"]) for item in catalog], [("Rim", "Reviewer")])
            self.assertEqual(call("generation.assign", analysis_ids=[neighbor], new_name="rim",
                                  actor="Reviewer")["error"]["code"], "GENERATION_NAME_EXISTS")
            replacement = call("generation.assign", analysis_ids=[second], new_name="Core", actor="Reviewer")["result"]
            conflict = call("generation.undo", operation_id=assigned["id"], actor="Reviewer")
            self.assertEqual(conflict["error"]["code"], "GENERATION_UNDO_CONFLICT")
            self.assertEqual(conflict["error"]["details"]["analysis_ids"], [second])
            visibility = call("plot_visibility.hide", analysis_ids=[first, second])["result"]
            self.assertEqual(visibility["category"], "view_only")
            self.assertEqual(call("generation.undo", operation_id=visibility["id"],
                                  actor="Reviewer")["error"]["code"], "GENERATION_UNDO_UNAVAILABLE")
            page = call("operation_journal.list", limit=2)["result"]
            self.assertEqual([item["id"] for item in page["entries"]], [visibility["id"], replacement["id"]])
            self.assertEqual(page["entries"][0]["scope_count"], 2)
            self.assertNotIn("scope", page["entries"][0])
            older = call("operation_journal.list", category="domain", before_id=page["next_before_id"])["result"]
            self.assertEqual([item["id"] for item in older["entries"]], [assigned["id"]])
            self.assertIsNone(older["next_before_id"])
            self.assertEqual(call("operation_journal.open", operation_id=assigned["id"])["result"], assigned)
            self.assertEqual(call("operation_journal.open", operation_id=str(uuid.uuid4()))["error"]["code"],
                             "OPERATION_NOT_FOUND")
            projected = {row["analysis_id"]: row["generation"] for row in call("project.analyses.list")["result"]["analyses"]}
            self.assertEqual([projected[item]["name"] for item in (first, second)], ["Rim", "Core"])
            self.assertIsNone(projected[neighbor])
            self.assertIn("result", call("generation.undo", operation_id=replacement["id"], actor="Reviewer"))
            reversed_entry = call("operation_journal.undo", operation_id=assigned["id"], actor="Reviewer")["result"]
            self.assertEqual(reversed_entry["action"], "restore_generation")
            self.assertEqual([row["entity_id"] for row in reversed_entry["scope"]], [first, second])
            self.assertEqual(call("generation.undo", operation_id=assigned["id"],
                                  actor="Reviewer")["error"]["code"], "GENERATION_UNDO_UNAVAILABLE")
            self.assertEqual(call("operation_journal.open", operation_id=assigned["id"])["result"]["state"], "undone")
            self.assertTrue(all(row["generation"] is None for row in call("project.analyses.list")["result"]["analyses"]))
            self.assertEqual(evidence(), originals)
            self.assertEqual(FIXTURE.read_bytes(), source_bytes)

    def test_mineral_trace_patterns_normalize_units_and_keep_gaps(self) -> None:
        from petrolab.desktop_workflow import suggest_import_recipe

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "project.sqlite")
            source = root / "trace.csv"
            source.write_text(
                "Analysis,Cs (ppm),La (ppm),Ce (ppb),Pb (ppm),Pr (ppm),Nd (ppm)\n"
                "M1,0.079,2.37,<100,0.71,0.095,0.0467\n"
                "M2,0.0079,0,6120,0.071,,0.467\n"
                "M3,0,0,<100,0,,0\n", encoding="utf-8",
            )
            before = source.read_bytes()

            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            imported = call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"])
            self.assertIn("result", imported, imported)
            catalog = call("plot_data.catalog")["result"]
            axes = {axis["field"]: axis for axis in catalog["axes"]}
            ree_axes = [axes[element] for element in ("La", "Ce", "Pr", "Nd")]
            ree = call("plot_data.query", kind="ree_pattern", axes=ree_axes)["result"]
            self.assertEqual(ree["normalization"]["id"], "sun_mcdonough_1989_c1_v1")
            self.assertEqual(catalog["patterns"]["ree_pattern"]["default_normalization"], ree["normalization"]["id"])
            self.assertEqual(ree["excluded_count"], 1)
            self.assertEqual(ree["exclusions"][0]["reason"], "no_positive_ratio")
            series = {point["label"]: point for point in ree["points"]}
            la, ce, pr, nd = series["M1"]["vertices"]
            self.assertAlmostEqual(la["ratio"], 10)
            self.assertEqual(ce["status"], "below_detection_limit")
            measurement, = ce["measurements"]
            self.assertTrue(measurement["measurement_id"])
            self.assertEqual(measurement["raw_token"], "<100")
            self.assertEqual(measurement["detection_limit"], 100)
            self.assertIsNone(ce["ratio"])
            self.assertIsNone(ce["v"])
            self.assertAlmostEqual(pr["ratio"], 1)
            self.assertAlmostEqual(pr["v"], 0.5)
            self.assertAlmostEqual(nd["ratio"], 0.1)
            self.assertEqual(ree["ticks"][1], [{"at": 0, "label": "0.1"}, {"at": 0.5, "label": "1"}, {"at": 1, "label": "10"}])
            self.assertEqual(series["M2"]["vertices"][0]["status"], "nonpositive")
            self.assertAlmostEqual(series["M2"]["vertices"][1]["ratio"], 10)
            self.assertIsNone(series["M2"]["vertices"][2]["ratio"])
            hidden = call("plot_data.query", kind="ree_pattern", axes=ree_axes,
                          hidden_analysis_ids=[series["M2"]["analysis_id"]])["result"]
            self.assertEqual(hidden["hidden_count"], 1)
            self.assertEqual([point["label"] for point in hidden["points"]], ["M1"])
            self.assertNotEqual(hidden["projection_sha256"], ree["projection_sha256"])

            spider = call("plot_data.query", kind="spider", axes=[axes["Cs"], axes["Pb"]])["result"]
            self.assertEqual(spider["normalization"]["concentrations"], {"Cs": 0.0079, "Pb": 0.071})
            for vertex in next(point["vertices"] for point in spider["points"] if point["label"] == "M1"):
                self.assertAlmostEqual(vertex["ratio"], 10)
            normalization = spider["normalization"]["id"]
            saved = call("plot_spec.save", name="Минералы", colors={}, panels=[{
                "id": str(uuid.uuid4()), "kind": "ree_pattern", "axes": ree_axes, "normalization": normalization,
            }])["result"]
            reopened = call("plot_spec.open", id=saved["id"])["result"]
            panel, = reopened["panels"]
            self.assertEqual(panel["normalization"], normalization)
            self.assertEqual([axis["field"] for axis in panel["axes"]], ["La", "Ce", "Pr", "Nd"])
            template = call("workspace.template.save", name="Шаблон РЗЭ", plot_id=saved["id"])["result"]
            applied = call("workspace.template.apply", id=template["id"], name="Спектр из шаблона",
                           analysis_ids=reopened["input"]["analysis_ids"])["result"]
            self.assertEqual(applied["plot"]["panels"][0]["normalization"], normalization)
            projected = call("plot_data.query", kind=panel["kind"], axes=ree_axes,
                             analysis_ids=reopened["input"]["analysis_ids"], normalization=panel["normalization"])["result"]
            projected_la = next(point["vertices"][0] for point in projected["points"] if point["label"] == "M1")
            self.assertAlmostEqual(projected_la["ratio"], 2.37 / 0.687)
            invalid = call("plot_data.query", kind="ree_pattern", axes=[axes["Ce"], axes["La"]])
            self.assertEqual(invalid["error"]["code"], "INVALID_REQUEST")
            invalid = call("plot_data.query", kind="ree_pattern", axes=ree_axes, normalization="unknown")
            self.assertEqual(invalid["error"]["code"], "INVALID_REQUEST")
            alternate = root / "alternate.csv"
            alternate.write_text("Analysis,La (ppb),Ce (ppm)\nM4,2370,6.12\n", encoding="utf-8")
            self.assertIn("result", call("import.plan.apply", source_path=str(alternate), recipe=suggest_import_recipe(alternate)["recipe"]))
            combined = call("plot_data.query", kind="ree_pattern", axes=ree_axes)["result"]
            mixed = next(point["vertices"] for point in combined["points"] if point["label"] == "M4")
            self.assertEqual([vertex["measurements"][0]["unit"] for vertex in mixed[:2]], ["ppb", "ppm"])
            self.assertAlmostEqual(mixed[0]["ratio"], 10)
            self.assertAlmostEqual(mixed[1]["ratio"], 10)
            self.assertEqual(source.read_bytes(), before)

    def test_plot_coordinates_respect_units_selection_and_censored_values(self) -> None:
        from petrolab.desktop_workflow import suggest_import_recipe

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "project.sqlite")
            source = root / "plot.csv"
            source.write_text("Analysis,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),F (ppm)\n"
                              "P1,20,30,50,5\nP2,10,80,10,20\nP3,<1,5,5,2\nP4,10,-1,5,2\n", encoding="utf-8")
            source_bytes = source.read_bytes()
            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            self.assertIn("result", call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"]))
            axes = {axis["field"]: axis for axis in call("plot_data.catalog")["result"]["axes"]}
            keys = [axes[field] for field in ("SiO2", "Al2O3", "MgO")]
            incompatible = call("plot_data.query", kind="ternary", axes=[*keys[:2], axes["F"]])
            self.assertEqual(incompatible["error"]["code"], "PLOT_TERNARY_INCOMPATIBLE_AXES")
            ternary = call("plot_data.query", kind="ternary", axes=keys)["result"]
            self.assertEqual(ternary["excluded_count"], 2)
            points = {point["label"]: point for point in ternary["points"]}
            self.assertAlmostEqual(points["P1"]["u"], 0.55)
            self.assertAlmostEqual(points["P1"]["v"], 0.50)
            self.assertEqual(points["P1"]["values"], [20, 30, 50])
            binary = call("plot_data.query", kind="binary", axes=[axes["SiO2"], axes["F"]],
                          analysis_ids=[points["P1"]["analysis_id"], points["P2"]["analysis_id"]])["result"]
            self.assertEqual(binary["input_count"], 2)
            grouped = {point["label"]: point for point in binary["points"]}
            self.assertEqual([grouped["P1"]["u"], grouped["P1"]["v"]], [1, 0])
            self.assertEqual([grouped["P2"]["u"], grouped["P2"]["v"]], [0, 1])
            p2 = grouped["P2"]
            mask = {"kind": "binary", "axes": [axes["SiO2"], axes["F"]],
                    "analysis_ids": [grouped["P1"]["analysis_id"], p2["analysis_id"]]}
            hidden = call("plot_data.query", **mask, hidden_analysis_ids=[p2["analysis_id"]])["result"]
            self.assertEqual(hidden["hidden_count"], 1)
            self.assertEqual(hidden["excluded_count"], 0)
            self.assertEqual([(point["label"], point["u"], point["v"]) for point in hidden["points"]], [("P1", 0.5, 0.5)])
            source_hidden = call("plot_data.query", **mask, hidden_source_ids=[p2["source_id"]])["result"]
            self.assertEqual(source_hidden["hidden_count"], 2)
            self.assertEqual(source_hidden["points"], [])
            self.assertEqual(call("plot_data.catalog")["result"]["sources"],
                             [{"source_id": p2["source_id"], "source_name": "plot.csv"}])
            hide = call("plot_visibility.hide", analysis_ids=[p2["analysis_id"]])["result"]
            self.assertEqual(hide["category"], "view_only")
            self.assertEqual(hide["inverse_action"]["action"], "restore_plot_points")
            self.assertEqual(call("plot_visibility.restore", analysis_ids=[p2["analysis_id"]])["result"]["action"],
                             "restore_plot_points")
            session = str(uuid.uuid4())
            scope = mask["analysis_ids"]
            operation = call("plot_visibility.hide", analysis_ids=scope, session_id=session)["result"]
            self.assertEqual([item["entity_id"] for item in operation["scope"]], scope)
            undo = {"operation_id": operation["id"], "session_id": session}
            conflict = call("plot_visibility.undo", **undo, hidden_analysis_ids=scope[:1])
            self.assertEqual(conflict["error"]["details"]["analysis_ids"], scope[1:])
            self.assertEqual(call("plot_visibility.undo", **{**undo, "session_id": str(uuid.uuid4())},
                                  hidden_analysis_ids=scope)["error"]["code"], "PLOT_VISIBILITY_UNDO_UNAVAILABLE")
            later = call("plot_visibility.restore", analysis_ids=scope[1:], session_id=session)["result"]
            self.assertEqual(call("plot_visibility.undo", **undo, hidden_analysis_ids=scope)["error"]["code"],
                             "PLOT_VISIBILITY_UNDO_CONFLICT")
            inverse = call("plot_visibility.undo", **{**undo, "operation_id": later["id"]},
                           hidden_analysis_ids=scope[:1])["result"]
            self.assertEqual(inverse["parameters"]["analysis_ids"], scope[1:])
            self.assertTrue(inverse["parameters"]["hidden"])
            restored = call("operation_journal.undo", **undo, actor="QA", hidden_analysis_ids=scope)["result"]
            self.assertEqual(restored["actor"], "QA")
            self.assertEqual(restored["parameters"]["reverses_operation_id"], operation["id"])
            self.assertEqual(restored["parameters"]["analysis_ids"], scope)
            self.assertFalse(restored["parameters"]["hidden"])
            self.assertEqual(call("plot_visibility.undo", **undo, hidden_analysis_ids=[])["error"]["code"],
                             "PLOT_VISIBILITY_UNDO_UNAVAILABLE")
            self.assertEqual(call("plot_data.query", **mask)["result"], binary)
            panels = [{"id": str(uuid.uuid4()), "kind": "binary", "axes": mask["axes"]},
                      {"id": str(uuid.uuid4()), "kind": "ternary", "axes": keys}]
            saved = call("plot_spec.save", name="Две панели", analysis_ids=mask["analysis_ids"],
                         panels=panels, colors={p2["source_id"]: "#7654a3"}, hidden_analysis_ids=[p2["analysis_id"]],
                         hidden_source_ids=[p2["source_id"]])["result"]
            self.assertEqual(saved["input"]["analysis_ids"], mask["analysis_ids"])
            self.assertEqual(saved["hidden_analysis_ids"], [p2["analysis_id"]])
            self.assertEqual(saved["hidden_source_ids"], [p2["source_id"]])
            self.assertEqual(saved["legend"]["entries"][0]["color"], "#7654a3")
            self.assertEqual(saved["panels"][1]["normalization"], "sum_of_three_components")
            self.assertEqual(call("plot_spec.list")["result"], [{"id": saved["id"], "name": saved["name"]}])
            self.assertEqual(call("plot_spec.open", id=saved["id"])["result"], saved)
            field_axes = [axes["Al2O3"], axes["F"]]
            field_input = call("plot_data.query", kind="binary", axes=field_axes)["result"]
            layer = {"id": str(uuid.uuid4()), "name": "Сравнение", "analysis_ids": [
                point["analysis_id"] for point in field_input["points"] if point["label"] != "P4"],
                "show_points": False, "opacity": 0.7, "field": {"method": "convex_hull", "visible": True, "probability": None}}
            with_field = call("plot_data.query", kind="binary", axes=field_axes, layers=[layer])["result"]
            self.assertEqual(len(with_field["fields"][0]["vertices"]), 3)
            self.assertEqual(with_field["fields"][0]["analysis_ids"], layer["analysis_ids"])
            hidden_field = call("plot_data.query", kind="binary", axes=field_axes, layers=[layer],
                                hidden_analysis_ids=[p2["analysis_id"]])["result"]["fields"][0]
            self.assertEqual(hidden_field["vertices"], [])
            self.assertNotIn(p2["analysis_id"], hidden_field["analysis_ids"])
            layer["field"] = {"method": "normal_probability_ellipse", "visible": True, "probability": 0.95}
            ellipse = call("plot_data.query", kind="binary", axes=field_axes, layers=[layer])["result"]["fields"][0]
            self.assertIsNone(ellipse["message"])
            self.assertGreaterEqual(len(ellipse["vertices"]), 3)
            self.assertTrue(all(-1e-12 <= value <= 1 + 1e-12 for vertex in ellipse["vertices"] for value in vertex))
            layered = call("plot_spec.save", name="С полем", panels=panels, colors={}, layers=[layer])["result"]
            self.assertEqual(call("plot_spec.open", id=layered["id"])["result"]["layers"], [layer])
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_project_search_keeps_source_identity_and_opens_exact_analysis(self) -> None:
        from petrolab.desktop_workflow import suggest_import_recipe

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "test-project.sqlite")
            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            sources = [root / "first" / "article.csv", root / "second" / "article.csv"]
            for index, source in enumerate(sources):
                source.parent.mkdir()
                source.write_text(f"Analysis,Sample,Mineral,SiO2 (wt.%)\nP{index},KIV-{index},Апатит,40\n", encoding="utf-8")
                self.assertIn("result", call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"]))
            overview = call("project.overview")["result"]
            self.assertEqual(overview["project_name"], "test project")
            self.assertEqual(len(overview["recent_imports"]), 2)
            source_id = overview["recent_imports"][0]["source_id"]
            results = call("analysis.query", mineral="АПАТИТ", source="ARTICLE.CSV", limit=1)["result"]
            self.assertEqual(results["total"], 2)
            self.assertTrue(results["has_more"])
            narrowed = call("analysis.query", mineral="апатит", source_id=source_id)["result"]
            self.assertEqual(narrowed["total"], 1)
            hit = narrowed["analyses"][0]
            exact = call("project.analysis.get", analysis_id=hit["analysis_id"])["result"]
            self.assertEqual(exact["source_id"], source_id)
            self.assertEqual(exact["source_row_number"], hit["source_row_number"])

    def test_work_plan_rejects_stale_revision_and_keeps_task_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "test-project.sqlite")

            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            self.assertEqual(call("project.overview")["result"]["work_plan"], [])
            task = call("project.work_plan.save", title="  Проверить импорт  ", completed=False, expected_revision=0)["result"]
            self.assertEqual(task["title"], "Проверить импорт")
            revised = call("project.work_plan.save", task_id=task["id"], title="Проверить EPMA", completed=True,
                           expected_revision=task["revision"])["result"]
            self.assertEqual(revised, {"id": task["id"], "title": "Проверить EPMA", "completed": True, "revision": 2})
            stale = call("project.work_plan.save", task_id=task["id"], title="Устаревшая правка", completed=False,
                         expected_revision=task["revision"])
            self.assertEqual(stale["error"]["code"], "WORK_PLAN_TASK_CONFLICT")
            self.assertEqual(call("project.overview")["result"]["work_plan"], [revised])

    def test_publication_metadata_matches_only_analyses_with_the_same_citation(self) -> None:
        from petrolab.clean_table import classify_clean_table
        from petrolab.import_preview import inspect_source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "measurements.csv"
            original = (
                "Analysis,Mineral,SiO2 [wt.%],Publication authors,Publication year,Publication title,Publication journal,DOI,Publication URL\n"
                "P1,apatite,40,Иванов,2021,Северный массив,Journal,10.1234/apatite,https://example.org/reference\n"
                "P2,apatite,41,Петров,2022,Южный массив,Other,10.1234/other,javascript:alert(1)\n"
                "P3,olivine,42,Иванов,2021,Северный массив,Journal,10.1234/apatite,\n"
            ).encode("utf-8")
            source.write_bytes(original)

            def call(command, **payload):
                reply = handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": str(root / "project.sqlite"), **payload}})
                self.assertIn("result", reply, reply)
                return reply["result"]

            classification = classify_clean_table(inspect_source(source))
            self.assertEqual(classification["mode"], "clean_table_fast")
            call("import.plan.apply", source_path=str(source), recipe=classification["recipe"])
            for term in ("ИВАНОВ", "2021", "северный массив", "10.1234/apatite", "https://doi.org/10.1234/apatite"):
                with self.subTest(term=term):
                    result = call("analysis.query", source=term, mineral="apatite")
                    self.assertEqual([row["identity"] for row in result["analyses"]], ["P1"])
                    hit = result["analyses"][0]
                    self.assertEqual(call("analysis.query.ids", source=term, mineral="apatite")["analysis_ids"], [hit["analysis_id"]])
            metadata = {item["field"]: item for item in hit["publication_metadata"]}
            self.assertEqual(metadata["DOI"], {"field": "DOI", "value": "10.1234/apatite", "source_cell": "H2",
                                              "url": "https://doi.org/10.1234/apatite"})
            self.assertEqual(metadata["Publication year"]["value"], "2021")
            self.assertEqual(metadata["Publication URL"]["url"], "https://example.org/reference")
            other = call("analysis.query", query="Южный массив")["analyses"]
            self.assertEqual([row["identity"] for row in other], ["P2"])
            rejected = next(item for item in other[0]["publication_metadata"] if item["field"] == "Publication URL")
            self.assertEqual(rejected["value"], "javascript:alert(1)")
            self.assertIsNone(rejected["url"])
            self.assertEqual(source.read_bytes(), original)

    def test_edit_draft_detects_external_excel_change_using_original_path(self) -> None:
        from hashlib import sha256
        from io import BytesIO
        from os import name as os_name
        from zipfile import ZipFile
        from openpyxl import Workbook, load_workbook

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = str(root / "project.sqlite")
            source = root / "original.xlsx"
            staged = root / "staged.xlsx"
            workbook = Workbook()
            workbook.active.append(["Analysis", "F (wt.%)"])
            workbook.active.append(["A1", 4.5])
            workbook.active.append(["A2", 5.5])
            workbook.save(source)
            original_bytes = source.read_bytes()
            staged.write_bytes(original_bytes)

            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            opened = call("import.workspace.create", sources=[{
                "staged_path": str(staged), "original_display_path": str(source),
            }])["result"]["session"]
            self.assertIn("result", call("import.workspace.commit", workspace_id=opened["workspace_id"], expected_revision=0))
            analysis = call("project.analyses.list")["result"]["analyses"][0]
            old = analysis["measurement_list"][0]
            draft = call("edit_draft.save", measurement_id=old["measurement_id"], new_value="6.5")["result"]
            self.assertEqual(draft["changes"][0]["old_value"], "4.5")
            self.assertEqual(draft["source_fingerprint_at_start"], sha256(original_bytes).hexdigest())
            self.assertEqual(call("edit_draft.check", draft_id=draft["id"])["result"]["conflict"]["kind"], "none")

            workbook.active["B2"] = 7.5
            workbook.save(source)
            workbook.close()
            changed_bytes = source.read_bytes()
            restored = call("edit_draft.list", analysis_id=analysis["analysis_id"])["result"]["drafts"][0]["draft"]
            self.assertEqual(restored["id"], draft["id"])
            checked = call("edit_draft.check", draft_id=draft["id"])["result"]
            self.assertEqual(checked["status"], "conflict")
            self.assertEqual(checked["conflict"]["kind"], "source_changed")
            self.assertEqual(checked["conflict"]["current_source_fingerprint"], sha256(changed_bytes).hexdigest())
            self.assertEqual(checked["conflict"]["current_values"][0]["current_value"], "7.5")
            from scripts.validate_contracts import _validate
            schema = json.loads((ROOT / "schemas/edit-draft.schema.json").read_text())
            _validate(checked, schema, schema, {})
            self.assertEqual(call("edit_draft.list", analysis_id=analysis["analysis_id"])["result"]["drafts"][0]["draft"], checked)
            self.assertEqual(call("project.analyses.list")["result"]["analyses"][0]["measurement_list"][0], old)
            self.assertEqual(source.read_bytes(), changed_bytes)
            self.assertEqual(staged.read_bytes(), original_bytes)
            if os_name != "nt":
                refused = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")
                self.assertEqual(refused["error"]["code"], "EDIT_EXCLUSIVE_ACCESS_UNAVAILABLE")
                return
            refused = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")["result"]
            self.assertFalse(refused["applied"])
            self.assertEqual(refused["draft"]["conflict"]["kind"], "source_changed")
            self.assertEqual(source.read_bytes(), changed_bytes)
            self.assertEqual(list(root.glob("original.xlsx.before-edit-*.bak")), [])
            source.write_bytes(original_bytes)
            with source.open("rb"):
                locked = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")
            self.assertEqual(locked["error"]["code"], "EDIT_SOURCE_LOCKED")
            self.assertEqual(source.read_bytes(), original_bytes)

            from sqlite3 import OperationalError
            from petrolab.edit_drafts import _persist_operation, _write_content
            def interrupted_write(stream, content):
                if content == original_bytes:
                    _write_content(stream, content)
                    return
                _write_content(stream, content[:128])
                raise OSError("Injected storage failure")

            with patch("petrolab.edit_drafts._write_content", side_effect=interrupted_write):
                interrupted = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")
            self.assertEqual(interrupted["error"]["code"], "EDIT_WRITE_FAILED")
            self.assertEqual(source.read_bytes(), original_bytes)
            def interrupted_journal(connection, draft_id, entry):
                if entry["state"] == "applied":
                    raise OperationalError("Injected journal failure")
                _persist_operation(connection, draft_id, entry)

            with patch("petrolab.edit_drafts._persist_operation", side_effect=interrupted_journal):
                pending = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")["result"]
            self.assertTrue(pending["applied"])
            self.assertIn("maintenance_error", pending)
            written = source.read_bytes()
            applied = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")["result"]
            self.assertEqual(source.read_bytes(), written)
            self.assertEqual(applied["operation"]["id"], pending["operation"]["id"])
            self.assertTrue(applied["applied"])
            self.assertEqual(applied["draft"]["status"], "committed")
            operation = applied["operation"]
            journal_schema = json.loads((ROOT / "schemas/operation-journal-entry.schema.json").read_text())
            _validate(operation, journal_schema, journal_schema, {})
            self.assertEqual(operation["state"], "applied")
            self.assertEqual(Path(operation["parameters"]["backup_path"]).read_bytes(), original_bytes)
            after = source.read_bytes()
            self.assertEqual(sha256(after).hexdigest(), operation["parameters"]["after_sha256"])
            with closing(load_workbook(source)) as edited:
                self.assertEqual(edited.active["B2"].value, 6.5)
                self.assertEqual(edited.active["B3"].value, 5.5)
            with ZipFile(BytesIO(original_bytes)) as before_zip, ZipFile(BytesIO(after)) as after_zip:
                self.assertEqual(before_zip.namelist(), after_zip.namelist())
                changed_parts = [part for part in before_zip.namelist() if before_zip.read(part) != after_zip.read(part)]
                self.assertEqual(changed_parts, ["xl/worksheets/sheet1.xml"])
            again = call("edit_draft.commit", draft_id=draft["id"], actor="QA", reason="Known reference")["result"]
            self.assertEqual(again["operation"]["id"], operation["id"])
            self.assertEqual(source.read_bytes(), after)
            self.assertEqual(call("project.analyses.list")["result"]["analyses"][0]["measurement_list"][0], old)
            self.assertEqual(staged.read_bytes(), original_bytes)

    def test_table_view_round_trip_tracks_dataset_and_refuses_selection_in_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            self.assertIn("result", call("import.plan.apply", source_path=str(FIXTURE), recipe=fixture_recipe()))
            columns = [{"field": "source", "order": 0, "visible": True, "width_px": None}]
            sort = [{"field": "source", "direction": "descending"}]
            rule = {"id": str(uuid.uuid4()), "field": "column:source", "operator": "contains", "value": "test", "enabled": True}
            blocked = call("table_view.save", name="Bad", columns=columns, sort=sort,
                           filters=[{**rule, "field": "selection"}])
            self.assertEqual(blocked["error"]["code"], "INVALID_REQUEST")
            saved = call("table_view.save", name="Reviewed", columns=columns, sort=sort, filters=[rule])["result"]
            from scripts.validate_contracts import _validate
            schema = json.loads((ROOT / "schemas/table-view.schema.json").read_text())
            filter_schema = json.loads((ROOT / "schemas/analysis-filter.schema.json").read_text())
            _validate(saved, schema, schema, {"analysis-filter.schema.json": filter_schema})
            current = call("table_view.list")["result"]
            self.assertEqual(current["views"], [saved])
            self.assertEqual(current["data_universe_fingerprint"], saved["data_universe_fingerprint"])
            self.assertIn("result", call("project.last_import.retract"))
            changed = call("table_view.list")["result"]
            self.assertEqual(changed["views"], [saved])
            self.assertNotEqual(changed["data_universe_fingerprint"], saved["data_universe_fingerprint"])

    def test_selection_export_keeps_exact_ids_raw_cells_and_source_fingerprints(self) -> None:
        from hashlib import sha256
        from openpyxl import load_workbook
        from petrolab.desktop_workflow import suggest_import_recipe

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            source = root / "source.csv"
            output = root / "selection.xlsx"
            source.write_text("Analysis,F (wt.%)\n" + "".join(
                f"A{index},{'=2+3' if index == 0 else '<0.01' if index == 1 else index}\n" for index in range(20)
            ), encoding="utf-8")
            source_bytes = source.read_bytes()
            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": str(database), **payload}})

            self.assertIn("result", call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"]))
            first = call("project.analyses.list", limit=10)["result"]["analyses"]
            second = call("project.analyses.list", limit=10, offset=10)["result"]["analyses"]
            selection = [*second[2:], *first[:9]]
            ids = [analysis["analysis_id"] for analysis in selection]
            before = database.read_bytes()
            rejected = call("analysis.selection.export_xlsx", analysis_ids=[ids[0], str(uuid.uuid4())], output_path=str(output))
            self.assertEqual(rejected["error"]["code"], "EXPORT_ANALYSES_UNAVAILABLE")
            self.assertFalse(output.exists())
            exported = call("analysis.selection.export_xlsx", analysis_ids=ids, output_path=str(output))
            result = exported["result"]
            self.assertEqual(result["analysis_count"], 17)
            self.assertTrue(Path(result["output_path"]).samefile(output))
            with closing(load_workbook(output, read_only=True)) as workbook:
                analyses = list(workbook["Analyses"].values)
                by_header = [dict(zip(analyses[0], row)) for row in analyses[1:]]
                self.assertEqual([row["analysis_id"] for row in by_header], ids)
                self.assertEqual({row["source_sha256"] for row in by_header}, {sha256(source_bytes).hexdigest()})
                self.assertEqual([row["source_row_number"] for row in by_header], [row["source_row_number"] for row in selection])
                measurement_rows = list(workbook["Measurements"].iter_rows())
                headers = [cell.value for cell in measurement_rows[0]]
                cells = [{key: cell for key, cell in zip(headers, row)} for row in measurement_rows[1:]]
                formula_token = next(row for row in cells if row["raw_token"].value == "=2+3")
                self.assertEqual(formula_token["raw_token"].data_type, "s")
                censored = next(row for row in cells if row["raw_token"].value == "<0.01")
                self.assertEqual(censored["detection_limit"].value, 0.01)
                self.assertEqual(censored["source_cell"].value, "B3")
                self.assertEqual(censored["unit"].value, "wt.%")
            workbook_bytes = output.read_bytes()
            self.assertEqual(call("analysis.selection.export_xlsx", analysis_ids=ids, output_path=str(output))["error"]["code"], "EXPORT_FILE_EXISTS")
            self.assertEqual(output.read_bytes(), workbook_bytes)
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_work_group_keeps_exact_order_and_retracted_members_in_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": database, **payload}})

            self.assertIn("result", call("import.plan.apply", source_path=str(FIXTURE), recipe=fixture_recipe()))
            analyses = call("project.analyses.list")["result"]["analyses"]
            ids = [analyses[2]["analysis_id"], analyses[0]["analysis_id"]]
            rejected = call("work_group.create", name="Invalid", created_by="QA", analysis_ids=[ids[0], str(uuid.uuid4())])
            self.assertEqual(rejected["error"]["code"], "WORK_GROUP_ANALYSES_UNAVAILABLE")
            self.assertEqual(call("work_group.list")["result"]["groups"], [])

            group = call("work_group.create", name="Published cohort", created_by="QA", analysis_ids=ids)["result"]
            self.assertEqual(group["analysis_ids"], ids)
            from scripts.validate_contracts import _validate
            schema = json.loads((ROOT / "schemas/work-group.schema.json").read_text())
            _validate(group, schema, schema, {})
            self.assertEqual(call("work_group.list")["result"]["groups"], [
                {"group": group, "unavailable_analysis_ids": []},
            ])
            self.assertIn("result", call("project.last_import.retract"))
            self.assertEqual(call("work_group.list")["result"]["groups"], [
                {"group": group, "unavailable_analysis_ids": ids},
            ])

    def test_failed_migration_reports_backup_in_protocol(self) -> None:
        from petrolab.import_apply import MIGRATIONS, open_project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            with closing(open_project(database)):
                pass
            migrations = root / "migrations"
            migrations.mkdir()
            for file in MIGRATIONS.glob("*.sql"):
                shutil.copyfile(file, migrations / file.name)
            next_version = 1 + max(int(path.name.split("_", 1)[0]) for path in migrations.glob("*.sql"))
            broken = f"{next_version:04d}_broken.sql"
            (migrations / broken).write_text("CREATE TABLE rollback_me (id INTEGER); INVALID SQL;", encoding="utf-8")
            with patch("petrolab.import_apply.MIGRATIONS", migrations):
                response = handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                                           "command": "project.analyses.list", "payload": {"project_database_path": str(database)}})
            self.assertEqual(response["error"]["code"], "PROJECT_MIGRATION_FAILED")
            self.assertEqual(response["error"]["details"]["migration"], broken)
            self.assertTrue(Path(response["error"]["details"]["backup_path"]).is_file())

    def test_newer_project_returns_actionable_error_without_changes(self) -> None:
        from petrolab.import_apply import open_project
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "future.sqlite"
            with closing(open_project(database)) as connection:
                connection.execute("INSERT INTO schema_migration VALUES (?, ?)", (999, "future"))
                connection.commit()
            before = database.read_bytes()
            response = handle_request({
                "protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                "command": "project.analyses.list",
                "payload": {"project_database_path": str(database), "limit": 10},
            })
            self.assertEqual(response["error"]["code"], "PROJECT_SCHEMA_UNSUPPORTED")
            self.assertEqual(response["error"]["details"]["unsupported_migrations"], [999])
            self.assertEqual(database.read_bytes(), before)

    def test_command_result_is_versioned_and_correlated(self) -> None:
        response = handle_request({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "command": "import.inspect_source",
            "payload": {"source_path": str(FIXTURE)},
        })
        self.assertIsNotNone(uuid.UUID(response["request_id"]))
        self.assertEqual(response["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(response["result"]["source_fingerprint"], inspect_source(FIXTURE).fingerprint)

    def test_error_is_structured_and_request_id_is_preserved(self) -> None:
        response = handle_request({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "command": "import.recipe.validate",
            "payload": {"source_path": str(FIXTURE), "recipe": {}},
        })
        self.assertIsNotNone(uuid.UUID(response["request_id"]))
        self.assertEqual(response["error"]["code"], "RECIPE_SCHEMA_INCOMPATIBLE")

    def test_protocol_unknown_command_and_invalid_request_do_not_raise(self) -> None:
        request_id = str(uuid.uuid4())
        self.assertEqual(handle_request({"protocol_version": "2.0", "request_id": request_id, "command": "import.inspect_source", "payload": {}})["error"]["code"], "PROTOCOL_VERSION_UNSUPPORTED")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": request_id, "command": "plot.query", "payload": {}})["error"]["code"], "UNKNOWN_COMMAND")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": request_id, "command": "import.inspect_source"})["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(handle_request({"protocol_version": "1.0", "request_id": "not-a-uuid", "command": "import.inspect_source"})["error"]["code"], "INVALID_REQUEST")

    def test_stream_writes_one_json_response_per_line_and_shutdowns(self) -> None:
        input_stream = io.StringIO("\n".join([
            json.dumps({"protocol_version": "1.0", "request_id": "6b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "import.plan.create", "payload": {"source_path": str(FIXTURE), "recipe": fixture_recipe()}}),
            json.dumps({"protocol_version": "1.0", "request_id": "7b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "shutdown", "payload": {}}),
        ]) + "\n")
        output_stream = io.StringIO()
        serve(input_stream, output_stream)
        responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["result"]["summary"]["planned_analysis_count"], 8)
        self.assertEqual(responses[1], {"protocol_version": "1.0", "request_id": "7b178581-aa86-4bb1-9742-4fd5324c22ed", "result": {"status": "shutting_down"}})

    def test_shutdown_obeys_protocol_version(self) -> None:
        input_stream = io.StringIO(json.dumps({"protocol_version": "2.0", "request_id": "8b178581-aa86-4bb1-9742-4fd5324c22ed", "command": "shutdown", "payload": {}}) + "\n")
        output_stream = io.StringIO()
        serve(input_stream, output_stream)
        response = json.loads(output_stream.getvalue())
        self.assertEqual(response["request_id"], "8b178581-aa86-4bb1-9742-4fd5324c22ed")
        self.assertEqual(response["error"]["code"], "PROTOCOL_VERSION_UNSUPPORTED")

    def test_apply_and_linked_source_check_are_available_through_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            response = handle_request({
                "protocol_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "command": "import.plan.apply",
                "payload": {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()},
            })
            self.assertEqual(response["result"]["analysis_count"], 8)
            status = handle_request({
                "protocol_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "command": "source.check_linked",
                "payload": {"project_database_path": database, "source_id": response["result"]["source_id"]},
            })
            self.assertEqual(status["result"]["state"], "current")

    def test_recipe_revision_is_saved_as_a_new_transport_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "project.sqlite")
            imported = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "import.plan.apply",
                "payload": {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()},
            })["result"]
            revised = fixture_recipe()
            revised["global_decisions"]["duplicate_policy"] = "keep_all"
            from test_import_preview import refresh_recipe_fingerprint
            refresh_recipe_fingerprint(revised)
            response = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "import.recipe.save_revision",
                "payload": {
                    "project_database_path": database, "source_id": imported["source_id"], "recipe": revised,
                    "supersedes_recipe_revision_id": imported["recipe_revision_id"],
                },
            })
            self.assertEqual(response["result"]["supersedes_recipe_revision_id"], imported["recipe_revision_id"])

    def test_saved_legacy_recipe_reopens_with_exact_semantics_or_rejects_changed_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"
            legacy = fixture_recipe()

            def call(command, **payload):
                return handle_request({"protocol_version": PROTOCOL_VERSION, "request_id": str(uuid.uuid4()),
                    "command": command, "payload": {"project_database_path": str(database), **payload}})

            def candidate(name, old, new):
                target = root / name
                with ZipFile(FIXTURE) as source, ZipFile(target, "w") as output:
                    for member in source.infolist():
                        content = source.read(member)
                        if member.filename == "xl/worksheets/sheet2.xml":
                            self.assertIn(old, content)
                            content = content.replace(old, new, 1)
                        output.writestr(member, content)
                return target

            imported = call("import.plan.apply", source_path=str(FIXTURE), recipe=legacy)["result"]
            revision = imported["recipe_revision_id"]
            stored_bytes = database.read_bytes()
            original_bytes = FIXTURE.read_bytes()
            reopened = call("import.recipe.open_revision", source_path=str(FIXTURE), recipe_revision_id=revision)["result"]
            self.assertEqual(reopened["status"], "review_required")
            self.assertEqual(reopened["issue"]["code"], "DUPLICATE_REVIEW_REQUIRED")
            self.assertEqual(reopened["recipe"], {**legacy, "schema_version": 2})
            self.assertEqual(reopened["migration_report"]["report_version"], 1)
            self.assertEqual(reopened["migration_report"]["from_schema_version"], 1)
            self.assertEqual(reopened["migration_report"]["to_schema_version"], 2)
            self.assertEqual(reopened["migration_report"]["dropped_fields"], [])
            self.assertEqual(reopened["semantic_fingerprint"], legacy["semantic_fingerprint"])
            self.assertEqual(call("import.plan.apply", source_path=str(FIXTURE),
                                  recipe=reopened["recipe"])["error"]["code"], "DUPLICATE_REVIEW_REQUIRED")

            compatible = candidate("compatible.xlsx", b'>18.2</x:v>', b'>19.2</x:v>')
            rebinding = call("import.recipe.open_revision", source_path=str(compatible), recipe_revision_id=revision)["result"]
            self.assertEqual(rebinding["status"], "review_required")
            self.assertEqual(rebinding["recipe"], {**legacy, "schema_version": 2,
                "source_file_sha256": inspect_source(compatible).fingerprint})
            self.assertEqual(rebinding["semantic_fingerprint"], legacy["semantic_fingerprint"])
            changed = candidate("changed.xlsx", b'Li (ppm)', b'Li (ppb)')
            rejected = call("import.recipe.open_revision", source_path=str(changed), recipe_revision_id=revision)["result"]
            self.assertEqual(rejected["status"], "incompatible")
            self.assertIsNone(rejected["recipe"])
            self.assertEqual(rejected["issue"]["details"]["sheets"], ["Trace_elements"])
            self.assertEqual(rejected["migration_report"]["dropped_fields"], [])
            self.assertEqual(database.read_bytes(), stored_bytes)
            self.assertEqual(FIXTURE.read_bytes(), original_bytes)

            unsupported = call("import.plan.apply", source_path=str(FIXTURE), recipe={**legacy, "schema_version": 3})
            self.assertEqual(unsupported["error"]["code"], "RECIPE_VERSION_UNSUPPORTED")

            reviewed = call("import.recipe.review_duplicates", source_path=str(compatible),
                            recipe=rebinding["recipe"], decision="keep_all")["result"]["recipe"]
            applied = call("import.plan.apply", source_path=str(compatible), recipe=reviewed)["result"]
            self.assertEqual(applied["analysis_count"], 8)
            current = call("import.recipe.open_revision", source_path=str(compatible),
                           recipe_revision_id=applied["recipe_revision_id"])["result"]
            self.assertEqual(current["status"], "compatible")
            self.assertEqual(current["recipe"], reviewed)
            self.assertEqual(current["migration_report"]["changes"], [])
            bound = call("import.recipe.open_revision", source_path=str(FIXTURE),
                         recipe_revision_id=applied["recipe_revision_id"])["result"]
            self.assertEqual(bound["status"], "incompatible")
            self.assertIsNone(bound["recipe"])
            self.assertEqual(bound["issue"]["details"]["blocked_fields"], ["global_decisions.duplicate_review"])

    def test_media_inspection_and_point_placement_are_available_through_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            database = str(directory / "project.sqlite")
            imported = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "import.plan.apply",
                "payload": {"project_database_path": database, "source_path": str(FIXTURE), "recipe": fixture_recipe()},
            })["result"]
            import sqlite3
            with closing(sqlite3.connect(database)) as connection:
                analysis_ids = [row[0] for row in connection.execute("SELECT analysis_id FROM analysis ORDER BY rowid LIMIT 2")]
            point = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "analytical_point.create",
                "payload": {"project_database_path": database, "sample_name": "KIV-2", "point_name": "P-07", "analysis_ids": analysis_ids, "link_type": "same_point"},
            })["result"]
            image = directory / "KIV-2_BSE.png"
            write_png(image)
            inspection = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "media.inspect_sources",
                "payload": {"source_paths": [str(image)]},
            })["result"]
            self.assertEqual(inspection["items"][0]["width_px"], 12)
            assignments = [{
                "source_path": str(image), "ownership_mode": "managed_copy", "media_type": "BSE",
                "sample_name": "KIV-2", "thin_section_name": "KIV-2-TS1",
                "placements": [{
                    "analytical_point_id": point["analytical_point_id"],
                    "geometry": {"kind": "point", "x_px": 3, "y_px": 4},
                    "cross_sample_exception_reason": None,
                }],
            }]
            plan = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "media.import.plan",
                "payload": {"project_database_path": database, "assignments": assignments},
            })["result"]
            applied = handle_request({
                "protocol_version": "1.0", "request_id": str(uuid.uuid4()), "command": "media.import.apply",
                "payload": {"project_database_path": database, "plan": plan},
            })["result"]
            self.assertEqual(applied["spatial_annotation_count"], 1)


if __name__ == "__main__":
    unittest.main()
