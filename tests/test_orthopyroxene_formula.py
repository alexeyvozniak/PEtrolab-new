"""Independent stoichiometric and published expectations for draft Opx 6 O."""
import copy
import json
import unittest

from petrolab.orthopyroxene_formula import calculate_orthopyroxene


def measurements(composition):
    return [{'measurement_id': f'm-{field}', 'field': field, 'raw_token': str(value),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None,
             'reported_fe_form': field if field.startswith('Fe') else None}
            for field, value in composition.items()]


def run(composition, fe_mode='all_fe2'):
    return calculate_orthopyroxene(measurements(composition), fe_mode)


class OrthopyroxeneFormulaTests(unittest.TestCase):
    def test_ideal_enstatite_ferrosilite_and_equal_mix(self):
        # Independent masses for (Mg,Fe)2Si2O6; no production function in expected values.
        for mg, fe, expected_en, expected_fs in [(80.608, 0, 100, 0),
                                                  (0, 143.688, 0, 100),
                                                  (40.304, 71.844, 50, 50)]:
            with self.subTest(mg=mg, fe=fe):
                source = measurements({'SiO2': 120.166, 'MgO': mg, 'FeO': fe, 'CaO': 0})
                before = copy.deepcopy(source)
                result = calculate_orthopyroxene(source, 'all_fe2')
                self.assertEqual(result['status'], 'current', result['errors'])
                self.assertAlmostEqual(result['values']['Si_apfu'], 2, places=12)
                self.assertAlmostEqual(result['values']['Mg_apfu'], mg / 40.304, places=12)
                self.assertAlmostEqual(result['values']['Fe2_apfu'], fe / 71.844, places=12)
                self.assertEqual(result['values']['Ca_apfu'], 0)
                self.assertAlmostEqual(result['values']['Wo'], 0, places=12)
                self.assertAlmostEqual(result['values']['En'], expected_en, places=12)
                self.assertAlmostEqual(result['values']['Fs'], expected_fs, places=12)
                self.assertEqual(result['method_status'], 'draft')
                self.assertEqual(source, before)
                json.dumps(result, allow_nan=False)

    def test_published_experimental_e17_016_orthopyroxene(self):
        # Journal of Petrology 63(11), egac110 (2022), Table 6, E17–016 Opx (n=4).
        # The published rounded cations and Wo/En/Fs are independent of this code.
        composition = {'SiO2': 52.43, 'TiO2': .21, 'Al2O3': 9.10,
                       'Cr2O3': .65, 'FeO': 6.73, 'MgO': 30.39,
                       'CaO': 1.19, 'Na2O': .06, 'K2O': 0}
        published = {'Si_apfu': 1.80, 'Ti_apfu': .01, 'Al_apfu': .37,
                     'Cr_apfu': .02, 'Fe2_apfu': .19, 'Mg_apfu': 1.56,
                     'Ca_apfu': .04, 'Na_apfu': 0, 'cation_sum': 4.00,
                     'Wo': 2.45, 'En': 86.76, 'Fs': 10.79}
        result = run(composition)
        self.assertEqual(result['status'], 'current', result['errors'])
        for field, value in published.items():
            with self.subTest(field=field):
                self.assertAlmostEqual(result['values'][field], value,
                                       delta=.011 if field.endswith('_apfu') or field == 'cation_sum' else .05)
        # Displayed oxides sum to 100.76, whereas the paper prints 100.78.
        # Do not alter the displayed inputs to force agreement with that total.
        self.assertAlmostEqual(result['values']['oxide_total'], 100.76, places=12)

    def test_explicit_calcium_and_fe_basis_are_required(self):
        baseline = {'SiO2': 120.166, 'MgO': 80.608, 'FeO': 0, 'CaO': 0}
        self.assertEqual(run(baseline)['status'], 'current')
        for field in ('SiO2', 'MgO', 'FeO', 'CaO'):
            composition = dict(baseline)
            del composition[field]
            self.assertEqual(run(composition)['status'], 'failed')
        self.assertEqual(run({**baseline, 'Fe2O3': 0}, 'all_fe2')['status'], 'failed')
        self.assertEqual(run(baseline, 'reported_split')['status'], 'failed')
        self.assertEqual(run({**baseline, 'Fe2O3': 0}, 'reported_split')['status'], 'current')
        self.assertEqual(run({**baseline, 'FeOt': 0}, 'all_fe2')['status'], 'failed')
        self.assertEqual(run({**baseline, 'H2O': 0})['status'], 'failed')
        self.assertEqual(run({**baseline, 'P2O5': 0})['status'], 'failed')
        self.assertEqual(run({**baseline, 'SiO2': 0})['status'], 'failed')

    def test_missing_censored_wrong_unit_nonfinite_and_trace_exclusion(self):
        baseline = {'SiO2': 120.166, 'MgO': 80.608, 'FeO': 0, 'CaO': 0}
        for change in ({'raw_token': '<0.1', 'value_status': 'below_detection_limit'},
                       {'raw_token': None, 'value_status': 'missing'}, {'unit': 'ppm'},
                       {'raw_token': 'NaN'}, {'raw_token': '-1'}):
            source = measurements(baseline)
            source[0].update(change)
            self.assertEqual(calculate_orthopyroxene(source, 'all_fe2')['status'], 'failed')
        source = measurements(baseline)
        source.append({'measurement_id': 'm-Rb', 'field': 'Rb', 'raw_token': '50',
                       'unit': 'ppm', 'value_status': 'numeric'})
        result = calculate_orthopyroxene(source, 'all_fe2')
        self.assertEqual(result['status'], 'current', result['errors'])
        self.assertEqual(result['excluded'][0]['measurement_id'], 'm-Rb')


if __name__ == '__main__':
    unittest.main()
