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
                                     semantic_fingerprint, value_status, reported_fe_form, _qualifier)
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.manual_mapping import revise_import_mappings
from test_import_preview import fixture_recipe, FIXTURE


class ImportHardeningTests(unittest.TestCase):
    def test_detection_limit_notation_preserves_finite_scientific_values(self):
        for token, limit in [('<1e-3', 0.001), ('<,02', 0.02), ('<2,5E+1', 25.0), ('<1e999', None), ('<1e-999', None), ('<0e-999', 0.0)]:
            with self.subTest(token=token):
                self.assertEqual(_qualifier(token), ('below_detection_limit', limit))

    def test_nonempty_database_with_empty_migration_history_is_not_reinitialized(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'incomplete.sqlite'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE schema_migration (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
                connection.execute('CREATE TABLE original (value TEXT)')
                connection.execute("INSERT INTO original VALUES ('preserve')")
                connection.commit()
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(database.read_bytes(), before)

    def test_missing_middle_migration_is_rejected_before_backup_or_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'incomplete.sqlite'
            with closing(open_project(database)) as connection:
                connection.execute('DELETE FROM schema_migration WHERE version = 8')
                connection.commit()
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(caught.exception.details['missing_migrations'], [8])
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(list(Path(folder).glob('*.bak')), [])

    def test_unrelated_database_is_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'other.sqlite'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE original (value TEXT)')
                connection.execute("INSERT INTO original VALUES ('preserve')")
                connection.commit()
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(database.read_bytes(), before)

    def test_project_claiming_work_groups_without_their_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'project.sqlite'
            with closing(open_project(database)) as connection, connection:
                connection.execute('DROP TABLE work_group_analysis')
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(caught.exception.details['incompatible_migration'], 11)
            self.assertEqual(database.read_bytes(), before)

    def test_opening_current_project_does_not_rewrite_database(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'current.sqlite'
            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            before = database.read_bytes()
            with closing(open_project(database)) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(database.read_bytes(), before)

    def test_newer_schema_metadata_is_not_silently_downgraded(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'future-meta.sqlite'
            with closing(open_project(database)) as connection:
                connection.execute('UPDATE project_meta SET project_schema_version = 999')
                connection.commit()
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(database.read_bytes(), before)

    def test_failed_migration_rolls_back_the_entire_upgrade_and_retains_backup(self):
        from petrolab.import_apply import MIGRATIONS
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            migrations = folder / 'migrations'
            migrations.mkdir()
            for migration in MIGRATIONS.glob('*.sql'):
                shutil.copyfile(migration, migrations / migration.name)
            database = folder / 'project.sqlite'
            with closing(open_project(database)) as connection:
                connection.execute('INSERT INTO sample (sample_id, sample_name, created_at) VALUES (?, ?, ?)', ('s1', 'Original', '2026-01-01'))
                connection.commit()
            latest_version = max(int(path.name.split('_', 1)[0]) for path in migrations.glob('*.sql'))
            next_version = latest_version + 1
            first = migrations / f'{next_version:04d}_test_first.sql'
            first.write_text("CREATE TABLE should_rollback (id INTEGER);\nUPDATE sample SET sample_name = 'Changed';\n", encoding='utf-8')
            failing = migrations / f'{next_version + 1:04d}_test_failure.sql'
            failing.write_text('INSERT INTO should_rollback VALUES (1);\nTHIS IS INVALID SQL;', encoding='utf-8')
            with patch('petrolab.import_apply.MIGRATIONS', migrations):
                with self.assertRaises(ImportCommandError) as caught:
                    open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_MIGRATION_FAILED')
            self.assertEqual(caught.exception.details['migration'], failing.name)
            self.assertTrue(Path(caught.exception.details['backup_path']).is_file())
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM sqlite_master WHERE name='should_rollback'").fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT MAX(version) FROM schema_migration').fetchone()[0], latest_version)
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], latest_version)
                self.assertEqual(connection.execute('SELECT sample_name FROM sample WHERE sample_id=?', ('s1',)).fetchone()[0], 'Original')
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            backups = list(folder.glob(f'project.sqlite.before-v{next_version}-*.bak'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute('SELECT sample_name FROM sample WHERE sample_id=?', ('s1',)).fetchone()[0], 'Original')
            failing.write_text('INSERT INTO should_rollback VALUES (1);', encoding='utf-8')
            with patch('petrolab.import_apply.MIGRATIONS', migrations), closing(open_project(database)) as connection:
                self.assertEqual(connection.execute('SELECT id FROM should_rollback').fetchone()[0], 1)
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], next_version + 1)

    def test_newer_project_is_rejected_without_changing_the_database(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'future.sqlite'
            with closing(open_project(database)) as connection:
                connection.execute("INSERT INTO schema_migration VALUES (?, ?)", (999, 'future'))
                connection.execute("UPDATE project_meta SET project_schema_version = 999")
                connection.commit()
            before = database.read_bytes()
            with self.assertRaises(ImportCommandError) as caught:
                open_project(database)
            self.assertEqual(caught.exception.code, 'PROJECT_SCHEMA_UNSUPPORTED')
            self.assertEqual(database.read_bytes(), before)

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
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 25)
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(connection.execute('SELECT sample_name FROM sample WHERE sample_id = ?', ('old-sample',)).fetchone()[0], 'Keep original label')
            backups = list(folder.glob('old.sqlite.before-v9-*.bak'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], 8)

    def test_upgrade_and_restore_populated_version_nine_project(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            database = folder / 'project.sqlite'
            original = folder / FIXTURE.name
            shutil.copyfile(FIXTURE, original)
            source_bytes = original.read_bytes()
            apply_import_plan(database, original, fixture_recipe())
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript("""
                    DROP TABLE project_plot_presets;
                    DROP TABLE project_plot_colors;
                    DROP TABLE project_work_plan_task;
                    DROP TABLE media_import_draft;
                    DROP TABLE media_link;
                    ALTER TABLE spatial_annotation DROP COLUMN label;
                    DROP TABLE analysis_template;
                    DROP TABLE workspace_snapshot;
                    DROP TABLE work_group_calculation_origin;
                    DROP TABLE calculation_run;
                    DROP TABLE sample_note;
                    DROP TABLE sample_context;
                    DROP TABLE plot_specification;
                    DROP TABLE analysis_generation;
                    DROP TABLE generation;
                    DROP TABLE operation_journal;
                    DROP TABLE edit_draft;
                    DROP TABLE table_view;
                    DROP TABLE work_group_analysis;
                    DROP TABLE work_group;
                    DROP TABLE project_identity;
                    DROP TABLE analysis_import_semantics;
                    DROP TABLE project_analyte_alias;
                    DELETE FROM schema_migration WHERE version > 9;
                    UPDATE project_meta SET project_schema_version = 9;
                """)
                tables = [
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' "
                        "AND name NOT LIKE 'sqlite_%' AND name NOT IN ('project_meta', 'schema_migration')"
                    )
                ]
                columns = {table: ', '.join(f'"{row[1]}"' for row in connection.execute(f'PRAGMA table_info("{table}")')) for table in tables}
                expected = {
                    table: connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                    for table in tables
                }
                self.assertEqual(len(expected['analysis']), 8)
                self.assertTrue(expected['measurement'])
                self.assertTrue(expected['source_cell_provenance'])

            self.assertEqual(list_project_analyses(database)['total'], 8)
            backup, = folder.glob('project.sqlite.before-v10-*.bak')
            restored = folder / 'restored.sqlite'
            shutil.copyfile(backup, restored)
            for candidate, version in ((database, 25), (restored, 9)):
                with closing(sqlite3.connect(candidate)) as connection:
                    self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                    self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                    self.assertEqual(connection.execute('SELECT project_schema_version FROM project_meta').fetchone()[0], version)
                    for table, rows in expected.items():
                        self.assertEqual(
                            connection.execute(f'SELECT {columns[table]} FROM "{table}" ORDER BY rowid').fetchall(),
                            rows,
                            table,
                        )
            self.assertEqual(list_project_analyses(restored)['total'], 8)
            self.assertEqual(original.read_bytes(), source_bytes)

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
        tokens = ['<0.01', '<1e-3', '<.02', '<DL', 'bdl', 'BDL', 'n.d.', 'N.D.', 'nd', '', '0', 'bad', '1e-999']
        expected = ['below_detection_limit'] * 6 + ['not_determined'] * 3 + ['missing', 'numeric', 'non_numeric', 'numeric']
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "tokens.csv"
            source.write_text('Analysis,F (wt.%)\n' + ''.join(f'A{i},{token}\n' for i, token in enumerate(tokens)), encoding="utf-8")
            original = source.read_bytes()
            recipe = suggest_import_recipe(source)["recipe"]
            plan = create_import_plan(inspect_source(source), recipe)
            values = [row["measurements"][0] for row in plan["planned_records"]]
            self.assertEqual([item["value_status"] for item in values], expected)
            self.assertEqual(values[0]["detection_limit"], 0.01)
            self.assertEqual(values[1]["detection_limit"], 0.001)
            self.assertEqual(values[2]["detection_limit"], 0.02)
            self.assertTrue(all(item["detection_limit"] is None for item in values[3:]))
            database = Path(folder) / "project.sqlite"
            apply_import_plan(database, source, recipe)
            with closing(open_project(database)) as connection:
                for table in ['measurement', 'source_row_provenance', 'source_cell_provenance']:
                    rows = connection.execute(f'SELECT raw_token, value_status FROM {table} ORDER BY rowid').fetchall()
                    self.assertEqual([tuple(row) for row in rows], list(zip([token or None for token in tokens], expected)))
                limits = connection.execute('SELECT detection_limit FROM measurement ORDER BY rowid').fetchall()
                self.assertEqual([row[0] for row in limits[:3]], [0.01, 0.001, 0.02])
            self.assertEqual(source.read_bytes(), original)
            projection = list_project_analyses(database)
            self.assertEqual(projection["total"], len(tokens))
            values = {row["measurements"]["F"]["raw_token"]: row["measurements"]["F"]["numeric_value"]
                      for row in projection["analyses"]}
            self.assertEqual([token for token, value in values.items() if value == 0], ["0"])
            self.assertIsNone(values["1e-999"])

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
