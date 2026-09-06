from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.import_preview import ImportCommandError, inspect_source, create_import_plan
from petrolab.semantic_import import apply_semantic_decision


class SemanticImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'not-a-sample.csv'
        self.source.write_text('Analysis,SiO2 (wt.%),Mineral\nA1,40,olivine\nA2,41,olivine\nA3,42,garnet\n', encoding='utf-8')
        self.original = self.source.read_bytes()
        self.recipe = suggest_import_recipe(self.source)['recipe']
        self.block = self.recipe['sections'][0]['block_id']

    def decision(self, **extra):
        return {'role': 'sample', 'value': 'K-17', 'block_id': self.block,
                'range': {'start_row': 2, 'end_row': 3, 'start_column': 0, 'end_column': 2}, **extra}

    def plan(self, recipe=None):
        return create_import_plan(inspect_source(self.source), recipe or self.recipe)

    def test_sample_is_optional_and_filename_does_not_create_one(self):
        records = self.plan()['planned_records']
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r['sample_association']['status'] == 'unresolved' for r in records))
        self.assertEqual(records[0]['reported_mineral']['value'], 'olivine')

    def test_assignment_extension_preview_commit_and_undo_preserve_raw(self):
        revised = apply_semantic_decision(self.source, self.recipe, self.decision())
        first = revised['global_decisions']['semantic_annotations'][0]
        records = self.plan(revised)['planned_records']
        self.assertEqual(records[0]['sample_association']['reported']['value'], 'K-17')
        self.assertEqual(records[2]['sample_association']['status'], 'unresolved')
        extend = {'action': 'extend', 'annotation_id': first['id'], 'range': dict(first['range'], end_row=4)}
        result = apply_semantic_decision(self.source, revised, extend, preview=True)
        self.assertTrue(result['confirmation_required'])
        self.assertEqual(revised['global_decisions']['semantic_annotations'][0]['range']['end_row'], 3)
        extended = apply_semantic_decision(self.source, revised, extend)
        self.assertEqual(self.plan(extended)['planned_records'][2]['sample_association']['reported']['value'], 'K-17')
        undone = apply_semantic_decision(self.source, extended, {'action': 'undo'})
        self.assertEqual(self.plan(undone)['planned_records'][2]['sample_association']['status'], 'unresolved')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_conflicting_assignment_and_boundary_are_rejected(self):
        revised = apply_semantic_decision(self.source, self.recipe, self.decision())
        for decision in [self.decision(value='K-18'), self.decision(range={'start_row': 1, 'end_row': 3, 'start_column': 0, 'end_column': 2})]:
            with self.assertRaises(ImportCommandError):
                apply_semantic_decision(self.source, revised, decision)

    def test_column_role_is_reversible(self):
        decision = self.decision(role='sample_name_column', value='', range={'start_row': 1, 'end_row': 4, 'start_column': 2, 'end_column': 2})
        revised = apply_semantic_decision(self.source, self.recipe, decision)
        self.assertEqual(revised['sections'][0]['mappings'][2]['canonical_field'], 'Sample name')
        restored = apply_semantic_decision(self.source, revised, {'action': 'undo'})
        self.assertEqual(restored['sections'], self.recipe['sections'])

    def test_same_reported_name_across_files_does_not_merge_entities(self):
        self.source.write_text('Analysis,Sample,SiO2 (wt.%)\nA1,K-17,40\nA2,K-18,41\n', encoding='utf-8')
        self.recipe = suggest_import_recipe(self.source)['recipe']
        records = self.plan()['planned_records']
        self.assertEqual([r['sample_association']['reported']['value'] for r in records], ['K-17', 'K-18'])
        self.assertTrue(all(r['sample_association']['sample_id'] is None for r in records))
        self.block = self.recipe['sections'][0]['block_id']
        with self.assertRaises(ImportCommandError):
            apply_semantic_decision(self.source, self.recipe, self.decision())

    def test_ignore_rows_preserves_identity_of_remaining_records(self):
        revised = apply_semantic_decision(self.source, self.recipe, self.decision(role='ignore', value=''))
        records = self.plan(revised)['planned_records']
        self.assertEqual([r['identity'] for r in records], [('A3',)])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_ignoring_identity_cells_does_not_silently_import_them(self):
        revised = apply_semantic_decision(self.source, self.recipe, self.decision(role='ignore', value='', range={'start_row': 2, 'end_row': 2, 'start_column': 0, 'end_column': 0}))
        plan = self.plan(revised)
        self.assertEqual(plan['planned_records'][0]['identity'], ('',))
        self.assertFalse(plan['ready_to_commit'])
        self.assertEqual(plan['issues'][0]['code'], 'ANALYSIS_IDENTITY_REQUIRED')

    def test_runtime_recipe_contract_and_forged_annotation_are_rejected(self):
        import json
        from petrolab.import_preview import semantic_fingerprint
        from scripts.validate_contracts import _validate
        revised = apply_semantic_decision(self.source, self.recipe, self.decision())
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/import-recipe-v2.schema.json').read_text(encoding='utf-8'))
        _validate(revised, schema, schema, {})
        revised['global_decisions']['semantic_annotations'][0]['source_fingerprint'] = '0' * 64
        revised['semantic_fingerprint'] = semantic_fingerprint(revised)
        with self.assertRaises(ImportCommandError):
            self.plan(revised)

    def test_merged_sample_evidence_is_bounded_and_pattern_is_only_a_proposal(self):
        from petrolab.import_preview import SheetInspection
        from petrolab.semantic_import import merged_sample_evidence, sample_candidates
        sheet = SheetInspection('Data', (('Sample: preamble',), ('Analysis', 'Sample'), ('K17-1', 'K17'), ('K17-2', None), ('K18-1', None)), (2,),
                                ({'code': 'MERGED_HEADERS', 'ranges': ['B3:B4']},))
        section = {'header_row': 2, 'data_start_row': 3, 'data_end_row': 5}
        evidence = merged_sample_evidence(sheet, section, 4, 1, 'abc')
        self.assertEqual(evidence['value'], 'K17')
        self.assertEqual(evidence['merged_range'], 'B3:B4')
        self.assertIsNone(merged_sample_evidence(sheet, section, 5, 1, 'abc'))
        candidates = sample_candidates(sheet, section, {'identity': ['K18-1'], 'row_number': 5}, 'abc')
        self.assertEqual([c['value'] for c in candidates], ['preamble', 'K18'])
        self.assertTrue(all(c['origin'] == 'suggested' for c in candidates))

    def test_block_rectangle_excludes_fields_outside_its_columns_and_undo_restores(self):
        revised = apply_semantic_decision(self.source, self.recipe, self.decision(role='block', value='', range={'start_row': 2, 'end_row': 3, 'start_column': 0, 'end_column': 1}))
        records = self.plan(revised)['planned_records']
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r['reported_mineral'] is None for r in records))
        restored = apply_semantic_decision(self.source, revised, {'action': 'undo'})
        self.assertEqual(restored['sections'], self.recipe['sections'])

    def test_embedded_drawing_warning_and_preview_have_only_physical_columns(self):
        import zipfile
        from petrolab.import_preview import preview_source_window
        from real_world_fixtures import write_xlsx
        path = write_xlsx(Path(self.temp.name) / 'drawings.xlsx', {'Data': [['Analysis', 'SiO2 (wt.%)'], ['A1', 40]]})
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts['xl/worksheets/sheet1.xml'] = parts['xl/worksheets/sheet1.xml'].replace(b'</worksheet>', b'<drawing xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/></worksheet>')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in parts.items():
                archive.writestr(name, data)
        before = path.read_bytes()
        preview = preview_source_window(path, 'Data', 1, column_count=18)
        self.assertEqual(len(preview['rows'][0]['values']), 2)
        self.assertEqual(preview['column_labels'], ['A', 'B'])
        self.assertEqual(preview['warnings'][0]['code'], 'EMBEDDED_DRAWINGS_NOT_PREVIEWED')
        self.assertEqual(path.read_bytes(), before)
