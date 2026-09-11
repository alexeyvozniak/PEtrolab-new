from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from petrolab import import_apply
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.import_preview import ImportCommandError
from petrolab.desktop_workflow import list_project_mineral_identifications, decide_project_mineral_assignment
from petrolab.formula_methods import METHOD_ID, METHOD_VERSION, IMPLEMENTATION_SHA256, method_definition
from petrolab.formula_workflow import preview_formula, save_formula, list_formula_runs
from petrolab.olivine_formula import calculate_olivine
from petrolab.ndjson_service import handle_request


def measurements(values):
    return [{'measurement_id': str(uuid.uuid4()), 'field': f, 'raw_token': str(v),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None} for f, v in values.items()]


class OlivineBenchmarks(unittest.TestCase):
    def test_independent_stoichiometric_endpoints_and_mixture(self):
        # Weights built independently from SiO2=60.083, MgO=40.304, FeO=71.844.
        # Expected cations come from Mg2SiO4 / Fe2SiO4 / MgFeSiO4, NOT production.
        for mg, fe, fo in [(80.608, 0, 100), (0, 143.688, 0), (40.304, 71.844, 50)]:
            with self.subTest(fo=fo):
                r = calculate_olivine(measurements({'SiO2': 60.083, 'MgO': mg, 'FeO': fe}), 'all_fe2')
                self.assertEqual(r['status'], 'current', r)
                self.assertAlmostEqual(r['values']['Si_apfu'], 1, places=12)
                self.assertAlmostEqual(r['values']['Mg_apfu'], fo / 50, places=12)
                self.assertAlmostEqual(r['values']['Fe2_apfu'], (100-fo) / 50, places=12)
                self.assertAlmostEqual(r['values']['Fo'], fo, places=12)
                self.assertAlmostEqual(r['values']['Fa'], 100-fo, places=12)
                self.assertNotIn('Ni_apfu', r['values'])

    def test_mn_ca_ni_not_in_binary_denominator(self):
        # Si Mg Fe Mn Ca Ni = 1,1,.7,.1,.1,.1; four oxygens, three cations.
        r = calculate_olivine(measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 50.2908,
            'MnO': 7.0937, 'CaO': 5.6077, 'NiO': 7.4692}), 'all_fe2')
        self.assertAlmostEqual(r['values']['Fo'], 100/1.7, places=10)
        for field in ('Mn', 'Ca', 'Ni'):
            self.assertAlmostEqual(r['values'][field+'_apfu'], .1, places=12)

    def test_split_iron_and_total_equivalence(self):
        m = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 71.844})
        total = deepcopy(m); total[-1]['field'] = 'FeOt'
        self.assertEqual(calculate_olivine(m, 'all_fe2')['values'], calculate_olivine(total, 'all_fe2')['values'])
        split = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 43.1064, 'Fe2O3': 21.2916})
        r = calculate_olivine(split, 'reported_split')
        self.assertAlmostEqual(r['values']['Fe2_apfu'], .6, places=12)
        self.assertAlmostEqual(r['values']['Fe3_apfu'], 4/15, places=12)
        self.assertAlmostEqual(r['values']['Fo'], 62.5, places=12)

    def test_rejects_invalid_values_units_duplicates_and_missing(self):
        baseline = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 71.844})
        for update in [{'raw_token': '-1'}, {'raw_token': 'nan'}, {'raw_token': 'inf'}, {'raw_token': 'abc'},
                       {'raw_token': '<0.1', 'value_status': 'below_detection_limit'},
                       {'raw_token': None, 'value_status': 'missing'}, {'unit': 'ppm'},
                       {'qualifier': 'below_detection_limit'}]:
            with self.subTest(update=update):
                m = deepcopy(baseline); m[0].update(update)
                self.assertEqual(calculate_olivine(m, 'all_fe2')['status'], 'failed')
        for m in [baseline[:-1], baseline + [baseline[1]], measurements({'SiO2': 0, 'MgO': 1, 'FeO': 1}),
                  measurements({'SiO2': 1, 'MgO': 0, 'FeO': 0})]:
            self.assertEqual(calculate_olivine(m, 'all_fe2')['status'], 'failed')
        for field in ['Fe2O3', 'Fe2O3t', 'FeOt', 'F']:
            m = baseline + measurements({field: 0})
            self.assertEqual(calculate_olivine(m, 'all_fe2')['status'], 'failed')
        self.assertEqual(calculate_olivine(baseline, 'reported_split')['status'], 'failed')

    def test_optional_missing_is_not_zero_and_trace_exclusion_is_explicit(self):
        m = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 71.844, 'NiO': 0})
        m[-1].update(raw_token=None, value_status='missing')
        self.assertEqual(calculate_olivine(m, 'all_fe2')['status'], 'failed')
        m[-1].update(field='Rb', raw_token='5', unit='ppm', value_status='numeric')
        r = calculate_olivine(m, 'all_fe2')
        self.assertEqual(r['excluded'][0]['field'], 'Rb')
        self.assertNotIn('Ni_apfu', r['values'])

    def test_reported_total_iron_cannot_masquerade_as_measured_split(self):
        for field, form in [('FeO', 'FeOt'), ('Fe2O3', 'Fe2O3t')]:
            m = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 71.844, 'Fe2O3': 0})
            next(item for item in m if item['field'] == field)['reported_fe_form'] = form
            self.assertEqual(calculate_olivine(m, 'reported_split')['status'], 'failed')
        m = measurements({'SiO2': 60.083, 'MgO': 40.304, 'FeO': 71.844})
        m[-1]['reported_fe_form'] = 'Fe2O3'
        self.assertEqual(calculate_olivine(m, 'all_fe2')['status'], 'failed')

    def test_implementation_hash_pins_algorithm(self):
        path = Path(__file__).parents[1] / 'src/petrolab/olivine_formula.py'
        self.assertEqual(hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest(), IMPLEMENTATION_SHA256)


class FormulaPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name); self.database = self.folder / 'project.sqlite'
        self.source = self.folder / 'olivine.csv'
        self.source.write_text(f'Analysis,Mineral,SiO2 (wt.%),MgO (wt.%),FeO (wt.%)\nFo50,olivine,{60.083/172.231*100},{40.304/172.231*100},{71.844/172.231*100}\n', encoding='utf-8')
        self.original = self.source.read_bytes()
        store = ImportWorkspaceStore()
        self.recipe = store.command('create', {'sources': [{'staged_path': str(self.source)}]})['active']['recipe']
        apply_import_plan(self.database, self.source, self.recipe)
        item = list_project_mineral_identifications(self.database)['identifications'][0]
        self.analysis_id = item['analysis_id']
        decide_project_mineral_assignment(self.database, self.analysis_id, 'olivine', item['input_fingerprint'], item['ruleset_version'], 'Независимая проверка минерала')
        self.args = (self.database, [self.analysis_id], METHOD_ID, METHOD_VERSION, {'fe_mode': 'all_fe2'})

    def test_save_retry_reopen_schema_and_unchanged_measurements(self):
        with closing(open_project(self.database)) as c:
            before = [tuple(r) for r in c.execute('SELECT * FROM measurement')]
        p = preview_formula(*self.args)
        self.assertTrue(p['can_save'], p)
        result = save_formula(*self.args, p['input_fingerprint'])
        retry = save_formula(*self.args, p['input_fingerprint'])
        self.assertTrue(retry['reused']); self.assertEqual(retry['run']['id'], result['run']['id'])
        history = list_formula_runs(self.database, self.analysis_id)['runs']
        self.assertEqual(len(history), 1); self.assertEqual(history[0]['run']['status'], 'current')
        from scripts.validate_contracts import _validate
        root = Path(__file__).parents[1] / 'schemas'
        for name, documents in [('scientific-method-definition', [method_definition()]),
                                ('calculation-run', [history[0]['run']]),
                                ('derived-value', history[0]['derived_values'])]:
            schema = json.loads((root / (name+'.schema.json')).read_text())
            for document in documents:
                _validate(document, schema, schema, {}, name)
        with closing(open_project(self.database)) as c:
            self.assertEqual(before, [tuple(r) for r in c.execute('SELECT * FROM measurement')])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_stale_measurement_preview_and_history(self):
        p = preview_formula(*self.args); save_formula(*self.args, p['input_fingerprint'])
        # Simulate a future explicit correction, never a production write path.
        with closing(open_project(self.database)) as c:
            c.execute("UPDATE measurement SET raw_token='35' WHERE canonical_field='SiO2'"); c.commit()
        with self.assertRaises(ImportCommandError) as caught:
            save_formula(*self.args, p['input_fingerprint'])
        self.assertEqual(caught.exception.code, 'FORMULA_PREVIEW_STALE')
        self.assertEqual(list_formula_runs(self.database, self.analysis_id)['runs'][0]['run']['status'], 'stale')

    def test_stale_method_and_clear_assignment(self):
        p = preview_formula(*self.args); save_formula(*self.args, p['input_fingerprint'])
        changed = method_definition(); changed['definition_fingerprint'] = '0'*64
        with patch('petrolab.formula_workflow.method_definition', return_value=changed):
            self.assertEqual(list_formula_runs(self.database, self.analysis_id)['runs'][0]['run']['status'], 'stale')
        row = list_project_mineral_identifications(self.database)['identifications'][0]
        decide_project_mineral_assignment(self.database, self.analysis_id, None, row['input_fingerprint'], row['ruleset_version'], 'Отмена')
        self.assertFalse(preview_formula(*self.args)['can_save'])
        self.assertEqual(list_formula_runs(self.database, self.analysis_id)['runs'][0]['run']['status'], 'stale')

    def test_invalid_batch_never_silently_shrinks_and_failure_rolls_back(self):
        args = (self.database, [self.analysis_id, str(uuid.uuid4())], *self.args[2:])
        p = preview_formula(*args)
        self.assertEqual(len(p['results']), 2); self.assertFalse(p['can_save'])
        with self.assertRaises(ImportCommandError): save_formula(*args, p['input_fingerprint'])
        with closing(open_project(self.database)) as c:
            c.execute("CREATE TRIGGER fail_value BEFORE INSERT ON formula_derived_value BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
            c.commit()
        p = preview_formula(*self.args)
        with self.assertRaises(sqlite3.IntegrityError): save_formula(*self.args, p['input_fingerprint'])
        with closing(open_project(self.database)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM formula_run').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM formula_project').fetchone()[0], 0)

    def test_ndjson_contract_and_parameter_rejection(self):
        payload = {'project_database_path': str(self.database), 'analysis_ids': [self.analysis_id],
                   'method_id': METHOD_ID, 'method_version': METHOD_VERSION, 'parameters': {'fe_mode': 'all_fe2'}}
        def send(command, data):
            return handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()), 'command': command, 'payload': data})
        p = send('formula.preview', payload)['result']
        result = send('formula.save', {**payload, 'preview_fingerprint': p['input_fingerprint']})
        self.assertIn('run', result['result'])
        self.assertIn('error', send('formula.preview', {**payload, 'parameters': {}}))
        self.assertIn('error', send('formula.preview', {**payload, 'method_version': 'not-installed'}))
        self.assertIn('error', send('formula.preview', {**payload, 'analysis_ids': [self.analysis_id]*2}))

    def test_v12_upgrade_backs_up_and_preserves_project(self):
        historical = self.folder / 'migrations12'; historical.mkdir()
        for p in import_apply.MIGRATIONS.glob('*.sql'):
            if int(p.name.split('_')[0]) <= 12: shutil.copyfile(p, historical/p.name)
        old = self.folder/'old.sqlite'
        with patch.object(import_apply, 'MIGRATIONS', historical):
            apply_import_plan(old, self.source, self.recipe)
        with closing(open_project(old)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM formula_run').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 13)
        self.assertEqual(len(list(self.folder.glob('old.sqlite.before-v13-*.bak'))), 1)
