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
        self.assertEqual(result['status'], 'conflict')
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
