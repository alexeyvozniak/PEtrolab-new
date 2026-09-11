from contextlib import closing
from copy import deepcopy
from pathlib import Path
import tempfile
import sqlite3
import shutil
from unittest.mock import patch
import unittest

from petrolab.desktop_workflow import suggest_import_recipe, list_project_analyses
from petrolab.import_preview import (ImportCommandError, inspect_source, create_import_plan,
                                     semantic_fingerprint, value_status, reported_fe_form)
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.manual_mapping import revise_import_mappings
from test_import_preview import fixture_recipe, FIXTURE


class ImportHardeningTests(unittest.TestCase):
    def test_additive_migration_backs_up_and_preserves_old_rows(self):
        from petrolab.import_apply import MIGRATIONS
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            old_migrations = folder / 'migrations'
            old_migrations.mkdir()
            for migration in MIGRATIONS.glob('*.sql'):
                if int(migration.name.split('_')[0]) <= 8:
                    shutil.copyfile(migration, old_migrations / migration.name)
            database = folder / 'old.sqlite'
            with patch('petrolab.import_apply.MIGRATIONS', old_migrations):
                with closing(open_project(database)) as connection:
                    self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 8)
                    connection.execute('INSERT INTO sample (sample_id, sample_name, created_at) VALUES (?, ?, ?)', ('old-sample', 'Keep original label', '2026-09-01T00:00:00Z'))
                    connection.commit()
            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 13)
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(connection.execute('SELECT sample_name FROM sample WHERE sample_id = ?', ('old-sample',)).fetchone()[0], 'Keep original label')
            backups = list(folder.glob('old.sqlite.before-v9-*.bak'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 8)

    def test_ignore_all_identity_blocks_apply_then_mapping_repairs_it(self):
        recipe = fixture_recipe()
        decisions = [{"block_id": section["block_id"], "source_axis": "column",
                      "source_index": field["source_column_index"], "target": "Ignore"}
                     for section in recipe["sections"] for field in section["mappings"]
                     if field["target_role"] == "identity"]
        revised = revise_import_mappings(FIXTURE, recipe, decisions)["recipe"]
        plan = create_import_plan(inspect_source(FIXTURE), revised)
        self.assertFalse(plan["ready_to_commit"])
        self.assertEqual(plan["issues"][0]["code"], "ANALYSIS_IDENTITY_REQUIRED")
        self.assertEqual(plan["issues"][0]["row_number"], 3)
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "project.sqlite"
            with self.assertRaises(ImportCommandError) as caught:
                apply_import_plan(database, FIXTURE, revised)
            self.assertEqual(caught.exception.code, "ANALYSIS_IDENTITY_REQUIRED")
            self.assertFalse(database.exists())
        restored = revise_import_mappings(FIXTURE, revised, [dict(item, target="Analysis") for item in decisions])["recipe"]
        self.assertTrue(create_import_plan(inspect_source(FIXTURE), restored)["ready_to_commit"])

    def test_blank_identity_is_not_a_measurement(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "blank.csv"
            source.write_text('Analysis,SiO2 (wt.%)\n   ,40\nA2,41\n', encoding="utf-8")
            recipe = suggest_import_recipe(source)["recipe"]
            plan = create_import_plan(inspect_source(source), recipe)
            self.assertFalse(plan["ready_to_commit"])
            self.assertEqual(plan["issues"][0]["row_number"], 2)

    def test_tokens_survive_plan_sqlite_and_cell_provenance(self):
        tokens = ['<0.01', '<DL', 'bdl', 'BDL', 'n.d.', 'N.D.', 'nd', '', '0', 'bad']
        expected = ['below_detection_limit'] * 4 + ['not_determined'] * 3 + ['missing', 'numeric', 'non_numeric']
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "tokens.csv"
            source.write_text('Analysis,F (wt.%)\n' + ''.join(f'A{i},{token}\n' for i, token in enumerate(tokens)), encoding="utf-8")
            original = source.read_bytes()
            recipe = suggest_import_recipe(source)["recipe"]
            plan = create_import_plan(inspect_source(source), recipe)
            values = [row["measurements"][0] for row in plan["planned_records"]]
            self.assertEqual([item["value_status"] for item in values], expected)
            self.assertEqual(values[0]["detection_limit"], 0.01)
            self.assertTrue(all(item["detection_limit"] is None for item in values[1:]))
            database = Path(folder) / "project.sqlite"
            apply_import_plan(database, source, recipe)
            with closing(open_project(database)) as connection:
                for table in ['measurement', 'source_row_provenance', 'source_cell_provenance']:
                    rows = connection.execute(f'SELECT raw_token, value_status FROM {table} ORDER BY rowid').fetchall()
                    self.assertEqual([tuple(row) for row in rows], list(zip([token or None for token in tokens], expected)))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list_project_analyses(database)["total"], len(tokens))

    def test_fe_source_forms_never_imply_conversion(self):
        forms = {'FeO': 'FeO', 'FeOt': 'FeOt', 'FeO total': 'FeOt', 'Fe2O3': 'Fe2O3',
                 'Fe2O3t': 'Fe2O3t', 'total Fe as Fe2O3': 'Fe2O3t', 'Fe': 'unresolved',
                 'Fe uncertain': 'unresolved'}
        for header, expected in forms.items():
            with self.subTest(header=header), tempfile.TemporaryDirectory() as folder:
                self.assertEqual(reported_fe_form(header), expected)
                source = Path(folder) / 'iron.csv'
                source.write_text(f'Analysis,{header} (wt.%)\nA1,10\nA2,11\n', encoding='utf-8')
                recipe = suggest_import_recipe(source)['recipe']
                plan = create_import_plan(inspect_source(source), recipe)
                value = plan['planned_records'][0]['measurements'][0]
                self.assertEqual(value['reported_fe_form'], expected)
                self.assertEqual(value['fe_handling'], 'strictly_as_reported_no_conversion')
                self.assertEqual(value['raw_token'], '10')
                self.assertEqual(any(w['code'] == 'FE_STRICTLY_REPORTED' for w in plan['warnings']), expected == 'unresolved')
                database = Path(folder) / 'project.sqlite'
                apply_import_plan(database, source, recipe)
                with closing(open_project(database)) as connection:
                    self.assertEqual(connection.execute('SELECT reported_fe_form FROM measurement LIMIT 1').fetchone()[0], expected)

    def test_nonfinite_is_not_numeric(self):
        for token in ['NaN', 'Infinity', '-inf']:
            self.assertEqual(value_status(token), 'non_numeric')
