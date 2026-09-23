import unittest

from petrolab.analyte_dictionary import (ELEMENT_DATA, ELEMENTS, recognize_analyte,
                                         confirmed_alias)
from petrolab.import_recognition import mapping_for_header


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
