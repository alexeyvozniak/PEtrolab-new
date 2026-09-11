"""Small executable registry, separate from presentation and persistence."""
import copy
import hashlib
import json

from .olivine_formula import ATOMIC_MASSES, FE_MODES, OXIDES, calculate_olivine

METHOD_ID = 'olivine.oxygen4'
METHOD_VERSION = '1.0.0'
IMPLEMENTATION_SHA256 = '0d1313ebe3ab47cca45f8e6c5364be51ed8d113c44677f95890bdeeedadc16ee'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def method_definition():
    fields = sorted({f'{oxide[3]}_apfu' for oxide in OXIDES.values()})
    definition = {
        'method_id': METHOD_ID, 'version': METHOD_VERSION,
        'name': 'Оливин · 4 O · APFU и бинарные Fo–Fa', 'kind': 'formula', 'status': 'draft',
        'input_domain': {'semantic_domain': 'oxide_wt_percent',
                         'required_fields': ['SiO2', 'MgO'], 'allowed_units': ['wt.%'],
                         'missing_policy': 'reject_row', 'censored_policy': 'reject_row',
                         'compositional_domain_policy': 'explicit_subcomposition_required',
                         'nonpositive_policy': 'not_applicable', 'mixed_unit_policy': 'reject'},
        'parameters': [{'name': 'fe_mode', 'value_type': 'choice', 'scientifically_significant': True}],
        'output_fields': [{'field': f, 'semantic_role': 'derived_value', 'unit': 'apfu'} for f in fields]
                         + [{'field': f, 'semantic_role': 'derived_value', 'unit': 'mol.%'} for f in ('Fo', 'Fa')]
                         + [{'field': 'cation_sum', 'semantic_role': 'diagnostic', 'unit': 'apfu'},
                            {'field': 'oxide_total', 'semantic_role': 'diagnostic', 'unit': 'wt.%'}],
        'citations': [
            {'title': 'Brady & Perkins (2007), Mineral Formulae Recalculation',
             'url': 'https://serc.carleton.edu/research_education/equilibria/mineralformulaerecalculation.html'},
            {'title': 'CIAAW Abridged Standard Atomic Weights 2024',
             'url': 'https://ciaaw.org/abridged-atomic-weights.htm'}],
        'assumptions': ['4 O; без нормировки суммы wt.% к 100%.',
                        'Fo = 100 Mg/(Mg+Fe2), Fa = 100 Fe2/(Mg+Fe2); Mn/Ca/Ni отдельно.',
                        'Нули допустимы; SiO2 и Mg+Fe2 должны быть положительны.',
                        'Fe: ровно один FeO/FeOt для all_fe2; FeO и Fe2O3 для reported_split.',
                        'Fe3+, OH, позиции и неопределённость не оцениваются.'],
        'applicability': ['Только явно принятый оливин/форстерит/фаялит.',
                          'Пригодность состава проверяется независимо от назначения.',
                          'Неизмеренные дополнительные оксиды перечисляются, не заменяются нулями.',
                          'Первый метод: внешняя проверка на природных анализах ещё требуется.'],
        'benchmark_ids': ['ol-fo100', 'ol-fa100', 'ol-fo50', 'ol-mn-ca-ni', 'ol-split-fe'],
        'implementation': {'algorithm_id': METHOD_ID, 'algorithm_version': METHOD_VERSION,
                           'implementation_sha256': IMPLEMENTATION_SHA256},
        'created_at': '2026-09-11T00:00:00Z',
    }
    definition['definition_fingerprint'] = fingerprint(definition)
    return definition


def list_methods():
    return {'methods': [{**method_definition(), 'fe_modes': copy.deepcopy(FE_MODES),
                         'atomic_masses': copy.deepcopy(ATOMIC_MASSES)}]}
