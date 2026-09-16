from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.import_preview import ImportCommandError
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.desktop_workflow import decide_project_mineral_assignment, list_project_analyses, list_project_mineral_identifications
from petrolab.mineral_verification import verify_record
from petrolab.mineral_recognition_extended import recognize_mineral_extended


class ImportMineralVerificationTests(unittest.TestCase):
    def test_v11_upgrade_preserves_decision_history_order_and_backup(self):
        import shutil
        from unittest.mock import patch
        from petrolab import import_apply
        historical = Path(self.temp.name) / 'v11-migrations'
        historical.mkdir()
        for migration in import_apply.MIGRATIONS.glob('*.sql'):
            if int(migration.name.split('_')[0]) <= 11:
                shutil.copyfile(migration, historical / migration.name)
        database = Path(self.temp.name) / 'old-project.sqlite'
        with patch.object(import_apply, 'MIGRATIONS', historical):
            apply_import_plan(database, self.path, self.current['active']['recipe'])
            row = list_project_mineral_identifications(database)['identifications'][0]
            args = (database, row['analysis_id'])
            tail = (row['input_fingerprint'], row['ruleset_version'])
            decide_project_mineral_assignment(*args, row['prediction'], *tail, 'Первое решение')
            decide_project_mineral_assignment(*args, None, *tail, 'Снять решение')
            with closing(open_project(database)) as connection:
                before = [tuple(r) for r in connection.execute('SELECT * FROM mineral_assignment_decision ORDER BY rowid')]
        with closing(open_project(database)) as connection:
            after = [tuple(r) for r in connection.execute('SELECT * FROM mineral_assignment_decision ORDER BY rowid')]
            self.assertEqual(before, after)
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len(list(database.parent.glob('old-project.sqlite.before-v12-*.bak'))), 1)
        self.assertIsNone(list_project_mineral_identifications(database)['identifications'][0]['accepted'])

    def test_scientific_snapshot_matches_the_reused_source_manifest(self):
        import hashlib
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'docs/qa/classifier-source-manifest.json').read_text(encoding='utf-8'))
        for name, expected in manifest['sha256_utf8_lf'].items():
            content = (root / 'src/petrolab' / name).read_text(encoding='utf-8')
            self.assertEqual(hashlib.sha256(content.encode()).hexdigest(), expected, name)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'mineral.csv'
        self.path.write_text('Analysis,Mineral,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%)\n'
                             'A1,olivine,40,0,50,0,0,0,10\nA2,garnet,40,0,50,0,0,0,10\nA3,,40,0,50,0,0,0,10\n', encoding='utf-8')
        self.original = self.path.read_bytes()
        self.store = ImportWorkspaceStore()
        self.current = self.store.command('create', {'sources': [{'staged_path': str(self.path)}]})

    def decide(self, **decision):
        session = self.current['session']
        self.current = self.store.command('apply_decision', {'workspace_id': session['workspace_id'],
            'expected_revision': session['draft_revision'], 'source_id': session['active_source_id'], 'decision': decision})
        return self.current

    def test_stages_group_acceptance_and_persisted_reported_prediction_accepted(self):
        self.assertNotIn('mineral_verification', self.current['active']['plan']['planned_records'][0])
        self.decide(kind='verify_minerals')
        records = self.current['active']['plan']['planned_records']
        self.assertEqual([r['mineral_verification']['status'] for r in records], ['consistent', 'conflict', 'missing_reported'])
        reference = recognize_mineral_extended(dict(SiO2=40, Al2O3=0, MgO=50, CaO=0, Na2O=0, K2O=0, FeO=10))
        self.assertEqual(records[0]['mineral_verification']['prediction'], reference.target)
        scope = self.current['active']['mineral_acceptance_scopes'][0]
        self.assertEqual(scope['count'], 1)
        self.decide(kind='accept_mineral', scope_id=scope['scope_id'])
        with self.assertRaises(ImportCommandError):
            self.decide(kind='accept_mineral', scope_id=scope['scope_id'])
        records = self.current['active']['plan']['planned_records']
        self.assertEqual(records[0]['mineral_verification']['status'], 'verified')
        self.assertEqual(records[1]['reported_mineral']['value'], 'garnet')
        database = Path(self.temp.name) / 'project.sqlite'
        apply_import_plan(database, self.path, self.current['active']['recipe'])
        with closing(open_project(database)) as connection:
            values = connection.execute('SELECT reported_mineral_json, mineral_verification_json FROM analysis_import_semantics ORDER BY rowid').fetchall()
            self.assertEqual(json.loads(values[0][1])['accepted']['target'], 'olivine')
            self.assertEqual(json.loads(values[1][0])['value'], 'garnet')
            self.assertIsNone(json.loads(values[1][1])['accepted'])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_missing_censored_wrong_units_and_iron_are_not_zero(self):
        record = self.current['active']['plan']['planned_records'][0]
        for mutation in [{'value_status': 'missing', 'raw_token': None}, {'value_status': 'below_detection_limit', 'raw_token': '<DL'},
                         {'unit': 'ppm'}, {'reported_fe_form': 'unresolved'}]:
            changed = deepcopy(record)
            changed['measurements'][0].update(mutation)
            result = verify_record(changed)
            self.assertEqual(result['status'], 'insufficient_input')
            self.assertIsNone(result['prediction'])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_accepted_assignment_is_invalidated_by_changed_evidence(self):
        self.decide(kind='verify_minerals')
        first = self.current['active']['plan']['planned_records'][0]
        self.decide(kind='accept_mineral', preview_id=first['preview_id'], input_fingerprint=first['mineral_verification']['input_fingerprint'])
        accepted = self.current['active']['plan']['planned_records'][0]['mineral_verification']['accepted']
        changed = deepcopy(first)
        changed['reported_mineral']['value'] = 'garnet'
        result = verify_record(changed, accepted)
        self.assertEqual(result['status'], 'stale_assignment')
        self.assertIn('accepted_assignment_stale', result['issues'])

    def test_post_import_decision_is_append_only_stale_safe_and_reversible(self):
        self.decide(kind='verify_minerals')
        database = Path(self.temp.name) / 'project.sqlite'
        apply_import_plan(database, self.path, self.current['active']['recipe'])
        review = list_project_mineral_identifications(database)
        conflict = next(item for item in review['identifications'] if item['status'] == 'conflict')

        decided = decide_project_mineral_assignment(
            database,
            conflict['analysis_id'],
            conflict['prediction'],
            conflict['input_fingerprint'],
            conflict['ruleset_version'],
            'Принято после проверки конфликта',
        )
        self.assertEqual(decided['verification']['status'], 'verified')
        projected = list_project_analyses(database, analysis_id=conflict['analysis_id'])['analyses'][0]
        self.assertEqual(projected['mineral_assignment']['target'], conflict['prediction'])
        self.assertEqual(projected['reported_mineral']['value'], 'garnet')

        with self.assertRaises(ImportCommandError) as stale:
            decide_project_mineral_assignment(
                database, conflict['analysis_id'], conflict['prediction'], 'stale',
                conflict['ruleset_version'], 'Устаревшее решение',
            )
        self.assertEqual(stale.exception.code, 'STALE_MINERAL_INPUT')

        cleared = decide_project_mineral_assignment(
            database,
            conflict['analysis_id'],
            None,
            conflict['input_fingerprint'],
            conflict['ruleset_version'],
            'Вернуть в очередь проверки',
        )
        self.assertIsNone(cleared['decision'])
        with closing(open_project(database)) as connection:
            rows = connection.execute(
                'SELECT decision_kind, target FROM mineral_assignment_decision WHERE analysis_id = ? ORDER BY rowid',
                (conflict['analysis_id'],),
            ).fetchall()
        self.assertEqual([(row[0], row[1]) for row in rows], [('accept_suggestion', conflict['prediction']), ('clear', None)])
        self.assertEqual(list_project_mineral_identifications(database)['status_counts']['conflict'], 1)

    def test_post_import_clear_overrides_an_assignment_accepted_during_import(self):
        self.decide(kind='verify_minerals')
        accepted_scope = self.current['active']['mineral_acceptance_scopes'][0]
        self.decide(kind='accept_mineral', scope_id=accepted_scope['scope_id'])
        database = Path(self.temp.name) / 'accepted.sqlite'
        apply_import_plan(database, self.path, self.current['active']['recipe'])
        review = list_project_mineral_identifications(database)
        self.assertTrue(
            any(item['status'] == 'verified' for item in review['identifications']),
            review['identifications'],
        )
        verified = next(item for item in review['identifications'] if item['status'] == 'verified')

        decide_project_mineral_assignment(
            database,
            verified['analysis_id'],
            None,
            verified['input_fingerprint'],
            verified['ruleset_version'],
            'Снять ранее принятое решение',
        )

        projected = list_project_analyses(database, analysis_id=verified['analysis_id'])['analyses'][0]
        self.assertNotIn('mineral_assignment', projected)
        refreshed = next(
            item for item in list_project_mineral_identifications(database)['identifications']
            if item['analysis_id'] == verified['analysis_id']
        )
        self.assertEqual(refreshed['status'], 'consistent')
        self.assertIsNone(refreshed['accepted'])

    def test_project_alias_requires_confirmation_and_is_project_scoped(self):
        database = Path(self.temp.name) / 'aliases.sqlite'
        store = ImportWorkspaceStore()
        result = store.command('create', {'project_database_path': str(database), 'sources': [{'staged_path': str(self.path)}]})
        session = result['session']
        params = {'workspace_id': session['workspace_id'], 'expected_revision': session['draft_revision'],
                  'source_id': session['active_source_id'], 'decision': {'kind': 'alias', 'raw_header': 'Lab silica', 'canonical_field': 'SiO2'}}
        with self.assertRaises(ValueError):
            store.command('apply_decision', params)
        params['decision']['confirmed'] = True
        store.command('apply_decision', params)
        self.path.write_text('Analysis,Lab silica (wt.%)\nB1,40\n', encoding='utf-8')
        linked = ImportWorkspaceStore().command('create', {'project_database_path': str(database), 'sources': [{'staged_path': str(self.path)}]})
        field = linked['active']['recipe']['sections'][0]['mappings'][1]
        self.assertEqual(field['canonical_field'], 'SiO2')
        self.assertEqual(field['recognition']['confidence'], 'project_alias')
        separate = ImportWorkspaceStore().command('create', {'sources': [{'staged_path': str(self.path)}]})
        self.assertEqual(separate['active']['recipe']['sections'][0]['mappings'][1]['target_role'], 'ignore')

    def test_manual_range_survives_review_import_and_clear(self):
        section = self.current['active']['recipe']['sections'][0]
        self.decide(kind='verify_minerals')
        self.decide(kind='accept_mineral', scope_id=self.current['active']['mineral_acceptance_scopes'][0]['scope_id'])
        self.decide(kind='semantic', role='mineral', value='Форстерит', block_id=section['block_id'],
                    range={'start_row': 2, 'end_row': 2, 'start_column': 0, 'end_column': 8})
        record = self.current['active']['plan']['planned_records'][0]
        self.assertEqual(record['mineral_verification']['status'], 'manually_assigned')
        self.assertEqual(record['mineral_verification']['accepted']['target'], 'forsterite')
        self.assertNotIn('accepted_assignment_stale', record['mineral_verification']['issues'])
        database = Path(self.temp.name) / 'manual.sqlite'
        apply_import_plan(database, self.path, self.current['active']['recipe'])
        review = list_project_mineral_identifications(database)
        manual = next(v for v in review['identifications'] if v['status'] == 'manually_assigned')
        self.assertEqual(manual['accepted']['target'], 'forsterite')
        self.assertEqual(manual['reported_mineral'], 'olivine')
        decide_project_mineral_assignment(database, manual['analysis_id'], None,
            manual['input_fingerprint'], manual['ruleset_version'], 'Снять ручное назначение')
        refreshed = next(v for v in list_project_mineral_identifications(database)['identifications'] if v['analysis_id'] == manual['analysis_id'])
        self.assertIsNone(refreshed['accepted'])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_manual_post_import_catalog_validation_reason_and_history(self):
        database = Path(self.temp.name) / 'manual-post.sqlite'
        apply_import_plan(database, self.path, self.current['active']['recipe'])
        review = list_project_mineral_identifications(database)
        row = review['identifications'][0]
        self.assertIn('forsterite', review['mineral_options'])
        args = (database, row['analysis_id'])
        tail = (row['input_fingerprint'], row['ruleset_version'])
        with self.assertRaises(ImportCommandError):
            decide_project_mineral_assignment(*args, 'made-up-mineral', *tail, 'Проверка')
        with self.assertRaises(ImportCommandError):
            decide_project_mineral_assignment(*args, 'forsterite', *tail, ' ')
        result = decide_project_mineral_assignment(*args, 'Форстерит', *tail, 'Проверено по независимым данным')
        self.assertEqual(result['decision']['target'], 'forsterite')
        self.assertEqual(result['decision']['decision_kind'], 'manual_assignment')
        with closing(open_project(database)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM mineral_assignment_decision').fetchone()[0], 1)
        self.assertEqual(self.path.read_bytes(), self.original)
