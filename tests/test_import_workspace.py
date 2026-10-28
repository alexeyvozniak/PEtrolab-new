from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import uuid

from petrolab.import_preview import ImportCommandError
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
        self.assertFalse(session['readiness']['ready_to_commit'])
        self.assertIn('MULTI_SOURCE_COMMIT_UNAVAILABLE', session['readiness']['blocking_reason_codes'])
        self.assertEqual(original, self.source.read_bytes())

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
