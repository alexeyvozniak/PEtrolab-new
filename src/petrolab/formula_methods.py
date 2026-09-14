"""Small executable registry, separate from presentation and persistence."""
import copy
import hashlib
import json

from .mica_formula import (ANION_BASES as MICA_ANION_BASES, ATOMIC_MASSES as MICA_ATOMIC_MASSES,
                           FE_MODES as MICA_FE_MODES, METHOD_ID as MICA_METHOD_ID,
                           METHOD_VERSION as MICA_METHOD_VERSION, OH_MODES as MICA_OH_MODES,
                           OXIDES as MICA_OXIDES, calculate_mica)
from .olivine_formula import (ATOMIC_MASSES as OLIVINE_ATOMIC_MASSES,
                              FE_MODES as OLIVINE_FE_MODES, OXIDES as OLIVINE_OXIDES,
                              calculate_olivine)
from .mineral_verification import reported_target

METHOD_ID = 'olivine.oxygen4'
METHOD_VERSION = '1.0.0'
IMPLEMENTATION_SHA256 = '0d1313ebe3ab47cca45f8e6c5364be51ed8d113c44677f95890bdeeedadc16ee'
MICA_IMPLEMENTATION_SHA256 = '95821d9252d7577ad1d7bf95e64e6fb62a4ea536086c3c8d0c0c7742afc1442a'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _olivine_definition():
    fields = sorted({f'{oxide[3]}_apfu' for oxide in OLIVINE_OXIDES.values()})
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


def _mica_definition():
    fields = sorted({f'{oxide[4]}_apfu' for oxide in MICA_OXIDES.values()})
    definition = {
        'method_id': MICA_METHOD_ID, 'version': MICA_METHOD_VERSION,
        'name': 'Слюды · 22 заряда · bulk APFU', 'kind': 'formula', 'status': 'draft',
        'input_domain': {'semantic_domain': 'oxide_wt_percent',
                         'required_fields': ['SiO2', 'Al2O3', 'MgO', 'K2O'],
                         'allowed_units': ['wt.%'], 'missing_policy': 'reject_row',
                         'censored_policy': 'reject_row',
                         'compositional_domain_policy': 'explicit_subcomposition_required',
                         'nonpositive_policy': 'not_applicable', 'mixed_unit_policy': 'reject'},
        'parameters': [
            {'name': 'fe_mode', 'value_type': 'choice', 'scientifically_significant': True},
            {'name': 'anion_basis', 'value_type': 'choice', 'scientifically_significant': True},
            {'name': 'oh_mode', 'value_type': 'choice', 'scientifically_significant': True}],
        'output_fields': ([{'field': field, 'semantic_role': 'derived_value', 'unit': 'apfu'}
                           for field in fields]
                          + [{'field': field, 'semantic_role': 'derived_value', 'unit': 'apfu'}
                             for field in ('F_apfu', 'Cl_apfu', 'OH_est_apfu')]
                          + [{'field': 'cation_sum', 'semantic_role': 'diagnostic', 'unit': 'apfu'},
                             {'field': 'oxide_total', 'semantic_role': 'diagnostic', 'unit': 'wt.%'}]),
        'citations': [
            {'title': 'Rieder et al. (1998), Nomenclature of the Micas',
             'url': 'https://minsocam.org/msa/ima/ima98%2810%29.pdf'},
            {'title': 'CIAAW Abridged Standard Atomic Weights 2024',
             'url': 'https://ciaaw.org/abridged-atomic-weights.htm'}],
        'assumptions': [
            'Идеальная анионная группа O10W2; нормировка на 22 положительных заряда.',
            'OH_est = 2 - F - Cl только по пригодным измеренным F и Cl и явному выбору.',
            'Без нормировки суммы wt.% к 100%, распределения по позициям и номенклатуры.',
            'Fe3+, Li, вакансии и неопределённость не оцениваются автоматически.'],
        'applicability': [
            'Только явно принятая слюда из trioctahedral, dioctahedral или Li-mica target.',
            'Варианты с измеренным H2O и окисленный базис 22+z не поддерживаются.',
            'Пригодность состава проверяется независимо от назначения.',
            'Метод draft: внешняя проверка на природных составах ещё требуется.'],
        'benchmark_ids': ['mica-phlogopite', 'mica-annite', 'mica-muscovite',
                          'mica-fluorophlogopite', 'mica-ti-ferric'],
        'implementation': {'algorithm_id': MICA_METHOD_ID,
                           'algorithm_version': MICA_METHOD_VERSION,
                           'implementation_sha256': MICA_IMPLEMENTATION_SHA256},
        'created_at': '2026-09-14T00:00:00Z',
    }
    definition['definition_fingerprint'] = fingerprint(definition)
    return definition


def method_definition(method_id=METHOD_ID, version=None):
    """Return one installed definition without changing existing olivine identity."""
    installed = {METHOD_ID: (METHOD_VERSION, _olivine_definition),
                 MICA_METHOD_ID: (MICA_METHOD_VERSION, _mica_definition)}
    current = installed.get(method_id)
    if current is None or (version is not None and version != current[0]):
        raise KeyError((method_id, version))
    return current[1]()


def executable_method(method_id, version):
    """Resolve domain behavior for workflow dispatch; values are never serialized."""
    definition = method_definition(method_id, version)
    if method_id == METHOD_ID:
        return {'definition': definition, 'accepted_targets': {'olivine'}, 'target_label': 'оливина',
                'parameter_choices': {'fe_mode': OLIVINE_FE_MODES},
                'calculate': lambda rows, p: calculate_olivine(rows, p['fe_mode'])}
    return {'definition': definition,
            'accepted_targets': {'trioctahedral mica', 'dioctahedral mica', 'Li-mica'},
            'target_label': 'слюды',
            'parameter_choices': {'fe_mode': MICA_FE_MODES, 'anion_basis': MICA_ANION_BASES,
                                  'oh_mode': MICA_OH_MODES},
            'calculate': lambda rows, p: calculate_mica(rows, p['fe_mode'],
                anion_basis=p['anion_basis'], oh_mode=p['oh_mode'])}


def list_methods(accepted_assignment=None):
    """List installed methods, optionally narrowed to one accepted mineral label."""
    accepted_target = reported_target(accepted_assignment) if accepted_assignment is not None else None
    methods = []
    for method_id, version, masses in ((METHOD_ID, METHOD_VERSION, OLIVINE_ATOMIC_MASSES),
                                       (MICA_METHOD_ID, MICA_METHOD_VERSION, MICA_ATOMIC_MASSES)):
        registration = executable_method(method_id, version)
        if accepted_assignment is not None and accepted_target not in registration['accepted_targets']:
            continue
        choices = registration['parameter_choices']
        item = {**registration['definition'], 'parameter_choices': copy.deepcopy(choices),
                'fe_modes': copy.deepcopy(choices['fe_mode']),
                'atomic_masses': copy.deepcopy(masses)}
        if method_id == MICA_METHOD_ID:
            item.update(anion_bases=copy.deepcopy(MICA_ANION_BASES),
                        oh_modes=copy.deepcopy(MICA_OH_MODES))
        methods.append(item)
    return {'methods': methods}
