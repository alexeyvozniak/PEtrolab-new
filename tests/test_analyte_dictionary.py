import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from petrolab.analyte_dictionary import (ELEMENT_DATA, ELEMENTS, recognize_analyte,
                                         confirmed_alias)
from petrolab.clean_table import _mapping
from petrolab.desktop_workflow import suggest_import_recipe
from petrolab.import_preview import ImportCommandError
from petrolab.import_recognition import mapping_for_header
from petrolab.manual_mapping import revise_import_mappings


class AnalyteDictionaryTests(unittest.TestCase):
    def test_all_118_elements_names_and_symbols(self):
        self.assertEqual(len(set(ELEMENTS)), 118)
        for line in ELEMENT_DATA.splitlines():
            symbol, english, russian = line.split()
            for label in (symbol, english, russian):
                with self.subTest(label=label):
                    self.assertEqual(recognize_analyte(label)['canonical_field'], symbol)

    def test_safe_normalization_separate_unit_and_raw(self):
        for header in ['SiO2', 'SIO2', 'SiO₂', 'Si O2', 'SiO2 wt.%', 'SiO2,%', 'SiO2 (wt%)']:
            value = recognize_analyte(header)
            self.assertEqual(value['canonical_field'], 'SiO2')
            self.assertEqual(value['raw_header'], header)
            self.assertTrue(value['automatic'])
        self.assertIsNone(recognize_analyte('SiO2,%')['unit'])
        self.assertEqual(recognize_analyte('Si O₂ (wt%)')['unit'], 'wt.%')
        mapping, issue = mapping_for_header(0, 'Si O₂ (wt%)')
        self.assertEqual((mapping['canonical_field'], mapping['unit']), ('SiO2', 'wt.%'))
        self.assertIsNone(issue)

    def test_real_symbols_never_fuzzy_collide(self):
        for symbol in ['Co', 'Ca', 'S', 'Si', 'Na', 'Nb']:
            self.assertEqual(recognize_analyte(symbol, fuzzy=True)['canonical_field'], symbol)
        self.assertFalse(recognize_analyte('SiiO2', fuzzy=True)['automatic'])
        self.assertIsNone(recognize_analyte('SiiO2', fuzzy=True)['canonical_field'])

    def test_reported_indices_are_distinct_from_elements_and_require_explicit_scales(self):
        for field, unit in [('Mg#', 'ratio'), ('Cr#', 'mol%')]:
            header = f'{field} [{unit}]'
            for suggest in (mapping_for_header, _mapping):
                mapping, warning = suggest(0, header)
                self.assertIsNone(warning)
                self.assertEqual(mapping['canonical_field'], field)
                self.assertEqual(mapping['unit'], unit)
                self.assertEqual(mapping['source_header'], header)
                self.assertEqual(mapping['measurement_semantics'], 'source_derived')
            ignored, warning = mapping_for_header(0, field, context_unit='wt.%')
            self.assertEqual(ignored['target_role'], 'ignore')
            self.assertEqual(ignored['suggested_canonical_field'], field)
            self.assertEqual(warning['code'], 'UNIT_REQUIRES_REVIEW')
        magnesium, _ = mapping_for_header(0, 'Mg [ppm]')
        self.assertEqual(magnesium['canonical_field'], 'Mg')
        self.assertEqual(magnesium['measurement_semantics'], 'measured')

    def test_index_unit_review_preserves_reported_semantics(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "index.csv"
            source.write_text("Analysis,SiO2 [wt.%],Mg#\nP1,40,0.87\n", encoding="utf-8")
            recipe = suggest_import_recipe(source)["recipe"]
            section = recipe["sections"][0]
            decision = {"block_id": section["block_id"], "source_axis": "column", "source_index": 2,
                        "target": "Measurement", "canonical_field": "mg#", "unit": "ratio"}
            reviewed = revise_import_mappings(source, recipe, [decision])["recipe"]
            mapping = reviewed["sections"][0]["mappings"][2]
            self.assertEqual((mapping["canonical_field"], mapping["unit"], mapping["measurement_semantics"]),
                             ("Mg#", "ratio", "source_derived"))
            with self.assertRaises(ImportCommandError) as error:
                revise_import_mappings(source, recipe, [{**decision, "unit": "wt.%"}])
            self.assertEqual(error.exception.code, "UNKNOWN_UNIT")

    def test_isotopes_and_aliases(self):
        cases = {'⁸⁷Sr/⁸⁶Sr': '87Sr/86Sr', '87Sr/86Sr(0)': '87Sr/86Sr(0)',
                 'U-238': '238U', 'δ18O': 'δ18O', 'εNd(t)': 'εNd(t)',
                 'ППП': 'LOI', 'loss on ignition': 'LOI', 'FeO total': 'FeOt'}
        for raw, canonical in cases.items():
            self.assertEqual(recognize_analyte(raw)['canonical_field'], canonical)

    def test_alias_requires_confirmation_and_cannot_shadow(self):
        key, alias = confirmed_alias('Silica_lab', 'SiO2')
        self.assertEqual(recognize_analyte('Silica_lab ppm', {key: alias})['canonical_field'], 'SiO2')
        self.assertFalse(recognize_analyte('Silica_lab', {key: dict(alias, confirmed=False)})['automatic'])
        self.assertFalse(recognize_analyte('Silica_lab')['automatic'])
        with self.assertRaises(ValueError):
            confirmed_alias('Co', 'Ca')
