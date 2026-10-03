"""Independent ideal and published 23 O benchmarks for the draft core."""

import copy
import json
import unittest

from petrolab.amphibole_formula import calculate_amphibole


def measurements(composition):
    return [{'measurement_id': f'm-{field}', 'field': field, 'raw_token': str(value),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None,
             'reported_fe_form': field if field.startswith('Fe') else None}
            for field, value in composition.items()]


class AmphiboleFormulaTests(unittest.TestCase):
    def test_ideal_tremolite_bulk_cations_without_inventing_oh(self):
        # Ca2Mg5Si8O22(OH)2 => 8 SiO2 + 5 MgO + 2 CaO, 23 oxide O.
        source = measurements({'SiO2': 8 * 60.083, 'MgO': 5 * 40.304,
                               'CaO': 2 * 56.077})
        before = copy.deepcopy(source)
        result = calculate_amphibole(source, 'all_fe2')
        self.assertEqual(result['status'], 'current', result['errors'])
        for name, expected in [('Si_apfu', 8), ('Mg_apfu', 5),
                               ('Ca_apfu', 2), ('cation_sum', 15)]:
            self.assertAlmostEqual(result['values'][name], expected, places=12)
        self.assertNotIn('OH_apfu', result['values'])
        self.assertEqual(result['method_status'], 'draft')
        self.assertIn('Железо не измерено', result['warnings'][0])
        self.assertEqual(source, before)
        json.dumps(result, allow_nan=False)

    def test_published_ni_tremolite_tn8(self):
        # Nanomaterials 13(8), 1303 (2023), Table 2, monophase TN8.
        # Paper reports Si 8.0, Mg 4.4, Ca 1.6, Ni 1.0 on 23 O, rounded
        # to one decimal. The expectations are transcribed, not calculated
        # through the production function.
        source = {'SiO2': 58.8, 'MgO': 21.5, 'CaO': 10.4, 'NiO': 9.1}
        result = calculate_amphibole(measurements(source), 'all_fe2')
        self.assertEqual(result['status'], 'current', result['errors'])
        for name, expected in [('Si_apfu', 8.0), ('Mg_apfu', 4.4),
                               ('Ca_apfu', 1.6), ('Ni_apfu', 1.0)]:
            with self.subTest(name=name):
                self.assertAlmostEqual(result['values'][name], expected, delta=0.1)
        self.assertAlmostEqual(result['values']['oxide_total'], 99.8, places=12)

    def test_explicit_input_scope_and_fe_assumption(self):
        baseline = {'SiO2': 8 * 60.083, 'MgO': 5 * 40.304, 'CaO': 2 * 56.077}
        for field in baseline:
            with self.subTest(missing=field):
                source = dict(baseline)
                del source[field]
                self.assertEqual(calculate_amphibole(measurements(source), 'all_fe2')['status'], 'failed')
        for field in baseline:
            with self.subTest(zero=field):
                self.assertEqual(calculate_amphibole(measurements({**baseline, field: 0}), 'all_fe2')['status'], 'failed')
        for field in ('Fe2O3', 'Fe2O3t', 'F', 'Cl', 'H2O'):
            with self.subTest(unsupported=field):
                self.assertEqual(calculate_amphibole(measurements({**baseline, field: 0}), 'all_fe2')['status'], 'failed')
        self.assertEqual(calculate_amphibole(measurements(baseline), 'reported_split')['status'], 'failed')
        self.assertEqual(calculate_amphibole(measurements({**baseline, 'FeO': 0}), 'all_fe2')['status'], 'current')
        self.assertEqual(calculate_amphibole(measurements({**baseline, 'FeO': 0, 'FeOt': 0}), 'all_fe2')['status'], 'failed')

    def test_missing_censored_units_duplicate_and_noncomposition(self):
        baseline = measurements({'SiO2': 8 * 60.083, 'MgO': 5 * 40.304,
                                 'CaO': 2 * 56.077})
        for change in ({'raw_token': '<0.1', 'value_status': 'below_detection_limit'},
                       {'raw_token': None, 'value_status': 'missing'},
                       {'unit': 'ppm'}, {'raw_token': 'NaN'}, {'raw_token': '-1'}):
            with self.subTest(change=change):
                source = copy.deepcopy(baseline)
                source[0].update(change)
                self.assertEqual(calculate_amphibole(source, 'all_fe2')['status'], 'failed')
        self.assertEqual(calculate_amphibole(baseline + [baseline[0]], 'all_fe2')['status'], 'failed')
        source = baseline + [{'measurement_id': 'm-Rb', 'field': 'Rb', 'raw_token': '50',
                              'unit': 'ppm', 'value_status': 'numeric'}]
        result = calculate_amphibole(source, 'all_fe2')
        self.assertEqual(result['status'], 'current', result['errors'])
        self.assertEqual(result['excluded'][0]['measurement_id'], 'm-Rb')


if __name__ == '__main__':
    unittest.main()
