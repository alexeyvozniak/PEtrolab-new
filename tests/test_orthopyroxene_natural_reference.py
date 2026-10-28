"""Original natural Opx input and independent ferric reference, without fitted sites."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from petrolab.orthopyroxene_structural_formula import calculate_orthopyroxene_structural


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'fixtures/formula/orthopyroxene_tariat2018_reference.json'


def reference_rows(reference, split=False):
    # Test-only transcription of published inputs. No inverse formula and no
    # call to production calculation prepares either inputs or expected values.
    oxides = dict(reference['original_mean_oxides'])
    if split:
        del oxides['FeOt']
        oxides.update(reference['published_recast_iron_oxides'])
    rows = []
    for field, value in oxides.items():
        recast = split and field in reference['published_recast_iron_oxides']
        rows.append({'measurement_id': reference['reference_id'] + '/' + field,
                     'field': field, 'raw_token': str(value), 'unit': reference['oxide_unit'],
                     'value_status': 'numeric', 'qualifier': None,
                     'reported_fe_form': field if field.startswith('Fe') else None,
                     # Fixture provenance only; not a new production/domain field.
                     'reference_provenance': {
                         'doi': reference['citation']['doi'],
                         'source': 'section5.1/recast' if recast else 'Table1/EPMA',
                         'published_recast_not_direct_measurement': recast}})
    return rows


class OrthopyroxeneNaturalReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference_bytes = REFERENCE.read_bytes()
        self.reference = json.loads(self.reference_bytes)

    def check_published(self, result, key):
        self.assertEqual(result['status'], 'current', result)
        self.assertEqual(result['method_status'], 'draft')
        for field, expected in self.reference[key].items():
            with self.subTest(field=field):
                self.assertAlmostEqual(result['values'][field + '_apfu'], expected,
                                       delta=self.reference['bulk_reference_tolerance_apfu'])
        for field, amount in result['values'].items():
            if field.endswith('_apfu') and not field.startswith(('T_', 'M1_', 'M2_')):
                self.assertAlmostEqual(sum(site.get(field[:-5], 0) for site in result['sites'].values()),
                                       amount, places=12)
        self.assertAlmostEqual(result['values']['charge_sum'], 12, places=12)

    def test_original_total_iron_matches_printed_bulk_and_retains_total_discrepancy(self):
        rows = reference_rows(self.reference); before = deepcopy(rows)
        result = calculate_orthopyroxene_structural(rows, 'all_fe2')
        self.check_published(result, 'original_table1_bulk_apfu_all_fe2')
        self.assertAlmostEqual(result['values']['oxide_total'], 99.84, places=12)
        self.assertAlmostEqual(self.reference['printed_original_total_wt_percent'], 99.83, places=12)
        self.assertNotIn('Fe3_apfu', result['values'])
        self.assertNotIn('estimated_fields', result)
        self.assertEqual(rows, before)
        self.assertEqual(result['used'], before)
        self.assertEqual(REFERENCE.read_bytes(), self.reference_bytes)

    def test_published_ferric_recast_matches_bulk_but_not_physical_ordering(self):
        rows = reference_rows(self.reference, split=True); before = deepcopy(rows)
        result = calculate_orthopyroxene_structural(rows, 'reported_split')
        self.check_published(result, 'published_section51_bulk_apfu_split')
        self.assertAlmostEqual(result['values']['oxide_total'], 99.94, places=12)
        self.assertAlmostEqual(result['values']['T_Al_apfu'], .101, delta=.001)
        self.assertAlmostEqual(result['values']['M1_Al_apfu'], .089, delta=.001)
        ferric_fraction = result['values']['Fe3_apfu'] / (
            result['values']['Fe2_apfu'] + result['values']['Fe3_apfu'])
        self.assertAlmostEqual(ferric_fraction, self.reference['independent_iron_measurement']['Fe3_fraction_of_total_Fe'],
                               delta=self.reference['independent_iron_measurement']['Fe3_fraction_standard_deviation'])
        # Independent physical occupancy is deliberately NOT the oracle for
        # ideal allocation. Atom conservation is the contract; no forced fit.
        self.assertGreater(abs(result['values']['M1_Fe2_apfu'] - .046), .04)
        self.assertGreater(abs(result['values']['M2_Fe2_apfu'] - .100), .04)
        # Keep Ni and the actual Mn input despite omissions in printed formula.
        self.assertGreater(result['values']['Ni_apfu'], .001)
        self.assertGreater(abs(result['values']['Mn_apfu'] - .003), .0015)
        self.assertIn('structural_warning', result)
        self.assertNotAlmostEqual(result['values']['cation_sum'], 4, places=3)
        self.assertNotIn('estimated_fields', result)
        recast = [row for row in result['used'] if row['field'] in {'FeO', 'Fe2O3'}]
        self.assertTrue(all(row['reference_provenance']['published_recast_not_direct_measurement'] for row in recast))
        self.assertTrue(any('происхождение' in text for text in result['assumptions']))
        self.assertFalse(any('измеренные' in text or 'из раздельных измерений' in text for text in result['assumptions']))
        self.assertEqual(rows, before)
        self.assertEqual(REFERENCE.read_bytes(), self.reference_bytes)

    def test_natural_droop_counterexample_is_not_fitted_to_measured_ferric_iron(self):
        rows = reference_rows(self.reference); before = deepcopy(rows)
        result = calculate_orthopyroxene_structural(rows, 'stoichiometric_droop')
        self.assertEqual(result['status'], 'current', result)
        self.assertEqual(result['estimated_fields'], ['Fe2_apfu', 'Fe3_apfu'])
        estimated_fraction = result['values']['Fe3_apfu'] / (
            result['values']['Fe2_apfu'] + result['values']['Fe3_apfu'])
        self.assertLess(estimated_fraction, .001)
        self.assertGreater(abs(estimated_fraction - .15), .14)
        self.assertTrue(any('не заменяет' in text for text in result['warnings']))
        self.assertAlmostEqual(result['values']['cation_sum'], 4, places=12)
        self.assertAlmostEqual(result['values']['charge_sum'], 12, places=12)
        self.assertEqual(rows, before)
        self.assertEqual(result['fe_est_basis']['input_measurement_ids'], [row['measurement_id'] for row in rows])
        self.assertEqual(REFERENCE.read_bytes(), self.reference_bytes)

    def test_reference_and_old_production_methods_cannot_be_silently_rewritten(self):
        self.assertEqual(self.reference['scope'], 'Natural enstatite mean, n=22; not a single analysis or validated method')
        self.assertEqual(set(self.reference['original_mean_oxides']), set(self.reference['original_mean_standard_deviation']))
        self.assertNotIn('Fe2O3', self.reference['original_mean_oxides'])
        self.assertEqual(set(self.reference['published_recast_iron_oxides']), {'FeO', 'Fe2O3'})
        self.assertTrue(self.reference['recast_iron_provenance']['not_direct_measurement_of_separate_oxides'])
        # Registry intentionally unchanged; natural benchmark is not native acceptance.
        from petrolab.formula_methods import list_methods
        self.assertEqual([method['method_id'] for method in list_methods('enstatite')['methods']], ['orthopyroxene.oxygen6'])
        self.assertEqual(hashlib.sha256((ROOT / 'src/petrolab/orthopyroxene_formula.py').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                         '90e6999502d392087e546ba2f5311b47fc57bc3f590c9292eec3180aa47cf0dd')
