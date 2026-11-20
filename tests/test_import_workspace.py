from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing

from petrolab.import_preview import ImportCommandError
from petrolab.import_apply import retract_latest_import
from petrolab.desktop_workflow import list_project_analyses
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.ndjson_service import handle_request
from test_import_preview import FIXTURE


class ImportWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'first.csv'
        self.other = Path(self.temp.name) / 'second.csv'
        self.source.write_text('Analysis,Fe (wt.%),F (wt.%)\nA1,10,<DL\nA2,11,n.d.\n', encoding='utf-8')
        self.other.write_text('Analysis,SiO2 [wt.%]\nB1,40\nB2,41\n', encoding='utf-8')
        self.store = ImportWorkspaceStore()
        self.current = self.store.command('create', {'sources': [{'staged_path': str(self.source)}]})

    def call(self, operation, **params):
        session = self.current['session']
        self.current = self.store.command(operation, {'workspace_id': session['workspace_id'],
            'expected_revision': session['draft_revision'], 'source_id': session['active_source_id'], **params})
        return self.current

    def test_two_sources_keep_mapping_identity_issue_and_raw_coordinates(self):
        first = self.current['session']['active_source_id']
        original = self.source.read_bytes()
        self.call('add_sources', sources=[{'staged_path': str(self.other)}])
        second_recipe = deepcopy(self.current['active']['recipe'])
        self.call('apply_decision', source_id=first, decision={'kind': 'activate'})
        block = self.current['active']['recipe']['sections'][0]['block_id']
        self.call('apply_decision', decision={'kind': 'mappings', 'decisions': [
            {'block_id': block, 'source_axis': 'column', 'source_index': 0, 'target': 'Ignore'}]})
        self.assertTrue(any(i['code'] == 'ANALYSIS_IDENTITY_REQUIRED' for i in self.current['session']['issues']))
        self.call('apply_decision', source_id=self.current['session']['sources'][1]['source_id'], decision={'kind': 'activate'})
        self.assertEqual(self.current['active']['recipe'], second_recipe)
        self.call('apply_decision', source_id=first, decision={'kind': 'activate'})
        self.assertEqual(self.current['active']['recipe']['sections'][0]['mappings'][0]['target_role'], 'ignore')
        self.call('apply_decision', decision={'kind': 'mappings', 'decisions': [
            {'block_id': block, 'source_axis': 'column', 'source_index': 0, 'target': 'Analysis'}]})
        self.assertFalse(any(i['code'] == 'ANALYSIS_IDENTITY_REQUIRED' for i in self.current['session']['issues']))
        session = self.current['session']
        preview = self.store.command('preview_window', {'workspace_id': session['workspace_id'], 'source_id': first,
             'sheet_name': 'first', 'start_row': 2, 'row_count': 1})
        self.assertEqual(preview['rows'][0]['values'][2], '<DL')
        self.assertEqual(original, self.source.read_bytes())

    def test_batch_failure_on_second_source_rolls_back_rows_and_managed_files(self):
        database = self.source.parent / 'project.sqlite'
        self.source.write_text('Analysis,SiO2 [wt.%]\nA1,39\n', encoding='utf-8')
        self.current = self.store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(path)} for path in (self.source, self.other)]})
        self.assertTrue(self.current['session']['readiness']['ready_to_commit'])
        first_source = self.current['session']['sources'][0]['source_id']
        self.call('apply_decision', source_id=first_source, decision={'kind': 'activate'})
        preview_id = self.current['active']['plan']['planned_records'][0]['preview_id']
        self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'new',
            'sample_name': 'K-17', 'preview_ids': [preview_id]})
        pending_sample = self.current['active']['project_samples'][0]
        self.assertTrue(pending_sample['pending'])
        second_source = self.current['session']['sources'][1]['source_id']
        self.call('apply_decision', source_id=second_source, decision={'kind': 'activate'})
        preview_id = self.current['active']['plan']['planned_records'][0]['preview_id']
        self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'existing',
            'sample_id': pending_sample['sample_id'], 'preview_ids': [preview_id]})
        workspace_id = self.current['session']['workspace_id']
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("""
                CREATE TRIGGER reject_second BEFORE INSERT ON source_file
                WHEN NEW.display_name = 'second.csv'
                BEGIN SELECT RAISE(ABORT, 'second source failed'); END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'second source failed'):
            self.call('commit')
        self.assertIn(workspace_id, self.store.sessions)
        with closing(sqlite3.connect(database)) as connection:
            for table in ('source_file', 'analysis', 'measurement', 'import_batch', 'sample'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
            connection.execute('DROP TRIGGER reject_second')
        self.assertEqual(list((database.parent / 'sources').iterdir()), [])

        saved = self.call('commit')
        self.assertEqual(saved['analysis_count'], 3)
        self.assertNotIn(workspace_id, self.store.sessions)
        with closing(sqlite3.connect(database)) as connection:
            plans = connection.execute('SELECT plan_json FROM import_batch').fetchall()
            self.assertEqual(len(plans), 2)
            self.assertEqual(connection.execute('SELECT sample_id FROM sample').fetchall(), [(pending_sample['sample_id'],)])
            for (plan,) in plans:
                self.assertEqual(json.loads(plan)['workspace_commit']['commit_id'], saved['workspace_commit_id'])
        self.assertEqual(len(list((database.parent / 'sources').iterdir())), 2)
        self.assertEqual(list_project_analyses(database)['latest_import']['analysis_count'], 3)
        self.assertEqual(retract_latest_import(database)['analysis_count'], 3)
        self.assertEqual(list_project_analyses(database)['total'], 0)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM analysis').fetchone()[0], 3)

    def test_stale_revision_is_structured_and_does_not_overwrite(self):
        previous = deepcopy(self.current['session'])
        self.call('replan')
        with self.assertRaises(ImportCommandError) as caught:
            self.store.command('discard', {'workspace_id': previous['workspace_id'], 'expected_revision': previous['draft_revision']})
        self.assertEqual(caught.exception.code, 'STALE_WORKSPACE_REVISION')
        self.assertIn(previous['workspace_id'], self.store.sessions)

    def test_probe_header_warnings_are_not_reused_for_current_mapping(self):
        state = self.store.sessions[self.current['session']['workspace_id']]
        state['sources'][0]['classification']['reasons'] = [{'code': 'CLEAN_TABLE_BLANK_HEADER', 'sheet_name': 'first', 'source_column_index': 1}]
        self.call('get')
        self.assertNotIn('CLEAN_TABLE_BLANK_HEADER', [item['code'] for item in self.current['session']['issues']])

    def test_source_change_blocks_review_and_rejects_decision(self):
        self.source.write_text('changed', encoding='utf-8')
        self.call('get')
        self.assertIn('SOURCE_FINGERPRINT_MISMATCH', self.current['session']['readiness']['blocking_reason_codes'])
        with self.assertRaises(ImportCommandError):
            self.call('apply_decision', decision={'kind': 'source_inclusion', 'included': False, 'reason': 'changed'})

    def test_excluded_source_remains_visible_without_contributing_records(self):
        self.call('add_sources', sources=[{'staged_path': str(self.other)}])
        self.call('apply_decision', decision={'kind': 'source_inclusion', 'included': False, 'reason': 'Контрольный файл'})
        source = self.current['session']['sources'][1]
        self.assertFalse(source['included'])
        self.assertEqual(source['exclusion_reason'], 'Контрольный файл')
        self.assertEqual(self.current['session']['plans'][1]['planned_analysis_count'], 0)

    def test_restore_rebuilds_review_from_the_same_sources_with_saved_decisions(self):
        database = self.source.parent / 'project.sqlite'
        self.current = self.store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(path)} for path in (self.source, self.other)]})
        self.call('apply_decision', decision={'kind': 'source_inclusion', 'included': False, 'reason': 'Контрольный файл'})
        draft_path = Path(str(database) + '.import-draft.json')
        draft = json.loads(draft_path.read_text(encoding='utf-8'))
        self.assertNotIn('inspection', draft['sources'][0])
        self.assertNotIn('plan', draft['sources'][0])
        self.store = ImportWorkspaceStore()
        restored = self.store.command('restore', {'project_database_path': str(database)})['workspace']
        self.assertEqual(restored['session'], self.current['session'])
        self.assertEqual(restored['active']['plan'], self.current['active']['plan'])
        self.call('discard')
        self.assertFalse(draft_path.exists())
        self.assertEqual(self.store.command('restore', {'project_database_path': str(database)}), {'workspace': None})
        self.assertTrue(self.source.exists())
        self.assertTrue(self.other.exists())

    def test_restore_rejects_changed_source_and_unknown_draft_version(self):
        database = self.source.parent / 'project.sqlite'
        params = {'project_database_path': str(database)}
        self.store.command('create', {**params, 'sources': [{'staged_path': str(self.source)}]})
        draft_path = Path(str(database) + '.import-draft.json')
        original_draft = draft_path.read_bytes()
        self.source.write_text('Analysis,SiO2 [wt.%]\nA1,100\n', encoding='utf-8')
        restored = ImportWorkspaceStore()
        with self.assertRaises(ImportCommandError) as caught:
            restored.command('restore', params)
        self.assertEqual(caught.exception.code, 'WORKSPACE_DRAFT_INCOMPATIBLE')
        self.assertEqual(caught.exception.details['cause'], 'SOURCE_FINGERPRINT_MISMATCH')
        self.assertEqual(draft_path.read_bytes(), original_draft)
        draft = json.loads(original_draft)
        draft['schema_version'] = 999
        draft_path.write_text(json.dumps(draft), encoding='utf-8')
        with self.assertRaises(ImportCommandError) as caught:
            restored.command('restore', params)
        self.assertEqual(caught.exception.code, 'WORKSPACE_DRAFT_INCOMPATIBLE')
        self.assertEqual(restored.sessions, {})

    def test_interrupted_cleanup_does_not_restore_an_already_committed_import(self):
        database = self.other.parent / 'project.sqlite'
        params = {'project_database_path': str(database)}
        self.current = self.store.command('create', {**params, 'sources': [{'staged_path': str(self.other)}]})
        draft_path = Path(str(database) + '.import-draft.json')
        old_draft = draft_path.read_bytes()
        self.call('commit')
        self.assertFalse(draft_path.exists())
        draft_path.write_bytes(old_draft)
        self.assertEqual(ImportWorkspaceStore().command('restore', params), {'workspace': None})
        self.assertEqual(list_project_analyses(database)['total'], 2)

    def test_matching_analysis_ids_across_sources_require_review_before_commit(self):
        database = self.source.parent / 'project.sqlite'
        self.source.write_text('Analysis,SiO2 [wt.%]\nB1,39\n', encoding='utf-8')
        self.current = self.store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(path)} for path in (self.source, self.other)]})
        comparison = self.current['duplicate_comparison']
        self.assertEqual(len(comparison['groups']), 1)
        self.assertEqual([row['source_name'] for row in comparison['groups'][0]], ['first.csv', 'second.csv'])
        with self.assertRaises(ImportCommandError) as caught:
            self.call('commit')
        self.assertEqual(caught.exception.code, 'WORKSPACE_NOT_READY')
        self.assertEqual(list_project_analyses(database)['total'], 0)
        with self.assertRaises(ImportCommandError) as caught:
            self.call('apply_decision', decision={'kind': 'workspace_duplicates', 'fingerprint': 'stale'})
        self.assertEqual(caught.exception.code, 'STALE_DUPLICATE_REVIEW')
        self.call('apply_decision', decision={'kind': 'workspace_duplicates', 'fingerprint': comparison['fingerprint']})
        self.assertTrue(self.current['session']['readiness']['ready_to_commit'])
        self.call('commit')
        self.assertEqual(list_project_analyses(database)['total'], 3)

    def test_sample_assignment_preserves_reported_labels_and_links_by_id(self):
        database = self.source.parent / 'project.sqlite'
        self.source.write_text('Analysis,Sample,SiO2 [wt.%]\nA1,K-17,39\nA2,K-17,40\nA3,K-17,41\n', encoding='utf-8')
        original = self.source.read_bytes()
        self.current = self.store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(self.source)}]})
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("INSERT INTO sample VALUES ('known-id', 'K-17', '2026-09-01T00:00:00Z')")
        records = self.current['active']['plan']['planned_records']
        self.assertTrue(all(row['sample_association']['sample_id'] is None for row in records))
        selected = [row['preview_id'] for row in records]
        with self.assertRaises(ImportCommandError) as caught:
            self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'new',
                'sample_name': 'K-17', 'preview_ids': [selected[0]]})
        self.assertEqual(caught.exception.code, 'SAMPLE_NAME_EXISTS')
        self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'existing',
            'sample_id': 'known-id', 'preview_ids': [selected[0]]})
        self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'new',
            'sample_name': 'K-17 B', 'preview_ids': [selected[1]]})
        self.call('commit')
        associations = [analysis['sample_association'] for analysis in list_project_analyses(database)['analyses']]
        self.assertEqual([item['reported']['value'] for item in associations], ['K-17', 'K-17', 'K-17'])
        self.assertEqual(associations[0]['sample_id'], 'known-id')
        self.assertEqual(associations[1]['assignment']['sample_name'], 'K-17 B')
        self.assertNotEqual(associations[1]['sample_id'], 'known-id')
        self.assertIsNone(associations[2]['sample_id'])
        self.assertEqual(self.source.read_bytes(), original)

    def test_failed_add_does_not_lose_queue_or_revision(self):
        before = deepcopy(self.current)
        with self.assertRaises(ImportCommandError):
            self.call('add_sources', sources=[{'staged_path': str(self.other)}, {'staged_path': 'missing.xlsx'}])
        self.call('get')
        self.assertEqual(self.current, before)

    def test_point_links_write_reversible_journal_with_exact_sample_scope(self):
        database = self.source.parent / 'project.sqlite'
        text = 'Analysis,Sample,SiO2 [wt.%]\nP1,K-17,39\nP2,K-17,40\nP3,K-17,41\n'
        self.source.write_text(text, encoding='utf-8')
        self.current = self.store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(self.source)}]})
        records = self.current['active']['plan']['planned_records']
        self.call('apply_decision', decision={'kind': 'sample_assignment', 'mode': 'new',
            'sample_name': 'K-17', 'preview_ids': [record['preview_id'] for record in records[:2]]})
        self.call('commit')

        def call(command, **payload):
            return handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()), 'command': command,
                'payload': {'project_database_path': str(database), **payload}})

        analyses = list_project_analyses(database)['analyses']
        samples = call('project.samples.list')['result']
        self.assertEqual(samples[0]['analysis_count'], 2)
        sample_id = samples[0]['sample_id']
        ids = [analysis['analysis_id'] for analysis in analyses]
        fields = {'sample_id': sample_id, 'point_name': 'KIV-01', 'link_type': 'same_point', 'actor': 'Иванов'}
        denied = call('analytical_point.create', **fields, analysis_ids=ids[1:])
        self.assertEqual(denied['error']['code'], 'POINT_SAMPLE_MISMATCH')
        point = call('analytical_point.create', **fields, analysis_ids=ids[:2])['result']
        point_id = point['analytical_point_id']
        self.assertEqual(point['journal']['parameters']['analysis_ids'], ids[:2])
        self.assertEqual(point['journal']['inverse_action']['action'], 'unlink_analytical_point')
        self.assertEqual(len(call('analytical_point.analyses', point_id=point_id)['result']), 2)
        change = {'point_id': point_id, 'analysis_id': ids[0], 'actor': 'Иванов'}
        removed = call('analytical_point.link.set', **change)['result']
        self.assertEqual(removed['inverse_action']['parameters']['link_type'], 'same_point')
        restored = call('analytical_point.link.set', **change, link_type='same_point')['result']
        self.assertEqual(restored['parameters']['analysis_ids'], [ids[0]])
        self.assertEqual(len(call('analytical_point.analyses', point_id=point_id)['result']), 2)
        self.assertEqual(list_project_analyses(database)['analyses'], analyses)
        self.assertEqual(self.source.read_text(encoding='utf-8'), text)

    def test_single_clean_source_ready_and_discard_only_session(self):
        result = self.store.command('create', {'sources': [{'staged_path': str(self.other)}]})
        session = result['session']
        self.assertTrue(session['readiness']['ready_to_commit'])
        self.assertEqual(result['active']['classification']['mode'], 'clean_table_fast')
        self.store.command('discard', {'workspace_id': session['workspace_id'], 'expected_revision': 0})
        self.assertTrue(self.other.exists())

    def test_bulk_scope_is_revision_bound(self):
        self.current = self.store.command('create', {'sources': [{'staged_path': str(FIXTURE)}]})
        scopes = self.current['active']['bulk_unit_scopes']
        self.assertTrue(scopes)
        self.call('replan')
        with self.assertRaises(ImportCommandError) as caught:
            self.call('apply_bulk_decision', decision={'kind': 'unit', 'unit': 'wt.%', 'bulk_scope_id': scopes[0]['bulk_scope_id']})
        self.assertEqual(caught.exception.code, 'STALE_BULK_SCOPE')

    def test_ndjson_commands_and_session_schema(self):
        response = handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
            'command': 'import.workspace.create', 'payload': {'sources': [{'staged_path': str(self.other)}]}})
        self.assertNotIn('error', response)
        from scripts.validate_contracts import _validate
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/import-workspace-session.schema.json').read_text())
        _validate(response['result']['session'], schema, schema, {})
