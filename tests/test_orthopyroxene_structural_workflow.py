"""Structural Opx through the real import, catalog, batch and history service."""
from contextlib import closing
import hashlib
from pathlib import Path
import tempfile
import unittest
import uuid

from petrolab.desktop_workflow import decide_project_mineral_assignment, list_project_mineral_identifications
from petrolab.formula_methods import OPS_IMPLEMENTATION_SHA256, list_methods
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.ndjson_service import handle_request


class OrthopyroxeneStructuralWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(__file__).resolve().parents[1]
        source_text = (self.root / 'fixtures/formula/orthopyroxene_tariat2018.csv').read_text(encoding='utf-8')
        header, sample = source_text.splitlines()
        self.source = Path(self.temp.name) / 'opx.csv'
        self.source.write_text(header + '\n' + sample + '\n' + sample.replace('Tariat mean n=22', 'Tariat duplicate') + '\n', encoding='utf-8')
        self.original = self.source.read_bytes()
        self.project = Path(self.temp.name) / 'project.sqlite'
        recipe = ImportWorkspaceStore().command('create', {'sources': [{'staged_path': str(self.source)}]})['active']['recipe']
        apply_import_plan(self.project, self.source, recipe)
        records = list_project_mineral_identifications(self.project)['identifications']
        self.ids = [row['analysis_id'] for row in records]
        self.assertEqual(len(self.ids), 2)
        for row in records:
            decide_project_mineral_assignment(self.project, row['analysis_id'], 'enstatite',
                row['input_fingerprint'], row['ruleset_version'], 'published natural Opx mean')
        self.payload = {'project_database_path': str(self.project), 'analysis_ids': self.ids,
                        'method_id': 'orthopyroxene.structural6', 'method_version': '0.1.0',
                        'parameters': {'fe_mode': 'all_fe2'}}

    def send(self, command, extra=None):
        return handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
                               'command': command, 'payload': {**self.payload, **(extra or {})}})

    def test_batch_natural_reference_save_retry_history_and_old_method(self):
        with closing(open_project(self.project)) as connection:
            before = [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        self.assertEqual([m['method_id'] for m in list_methods('enstatite')['methods']],
                         ['orthopyroxene.oxygen6', 'orthopyroxene.structural6'])
        old = self.send('formula.preview', {'method_id': 'orthopyroxene.oxygen6'})['result']
        old_run = self.send('formula.save', {'method_id': 'orthopyroxene.oxygen6',
            'preview_fingerprint': old['input_fingerprint']})['result']['run']
        preview = self.send('formula.preview')['result']
        self.assertTrue(preview['can_save'], preview)
        self.assertEqual(preview['method']['status'], 'draft')
        for row in preview['results']:
            for field, value in {'Si_apfu': 1.902, 'Fe2_apfu': .172, 'Mg_apfu': 1.677}.items():
                self.assertAlmostEqual(row['values'][field], value, delta=.001)
            self.assertEqual(row['site_order'], ['T', 'M1', 'M2'])
            self.assertNotIn('Fe3_apfu', row['values'])
        saved = self.send('formula.save', {'preview_fingerprint': preview['input_fingerprint']})['result']
        retry = self.send('formula.save', {'preview_fingerprint': preview['input_fingerprint']})['result']
        self.assertTrue(retry['reused'])
        self.assertEqual(saved['run']['id'], retry['run']['id'])
        for analysis_id, result in zip(self.ids, preview['results']):
            response = self.send('formula.runs.list', {'analysis_id': analysis_id})['result']['runs']
            self.assertEqual(len(response), 2)
            self.assertEqual(next(x['run'] for x in response if x['run']['id'] == old_run['id']), old_run)
            current = next(x for x in response if x['run']['id'] == saved['run']['id'])
            self.assertIn(result, current['run']['result_manifest']['results'])
            derived = {value['field']: value for value in current['derived_values']}
            self.assertEqual(derived['M1_Fe2_apfu']['unit'], 'apfu')
            self.assertIsNone(derived['structural_formula']['unit'])
            self.assertEqual(derived['Wo']['unit'], 'mol.%')
        with closing(open_project(self.project)) as connection:
            self.assertEqual(before, [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.source.read_bytes(), self.original)
        content = (self.root / 'src/petrolab/orthopyroxene_structural_formula.py').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(content).hexdigest(), OPS_IMPLEMENTATION_SHA256)

    def test_batch_invalid_member_blocks_atomic_save_and_stale_preview(self):
        preview = self.send('formula.preview')['result']
        with closing(open_project(self.project)) as connection:
            connection.execute("UPDATE measurement SET raw_token='0' WHERE analysis_id=? AND canonical_field='SiO2'", (self.ids[1],))
            connection.commit()
        self.assertEqual(self.send('formula.save', {'preview_fingerprint': preview['input_fingerprint']})['error']['code'],
                         'FORMULA_PREVIEW_STALE')
        invalid = self.send('formula.preview')['result']
        self.assertFalse(invalid['can_save'])
        self.assertEqual([item['status'] for item in invalid['results']], ['current', 'failed'])
        self.assertEqual(self.send('formula.save', {'preview_fingerprint': invalid['input_fingerprint']})['error']['code'],
                         'FORMULA_INPUT_INVALID')
        with closing(open_project(self.project)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formula_run').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM formula_derived_value').fetchone()[0], 0)

    def test_one_hundred_natural_compositions_are_saved_atomically_in_order(self):
        header, sample = self.source.read_text(encoding='utf-8').splitlines()[:2]
        batch_source = Path(self.temp.name) / 'opx-100.csv'
        batch_source.write_text(header + '\n' + '\n'.join(
            sample.replace('Tariat mean n=22', f'Tariat-{number:03d}') for number in range(100)) + '\n', encoding='utf-8')
        source_bytes = batch_source.read_bytes()
        batch_project = Path(self.temp.name) / 'opx-100.sqlite'
        recipe = ImportWorkspaceStore().command('create', {'sources': [{'staged_path': str(batch_source)}]})['active']['recipe']
        apply_import_plan(batch_project, batch_source, recipe)
        records = list_project_mineral_identifications(batch_project)['identifications']
        self.assertEqual(len(records), 100)
        ids = [row['analysis_id'] for row in records]
        for row in records:
            decide_project_mineral_assignment(batch_project, row['analysis_id'], 'enstatite',
                row['input_fingerprint'], row['ruleset_version'], 'published natural Opx mean, test copy')
        with closing(open_project(batch_project)) as connection:
            before = [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        args = {'project_database_path': str(batch_project), 'analysis_ids': ids}
        preview = self.send('formula.preview', args)['result']
        self.assertTrue(preview['can_save'], preview)
        self.assertEqual([row['analysis_id'] for row in preview['results']], ids)
        for row in preview['results']:
            self.assertEqual(row['status'], 'current')
            for field, expected in {'Si_apfu': 1.902, 'Fe2_apfu': .172, 'Mg_apfu': 1.677}.items():
                self.assertAlmostEqual(row['values'][field], expected, delta=.001)
        saved = self.send('formula.save', {**args, 'preview_fingerprint': preview['input_fingerprint']})['result']
        retry = self.send('formula.save', {**args, 'preview_fingerprint': preview['input_fingerprint']})['result']
        self.assertTrue(retry['reused'])
        self.assertEqual(saved['run']['id'], retry['run']['id'])
        for analysis_id in (ids[0], ids[-1]):
            history = self.send('formula.runs.list', {**args, 'analysis_id': analysis_id})['result']['runs']
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['run']['id'], saved['run']['id'])
            self.assertEqual([row['analysis_id'] for row in history[0]['run']['result_manifest']['results']], ids)
        with closing(open_project(batch_project)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM formula_run').fetchone()[0], 1)
            self.assertEqual(before, [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(batch_source.read_bytes(), source_bytes)
