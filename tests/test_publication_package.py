from hashlib import sha256
import csv
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe
from petrolab.formula_service import review_formula, run_formula
from petrolab.import_apply import apply_import_plan
from petrolab.import_preview import ImportCommandError
from petrolab.mineral_formulae import PYROXENE
from petrolab.ndjson_service import handle_request
from petrolab.plot_data import open_plot_specification, plot_catalog, query_plot_data, save_plot_specification
from petrolab.publication import capture_publication_plot, export_publication, prepare_publication
from petrolab.work_groups import create_work_group


class PublicationPackageTests(unittest.TestCase):
    def test_ternary_apfu_reopens_exact_formulae_and_reports_stale_runs(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'pyroxene.csv'
            database = root / 'project.sqlite'
            source.write_text('Analysis,SiO2 [wt.%],TiO2 [wt.%],Al2O3 [wt.%],Cr2O3 [wt.%],FeO [wt.%],MgO [wt.%],CaO [wt.%],Na2O [wt.%],K2O [wt.%]\n'
                              'Opx,52.43,0.21,9.10,0.65,6.73,30.39,1.19,0.06,0\n'
                              'Cpx,50.00,0.48,8.39,0.62,5.78,19.00,14.79,0.20,0.02\n'
                              'Uncalculated,50,0,0,0,10,24,10,0,0\n', encoding='utf-8')
            original = source.read_bytes()
            apply_import_plan(database, source, suggest_import_recipe(source)['recipe'])
            analyses = {row['identity']['Analysis']: row for row in list_project_analyses(database)['analyses']}

            def calculate(label):
                row = analyses[label]
                inputs = (database, PYROXENE['method_id'], row['analysis_id'], [m['measurement_id'] for m in row['measurement_list']])
                review = review_formula(*inputs)
                return run_formula(*inputs, review['input_fingerprint'], review['method_definition_fingerprint'])

            opx, cpx = calculate('Opx'), calculate('Cpx')
            newer_opx = calculate('Opx')
            binding = {'version': 1, 'method_id': opx['method_id'], 'method_version': opx['method_version'],
                       'method_definition_fingerprint': opx['method_definition_fingerprint'], 'run_ids': [opx['id'], cpx['id']]}
            axes = [{'field': f'apfu.{element}', 'unit': 'APFU', 'method': None, 'measurement_set': None, 'formula': binding}
                    for element in ('Mg', 'Fe2+', 'Ca')]

            def call(command, **parameters):
                return handle_request({'request_id': str(uuid4()), 'protocol_version': '1.0', 'command': command,
                                       'payload': {'project_database_path': str(database), **parameters}})

            catalog = call('plot_data.catalog', include_formula=True)['result']
            group, = catalog['formula_series']
            self.assertEqual(group['oxygen_basis'], 6)
            self.assertCountEqual([run['run_id'] for run in group['runs']], [opx['id'], cpx['id'], newer_opx['id']])
            scoped = call('plot_data.catalog', include_formula=True, analysis_ids=[cpx['analysis_id']])['result']
            self.assertEqual([run['run_id'] for run in scoped['formula_series'][0]['runs']], [cpx['id']])
            projection = call('plot_data.query', kind='ternary', axes=axes)['result']
            self.assertEqual([item['reason'] for item in projection['exclusions']], ['formula_run_missing'])
            points = {point['label']: point for point in projection['points']}
            for label, run, wo, fs in [('Opx', opx, 2.45, 10.79), ('Cpx', cpx, 32.34, 9.87)]:
                point = points[label]
                self.assertAlmostEqual(point['u'], (fs + wo / 2) / 100, delta=.002)
                self.assertAlmostEqual(point['v'], wo / 100, delta=.002)
                self.assertEqual({item['run_id'] for item in point['axis_inputs']}, {run['id']})
                self.assertEqual(point['axis_inputs'][0]['input_measurement_ids'], run['input_measurement_ids'])
                self.assertEqual(point['axis_inputs'][0]['oxygen_basis'], 6)
            measured_mg = next(axis for axis in catalog['axes'] if axis['field'] == 'MgO')
            binary = query_plot_data(database, 'binary', [axes[0], measured_mg], [cpx['analysis_id']])
            binary_point, = binary['points']
            self.assertAlmostEqual(binary_point['values'][0], 1.03, delta=.01)
            self.assertEqual(binary_point['values'][1], 19)
            missing = query_plot_data(database, 'binary', [{**axes[0], 'field': 'apfu.Zr'}, measured_mg], [cpx['analysis_id']])
            self.assertEqual(missing['exclusions'][0]['reason'], 'formula_component_missing')
            altered = {**axes[2], 'formula': {**binding, 'run_ids': [newer_opx['id'], cpx['id']]}}
            with self.assertRaises(ImportCommandError) as incompatible:
                query_plot_data(database, 'ternary', [*axes[:2], altered])
            self.assertEqual(incompatible.exception.code, 'PLOT_TERNARY_INCOMPATIBLE_AXES')
            duplicates = [{**axis, 'formula': {**binding, 'run_ids': [*binding['run_ids'], newer_opx['id']]}} for axis in axes]
            with self.assertRaises(ImportCommandError) as ambiguous:
                query_plot_data(database, 'ternary', duplicates)
            self.assertEqual(ambiguous.exception.code, 'PLOT_FORMULA_AMBIGUOUS')
            panel = {'id': str(uuid4()), 'kind': 'ternary', 'axes': axes}
            spec = save_plot_specification(database, 'Пироксены APFU', None, [panel], {}, [], [])
            self.assertEqual(open_plot_specification(database, spec['id']), spec)
            capture = {'name': 'APFU', 'format': 'svg', 'width_mm': 90, 'dpi': 600, 'include_csv': True,
                       'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g><text x="1" y="2">APFU</text></g></svg>',
                       'analysis_ids': None, 'hidden_analysis_ids': [], 'hidden_source_ids': [], 'layers': [], 'colors': {},
                       'panels': [{**panel, 'projection_sha256': projection['projection_sha256']}]}
            item = capture_publication_plot(database, capture, 'APFU')
            prepared = prepare_publication(database, 'Пироксены', [item])
            destination = root / 'pyroxene.zip'
            export_publication(database, 'Пироксены', [item], prepared['fingerprint'], str(destination))
            with ZipFile(destination) as archive:
                saved, = json.loads(archive.read('materials/01-plot_capture.json'))['panels']
                self.assertEqual(saved['axes'], axes)
                self.assertEqual(saved['points'], projection['points'])
                self.assertEqual(saved['exclusions'], projection['exclusions'])
            with patch.dict(PYROXENE, version='changed'):
                stale = query_plot_data(database, 'ternary', axes)
                self.assertEqual(stale['points'], [])
                self.assertCountEqual([row['reason'] for row in stale['exclusions']],
                                      ['formula_run_stale', 'formula_run_stale', 'formula_run_missing'])
                failed_run = next(row for row in stale['exclusions'] if row['reason'] == 'formula_run_stale')
                self.assertEqual(failed_run['axes'][0]['stale_reasons'], ['method_changed'])
                self.assertEqual(open_plot_specification(database, spec['id']), spec)
                with self.assertRaises(ImportCommandError) as changed:
                    prepare_publication(database, 'Пироксены', [item])
                self.assertEqual(changed.exception.code, 'PUBLICATION_PLOT_CHANGED')
            self.assertEqual(source.read_bytes(), original)

    def test_calculated_ternary_keeps_afm_arithmetic_inputs_and_exclusions(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / 'project.sqlite'
            source = root / 'afm.csv'
            source.write_text('Analysis,Na2O [wt.%],K2O [wt.%],FeOt [wt.%],MgO [wt.%]\n'
                              'P1,2,3,15,30\nP2,<DL,3,15,30\nP3,0,0,0,0\nP4,2,3,15,-1\n', encoding='utf-8')
            original = source.read_bytes()
            apply_import_plan(database, source, suggest_import_recipe(source)['recipe'])
            catalog = {axis['field']: axis for axis in plot_catalog(database)['axes']}
            alkalis = {**catalog['Na2O'], 'field': 'Na2O + K2O', 'calculation': {
                'operation': 'sum', 'version': 1, 'operands': [catalog['Na2O'], catalog['K2O']]}}
            axes = [alkalis, catalog['FeOt'], catalog['MgO']]
            projection = query_plot_data(database, 'ternary', axes)
            point, = projection['points']
            self.assertEqual(point['values'], [5, 15, 30])
            self.assertAlmostEqual(point['u'], .6)
            self.assertAlmostEqual(point['v'], .6)
            self.assertCountEqual([row['reason'] for row in projection['exclusions']],
                                  ['below_detection_limit', 'zero_component_sum', 'negative_component'])
            self.assertEqual([row['raw_token'] for row in point['axis_inputs'][0]['measurements']], ['2', '3'])
            self.assertEqual(point['axis_inputs'][1]['measurements'][0]['reported_fe_form'], 'FeOt')
            with self.assertRaises(ImportCommandError) as invalid:
                query_plot_data(database, 'ternary', [alkalis, catalog['K2O'], catalog['MgO']])
            self.assertEqual(invalid.exception.code, 'PLOT_TERNARY_INCOMPATIBLE_AXES')
            panel = {'id': str(uuid4()), 'kind': 'ternary', 'axes': axes}
            spec = save_plot_specification(database, 'AFM', None, [panel], {}, [], [])
            reopened = open_plot_specification(database, spec['id'])
            self.assertEqual(reopened, spec)
            reopened_axes = [{key: value for key, value in axis.items() if key not in {'scale', 'manual_range'}}
                             for axis in reopened['panels'][0]['axes']]
            self.assertEqual(query_plot_data(database, 'ternary', reopened_axes, reopened['input']['analysis_ids']), projection)
            capture = {'name': 'AFM', 'format': 'svg', 'width_mm': 90, 'dpi': 600, 'include_csv': True,
                       'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g><text x="1" y="2">AFM</text></g></svg>',
                       'analysis_ids': None, 'hidden_analysis_ids': [], 'hidden_source_ids': [], 'layers': [], 'colors': {},
                       'panels': [{**panel, 'projection_sha256': projection['projection_sha256']}]}
            item = capture_publication_plot(database, capture, 'AFM')
            prepared = prepare_publication(database, 'AFM', [item])
            destination = root / 'afm.zip'
            export_publication(database, 'AFM', [item], prepared['fingerprint'], str(destination))
            with ZipFile(destination) as archive:
                saved, = json.loads(archive.read('materials/01-plot_capture.json'))['panels']
                self.assertEqual(saved['axes'], axes)
                self.assertEqual(saved['points'], projection['points'])
                self.assertEqual(saved['exclusions'], projection['exclusions'])
            self.assertEqual(source.read_bytes(), original)

    def test_trace_ratios_use_declared_units_and_common_ternary_denominator(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'trace.csv'
            source.write_text('Analysis,La [ppm],Ce [ppm],Nd [ppm],Yb [ppb]\n'
                              'P1,2,4,6,2000\nP2,2,4,6,0\nP3,2,4,6,<DL\nP4,-2,-4,-6,-2000\n', encoding='utf-8')
            database = root / 'project.sqlite'
            apply_import_plan(database, source, suggest_import_recipe(source)['recipe'])
            measured = {axis['field']: axis for axis in plot_catalog(database)['axes']}

            def ratio(numerator, denominator):
                return {**measured[numerator], 'field': f'{numerator}/{denominator}', 'unit': 'ratio', 'calculation': {
                    'operation': 'ratio', 'version': 1, 'operands': [measured[numerator], measured[denominator]]}}

            axes = [ratio(element, 'Yb') for element in ('La', 'Ce', 'Nd')]
            projection = query_plot_data(database, 'ternary', axes)
            self.assertEqual(projection['points'][0]['values'], [1, 2, 3])
            self.assertAlmostEqual(projection['points'][0]['u'], 7 / 12)
            self.assertAlmostEqual(projection['points'][0]['v'], .5)
            self.assertCountEqual([row['reason'] for row in projection['exclusions']],
                                  ['zero_denominator', 'below_detection_limit', 'negative_operand'])
            binary = query_plot_data(database, 'binary', [axes[0], measured['Ce']])
            self.assertEqual(binary['points'][0]['values'], [1, 4])
            with self.assertRaises(ImportCommandError):
                query_plot_data(database, 'ternary', [*axes[:2], ratio('Nd', 'La')])

    def test_trace_pattern_package_keeps_reference_ratios_and_measurement_gaps(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "trace.csv"
            source.write_text(
                "Analysis,La (ppm),Ce (ppb),Pr (ppm),Nd (ppm),Nd (ppb)\n"
                "M1,6.87,<100,0.276,1.354,2708\n",
                encoding="utf-8",
            )
            source_bytes = source.read_bytes()
            database = root / "petrolab.sqlite"
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            by_element = {axis["field"]: axis for axis in plot_catalog(database)["axes"]}
            axes = [by_element[element] for element in ("La", "Ce", "Pr", "Nd")]
            normalization = "sun_mcdonough_1989_mantle_diagram_v1"
            projected = query_plot_data(database, "ree_pattern", axes, normalization=normalization)
            spider = query_plot_data(database, "spider", axes, normalization=normalization)
            duplicate = projected["points"][0]["vertices"][3]
            self.assertEqual(spider["points"][0]["vertices"][3], duplicate)
            self.assertEqual(duplicate["status"], "duplicate_measurements")
            self.assertIsNone(duplicate["ratio"])
            self.assertIsNone(duplicate["v"])
            self.assertCountEqual([(row["unit"], row["raw_token"]) for row in duplicate["measurements"]],
                                  [("ppm", "1.354"), ("ppb", "2708")])
            self.assertEqual(len({row["measurement_id"] for row in duplicate["measurements"]}), 2)
            capture = {
                "name": "РЗЭ", "format": "svg", "width_mm": 90, "dpi": 600, "include_csv": True,
                "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g id="panel-a"><text x="1" y="2">a</text></g></svg>',
                "analysis_ids": None, "hidden_analysis_ids": [], "hidden_source_ids": [], "layers": [], "colors": {},
                "panels": [{"id": str(uuid4()), "kind": "ree_pattern", "axes": axes, "normalization": normalization,
                            "projection_sha256": projected["projection_sha256"]}],
            }
            item = capture_publication_plot(database, capture, "Минерал M1")
            ready = prepare_publication(database, "Спектры", [item])
            exported = root / "package.zip"
            export_publication(database, "Спектры", [item], ready["fingerprint"], str(exported))
            with ZipFile(exported) as archive:
                panel, = json.loads(archive.read("materials/01-plot_capture.json"))["panels"]
                self.assertEqual(panel["normalization"], projected["normalization"])
                self.assertEqual(panel["points"], projected["points"])
                rows = list(csv.DictReader(StringIO(archive.read("data/01-plot_capture.csv").decode())))
                self.assertEqual([row["field"] for row in rows], ["La", "Ce", "Pr", "Nd"])
                self.assertTrue(all(row["normalization_id"] == normalization for row in rows))
                self.assertAlmostEqual(float(rows[0]["value"]), 10)
                self.assertEqual((rows[1]["value"], rows[1]["status"]), ("", "below_detection_limit"))
                self.assertAlmostEqual(float(rows[2]["value"]), 1)
                self.assertEqual((rows[3]["value"], rows[3]["status"]), ("", "duplicate_measurements"))
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_direct_plot_capture_keeps_exact_panels_and_source_scope(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.csv"
            source.write_text("Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP1,2,10\nP2,4,12\nP3,<1,9\n", encoding="utf-8")
            database = root / "petrolab.sqlite"
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            axes = plot_catalog(database)["axes"]
            projected = query_plot_data(database, "binary", axes)
            capture = {
                "name": "Panel b", "format": "svg", "width_mm": 90, "dpi": 600, "include_csv": True,
                "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g id="panel-b"><text x="1" y="2">b</text></g></svg>',
                "analysis_ids": None, "hidden_analysis_ids": [], "hidden_source_ids": [], "layers": [], "colors": {},
                "panels": [{"id": str(uuid4()), "kind": "binary", "axes": axes, "projection_sha256": projected["projection_sha256"]}],
            }
            before = database.read_bytes()
            item = capture_publication_plot(database, capture, "Панель b")
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(item["capture"]["analysis_ids"], projected["input_analysis_ids"])
            histogram_axis = [next(axis for axis in axes if axis["field"] == "SiO2")]
            histogram = query_plot_data(database, "histogram", histogram_axis)
            histogram_capture = {**capture, "panels": [{**capture["panels"][0], "kind": "histogram",
                "axes": histogram_axis, "projection_sha256": histogram["projection_sha256"]}]}
            histogram_item = capture_publication_plot(database, histogram_capture, "Гистограмма")
            histogram_package = prepare_publication(database, "Гистограмма", [histogram_item])
            histogram_path = root / "histogram.zip"
            export_publication(database, "Гистограмма", [histogram_item], histogram_package["fingerprint"], str(histogram_path))
            with ZipFile(histogram_path) as archive:
                saved_histogram = json.loads(archive.read("materials/01-plot_capture.json"))["panels"][0]
                self.assertEqual(saved_histogram["binning"], "sturges_v1")
                self.assertEqual(saved_histogram["bins"], histogram["bins"])
            incoming = root / "other.csv"
            incoming.write_text("Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP4,40,22\n", encoding="utf-8")
            apply_import_plan(database, incoming, suggest_import_recipe(incoming)["recipe"])
            ready = prepare_publication(database, "Материалы", [item])
            exported = root / "package.zip"
            export_publication(database, "Материалы", [item], ready["fingerprint"], str(exported))
            with ZipFile(exported) as archive:
                snapshot = json.loads(archive.read("materials/01-plot_capture.json"))
                self.assertEqual(snapshot["panels"][0]["svg_group"], "panel-b")
                self.assertEqual(snapshot["analysis_ids"], projected["input_analysis_ids"])
                exact_ids = [point["analysis_id"] for point in projected["points"]]
                self.assertEqual(ready["manifest"]["items"][0]["analysis_ids"], exact_ids)
                csv_text = archive.read("data/01-plot_capture.csv").decode()
                self.assertEqual(len(csv_text.splitlines()), 5)
                self.assertTrue(all(analysis_id in csv_text for analysis_id in exact_ids))
                self.assertEqual(archive.read("figures/01-plot_capture.svg"), capture["svg"].encode())
            altered = {**capture, "panels": [{**capture["panels"][0], "projection_sha256": "0" * 64}]}
            with self.assertRaises(ImportCommandError) as stale:
                capture_publication_plot(database, altered, "Панель b")
            self.assertEqual(stale.exception.code, "PUBLICATION_PLOT_CHANGED")

    def test_lithos_figures_have_ordered_captions_and_verified_width_and_resolution(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.csv"
            source.write_text("Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP1,2,10\n", encoding="utf-8")
            database = root / "petrolab.sqlite"
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            ids = [row["analysis_id"] for row in list_project_analyses(database)["analyses"]]
            layout = save_plot_specification(database, "Композиции", ids,
                [{"id": str(uuid4()), "kind": "binary", "axes": plot_catalog(database)["axes"]}], {}, [], [])
            raster = root / "figure.tif"
            Image.new("RGB", (3600, 400), "white").save(raster, dpi=(72, 72))
            preview = root / "figure.png"
            Image.new("RGB", (3600, 400), "white").save(preview)
            pdf = root / "figure.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=90 * 72 / 25.4, height=100)
            writer.write(pdf)
            items = [{"kind": "publication_figure", "id": layout["id"], "caption": caption, "source_path": str(path)}
                     for path, caption in [(raster, "Растровая фигура"), (pdf, "Векторная фигура"), (preview, "Просмотр")]]
            prepared = prepare_publication(database, "Lithos", items, "lithos", 90)
            manifest = prepared["manifest"]
            self.assertEqual(manifest["profile"], "lithos")
            self.assertEqual(manifest["figure_width_mm"], 90)
            self.assertEqual(manifest["items"][0]["figure"]["effective_dpi"], 1016)
            self.assertEqual(manifest["items"][1]["figure"]["page_width_mm"], 90)
            self.assertTrue(any("PNG" in warning for warning in manifest["warnings"]))
            destination = root / "lithos.zip"
            export_publication(database, "Lithos", items, prepared["fingerprint"], str(destination), "lithos", 90)
            with ZipFile(destination) as archive:
                self.assertEqual(archive.read("figures/Figure_01.tiff"), raster.read_bytes())
                self.assertEqual(archive.read("figures/Figure_02.pdf"), pdf.read_bytes())
                self.assertEqual(archive.read("figures/Figure_03.png"), preview.read_bytes())
                self.assertEqual(archive.read("figures/captions.txt").decode(),
                                 "Figure 1. Растровая фигура\n\nFigure 2. Векторная фигура\n\nFigure 3. Просмотр\n")
                self.assertEqual(json.loads(archive.read("manifest.json")), manifest)
            for item, width, code in [
                (items[0], 180, "PUBLICATION_FIGURE_DPI"),
                (items[1], 180, "PUBLICATION_FIGURE_WIDTH"),
                ({**items[0], "caption": " "}, 90, "PUBLICATION_FIGURE_CAPTION"),
            ]:
                with self.subTest(code=code), self.assertRaises(ImportCommandError) as rejected:
                    prepare_publication(database, "Lithos", [item], "lithos", width)
                self.assertEqual(rejected.exception.code, code)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): DictionaryObject({NameObject("/Subtype"): NameObject("/Type1")}),
                }),
            })
            writer.write(pdf)
            with self.assertRaises(ImportCommandError) as fonts:
                prepare_publication(database, "Lithos", items, "lithos", 90)
            self.assertEqual(fonts.exception.code, "PUBLICATION_FIGURE_FONTS")

    def test_export_matches_manifest_and_rejects_changed_figure(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "petrolab.sqlite"
            source = root / "input.csv"
            rows = "Analysis,SiO2 [wt.%],Al2O3 [wt.%]\nP1,2,10\nP2,<1,11\n"
            source.write_text(rows, encoding="utf-8")
            dataset = suggest_import_recipe(source)["recipe"]
            apply_import_plan(database, source, dataset)
            ids = [row["analysis_id"] for row in list_project_analyses(database)["analyses"]]
            group = create_work_group(database, "Группа", ids, "Иванов")
            layout = save_plot_specification(database, "Композиции", ids,
                [{"id": str(uuid4()), "kind": "binary", "axes": plot_catalog(database)["axes"]}], {}, [], [])
            figure = root / "figure.svg"
            content = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><g id="panel-b"><text x="1" y="2">b</text></g></svg>'
            figure.write_text(content, encoding="utf-8")
            items = [{"kind": "svg_figure", "id": layout["id"], "caption": "Рисунок b", "source_path": str(figure)},
                     {"kind": "work_group", "id": group["id"], "caption": "Исходные анализы"}]
            prepared = prepare_publication(database, "Материалы", items)
            destinations = [root / "one.zip", root / "two.zip"]
            for path in destinations:
                export_publication(database, "Материалы", items, prepared["fingerprint"], str(path))
            self.assertEqual(destinations[0].read_bytes(), destinations[1].read_bytes())
            with ZipFile(destinations[0]) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest, prepared["manifest"])
                self.assertEqual([item["reference_id"] for item in manifest["items"]], [layout["id"], group["id"]])
                self.assertEqual(set(archive.namelist()), {"manifest.json", *(entry["path"] for entry in manifest["files"])})
                for entry in manifest["files"]:
                    self.assertEqual(sha256(archive.read(entry["path"])).hexdigest(), entry["sha256"])
                measurements = [json.loads(line) for line in archive.read("data/measurements.jsonl").splitlines()]
                self.assertEqual({item["analysis_id"] for item in measurements}, set(ids))
                self.assertIn("<1", [item["raw_token"] for item in measurements])
            figure.write_text(content.replace(">b<", ">c<"), encoding="utf-8")
            with self.assertRaises(ImportCommandError) as changed:
                export_publication(database, "Материалы", items, prepared["fingerprint"], str(root / "changed.zip"))
            self.assertEqual(changed.exception.code, "PUBLICATION_CHANGED")
            figure.write_text(content.replace("<text", "<foreignObject").replace("</text>", "</foreignObject>"), encoding="utf-8")
            with self.assertRaises(ImportCommandError) as unsupported:
                prepare_publication(database, "Материалы", items)
            self.assertEqual(unsupported.exception.code, "PUBLICATION_FIGURE_UNSUPPORTED")
            self.assertEqual(source.read_text(encoding="utf-8"), rows)
