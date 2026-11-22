from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from petrolab.desktop_workflow import list_project_analyses, list_project_mineral_identifications
from petrolab.import_workspace import ImportWorkspaceStore
from petrolab.import_preview import ImportCommandError
from petrolab.import_apply import apply_import_plan, open_project
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
        reopened = list_project_mineral_identifications(database)
        self.assertEqual([row['status'] for row in reopened['identifications']], ['verified', 'conflict', 'missing_reported'])
        self.assertEqual(reopened['identifications'][0]['accepted'], records[0]['mineral_verification']['accepted'])
        with patch('petrolab.mineral_verification.EXTENDED_RULESET_VERSION', 'qa-next-ruleset'):
            reviewed = list_project_mineral_identifications(database)['identifications'][0]
        self.assertEqual(reviewed['status'], 'stale')
        self.assertIsNone(reviewed['accepted'])
        self.assertEqual(reviewed['previous_acceptance'], reopened['identifications'][0]['accepted'])
        self.assertIn('accepted_assignment_stale', reviewed['issues'])
        self.assertEqual(list_project_mineral_identifications(database), reopened)
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

    def test_published_epma_rows_keep_phase_labels_and_unresolved_cases(self):
        fixtures = Path(__file__).resolve().parents[1] / 'fixtures/import/mineral-recognition'
        expected = {
            'bec-dovaga.csv': [('olivine', 'high', 'consistent'), ('olivine', 'high', 'consistent')],
            'mount-agri.csv': [('orthopyroxene', 'medium', 'low_confidence'),
                               ('orthopyroxene', 'medium', 'low_confidence'),
                               ('clinopyroxene', 'medium', 'low_confidence')],
            'epma-averages.csv': [('plagioclase', 'high', 'consistent'),
                                  (None, 'ambiguous', 'low_confidence'),
                                  ('Ti-rich calcic amphibole', 'medium', 'low_confidence'),
                                  (None, 'unresolved', 'insufficient_input')],
        }
        for name, target_cases in expected.items():
            with self.subTest(source=name):
                fixture = fixtures / name
                source = Path(self.temp.name) / name
                original = fixture.read_bytes()
                source.write_bytes(original)
                self.current = self.store.command('create', {'sources': [{'staged_path': str(source)}]})
                self.decide(kind='verify_minerals')
                reviewed = self.current['active']['plan']['planned_records']
                outcomes = [record['mineral_verification'] for record in reviewed]
                self.assertEqual([(r['prediction'], r['confidence'], r['status']) for r in outcomes], target_cases)
                self.assertTrue(all(r['accepted'] is None for r in outcomes))
                if name == 'epma-averages.csv':
                    self.assertEqual({r['target'] for r in outcomes[1]['candidates']}, {'clinopyroxene', 'calcic amphibole'})
                    with self.assertRaises(ImportCommandError) as error:
                        self.decide(kind='accept_mineral', preview_id=reviewed[1]['preview_id'])
                    self.assertEqual(error.exception.code, 'MINERAL_UNRESOLVED')
                    self.decide(kind='accept_mineral', scope_id=self.current['active']['mineral_acceptance_scopes'][0]['scope_id'])

                database = source.with_suffix('.sqlite')
                apply_import_plan(database, source, self.current['active']['recipe'])
                saved = list_project_mineral_identifications(database)['identifications']
                self.assertEqual([row['reported_mineral'] for row in saved], [row['reported_mineral'] for row in outcomes])
                if name == 'epma-averages.csv':
                    self.assertEqual(saved[0]['accepted']['target'], 'plagioclase')
                    self.assertEqual([r['status'] for r in saved], ['verified', 'low_confidence', 'low_confidence', 'insufficient_input'])
                    row = list_project_analyses(database)['analyses'][-1]
                    self.assertEqual(row['measurements']['K2O']['raw_token'], 'bdl')
                    self.assertIsNone(row['measurements']['K2O']['numeric_value'])
                    self.assertEqual(row['measurements']['FeOt']['raw_token'], '7.22')
                    self.assertEqual(row['measurements']['FeOt']['source_cell'], 'J5')
                self.assertEqual(source.read_bytes(), original)

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
