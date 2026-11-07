"""Independent ideal and printed WinPyrox ferric benchmarks, not production oracles."""
from copy import deepcopy
import json
import unittest

from petrolab.clinopyroxene_structural_formula import calculate_clinopyroxene_structural


def measurements(values):
    return [{'measurement_id': 'm-' + field, 'field': field, 'raw_token': str(value),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None,
             'reported_fe_form': field if field.startswith('Fe') else None}
            for field, value in values.items()]


def ideal(**extra):
    return {'SiO2': 120.166, 'Al2O3': 0, 'MgO': 40.304, 'MnO': 0,
            'CaO': 56.077, 'Na2O': 0, 'FeO': 0, **extra}


S4 = {'SiO2': 45.9, 'TiO2': 1.4, 'Al2O3': 5.9, 'Cr2O3': 0,
      'Fe2O3': 8.1, 'FeO': 7.6, 'MnO': .35, 'MgO': 8,
      'CaO': 20, 'Na2O': 1.35, 'K2O': .04}


def run(values, mode='all_fe2'):
    return calculate_clinopyroxene_structural(measurements(values), mode)


class ClinopyroxeneStructuralTests(unittest.TestCase):
    def test_independent_ideal_sites_charge_and_element_conservation(self):
        cases = [
            (ideal(), 'all_fe2', '{Ca1}[Mg1](Si2)O6'),
            (ideal(MgO=0, FeO=71.844), 'all_fe2', '{Ca1}[Fe²⁺1](Si2)O6'),
            (ideal(MgO=0, CaO=0, Na2O=30.9895, Al2O3=50.9805), 'all_fe2', '{Na1}[Al1](Si2)O6'),
            (ideal(MgO=0, CaO=0, Na2O=30.9895, Fe2O3=79.8435), 'reported_split', '{Na1}[Fe³⁺1](Si2)O6'),
            (ideal(SiO2=60.083, MgO=0, Al2O3=101.961), 'all_fe2', '{Ca1}[Al1](Al1 Si1)O6'),
        ]
        for values, mode, formula in cases:
            with self.subTest(formula=formula):
                source = measurements(values)
                before = deepcopy(source)
                result = calculate_clinopyroxene_structural(source, mode)
                self.assertEqual(result['status'], 'current', result)
                self.assertEqual(result['values']['structural_formula'], formula)
                self.assertEqual(result['site_order'], ['T', 'M1', 'M2'])
                for site, expected in [('T', 2), ('M1', 1), ('M2', 1)]:
                    self.assertAlmostEqual(result['values'][site+'_sum'], expected, places=10)
                self.assertAlmostEqual(result['values']['charge_sum'], 12, places=10)
                self.assertAlmostEqual(result['values']['cation_sum'], 4, places=10)
                for field, value in result['values'].items():
                    if field.endswith('_apfu') and not field.startswith(('T_', 'M1_', 'M2_')):
                        self.assertAlmostEqual(sum(site.get(field[:-5], 0) for site in result['sites'].values()), value, places=10)
                self.assertEqual(source, before)
                self.assertEqual(result['method_status'], 'draft')
                self.assertNotIn('species', result)
                if formula.startswith('{Na1}'):
                    self.assertNotIn('Wo', result['values'])
                json.dumps(result, allow_nan=False)

    def test_published_s4_split_and_independent_hand_site_allocation(self):
        # Yavuz 2013, printed p1350 Table 5 S4; PDF visually checked.
        expected = {'Si': 1.788, 'Ti': .041, 'Al': .271, 'Fe3': .237,
                    'Fe2': .248, 'Mn': .012, 'Mg': .465, 'Ca': .835, 'Na': .102, 'K': .002}
        result = run(S4, 'reported_split')
        self.assertEqual(result['status'], 'current', result)
        # Printed cations sum ~4 but charge is 12.064, not 12: the paper's
        # default four-cation normalization is not our measured-split six-O basis.
        # Independent reference conversion uses ONLY the printed numbers/valences.
        printed_charge = sum(expected[field] * valence for field, valence in
            [('Si', 4), ('Ti', 4), ('Al', 3), ('Fe3', 3), ('Fe2', 2),
             ('Mn', 2), ('Mg', 2), ('Ca', 2), ('Na', 1), ('K', 1)])
        self.assertAlmostEqual(printed_charge, 12.064, places=10)
        reference_scale = 12 / printed_charge
        for field, value in expected.items():
            self.assertAlmostEqual(result['values'][field+'_apfu'], value * reference_scale, delta=.003, msg=field)
        self.assertAlmostEqual(result['values']['oxide_total'], 98.64, places=10)
        # Independent hand allocation after the reference conversion:
        # T Al=2-1.780=.220, M1 Al=.270-.220=.050, then Fe3/Ti/Mg/Fe2.
        # NOT temperature-dependent Nimis partition rows 80-85.
        for field, expected in {'T_Si_apfu': 1.780, 'T_Al_apfu': .220,
                                'M1_Al_apfu': .050, 'M1_Fe3_apfu': .236,
                                'M1_Ti_apfu': .041, 'M1_Mg_apfu': .463,
                                'M1_Fe2_apfu': .210, 'M2_Fe2_apfu': .037,
                                'M2_Ca_apfu': .831, 'M2_Na_apfu': .102}.items():
            self.assertAlmostEqual(result['values'][field], expected, delta=.004, msg=field)
        self.assertNotIn('estimated_fields', result)

    def test_droop_ferric_endpoint_and_reconstructed_published_s4(self):
        aegirine = ideal(MgO=0, CaO=0, Na2O=30.9895, FeO=71.844)
        result = run(aegirine, 'stoichiometric_droop')
        self.assertEqual(result['status'], 'current', result)
        self.assertAlmostEqual(result['values']['Fe3_apfu'], 1, places=10)
        self.assertAlmostEqual(result['values']['Fe2_apfu'], 0, places=10)
        self.assertEqual(result['values']['structural_formula'], '{Na1}[Fe³⁺1](Si2)O6')
        total = dict(S4)
        # Explicit transformed QA composition, not original measured FeOt.
        # Independent oxide formula masses: 2 FeO=143.688, Fe2O3=159.687.
        total['FeO'] += total.pop('Fe2O3') * 143.688 / 159.687
        result = run(total, 'stoichiometric_droop')
        self.assertEqual(result['status'], 'current', result)
        # Total-Fe reconstruction is a different model, NOT an oracle for the
        # independently supplied ferric fraction. Check balance and explicit estimate.
        self.assertGreater(result['values']['Fe3_apfu'], 0)
        self.assertLess(result['values']['Fe3_apfu'], run(S4, 'reported_split')['values']['Fe3_apfu'])
        self.assertAlmostEqual(result['values']['charge_sum'], 12, places=10)
        self.assertAlmostEqual(result['values']['cation_sum'], 4, places=10)
        self.assertEqual(result['estimated_fields'], ['Fe2_apfu', 'Fe3_apfu'])
        self.assertEqual(result['fe_est_basis']['formula'], 'Fe3+ = 12*(1-4/S)')

    def test_impossible_droop_excess_si_and_nonideal_sums_not_silently_repaired(self):
        for values in [ideal(SiO2=180.249), ideal(SiO2=60.083)]:
            result = run(values, 'stoichiometric_droop')
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['values'], {})
            self.assertTrue(any('Droop' in error for error in result['errors']))
        result = run(ideal(SiO2=180.249))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('Si > 2' in error for error in result['errors']))
        result = run(ideal(MgO=80.608))
        self.assertEqual(result['status'], 'current', result)
        self.assertIn('structural_warning', result)
        self.assertNotAlmostEqual(result['values']['cation_sum'], 4, places=5)

    def test_strict_missing_censored_duplicates_units_and_iron_domains(self):
        for field in ideal():
            composition = ideal(); del composition[field]
            self.assertEqual(run(composition)['status'], 'failed')
        for change in ({'raw_token': '-1'}, {'raw_token': 'nan'}, {'raw_token': 'inf'},
                       {'raw_token': None, 'value_status': 'missing'}, {'unit': 'ppm'},
                       {'qualifier': '<'}, {'raw_token': '<.1', 'value_status': 'below_detection_limit'}):
            rows = measurements(ideal()); rows[0].update(change)
            self.assertEqual(calculate_clinopyroxene_structural(rows, 'all_fe2')['status'], 'failed')
        rows = measurements(ideal())
        self.assertEqual(calculate_clinopyroxene_structural(rows+[rows[0]], 'all_fe2')['status'], 'failed')
        for composition, mode in [(ideal(Fe2O3=0), 'all_fe2'), (ideal(), 'reported_split'),
                                  (ideal(FeOt=0), 'stoichiometric_droop'), (ideal(Fe2O3t=0), 'reported_split')]:
            self.assertEqual(run(composition, mode)['status'], 'failed')
        rows = measurements(S4)
        next(row for row in rows if row['field'] == 'FeO')['reported_fe_form'] = 'FeOt'
        self.assertEqual(calculate_clinopyroxene_structural(rows, 'reported_split')['status'], 'failed')
        for argument in (None, [], 'unknown'):
            self.assertEqual(run(ideal(), argument)['status'], 'failed')
        self.assertEqual(calculate_clinopyroxene_structural(None, 'all_fe2')['status'], 'failed')

    def test_anions_unsupported_inputs_optional_absence_and_numeric_limits(self):
        for field in ('H2O', 'F', 'Cl'):
            self.assertEqual(run(ideal(**{field: 0}))['status'], 'current')
            self.assertEqual(run(ideal(**{field: .01}))['status'], 'failed')
        for field in ('P2O5', 'Mn2O3', 'BaO'):
            self.assertEqual(run(ideal(**{field: 0}))['status'], 'failed')
        result = run(ideal())
        self.assertIn('TiO2', result['unmeasured'])
        self.assertNotIn('Ti_apfu', result['values'])
        rows = measurements(ideal()) + [{'measurement_id': 'trace', 'field': 'Rb',
                                        'raw_token': '12', 'unit': 'ppm', 'value_status': 'numeric'}]
        result = calculate_clinopyroxene_structural(rows, 'all_fe2')
        self.assertEqual(result['excluded'][0]['measurement_id'], 'trace')
        for values in ({key: 1e308 for key in ideal()}, {key: 0 for key in ideal()}):
            result = run(values)
            self.assertEqual(result['status'], 'failed')
            json.dumps(result, allow_nan=False)
