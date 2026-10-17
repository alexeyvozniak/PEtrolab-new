"""Independent Opx stoichiometry; En-or-Cen is NOT an Opx validation oracle."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from petrolab.formula_methods import list_methods
from petrolab.orthopyroxene_structural_formula import calculate_orthopyroxene_structural


def measurements(values):
    return [{'measurement_id': 'm-' + field, 'field': field, 'raw_token': str(value),
             'unit': 'wt.%', 'value_status': 'numeric', 'qualifier': None,
             'reported_fe_form': field if field.startswith('Fe') else None}
            for field, value in values.items()]


def ideal(**extra):
    # Independently pinned oxide masses: SiO2=60.083, MgO=40.304, FeO=71.844.
    return {'SiO2': 120.166, 'Al2O3': 0, 'MgO': 80.608, 'FeO': 0,
            'MnO': 0, 'CaO': 0, 'Na2O': 0, **extra}


def run(values, mode='all_fe2'):
    return calculate_orthopyroxene_structural(measurements(values), mode)


# Yavuz 2013 p1350 Table 5 S1: its name is explicitly "En or Cen".
# No symmetry is inferred here; generic ideal pyroxene arithmetic only.
S1 = {'SiO2': 54.01, 'TiO2': .03, 'Al2O3': 3.95, 'Cr2O3': .57,
      'Fe2O3': 2.07, 'FeO': 1.57, 'MnO': 0, 'NiO': .09, 'MgO': 35.65,
      'CaO': .99, 'Na2O': .08, 'K2O': 0}


class OrthopyroxeneStructuralCoreTests(unittest.TestCase):
    def assert_balanced(self, result):
        self.assertEqual(result['status'], 'current', result)
        self.assertEqual(result['method_status'], 'draft')
        self.assertEqual(result['site_order'], ['T', 'M1', 'M2'])
        for field, value in result['values'].items():
            if field.endswith('_apfu') and not field.startswith(('T_', 'M1_', 'M2_')):
                self.assertAlmostEqual(sum(site.get(field[:-5], 0) for site in result['sites'].values()),
                                       value, places=10)
        self.assertAlmostEqual(result['values']['charge_sum'], 12, places=10)
        self.assertNotIn('species', result)
        self.assertNotIn('symmetry', result)
        self.assertNotIn('temperature', result['values'])
        json.dumps(result, allow_nan=False)

    def test_ideal_enstatite_ferrosilite_and_equal_mix_conserve_atoms(self):
        for composition, expected, formula in [
            (ideal(), {'T': {'Si': 2}, 'M1': {'Mg': 1}, 'M2': {'Mg': 1}}, '{Mg1}[Mg1](Si2)O6'),
            (ideal(MgO=0, FeO=143.688), {'T': {'Si': 2}, 'M1': {'Fe2': 1}, 'M2': {'Fe2': 1}}, '{Fe²⁺1}[Fe²⁺1](Si2)O6'),
            (ideal(MgO=40.304, FeO=71.844), {'T': {'Si': 2}, 'M1': {'Mg': 1}, 'M2': {'Fe2': 1}}, '{Fe²⁺1}[Mg1](Si2)O6'),
        ]:
            with self.subTest(formula=formula):
                source = measurements(composition); before = deepcopy(source)
                result = calculate_orthopyroxene_structural(source, 'all_fe2')
                self.assert_balanced(result)
                self.assertEqual(result['values']['structural_formula'], formula)
                for site, entries in expected.items():
                    self.assertAlmostEqual(result['values'][site + '_sum'], sum(entries.values()), places=10)
                    for field, value in entries.items():
                        self.assertAlmostEqual(result['sites'][site][field], value, places=10)
                self.assertEqual(source, before)
                # The Mg-first 50/50 result is ideal allocation, not measured ordering.
                self.assertTrue(any('не Fe-Mg ordering' in text for text in result['assumptions']))

    def test_independent_ferric_and_aluminous_substitution_endpoints(self):
        # MgFe3AlSiO6: 1 Mg, 1 Fe3, 1 Al, 1 Si; charge 12, four cations.
        split = ideal(SiO2=60.083, MgO=40.304, Al2O3=50.9805, Fe2O3=79.8435)
        estimated = dict(split); del estimated['Fe2O3']; estimated['FeO'] = 71.844
        for composition, mode in [(split, 'reported_split'), (estimated, 'stoichiometric_droop')]:
            with self.subTest(mode=mode):
                result = run(composition, mode); self.assert_balanced(result)
                self.assertAlmostEqual(result['sites']['T']['Si'], 1, places=10)
                self.assertAlmostEqual(result['sites']['T']['Al'], 1, places=10)
                self.assertAlmostEqual(result['sites']['M1']['Fe3'], 1, places=10)
                self.assertAlmostEqual(result['sites']['M2']['Mg'], 1, places=10)
                self.assertAlmostEqual(result['values']['Fe2_apfu'], 0, places=10)
                self.assertAlmostEqual(result['values']['cation_sum'], 4, places=10)
                self.assertEqual('estimated_fields' in result, mode == 'stoichiometric_droop')
                if mode == 'stoichiometric_droop':
                    self.assertEqual(result['fe_est_basis']['formula'], 'Fe3+ = 12*(1-4/S)')
                    self.assertEqual(set(result['fe_est_basis']['input_measurement_ids']),
                                     {row['measurement_id'] for row in measurements(composition)})
        # MgAl2SiO6 independently checks AlIV/AlVI allocation.
        result = run(ideal(SiO2=60.083, MgO=40.304, Al2O3=101.961))
        self.assert_balanced(result)
        self.assertAlmostEqual(result['sites']['T']['Al'], 1, places=10)
        self.assertAlmostEqual(result['sites']['M1']['Al'], 1, places=10)

    def test_printed_en_or_cen_ferric_bulk_and_hand_sites_on_explicit_six_o_basis(self):
        # Independent printed cations. Their charge is 11.934 despite "6 oxygen"
        # label: default four-cation normalization is NOT the measured-split basis.
        printed = {'Si': 1.855, 'Ti': .001, 'Al': .160, 'Cr': .015, 'Fe3': .054,
                   'Fe2': .045, 'Mn': 0, 'Ni': .002, 'Mg': 1.826, 'Ca': .036, 'Na': .005, 'K': 0}
        valences = {'Si': 4, 'Ti': 4, 'Al': 3, 'Cr': 3, 'Fe3': 3, 'Fe2': 2,
                    'Mn': 2, 'Ni': 2, 'Mg': 2, 'Ca': 2, 'Na': 1, 'K': 1}
        charge = sum(printed[field] * valences[field] for field in printed)
        self.assertAlmostEqual(charge, 11.934, places=10)
        expected = {field: value * 12 / charge for field, value in printed.items()}
        result = run(S1, 'reported_split'); self.assert_balanced(result)
        for field, value in expected.items():
            self.assertAlmostEqual(result['values'][field + '_apfu'], value, delta=.003)
        # Independent hand allocation from the printed reference, not production.
        al_t = 2 - expected['Si']
        al_m1 = expected['Al'] - al_t
        mg_m1 = 1 - sum([al_m1, expected['Fe3'], expected['Ti'], expected['Cr'], expected['Ni']])
        for field, value in {'T_Al': al_t, 'M1_Al': al_m1, 'M1_Fe3': expected['Fe3'],
                             'M1_Mg': mg_m1, 'M2_Mg': expected['Mg'] - mg_m1}.items():
            self.assertAlmostEqual(result['values'][field + '_apfu'], value, delta=.006)
        self.assertAlmostEqual(result['values']['oxide_total'], 99.01, places=10)
        self.assertIn('structural_warning', result)  # No forced four-cation repair.
        self.assertNotIn('fe_est_basis', result)

    def test_published_unambiguous_experimental_opx_checks_bulk_not_ferric_validation(self):
        # Journal of Petrology 2022 Table 6, E17-016: explicitly Opx, no
        # independent Fe3 or site occupancy. This is NOT a ferric benchmark.
        composition = {'SiO2': 52.43, 'TiO2': .21, 'Al2O3': 9.10, 'Cr2O3': .65,
                       'FeO': 6.73, 'MgO': 30.39, 'CaO': 1.19, 'Na2O': .06, 'K2O': 0}
        # Structural model additionally requires Mn, whereas this table omits it.
        self.assertEqual(run(composition)['status'], 'failed')
        # A declared subcomposition experiment, not alteration of the published
        # source: Mn=0 is a synthetic assumption for arithmetic verification.
        synthetic = {**composition, 'MnO': 0}
        result = run(synthetic); self.assert_balanced(result)
        for field, expected in {'Si': 1.80, 'Al': .37, 'Fe2': .19, 'Mg': 1.56, 'Ca': .04}.items():
            self.assertAlmostEqual(result['values'][field + '_apfu'], expected, delta=.011)
        self.assertAlmostEqual(result['values']['oxide_total'], 100.76, places=10)

    def test_all_declared_minor_elements_are_retained_in_sites(self):
        # Independently declared atomic/oxide masses and oxidation states;
        # additions perturb an ideal composition, not a natural Opx benchmark.
        for oxide, element, valence, count, mass in [
            ('TiO2', 'Ti', 4, 1, 79.865), ('Cr2O3', 'Cr', 3, 2, 151.989),
            ('NiO', 'Ni', 2, 1, 74.692), ('V2O3', 'V', 3, 2, 149.881),
            ('ZrO2', 'Zr', 4, 1, 123.22), ('Sc2O3', 'Sc', 3, 2, 137.909),
            ('ZnO', 'Zn', 2, 1, 81.379), ('CoO', 'Co', 2, 1, 74.932),
            ('Li2O', 'Li', 1, 2, 29.879), ('K2O', 'K', 1, 2, 94.195)]:
            with self.subTest(oxide=oxide, valence=valence):
                result = run(ideal(**{oxide: .1})); self.assert_balanced(result)
                # Baseline two SiO2 + two MgO contributes exactly six O moles.
                cation_moles = .1 / mass * count
                expected = 6 * cation_moles / (6 + cation_moles * valence / 2)
                self.assertAlmostEqual(result['values'][element + '_apfu'], expected, places=12)
                self.assertNotIn(oxide, result['unmeasured'])
                self.assertIn(oxide, {item['field'] for item in result['used']})

    def test_impossible_droop_and_excess_si_fail_without_preview_values(self):
        for composition in [ideal(SiO2=180.249), ideal(SiO2=60.083),
                            ideal(SiO2=60.083, FeO=0)]:
            result = run(composition, 'stoichiometric_droop')
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['values'], {})
            self.assertTrue(any('Droop' in error for error in result['errors']))
        result = run(ideal(SiO2=180.249))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('Si > 2' in error for error in result['errors']))
        result = run(ideal(MgO=120.912)); self.assert_balanced(result)
        self.assertIn('structural_warning', result)
        self.assertNotAlmostEqual(result['values']['cation_sum'], 4, places=5)

    def test_missing_censored_nonfinite_duplicate_and_wrong_unit_are_not_zero(self):
        for field in ideal():
            composition = ideal(); del composition[field]
            self.assertEqual(run(composition)['status'], 'failed')
        for change in [{'raw_token': '-1'}, {'raw_token': 'NaN'}, {'raw_token': 'inf'},
                       {'raw_token': None, 'value_status': 'missing'}, {'unit': 'ppm'},
                       {'raw_token': '<.1', 'value_status': 'below_detection_limit'}, {'qualifier': '<'}]:
            rows = measurements(ideal()); rows[0].update(change)
            self.assertEqual(calculate_orthopyroxene_structural(rows, 'all_fe2')['status'], 'failed')
        rows = measurements(ideal())
        self.assertEqual(calculate_orthopyroxene_structural(rows + [rows[0]], 'all_fe2')['status'], 'failed')
        for rows in (None, 'bad', [None], [{}]):
            self.assertEqual(calculate_orthopyroxene_structural(rows, 'all_fe2')['status'], 'failed')
        for mode in (None, [], 'not-installed'):
            self.assertEqual(run(ideal(), mode)['status'], 'failed')
        for composition in ({field: 1e308 for field in ideal()}, {field: 0 for field in ideal()}):
            result = run(composition); self.assertEqual(result['status'], 'failed')
            json.dumps(result, allow_nan=False)

    def test_fe_forms_cannot_masquerade_as_reported_split_or_be_combined(self):
        for composition, mode in [(ideal(Fe2O3=0), 'all_fe2'), (ideal(), 'reported_split'),
                                  (ideal(FeOt=0), 'stoichiometric_droop'), (ideal(Fe2O3t=0), 'reported_split')]:
            self.assertEqual(run(composition, mode)['status'], 'failed')
        for field, reported in [('FeO', 'FeOt'), ('Fe2O3', 'Fe2O3t')]:
            rows = measurements(S1)
            next(row for row in rows if row['field'] == field)['reported_fe_form'] = reported
            self.assertEqual(calculate_orthopyroxene_structural(rows, 'reported_split')['status'], 'failed')
        rows = measurements(ideal()); next(row for row in rows if row['field'] == 'FeO')['field'] = 'FeOt'
        self.assertEqual(calculate_orthopyroxene_structural(rows, 'all_fe2')['values'], run(ideal())['values'])

    def test_anions_trace_exclusions_and_optional_absence_preserve_provenance(self):
        for field in ('F', 'Cl', 'H2O'):
            result = run(ideal(**{field: 0})); self.assert_balanced(result)
            self.assertIn(field, {row['field'] for row in result['used']})
            self.assertEqual(run(ideal(**{field: .01}))['status'], 'failed')
        for field in ('P2O5', 'BaO', 'Mn2O3'):
            self.assertEqual(run(ideal(**{field: 0}))['status'], 'failed')
        rows = measurements(ideal()) + [{'measurement_id': 'trace-Rb', 'field': 'Rb',
                                         'unit': 'ppm', 'raw_token': '12', 'value_status': 'numeric'}]
        result = calculate_orthopyroxene_structural(rows, 'all_fe2'); self.assert_balanced(result)
        self.assertEqual(result['excluded'][0]['measurement_id'], 'trace-Rb')
        self.assertIn('TiO2', result['unmeasured'])
        self.assertNotIn('Ti_apfu', result['values'])
        self.assertNotIn('OH_apfu', result['values'])

    def test_core_is_not_installed_and_old_scientific_implementations_are_unchanged(self):
        self.assertEqual([method['method_id'] for method in list_methods('enstatite')['methods']],
                         ['orthopyroxene.oxygen6'])
        self.assertNotIn('orthopyroxene.structural6', [method['method_id'] for method in list_methods()['methods']])
        root = Path(__file__).resolve().parents[1] / 'src/petrolab'
        for module, expected in [
            ('orthopyroxene_formula.py', '90e6999502d392087e546ba2f5311b47fc57bc3f590c9292eec3180aa47cf0dd'),
            ('clinopyroxene_structural_formula.py', 'ffc297d084c065d1faa9fa95cf626f6978e20bf64f9f09114f89ec9fc22d60aa'),
        ]:
            self.assertEqual(hashlib.sha256((root / module).read_bytes().replace(b'\r\n', b'\n')).hexdigest(), expected)
