"""Real 100-analysis boundary: exact scope, single projection, atomic history."""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from petrolab import formula_workflow
from petrolab.desktop_workflow import (
    decide_project_mineral_assignment, list_project_mineral_identifications,
)
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.ndjson_service import handle_request


class FormulaBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'batch.csv'
        # Independent Fo50 composition: Si=1, Mg=1, Fe2=1 per 4 O.
        cls.source.write_text(
            'Analysis,Mineral,SiO2 (wt.%),MgO (wt.%),FeO (wt.%)\n'
            + ''.join(f'Fo50-{i},olivine,{60.083/172.231*100},'
                      f'{40.304/172.231*100},{71.844/172.231*100}\n'
                      for i in range(101)), encoding='utf-8')
        cls.original = cls.source.read_bytes()
        cls.base = cls.root / 'base.sqlite'
        recipe = ImportWorkspaceStore().command('create', {'sources': [
            {'staged_path': str(cls.source)}]})['active']['recipe']
        apply_import_plan(cls.base, cls.source, recipe)
        items = list_project_mineral_identifications(cls.base)['identifications']
        for item in items:
            decide_project_mineral_assignment(cls.base, item['analysis_id'], 'olivine',
                item['input_fingerprint'], item['ruleset_version'], 'Independent Fo50 batch')
        cls.ids = [item['analysis_id'] for item in reversed(items)]

    def setUp(self):
        self.project = self.root / (str(uuid.uuid4()) + '.sqlite')
        shutil.copyfile(self.base, self.project)
        self.payload = {'project_database_path': str(self.project),
            'analysis_ids': self.ids[:100], 'method_id': 'olivine.oxygen4',
            'method_version': '1.0.0', 'parameters': {'fe_mode': 'all_fe2'}}

    def send(self, command, **extra):
        return handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
            'command': command, 'payload': {**self.payload, **extra}})

    def counts(self):
        with closing(open_project(self.project)) as connection:
            return tuple(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                         for table in ('formula_run', 'formula_derived_value', 'formula_project'))

    def test_100_rows_one_projection_exact_order_roundtrip_and_retry(self):
        with closing(open_project(self.project)) as connection:
            before = [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        with patch.object(formula_workflow, 'list_project_analyses',
                          wraps=formula_workflow.list_project_analyses) as projection:
            preview = self.send('formula.preview')['result']
            self.assertEqual(projection.call_count, 1)
            self.assertEqual(projection.call_args.kwargs['analysis_ids'], self.ids[:100])
        self.assertTrue(preview['can_save'])
        self.assertEqual([r['analysis_id'] for r in preview['results']], self.ids[:100])
        self.assertEqual([r['analysis_id'] for r in preview['input_snapshots']], self.ids[:100])
        for row in preview['results']:
            for field, expected in {'Si_apfu': 1, 'Mg_apfu': 1, 'Fe2_apfu': 1,
                                    'Fo': 50, 'Fa': 50, 'cation_sum': 3}.items():
                self.assertAlmostEqual(row['values'][field], expected, places=10)
        saved = self.send('formula.save', preview_fingerprint=preview['input_fingerprint'])['result']
        retry = self.send('formula.save', preview_fingerprint=preview['input_fingerprint'])['result']
        self.assertTrue(retry['reused'])
        self.assertEqual(saved['run']['id'], retry['run']['id'])
        self.assertEqual(saved['run']['input']['analysis_ids'], self.ids[:100])
        for analysis_id in (self.ids[0], self.ids[99]):
            history = self.send('formula.runs.list', analysis_id=analysis_id)['result']['runs']
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['run'], saved['run'])
            self.assertEqual({v['analysis_id'] for v in history[0]['derived_values']}, set(self.ids[:100]))
            for value in history[0]['derived_values']:
                snapshot = next(r for r in preview['input_snapshots'] if r['analysis_id'] == value['analysis_id'])
                self.assertEqual(set(value['input_measurement_ids']),
                                 {m['measurement_id'] for m in snapshot['measurements']})
        self.assertEqual(self.send('formula.runs.list', analysis_id=self.ids[100])['result']['runs'], [])
        with closing(open_project(self.project)) as connection:
            self.assertEqual(before, [tuple(r) for r in connection.execute('SELECT * FROM measurement ORDER BY rowid')])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_missing_last_row_is_not_dropped_and_101_is_rejected(self):
        ids = [*self.ids[:99], str(uuid.uuid4())]
        preview = self.send('formula.preview', analysis_ids=ids)['result']
        self.assertFalse(preview['can_save'])
        self.assertEqual([r['analysis_id'] for r in preview['results']], ids)
        self.assertEqual([r['status'] for r in preview['results']], ['current']*99 + ['failed'])
        failed = self.send('formula.save', analysis_ids=ids, preview_fingerprint=preview['input_fingerprint'])
        self.assertEqual(failed['error']['code'], 'FORMULA_INPUT_INVALID')
        self.assertEqual(self.send('formula.preview', analysis_ids=self.ids)['error']['code'], 'FORMULA_SCOPE_INVALID')
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_failure_writing_last_analysis_rolls_back_previous_99(self):
        preview = self.send('formula.preview')['result']
        with closing(open_project(self.project)) as connection:
            connection.execute(f"""CREATE TRIGGER fail_last BEFORE INSERT ON formula_derived_value
                WHEN NEW.analysis_id = '{self.ids[99]}'
                BEGIN SELECT RAISE(ABORT, 'last analysis failed'); END""")
            connection.commit()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'last analysis failed'):
            formula_workflow.save_formula(self.project, self.ids[:100], 'olivine.oxygen4',
                '1.0.0', {'fe_mode': 'all_fe2'}, preview['input_fingerprint'])
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_last_input_change_rejects_whole_preview_and_marks_shared_run_stale(self):
        preview = self.send('formula.preview')['result']
        saved = self.send('formula.save', preview_fingerprint=preview['input_fingerprint'])['result']['run']
        with closing(open_project(self.project)) as connection:
            payload_before = connection.execute('SELECT payload_json FROM formula_run').fetchone()[0]
            # Only test fixture mutation, simulates an explicit future correction.
            connection.execute("UPDATE measurement SET raw_token='36' WHERE analysis_id=? AND canonical_field='SiO2'",
                               (self.ids[99],))
            connection.commit()
        failed = self.send('formula.save', preview_fingerprint=preview['input_fingerprint'])
        self.assertEqual(failed['error']['code'], 'FORMULA_PREVIEW_STALE')
        for analysis_id in (self.ids[0], self.ids[99]):
            history = self.send('formula.runs.list', analysis_id=analysis_id)['result']['runs']
            self.assertEqual(history[0]['run']['id'], saved['id'])
            self.assertEqual(history[0]['run']['status'], 'stale')
        with closing(open_project(self.project)) as connection:
            self.assertEqual(connection.execute('SELECT payload_json FROM formula_run').fetchone()[0], payload_before)
        self.assertEqual(self.counts()[0], 1)
