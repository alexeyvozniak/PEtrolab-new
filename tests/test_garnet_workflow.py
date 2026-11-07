"""AT-47: independent published garnet through persistence, not just arithmetic."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from petrolab.desktop_workflow import decide_project_mineral_assignment, list_project_mineral_identifications
from petrolab.formula_methods import GRT_IMPLEMENTATION_SHA256, list_methods
from petrolab.formula_workflow import preview_formula, save_formula, list_formula_runs
from petrolab.garnet_formula import METHOD_ID, METHOD_VERSION
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_preview import ImportCommandError
from petrolab.import_workspace import ImportWorkspaceStore


class GarnetWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(__file__).resolve().parents[1]
        self.source = Path(self.temp.name) / 'garnet.csv'
        self.project = Path(self.temp.name) / 'project.sqlite'
        shutil.copyfile(self.root / 'fixtures/formula/garnet_sg1.csv', self.source)
        self.original = self.source.read_bytes()
        recipe = ImportWorkspaceStore().command('create', {'sources': [
            {'staged_path': str(self.source)}]})['active']['recipe']
        apply_import_plan(self.project, self.source, recipe)
        record = list_project_mineral_identifications(self.project)['identifications'][0]
        self.analysis_id = record['analysis_id']
        decide_project_mineral_assignment(self.project, self.analysis_id, 'almandine',
            record['input_fingerprint'], record['ruleset_version'], 'AT-47: published SG1')
        methods = list_methods('almandine')['methods']
        self.assertEqual([m['method_id'] for m in methods], [METHOD_ID])
        self.parameters = methods[0]['quick_presets'][0]['parameters']
        self.assertEqual(self.parameters, {'fe_mode': 'stoichiometric_droop'})
        self.args = (self.project, [self.analysis_id], METHOD_ID, METHOD_VERSION, self.parameters)

    def test_published_formula_and_sites_reopen_with_units_estimates_and_unchanged_sources(self):
        with closing(open_project(self.project)) as connection:
            before = [tuple(row) for row in connection.execute('SELECT * FROM measurement')]
        preview = preview_formula(*self.args)
        self.assertTrue(preview['can_save'], preview)
        result = preview['results'][0]
        # WinGrt (2020), Table 4 SG1; not a production-generated oracle.
        for field, expected in {'Si': 2.938, 'Al': 1.972, 'Fe3': .153,
                                'Fe2': 2.358, 'Mg': .525, 'Mn': .016, 'Ca': .039}.items():
            self.assertAlmostEqual(result['values'][field + '_apfu'], expected, delta=.003)
        self.assertIn('structural_warning', result)
        self.assertAlmostEqual(result['values']['charge_sum'], 24, places=10)
        self.assertAlmostEqual(result['values']['cation_sum'], 8, places=10)
        saved = save_formula(*self.args, preview['input_fingerprint'])
        retry = save_formula(*self.args, preview['input_fingerprint'])
        self.assertTrue(retry['reused'])
        self.assertEqual(saved['run']['id'], retry['run']['id'])
        history = list_formula_runs(self.project, self.analysis_id)['runs']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['run']['result_manifest']['results'][0], result)
        self.assertEqual(history[0]['run']['result_manifest']['method']['status'], 'draft')
        derived = {item['field']: item for item in history[0]['derived_values']}
        self.assertIsNone(derived['structural_formula']['unit'])
        self.assertEqual(derived['structural_formula']['value'], result['values']['structural_formula'])
        self.assertIsNone(derived['charge_sum']['unit'])
        self.assertEqual(derived['X_Fe2_apfu']['unit'], 'apfu')
        self.assertEqual(derived['oxide_total']['unit'], 'wt.%')
        for item in derived.values():
            self.assertEqual(item['method_id'], METHOD_ID)
            self.assertEqual(set(item['input_measurement_ids']), set(saved['run']['input_measurement_ids']))
            self.assertTrue(any('Fe3+ = 24*(1-8/S)' in assumption for assumption in item['assumptions']))
        from scripts.validate_contracts import _validate
        for name, documents in [('scientific-method-definition', [preview['method']]),
                                ('calculation-run', [history[0]['run']]),
                                ('derived-value', list(derived.values()))]:
            schema = json.loads((self.root / 'schemas' / (name + '.schema.json')).read_text())
            for document in documents:
                _validate(document, schema, schema, {}, name)
        with closing(open_project(self.project)) as connection:
            self.assertEqual(before, [tuple(row) for row in connection.execute('SELECT * FROM measurement')])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.original, self.source.read_bytes())

    def test_invalid_split_is_not_saved_and_parameter_change_invalidates_preview(self):
        preview = preview_formula(*self.args)
        split_args = (*self.args[:-1], {'fe_mode': 'reported_split'})
        invalid = preview_formula(*split_args)
        self.assertFalse(invalid['can_save'])
        self.assertEqual(invalid['parameters']['fe_mode'], 'reported_split')
        self.assertEqual(invalid['results'][0]['values'], {})
        with self.assertRaises(ImportCommandError):
            save_formula(*split_args, invalid['input_fingerprint'])
        with self.assertRaises(ImportCommandError):
            save_formula(*self.args[:-1], {'fe_mode': 'all_fe2'}, preview['input_fingerprint'])
        self.assertEqual(list_formula_runs(self.project, self.analysis_id)['runs'], [])

    def test_stale_history_preserves_original_structure_and_estimate_basis(self):
        preview = preview_formula(*self.args)
        saved = save_formula(*self.args, preview['input_fingerprint'])
        with closing(open_project(self.project)) as connection, connection:
            stored = connection.execute('SELECT payload_json FROM formula_run').fetchone()[0]
            connection.execute("UPDATE measurement SET raw_token='20' WHERE canonical_field='MgO'")
        with self.assertRaises(ImportCommandError):
            save_formula(*self.args, preview['input_fingerprint'])
        reopened = list_formula_runs(self.project, self.analysis_id)['runs'][0]
        self.assertEqual(reopened['run']['status'], 'stale')
        self.assertEqual(reopened['run']['result_manifest'], saved['run']['result_manifest'])
        self.assertTrue(all(value['status'] == 'stale' for value in reopened['derived_values']))
        with closing(open_project(self.project)) as connection:
            self.assertEqual(connection.execute('SELECT payload_json FROM formula_run').fetchone()[0], stored)

    def test_algorithm_is_pinned(self):
        content = (self.root / 'src/petrolab/garnet_formula.py').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(content).hexdigest(), GRT_IMPLEMENTATION_SHA256)
