"""AT-48: coexistence and immutable structural history through the actual service."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from petrolab.desktop_workflow import decide_project_mineral_assignment, list_project_mineral_identifications
from petrolab.formula_methods import CPS_IMPLEMENTATION_SHA256, list_methods
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.ndjson_service import handle_request


class ClinopyroxeneStructuralWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(__file__).resolve().parents[1]
        self.source = Path(self.temp.name) / 'cpx-s4.csv'
        self.project = Path(self.temp.name) / 'project.sqlite'
        shutil.copyfile(self.root / 'fixtures/formula/clinopyroxene_winpyrox_s4.csv', self.source)
        self.original = self.source.read_bytes()
        recipe = ImportWorkspaceStore().command('create', {'sources': [
            {'staged_path': str(self.source)}]})['active']['recipe']
        apply_import_plan(self.project, self.source, recipe)
        record = list_project_mineral_identifications(self.project)['identifications'][0]
        self.analysis_id = record['analysis_id']
        decide_project_mineral_assignment(self.project, self.analysis_id, 'hedenbergite',
            record['input_fingerprint'], record['ruleset_version'], 'AT-48: published ferric S4')
        self.payload = {'project_database_path': str(self.project), 'analysis_ids': [self.analysis_id],
                        'method_id': 'clinopyroxene.structural6', 'method_version': '0.1.0',
                        'parameters': {'fe_mode': 'reported_split'}}

    def send(self, command, extra=None):
        return handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
                               'command': command, 'payload': {**self.payload, **(extra or {})}})

    def test_both_methods_save_without_rewriting_source_or_old_run_and_reopen_units(self):
        with closing(open_project(self.project)) as connection:
            before = [tuple(row) for row in connection.execute('SELECT * FROM measurement')]
        self.assertEqual([m['method_id'] for m in list_methods('hedenbergite')['methods']],
                         ['clinopyroxene.oxygen6', 'clinopyroxene.structural6'])
        old_preview = self.send('formula.preview', {'method_id': 'clinopyroxene.oxygen6'})['result']
        old_saved = self.send('formula.save', {'method_id': 'clinopyroxene.oxygen6',
            'preview_fingerprint': old_preview['input_fingerprint']})['result']['run']
        preview = self.send('formula.preview')['result']
        self.assertTrue(preview['can_save'], preview)
        result = preview['results'][0]
        self.assertAlmostEqual(result['values']['Fe3_apfu'], .237 * 12 / 12.064, delta=.003)
        self.assertAlmostEqual(result['values']['M1_Fe2_apfu'], .210, delta=.004)
        saved = self.send('formula.save', {'preview_fingerprint': preview['input_fingerprint']})['result']
        retry = self.send('formula.save', {'preview_fingerprint': preview['input_fingerprint']})['result']
        self.assertTrue(retry['reused'])
        self.assertEqual(saved['run']['id'], retry['run']['id'])
        history = handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
            'command': 'formula.runs.list', 'payload': {'project_database_path': str(self.project),
                                                       'analysis_id': self.analysis_id}})['result']['runs']
        self.assertEqual(len(history), 2)
        self.assertEqual(next(row['run'] for row in history if row['run']['id'] == old_saved['id']), old_saved)
        reopened = next(row for row in history if row['run']['id'] == saved['run']['id'])
        self.assertEqual(reopened['run']['result_manifest']['results'][0], result)
        self.assertEqual(reopened['run']['parameters'], {'fe_mode': 'reported_split'})
        derived = {item['field']: item for item in reopened['derived_values']}
        self.assertIsNone(derived['structural_formula']['unit'])
        self.assertIsNone(derived['charge_sum']['unit'])
        self.assertEqual(derived['M1_Fe3_apfu']['unit'], 'apfu')
        self.assertEqual(derived['Wo']['unit'], 'mol.%')
        self.assertEqual(derived['structural_formula']['value'], result['values']['structural_formula'])
        from scripts.validate_contracts import _validate
        for name, documents in [('scientific-method-definition', [preview['method']]),
                                ('calculation-run', [reopened['run']]),
                                ('derived-value', list(derived.values()))]:
            schema = json.loads((self.root / 'schemas' / (name+'.schema.json')).read_text())
            for document in documents:
                _validate(document, schema, schema, {}, name)
        used = {m['measurement_id'] for m in result['used']}
        for value in derived.values():
            self.assertEqual(set(value['input_measurement_ids']), used)
        with closing(open_project(self.project)) as connection:
            self.assertEqual(before, [tuple(row) for row in connection.execute('SELECT * FROM measurement')])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.original, self.source.read_bytes())

    def test_wrong_fe_mode_and_old_preview_cannot_save_any_partial_result(self):
        preview = self.send('formula.preview')['result']
        invalid = self.send('formula.preview', {'parameters': {'fe_mode': 'stoichiometric_droop'}})['result']
        self.assertFalse(invalid['can_save'])
        self.assertEqual(invalid['results'][0]['values'], {})
        self.assertEqual(invalid['parameters']['fe_mode'], 'stoichiometric_droop')
        response = self.send('formula.save', {'parameters': invalid['parameters'],
                                              'preview_fingerprint': invalid['input_fingerprint']})
        self.assertEqual(response['error']['code'], 'FORMULA_INPUT_INVALID')
        response = self.send('formula.save', {'method_id': 'clinopyroxene.oxygen6',
                                              'preview_fingerprint': preview['input_fingerprint']})
        self.assertEqual(response['error']['code'], 'FORMULA_PREVIEW_STALE')
        with closing(open_project(self.project)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formula_run').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM formula_derived_value').fetchone()[0], 0)

    def test_na_methods_and_implementation_pin(self):
        for mineral in ('jadeite', 'aegirine', 'omphacite'):
            self.assertEqual([m['method_id'] for m in list_methods(mineral)['methods']], ['clinopyroxene.structural6'])
        content = (self.root/'src/petrolab/clinopyroxene_structural_formula.py').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(content).hexdigest(), CPS_IMPLEMENTATION_SHA256)
