import unittest
from math import log, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np

from petrolab.statistics_core import fit_kmeans, pca_projection, review_feature_domains, scale_values, transform_values
from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.ndjson_service import handle_request


def feature(field, unit, method=None):
    return {"field": field, "unit": unit, "method": method, "measurement_set": None}


class StatisticsCoreTests(unittest.TestCase):
    def test_clr_and_ilr_exact_two_part_reference_and_scale_invariance(self):
        result = transform_values([[1, 4], [3, 12]], "clr")
        np.testing.assert_allclose(result, [[-log(2), log(2)]] * 2)
        ilr = transform_values([[1, 4], [4, 1]], "ilr")
        np.testing.assert_allclose(ilr, [[-sqrt(2) * log(2)], [sqrt(2) * log(2)]])
        with self.assertRaises(ValueError):
            transform_values([[0, 4]], "clr")
        self.assertEqual(pca_projection(ilr)["projection"][0][1], 0.5)

    def test_semantic_domains_distinguish_oxide_trace_and_index(self):
        oxide = [feature("SiO2", "wt.%"), feature("MgO", "wt.%")]
        self.assertTrue(review_feature_domains(oxide)["logratio_available"])
        mixed = review_feature_domains(oxide + [feature("La", "ppm"), feature("Mg#", "ratio"), feature("Fe", "apfu")])
        self.assertEqual(mixed["domains"], ["oxide_wt_percent", "oxide_wt_percent", "trace_concentration", "ratio_or_index", "apfu"])
        self.assertFalse(mixed["logratio_available"])
        self.assertTrue(mixed["euclidean_available"])
        self.assertFalse(review_feature_domains([feature("La", "ppm"), feature("Ce", "ppb")])["logratio_available"])
        self.assertFalse(review_feature_domains([feature("FeO", "wt.%"), feature("FeOt", "wt.%")])["logratio_available"])

    def test_seeded_clusters_match_independent_centers_and_inertia(self):
        data = np.array([[0, 0], [0, 2], [10, 10], [10, 12]], dtype=float)
        initial = fit_kmeans(data, 2, 42)
        self.assertEqual(initial["labels"], [0, 0, 1, 1])
        self.assertEqual(initial["centers"], [[0.0, 1.0], [10.0, 11.0]])
        self.assertEqual(initial["inertia"], 4.0)
        self.assertEqual(fit_kmeans(data, 2, 42), initial)
        scaled, parameters = scale_values(data, "standard")
        self.assertEqual(parameters["center"], [5.0, 6.0])
        np.testing.assert_allclose(parameters["scale"], [5.0, sqrt(26)])
        np.testing.assert_allclose(scaled.mean(axis=0), [0, 0], atol=1e-14)
        one_line = pca_projection(np.array([[-2., 0], [0., 0], [2., 0]]))
        np.testing.assert_allclose(one_line["projection"], [[0.0, 0.5], [0.5, 0.5], [1.0, 0.5]])
        self.assertEqual(one_line["explained_variance_ratio"], [1.0, 0.0])

    def test_review_run_cluster_snapshot_and_stale_provenance(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "stats.csv"
            database = Path(directory) / "project.sqlite"
            csv = "Analysis,SiO2 [wt.%],Al2O3 [wt.%],La [ppm]\nA,1,2,2\nB,2,3,4\nC,20,40,5\nD,21,41,6\nE,<1,2,5\nF,0,3,5\n"
            source.write_text(csv, encoding="utf-8")

            def call(command, **parameters):
                return handle_request({"protocol_version": "1.0", "request_id": str(uuid4()), "command": command,
                    "payload": {"project_database_path": str(database), **parameters}})

            self.assertIn("result", call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"]))
            listed = call("project.analyses.list")["result"]["analyses"]
            ids = [row["analysis_id"] for row in listed]
            group = call("work_group.create", name="Исходные анализы", analysis_ids=ids, created_by="Иванов")["result"]
            incoming = {"kind": "work_group", "work_group_id": group["id"]}
            parameters = {"transform": "ilr", "scaling": "none", "clusters": 2, "seed": 42}
            axes = {item["field"]: item for item in call("plot_data.catalog")["result"]["axes"]}
            mixed = [axes["SiO2"], axes["La"]]
            review = call("statistics.review", input=incoming, features=mixed)["result"]
            self.assertFalse(review["domain"]["logratio_available"])
            rejected = call("statistics.cluster.run", input=incoming, features=mixed,
                            review_fingerprint=review["input_fingerprint"], parameters=parameters)
            self.assertEqual(rejected["error"]["code"], "STATISTICS_MIXED_COMPOSITION_DOMAIN")
            features = [axes["SiO2"], axes["Al2O3"]]
            review = call("statistics.review", input=incoming, features=features)["result"]
            self.assertTrue(review["domain"]["logratio_available"])
            self.assertEqual(review["positive_complete_count"], 4)
            self.assertEqual({item["reason"] for item in review["logratio_excluded"]}, {"censored", "zero"})
            request = {"input": incoming, "features": features, "review_fingerprint": review["input_fingerprint"]}
            first = call("statistics.cluster.run", **request, parameters=parameters)["result"]
            self.assertEqual(first["input"]["analysis_ids"], ids)
            self.assertEqual(len(first["result_manifest"]["members"]), 4)
            cluster_ids = [item["analysis_id"] for item in first["result_manifest"]["members"] if item["cluster"] == 0]
            saved = call("statistics.cluster.save_group", run_id=first["id"], cluster=0, name="Кластер 1", actor="Иванов")["result"]
            self.assertEqual(saved["analysis_ids"], cluster_ids)
            self.assertEqual(saved["calculation_origin"]["calculation_run_id"], first["id"])
            second = call("statistics.cluster.run", **request, parameters={**parameters, "transform": "euclidean", "scaling": "standard"})["result"]
            self.assertEqual(second["input_fingerprint"], first["input_fingerprint"])
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(call("statistics.run.open", run_id=first["id"])["result"], first)
            self.assertIn(saved, [item["group"] for item in call("work_group.list")["result"]["groups"]])
            panels = [{"id": str(uuid4()), "kind": "binary", "axes": features} for _ in range(3)]
            plot = call("plot_spec.save", name="Три панели", analysis_ids=ids, panels=panels, colors={})["result"]
            template = call("workspace.template.save", name="Диаграммы оксидов", plot_id=plot["id"])["result"]
            encoded_template = repr(template)
            self.assertTrue(all(identifier not in encoded_template for identifier in ids + [listed[0]["source_id"]]))
            applied = call("workspace.template.apply", id=template["id"], name="Панели для двух анализов", analysis_ids=ids[2:4])["result"]
            self.assertEqual(applied["plot"]["input"]["analysis_ids"], ids[2:4])
            self.assertEqual(len(applied["plot"]["panels"]), 3)
            self.assertTrue(all(item["action"] == "unchanged" for item in applied["migration_report"]))
            view = call("table_view.save", name="Рабочая таблица",
                        columns=[{"field": "source", "order": 0, "visible": True, "width_px": None}],
                        sort=[{"field": "source", "direction": "ascending"}], filters=[])["result"]
            filtered = call("table_view.save", name="Исходный фильтр",
                            columns=[{"field": field, "order": index, "visible": True, "width_px": None}
                                     for index, field in enumerate(["source", "identity:Analysis", "measurement:SiO2", "generation"])],
                            sort=[{"field": "measurement:SiO2", "direction": "descending"}],
                            filters=[{"id": str(uuid4()), "field": "source", "operator": "equals",
                                      "value": listed[0]["source_id"], "enabled": True}])["result"]
            portable = call("workspace.template.save", name="Рабочий способ", plot_id=plot["id"],
                            table_view_id=filtered["id"], calculation_run_id=first["id"])["result"]
            self.assertEqual(portable["schema_version"], 2)
            self.assertTrue(portable["table_filters_omitted"])
            self.assertTrue(all(identifier not in repr(portable) for identifier in ids + [
                listed[0]["source_id"], first["id"], filtered["id"], group["id"]]))
            target_ids = [item["analysis_id"] for item in first["result_manifest"]["members"]][:2]
            preview = call("workspace.template.apply", id=portable["id"], analysis_ids=target_ids)["result"]
            self.assertIsNone(preview["plot"])
            self.assertIsNone(preview["table_view"])
            self.assertEqual(preview["method_plans"][0]["input"]["analysis_ids"], target_ids)
            self.assertTrue(any(entry["action"] == "omitted" for entry in preview["migration_report"]))
            applied_all = call("workspace.template.apply", id=portable["id"], analysis_ids=target_ids,
                               name="Другой набор")["result"]
            self.assertEqual(applied_all["plot"]["input"]["analysis_ids"], target_ids)
            self.assertEqual(applied_all["table_view"]["sort"], filtered["sort"])
            self.assertEqual(applied_all["table_view"]["columns"], filtered["columns"])
            self.assertEqual(applied_all["table_view"]["filters"], [])
            self.assertEqual(applied_all["method_plans"][0]["parameters"], parameters)
            self.assertEqual(len(call("statistics.runs.list")["result"]), 2)
            rerun = call("statistics.cluster.run", **applied_all["method_plans"][0])["result"]
            self.assertEqual(rerun["input"]["analysis_ids"], target_ids)
            self.assertNotEqual(rerun["id"], first["id"])
            conflict = call("workspace.template.apply", id=portable["id"], analysis_ids=target_ids, name="Рабочая таблица")
            self.assertEqual(conflict["error"]["code"], "TABLE_VIEW_NAME_EXISTS")
            self.assertNotIn("Рабочая таблица", [item["name"] for item in call("plot_spec.list")["result"]])
            too_few = call("workspace.template.apply", id=portable["id"], analysis_ids=target_ids[:1], name="Один")["result"]
            self.assertIsNone(too_few["plot"])
            self.assertIsNone(too_few["table_view"])
            self.assertTrue(any(entry["field"] == "method_templates" and entry["action"] == "blocked"
                                for entry in too_few["migration_report"]))
            table_only = call("workspace.template.save", name="Только таблица", table_view_id=view["id"])["result"]
            self.assertEqual(table_only["requirements"], [])
            table_applied = call("workspace.template.apply", id=table_only["id"], analysis_ids=target_ids,
                                 name="Колонки без диаграмм")["result"]
            self.assertIsNone(table_applied["plot"])
            self.assertEqual(table_applied["table_view"]["columns"], view["columns"])
            state = {"data_universe": {"dataset_ids": [], "work_group_ids": [group["id"]], "analysis_ids": ids},
                     "table_view_id": view["id"], "plot_specification_ids": [plot["id"]],
                     "source_visibility": [{"source_id": listed[0]["source_id"], "visible": False}],
                     "selection_restore_policy": "restore_exact_if_available", "selection_analysis_ids": ids[:2],
                     "active_calculation_run_id": second["id"], "active_surface": "statistics"}
            snapshot = call("workspace.snapshot.save", name="Утренний расчёт", state=state)["result"]
            self.assertEqual(call("workspace.snapshot.open", id=snapshot["id"])["result"],
                             {"snapshot": snapshot, "migration_report": []})
            self.assertIn("result", call("project.last_import.retract"))
            blocked = call("workspace.snapshot.open", id=snapshot["id"])["result"]
            self.assertIsNone(blocked["snapshot"])
            unavailable_axes = call("workspace.template.apply", id=template["id"], name="Недоступно", analysis_ids=ids[2:4])["result"]
            self.assertIsNone(unavailable_axes["plot"])
            self.assertTrue(all(item["action"] == "blocked" for item in unavailable_axes["migration_report"]))
            self.assertEqual({entry["field"] for entry in blocked["migration_report"]},
                             {"analysis_ids", "work_group_ids", "table_view_id", "plot_specification_ids", "active_calculation_run_id"})
            stale = call("statistics.run.open", run_id=first["id"])["result"]
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["result_manifest"], first["result_manifest"])
            self.assertEqual(source.read_text(encoding="utf-8"), csv)

    def test_workspace_template_uses_explicit_plot_context_for_shared_table_field(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "project.sqlite"

            def call(command, **payload):
                return handle_request({"protocol_version": "1.0", "request_id": str(uuid4()), "command": command,
                    "payload": {"project_database_path": str(database), **payload}})

            source_ids = []
            for name, unit in (("original", "wt.%"), ("target", "wt.%"), ("different", "ppm")):
                source = root / f"{name}.csv"
                source.write_text(f"Analysis,SiO2 [{unit}],Al2O3 [{unit}]\n{name},10,20\n", encoding="utf-8")
                imported = call("import.plan.apply", source_path=str(source), recipe=suggest_import_recipe(source)["recipe"])["result"]
                source_ids.append(imported["source_id"])
            analyses = {row["source_id"]: row["analysis_id"] for row in call("project.analyses.list")["result"]["analyses"]}
            original, target, different = ([analyses[item]] for item in source_ids)
            axes = call("plot_data.catalog", analysis_ids=original)["result"]["axes"]
            panels = [{"id": str(uuid4()), "kind": "binary", "axes": axes}]
            plot = call("plot_spec.save", name="Исходный график", analysis_ids=original, panels=panels, colors={})["result"]
            columns = [{"field": field, "order": index, "visible": True, "width_px": None}
                       for index, field in enumerate(["generation", "measurement:SiO2"])]
            table = call("table_view.save", name="Таблица", columns=columns,
                         sort=[{"field": "generation", "direction": "ascending"}], filters=[])["result"]
            ambiguous = call("workspace.template.save", name="Табличный шаблон", table_view_id=table["id"])
            self.assertEqual(ambiguous["error"]["code"], "TEMPLATE_FIELD_AMBIGUOUS")
            template = call("workspace.template.save", name="Контекст графика", plot_id=plot["id"],
                            table_view_id=table["id"])["result"]
            self.assertEqual(call("workspace.template.list")["result"], [{"id": template["id"], "name": template["name"]}])
            before = database.read_bytes()
            rejected = call("workspace.template.apply", id=template["id"], analysis_ids=different, name="Отказ")["result"]
            self.assertIsNone(rejected["plot"])
            self.assertIsNone(rejected["table_view"])
            self.assertEqual({item["field"] for item in rejected["migration_report"]
                              if item["action"] == "blocked" and "wt.%" in item["reason"] and "ppm" in item["reason"]},
                             {"SiO2", "Al2O3"})
            self.assertEqual(database.read_bytes(), before)
            applied = call("workspace.template.apply", id=template["id"], analysis_ids=target, name="Новая раскладка")["result"]
            self.assertEqual(applied["plot"]["input"]["analysis_ids"], target)
            self.assertEqual(applied["table_view"]["columns"], columns)
