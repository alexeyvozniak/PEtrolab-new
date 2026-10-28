"""Independent stoichiometric and published garnet structural expectations."""
from copy import deepcopy
import json
import unittest

from petrolab.garnet_formula import calculate_garnet


def measurements(values):
    return [{'measurement_id': 'm-' + field, 'field': field, 'raw_token': str(value),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None,
             'reported_fe_form': field if field.startswith('Fe') else None}
            for field, value in values.items()]


def ideal(**extra):
    # Independent oxide masses for 3 Si, 2 Al, 3 Mg; not production constants.
    return {'SiO2': 180.249, 'Al2O3': 101.961, 'MgO': 120.912,
            'MnO': 0, 'CaO': 0, 'FeO': 0, **extra}


def run(values, mode='all_fe2'):
    return calculate_garnet(measurements(values), mode)


class GarnetFormulaTests(unittest.TestCase):
    def test_ideal_endmembers_and_structural_site_conservation(self):
        cases = [
            (ideal(), 'all_fe2', 'Mg', 'Al', '{Mg3}[Al2](Si3)O12'),
            (ideal(MgO=0, FeO=215.532), 'all_fe2', 'Fe2', 'Al', '{Fe²⁺3}[Al2](Si3)O12'),
            (ideal(MgO=0, MnO=212.811), 'all_fe2', 'Mn', 'Al', '{Mn3}[Al2](Si3)O12'),
            (ideal(MgO=0, CaO=168.231), 'all_fe2', 'Ca', 'Al', '{Ca3}[Al2](Si3)O12'),
            (ideal(MgO=0, CaO=168.231, Al2O3=0, Cr2O3=151.989), 'all_fe2', 'Ca', 'Cr', '{Ca3}[Cr2](Si3)O12'),
            (ideal(MgO=0, CaO=168.231, Al2O3=0, Fe2O3=159.687), 'reported_split', 'Ca', 'Fe3', '{Ca3}[Fe³⁺2](Si3)O12'),
        ]
        for values, mode, x, y, formula in cases:
            with self.subTest(formula=formula):
                source = measurements(values)
                before = deepcopy(source)
                result = calculate_garnet(source, mode)
                self.assertEqual(result['status'], 'current', result)
                self.assertAlmostEqual(result['sites']['X'][x], 3, places=10)
                self.assertAlmostEqual(result['sites']['Y'][y], 2, places=10)
                self.assertAlmostEqual(result['sites']['Z']['Si'], 3, places=10)
                self.assertAlmostEqual(result['values']['cation_sum'], 8, places=10)
                self.assertAlmostEqual(result['values']['charge_sum'], 24, places=10)
                self.assertEqual(result['values']['structural_formula'], formula)
                self.assertEqual(source, before)
                self.assertEqual(result['method_status'], 'draft')
                self.assertNotIn('species', result)
                for field, value in result['values'].items():
                    if field.endswith('_apfu') and not field.startswith(('X_', 'Y_', 'Z_')):
                        element = field[:-5]
                        self.assertAlmostEqual(sum(site.get(element, 0) for site in result['sites'].values()), value, places=10)
                json.dumps(result, allow_nan=False)

    def test_ideal_andradite_droop_and_majorite_morimotoite_allocation(self):
        # All total Fe initially represented as FeO, with 2 Fe atoms; actual Fe3=2.
        result = run(ideal(Al2O3=0, MgO=0, CaO=168.231, FeO=143.688), 'stoichiometric_droop')
        self.assertEqual(result['status'], 'current', result)
        self.assertAlmostEqual(result['values']['Fe3_apfu'], 2, places=10)
        self.assertAlmostEqual(result['values']['Fe2_apfu'], 0, places=10)
        self.assertEqual(result['values']['structural_formula'], '{Ca3}[Fe³⁺2](Si3)O12')
        self.assertEqual(result['estimated_fields'], ['Fe2_apfu', 'Fe3_apfu'])
        self.assertTrue(result['fe_est_basis']['input_measurement_ids'])
        # Mg3[MgSi]Si3O12 and Ca3[TiFe2]Si3O12, independent stoichiometry.
        for values, expected in [
            (ideal(SiO2=240.332, Al2O3=0, MgO=161.216), {'Y_Si_apfu': 1, 'Y_Mg_apfu': 1, 'X_Mg_apfu': 3}),
            (ideal(Al2O3=0, MgO=0, CaO=168.231, FeO=71.844, TiO2=79.865),
             {'Y_Ti_apfu': 1, 'Y_Fe2_apfu': 1, 'X_Ca_apfu': 3}),
        ]:
            result = run(values)
            self.assertEqual(result['status'], 'current', result)
            for field, value in expected.items():
                self.assertAlmostEqual(result['values'][field], value, places=10)

    def test_published_table4_sg1_ferric_benchmark(self):
        # Yavuz & Yildirim 2020, J Geosciences 65, p83, Table 4 SG1.
        # Values transcribed from the visually inspected PDF, not this algorithm.
        composition = {'SiO2': 36.7, 'Al2O3': 20.9, 'FeO': 37.5,
                       'MgO': 4.4, 'MnO': .24, 'CaO': .45}
        published = {'Si_apfu': 2.938, 'Al_apfu': 1.972, 'Fe3_apfu': .153,
                     'Fe2_apfu': 2.358, 'Mg_apfu': .525, 'Mn_apfu': .016, 'Ca_apfu': .039}
        result = run(composition, 'stoichiometric_droop')
        self.assertEqual(result['status'], 'current', result)
        for field, value in published.items():
            self.assertAlmostEqual(result['values'][field], value, delta=.003, msg=field)
        self.assertAlmostEqual(result['values']['oxide_total'], 100.19, places=10)
        self.assertAlmostEqual(result['values']['charge_sum'], 24, places=10)
        self.assertAlmostEqual(result['values']['cation_sum'], 8, places=10)
        self.assertAlmostEqual(result['sites']['Z']['Al'], 3-result['values']['Si_apfu'], places=10)
        # Hand allocation from the published rounded cations: Z Al=.062;
        # Y Al=1.910 plus Fe3=.153. Do not force measured imbalance to 3/2/3.
        for site, expected in (('X', 2.938), ('Y', 2.063), ('Z', 3)):
            self.assertAlmostEqual(result['values'][site+'_sum'], expected, delta=.003)
        self.assertTrue(any('Сумма Y=' in warning for warning in result['warnings']))

    def test_impossible_droop_is_rejected_not_clamped(self):
        for composition in [ideal(SiO2=240.332), ideal(SiO2=120.166)]:
            result = run(composition, 'stoichiometric_droop')
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['values'], {})
            self.assertTrue(any('Droop' in error for error in result['errors']))

    def test_iron_forms_parameters_and_optional_values(self):
        for composition, mode in [(ideal(Fe2O3=0), 'all_fe2'), (ideal(), 'reported_split'),
                                  (ideal(FeOt=0), 'all_fe2'), (ideal(Fe2O3t=0), 'stoichiometric_droop')]:
            self.assertEqual(run(composition, mode)['status'], 'failed')
        total = ideal()
        total['FeOt'] = total.pop('FeO')
        self.assertEqual(run(total)['status'], 'current')
        source = measurements(ideal(Fe2O3=0))
        next(item for item in source if item['field'] == 'FeO')['reported_fe_form'] = 'FeOt'
        self.assertEqual(calculate_garnet(source, 'reported_split')['status'], 'failed')
        for mode in (None, [], 'unknown'):
            self.assertEqual(run(ideal(), mode)['status'], 'failed')
        self.assertEqual(calculate_garnet(None, 'all_fe2')['status'], 'failed')
        result = run(ideal())
        self.assertIn('Na2O', result['unmeasured'])
        self.assertNotIn('Na_apfu', result['values'])
        self.assertNotIn('Fe3_apfu', result['values'])

    def test_missing_censored_units_duplicates_unsupported_and_nonfinite(self):
        for field in ('SiO2', 'Al2O3', 'MgO', 'MnO', 'CaO', 'FeO'):
            composition = ideal()
            del composition[field]
            self.assertEqual(run(composition)['status'], 'failed')
        for change in ({'raw_token': '-1'}, {'raw_token': 'nan'}, {'raw_token': 'inf'}, {'unit': 'ppm'},
                       {'raw_token': None, 'value_status': 'missing'},
                       {'raw_token': '<.1', 'value_status': 'below_detection_limit'}, {'qualifier': '<'}):
            source = measurements(ideal())
            source[0].update(change)
            self.assertEqual(calculate_garnet(source, 'all_fe2')['status'], 'failed')
        for field in ('H2O', 'F', 'Cl'):
            self.assertEqual(run(ideal(**{field: 0}))['status'], 'current')
            self.assertEqual(run(ideal(**{field: .01}))['status'], 'failed')
        for field in ('NiO', 'P2O5', 'ZrO2', 'K2O', 'Mn2O3'):
            self.assertEqual(run(ideal(**{field: 0}))['status'], 'failed')
        source = measurements(ideal())
        self.assertEqual(calculate_garnet(source+[source[0]], 'all_fe2')['status'], 'failed')
        source.append({'measurement_id': 'm-Rb', 'field': 'Rb', 'raw_token': '1',
                       'unit': 'ppm', 'value_status': 'numeric'})
        result = calculate_garnet(source, 'all_fe2')
        self.assertEqual(result['status'], 'current')
        self.assertEqual(result['excluded'][0]['measurement_id'], 'm-Rb')
        huge = run({key: 1e308 for key in ideal()})
        self.assertEqual(huge['status'], 'failed')
        json.dumps(huge, allow_nan=False)
