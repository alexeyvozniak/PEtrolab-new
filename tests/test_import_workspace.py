from copy import deepcopy
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

from petrolab.import_preview import ImportCommandError
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab import import_apply
from petrolab.desktop_workflow import list_project_analyses
from petrolab.import_apply import retract_latest_import
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
        self.assertFalse(session['readiness']['ready_to_commit'])
        self.assertNotIn('MULTI_SOURCE_COMMIT_UNAVAILABLE', session['readiness']['blocking_reason_codes'])
        self.assertEqual(original, self.source.read_bytes())

    def test_two_ready_sources_commit_as_one_atomic_workspace(self):
        third = Path(self.temp.name) / 'third.csv'
        third.write_text('Analysis,MgO [wt.%]\nC1,30\nC2,31\n', encoding='utf-8')
        database = Path(self.temp.name) / 'project.sqlite'
        first_bytes, second_bytes = self.other.read_bytes(), third.read_bytes()
        store = ImportWorkspaceStore()
        current = store.command('create', {'project_database_path': str(database), 'sources': [
            {'staged_path': str(self.other), 'original_display_path': 'second.csv'},
            {'staged_path': str(third), 'original_display_path': 'third.csv'},
        ]})
        session = current['session']

        self.assertTrue(session['readiness']['ready_to_commit'])
        committed = store.command('commit', {'workspace_id': session['workspace_id'],
            'expected_revision': session['draft_revision']})

        self.assertEqual(committed['source_count'], 2)
        self.assertEqual(committed['analysis_count'], 4)
        self.assertEqual(len(committed['import_batches']), 2)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_workspace_commit').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_batch').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT COUNT(DISTINCT workspace_commit_id) FROM import_batch').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM analysis').fetchone()[0], 4)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_workspace_draft').fetchone()[0], 0)
        projection = list_project_analyses(database)
        self.assertEqual(projection['source_count'], 2)
        self.assertEqual(projection['import_batch_count'], 1)
        self.assertEqual(projection['latest_import']['source_count'], 2)
        retracted = retract_latest_import(database)
        self.assertEqual(retracted['source_count'], 2)
        self.assertEqual(retracted['analysis_count'], 4)
        self.assertEqual(list_project_analyses(database)['total'], 0)
        self.assertNotIn(session['workspace_id'], store.sessions)
        self.assertEqual(self.other.read_bytes(), first_bytes)
        self.assertEqual(third.read_bytes(), second_bytes)

    def test_persistence_failure_rolls_back_every_source_and_keeps_draft(self):
        third = Path(self.temp.name) / 'third.csv'
        third.write_text('Analysis,MgO [wt.%]\nC1,30\n', encoding='utf-8')
        database = Path(self.temp.name) / 'project.sqlite'
        store = ImportWorkspaceStore()
        current = store.command('create', {'project_database_path': str(database), 'sources': [
            {'staged_path': str(self.other)}, {'staged_path': str(third)},
        ]})
        session = current['session']
        original_write = import_apply._write_prepared_import
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('simulated second-source persistence failure')
            return original_write(*args, **kwargs)

        with patch('petrolab.import_apply._write_prepared_import', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'second-source'):
                store.command('commit', {'workspace_id': session['workspace_id'],
                    'expected_revision': session['draft_revision']})

        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM source_file').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_batch').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM analysis').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_workspace_commit').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_workspace_draft').fetchone()[0], 1)
        self.assertEqual(list((Path(self.temp.name) / 'sources').glob('*')), [])
        self.assertIn(session['workspace_id'], store.sessions)

    def test_draft_restores_only_when_every_source_fingerprint_matches(self):
        database = Path(self.temp.name) / 'project.sqlite'
        store = ImportWorkspaceStore()
        created = store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(self.other)}]})
        workspace_id = created['session']['workspace_id']
        revision = created['session']['draft_revision']

        restored = ImportWorkspaceStore().command('restore', {'project_database_path': str(database)})
        self.assertEqual(restored['restore_status'], 'restored')
        self.assertEqual(restored['session']['workspace_id'], workspace_id)
        self.assertEqual(restored['session']['draft_revision'], revision)
        with closing(sqlite3.connect(database)) as connection:
            draft_json = connection.execute('SELECT draft_json FROM import_workspace_draft').fetchone()[0]
        self.assertNotIn('planned_records', draft_json)

        self.other.write_text('Analysis,SiO2 [wt.%]\nB1,99\n', encoding='utf-8')
        with self.assertRaises(ImportCommandError) as mismatch:
            ImportWorkspaceStore().command('restore', {'project_database_path': str(database)})
        self.assertEqual(mismatch.exception.code, 'DRAFT_SOURCE_MISMATCH')

    def test_autosaved_revision_restores_and_rejects_incompatible_schema(self):
        database = Path(self.temp.name) / 'project.sqlite'
        store = ImportWorkspaceStore()
        created = store.command('create', {'project_database_path': str(database),
            'sources': [{'staged_path': str(self.other)}]})
        workspace_id = created['session']['workspace_id']
        changed = store.command('replan', {'workspace_id': workspace_id,
            'expected_revision': created['session']['draft_revision']})

        restored = ImportWorkspaceStore().command('restore', {'project_database_path': str(database)})
        self.assertEqual(restored['session']['draft_revision'], changed['session']['draft_revision'])
        self.assertEqual(restored['session']['workspace_id'], workspace_id)

        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('UPDATE import_workspace_draft SET schema_version = 99 WHERE workspace_id = ?',
                               (workspace_id,))
        with self.assertRaises(ImportCommandError) as incompatible:
            ImportWorkspaceStore().command('restore', {'project_database_path': str(database)})
        self.assertEqual(incompatible.exception.code, 'DRAFT_SCHEMA_INCOMPATIBLE')

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

    def test_failed_add_does_not_lose_queue_or_revision(self):
        before = deepcopy(self.current)
        with self.assertRaises(ImportCommandError):
            self.call('add_sources', sources=[{'staged_path': str(self.other)}, {'staged_path': 'missing.xlsx'}])
        self.call('get')
        self.assertEqual(self.current, before)

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
        linked = [item for item in self.current['session']['issues'] if item['code'] == 'UNIT_REQUIRES_REVIEW']
        self.assertTrue(linked)
        self.assertEqual({item['bulk_scope_id'] for item in linked}, {scopes[0]['bulk_scope_id']})
        self.call('replan')
        with self.assertRaises(ImportCommandError) as caught:
            self.call('apply_bulk_decision', decision={'kind': 'unit', 'unit': 'wt.%', 'bulk_scope_id': scopes[0]['bulk_scope_id']})
        self.assertEqual(caught.exception.code, 'STALE_BULK_SCOPE')

    def test_bulk_unit_is_one_decision_and_empty_plan_is_only_a_derived_notice(self):
        source = Path(self.temp.name) / 'units.csv'
        original = b'Analysis,SiO2,MgO\nA1,40,50\nA2,41,49\n'
        source.write_bytes(original)
        self.current = self.store.command('create', {'sources': [{'staged_path': str(source)}]})
        scope = self.current['active']['bulk_unit_scopes'][0]
        unit_issues = [item for item in self.current['session']['issues'] if item['code'] == 'UNIT_REQUIRES_REVIEW']
        self.assertEqual(len(unit_issues), 2)
        self.assertEqual({item['bulk_scope_id'] for item in unit_issues}, {scope['bulk_scope_id']})
        empty_plan = next(item for item in self.current['session']['issues'] if item['code'] == 'IMPORT_PLAN_EMPTY')
        self.assertFalse(empty_plan['blocking'])

        self.call('apply_bulk_decision', decision={
            'kind': 'unit', 'unit': 'wt.%', 'bulk_scope_id': scope['bulk_scope_id']})
        self.assertFalse(any(item['code'] in {'UNIT_REQUIRES_REVIEW', 'IMPORT_PLAN_EMPTY'}
                             for item in self.current['session']['issues']))
        self.assertTrue(self.current['session']['readiness']['ready_to_commit'])
        self.assertEqual(source.read_bytes(), original)

    def test_recognized_wrong_unit_is_corrected_once_without_changing_source(self):
        source = Path(self.temp.name) / 'recognized-wrong-unit.csv'
        original = b'Analysis,SiO2 (at.%),MgO (at.%)\nA1,40,50\nA2,41,49\n'
        source.write_bytes(original)
        self.current = self.store.command('create', {'sources': [{'staged_path': str(source)}]})
        scope = self.current['active']['bulk_unit_override_scopes'][0]

        self.assertEqual(scope['current_unit'], 'at.%')
        self.assertEqual(scope['field_count'], 2)
        self.call('apply_bulk_decision', decision={
            'kind': 'unit_override', 'unit': 'wt.%', 'bulk_scope_id': scope['bulk_scope_id']})

        measurements = [mapping for section in self.current['active']['recipe']['sections']
                        for mapping in section['mappings']
                        if mapping['target_role'] == 'measurement']
        self.assertEqual({mapping['unit'] for mapping in measurements}, {'wt.%'})
        self.assertTrue(self.current['session']['readiness']['ready_to_commit'])
        self.assertEqual(source.read_bytes(), original)

    def test_whitespace_only_trailing_row_is_not_an_unresolvable_analysis(self):
        source = Path(self.temp.name) / 'whitespace.csv'
        original = b'Analysis,SiO2 [wt.%]\nA1,40\n , \t\n'
        source.write_bytes(original)
        result = self.store.command('create', {'sources': [{'staged_path': str(source)}]})

        self.assertTrue(result['session']['readiness']['ready_to_commit'])
        self.assertEqual(result['active']['plan']['summary']['planned_analysis_count'], 1)
        self.assertFalse(any(item['code'] == 'ANALYSIS_IDENTITY_REQUIRED'
                             for item in result['session']['issues']))
        self.assertEqual(source.read_bytes(), original)

    def test_ndjson_commands_and_session_schema(self):
        response = handle_request({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
            'command': 'import.workspace.create', 'payload': {'sources': [{'staged_path': str(self.other)}]}})
        self.assertNotIn('error', response)
        from scripts.validate_contracts import _validate
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/import-workspace-session.schema.json').read_text())
        _validate(response['result']['session'], schema, schema, {})
