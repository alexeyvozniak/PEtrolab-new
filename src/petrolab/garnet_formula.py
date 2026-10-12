"""Versioned anhydrous silicate-garnet model: 12 O, explicit Fe and X/Y/Z."""
import math

METHOD_ID = 'garnet.structural12'
METHOD_VERSION = '0.1.0'
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Ti': 47.867, 'Al': 26.982,
                 'Cr': 51.996, 'Fe': 55.845, 'Mg': 24.305, 'Mn': 54.938,
                 'Ca': 40.078, 'Na': 22.990}
# element, cation count, oxygen count, output cation, valence
OXIDES = {'SiO2': ('Si', 1, 2, 'Si', 4), 'TiO2': ('Ti', 1, 2, 'Ti', 4),
          'Al2O3': ('Al', 2, 3, 'Al', 3), 'Cr2O3': ('Cr', 2, 3, 'Cr', 3),
          'FeO': ('Fe', 1, 1, 'Fe2', 2), 'FeOt': ('Fe', 1, 1, 'Fe2', 2),
          'Fe2O3': ('Fe', 2, 3, 'Fe3', 3), 'MgO': ('Mg', 1, 1, 'Mg', 2),
          'MnO': ('Mn', 1, 1, 'Mn', 2), 'CaO': ('Ca', 1, 1, 'Ca', 2),
          'Na2O': ('Na', 2, 1, 'Na', 1)}
FE_MODES = {'all_fe2': '12 O; всё измеренное Fe принято Fe²⁺, Fe³⁺ не оценено',
            'reported_split': '12 O; раздельные измеренные FeO и Fe₂O₃',
            'stoichiometric_droop': '12 O / 8 катионов; Fe³⁺ оценено по Droop (1987)'}
REQUIRED = {'SiO2', 'Al2O3', 'MgO', 'MnO', 'CaO'}
ZERO_ANIONS = {'F', 'Cl', 'H2O'}
ROUNDING_TOLERANCE = 1e-10


def _sites(cations):
    """Common-element subset of Yavuz & Yildirim 2020, section 2.1."""
    remaining = dict(cations)
    sites = {'X': {}, 'Y': {}, 'Z': {}}

    def put(site, element, amount=None):
        if element not in remaining:
            return
        available = remaining[element]
        quantity = available if amount is None else min(available, max(0.0, amount))
        sites[site][element] = sites[site].get(element, 0.0) + quantity
        remaining[element] = max(0.0, available - quantity)

    def space(site, capacity):
        return max(0.0, capacity - sum(sites[site].values()))

    put('Z', 'Si', 3)
    put('Y', 'Si')
    for element in ('Al', 'Fe3'):
        put('Z', element, space('Z', 3))
        put('Y', element)
    for element in ('Ca', 'Na'):
        put('X', element)
    for element in ('Cr', 'Ti'):
        put('Y', element)
    put('Z', 'Fe2', space('Z', 3))
    # Ti can move from overfull Y only to a remaining Z deficit.
    transfer = min(space('Z', 3), max(0.0, sum(sites['Y'].values()) - 2),
                   sites['Y'].get('Ti', 0.0))
    if transfer > 0:
        sites['Y']['Ti'] -= transfer
        sites['Z']['Ti'] = transfer
    for element in ('Mg', 'Fe2', 'Mn'):
        put('Y', element, space('Y', 2))
        put('X', element)
    return sites


def _formula(sites):
    labels = {'Fe2': 'Fe²⁺', 'Fe3': 'Fe³⁺'}
    parts = []
    for site, brackets in (('X', '{}'), ('Y', '[]'), ('Z', '()')):
        content = ' '.join(labels.get(element, element) + f'{amount:.3f}'.rstrip('0').rstrip('.')
                           for element, amount in sorted(sites[site].items(), key=lambda item: (-item[1], item[0]))
                           if round(amount, 3) > 0)
        parts.append(brackets[0] + content + brackets[1])
    return ''.join(parts) + 'O12'


def calculate_garnet(measurements, fe_mode):
    errors, warnings, used, excluded = [], [], [], []
    result = {'method_id': METHOD_ID, 'method_version': METHOD_VERSION, 'method_status': 'draft',
              'status': 'failed', 'errors': errors, 'warnings': warnings, 'used': used,
              'excluded': excluded, 'unmeasured': [], 'assumptions': [], 'values': {},
              'parameters': {'fe_mode': fe_mode}}
    if not isinstance(fe_mode, str) or fe_mode not in FE_MODES:
        errors.append('Явно выберите установленный режим железа для граната.')
        return result
    if not isinstance(measurements, list):
        errors.append('Ожидается список измерений одного анализа.')
        return result
    values, seen = {}, set()
    for measurement in measurements:
        if not isinstance(measurement, dict):
            errors.append('Неверная запись измерения.')
            continue
        field = measurement.get('field')
        if not isinstance(field, str) or not field:
            errors.append('Компонент без канонического названия.')
            continue
        if field in seen:
            errors.append(f'{field}: несколько измерений; выберите один набор до расчёта.')
        seen.add(field)
        if field not in OXIDES and field not in ZERO_ANIONS:
            if measurement.get('unit') == 'wt.%' or field.startswith(('Fe', 'H2O')):
                errors.append(f'{field}: не поддерживается этой версией; компонент нельзя отбросить молча.')
            else:
                excluded.append({'field': field, 'measurement_id': measurement.get('measurement_id'),
                                 'reason': 'Вне оксидного wt.% домена метода.'})
            continue
        if measurement.get('unit') != 'wt.%':
            errors.append(f'{field}: требуется wt.%.')
            continue
        if measurement.get('value_status') != 'numeric' or measurement.get('qualifier'):
            errors.append(f'{field}: пропуск или censored-значение не заменяется нулём.')
            continue
        allowed_fe = {'FeO', 'FeOt'} if fe_mode != 'reported_split' and field in {'FeO', 'FeOt'} else {field}
        if field.startswith('Fe') and measurement.get('reported_fe_form') not in {None, '', *allowed_fe}:
            errors.append(f'{field}: исходная форма железа несовместима с выбранным режимом.')
            continue
        try:
            value = float(str(measurement.get('raw_token')).replace(',', '.'))
        except (ValueError, TypeError):
            value = float('nan')
        if not math.isfinite(value) or value < 0:
            errors.append(f'{field}: требуется конечное неотрицательное число.')
            continue
        if field in ZERO_ANIONS and value != 0:
            errors.append(f'{field}: ненулевой анион несовместим с безводным 12 O методом.')
            continue
        values[field] = value
        used.append(dict(measurement))
    required = set(REQUIRED)
    if fe_mode == 'reported_split':
        required |= {'FeO', 'Fe2O3'}
        if {'FeOt', 'Fe2O3t'} & seen:
            errors.append('Измеренное раздельное железо несовместимо с суммарным FeOt/Fe₂O₃t.')
    else:
        if len({'FeO', 'FeOt'} & seen) != 1 or {'Fe2O3', 'Fe2O3t'} & seen:
            errors.append('Нужна ровно одна колонка FeO/FeOt без Fe₂O₃/Fe₂O₃t.')
        required.add('FeOt' if 'FeOt' in seen else 'FeO')
    for field in sorted(required - values.keys()):
        errors.append(f'{field}: нет пригодного обязательного измерения; явный ноль отличается от пропуска.')
    result['unmeasured'] = sorted((set(OXIDES) | ZERO_ANIONS) - seen - {'FeO', 'FeOt', 'Fe2O3'})
    if errors:
        return result
    if values['SiO2'] <= 0:
        errors.append('SiO2 должен быть больше нуля для силикатного граната.')
        return result
    amounts, oxygen_moles, oxide_total = {}, 0.0, 0.0
    for field, value in values.items():
        oxide_total += value
        if field in ZERO_ANIONS:
            continue  # Measured zero retained in used; no fabricated anion output.
        element, count, oxygens, output, _ = OXIDES[field]
        moles = value / (ATOMIC_MASSES[element] * count + ATOMIC_MASSES['O'] * oxygens)
        amounts[output] = moles * count
        oxygen_moles += moles * oxygens
    if not math.isfinite(oxygen_moles) or oxygen_moles <= 0 or not math.isfinite(oxide_total):
        errors.append('Сумма кислорода/оксидов вне допустимого числового диапазона.')
        return result
    cations = {name: amount / oxygen_moles * 12 for name, amount in amounts.items()}
    if any(not math.isfinite(value) for value in cations.values()):
        errors.append('APFU вне допустимого числового диапазона.')
        return result
    assumptions = ['Безводная модель O12; неизвестные H/F/Cl не считаются измеренным нулём.',
                   'Сумма wt.% не нормировалась к 100%.',
                   'Позиции X/Y/Z — оценка по последовательности Grew/WinGrt, не измеренная заселённость.',
                   'Формула для отображения округлена до 0,001 APFU; полные числа сохранены отдельно.',
                   'Нет автоматического имени вида, конечных членов или оценки Mn³⁺.']
    if fe_mode == 'stoichiometric_droop':
        initial_sum = sum(cations.values())
        if not math.isfinite(initial_sum) or initial_sum <= 0:
            errors.append('Сумма катионов непригодна для Droop.')
            return result
        scale = 8 / initial_sum
        cations = {name: amount * scale for name, amount in cations.items()}
        ferric = 24 * (1 - scale)
        total_fe = cations['Fe2']
        if ferric < -ROUNDING_TOLERANCE or ferric > total_fe + ROUNDING_TOLERANCE:
            errors.append('Droop даёт Fe³⁺ вне диапазона 0…Fe_total; проверьте состав/анионы, выберите другой обоснованный режим.')
            return result
        if ferric < 0 or ferric > total_fe:
            warnings.append('Fe³⁺ скорректировано только на числовое округление ≤1e-10 APFU.')
        ferric = min(total_fe, max(0.0, ferric))
        cations['Fe2'], cations['Fe3'] = total_fe - ferric, ferric
        result['fe_est_basis'] = {'formula': 'Fe3+ = 24*(1-8/S)', 'S': initial_sum,
                                  'oxygen_basis': 12, 'cation_basis': 8,
                                  'input_measurement_ids': [m['measurement_id'] for m in used if m.get('measurement_id')]}
        result['estimated_fields'] = ['Fe2_apfu', 'Fe3_apfu']
        assumptions.append('Fe³⁺ оценено по Droop; Fe — единственный переменно-валентный элемент, O — единственный анион, восемь занятых катионных позиций.')
    else:
        assumptions.append('Fe²⁺/Fe³⁺ взяты из раздельных измерений.' if fe_mode == 'reported_split' else
                           'Всё измеренное Fe принято Fe²⁺; отсутствие Fe³⁺ в результате не является его измерением.')
    sites = _sites(cations)
    for element, amount in cations.items():
        if not math.isclose(sum(site.get(element, 0.0) for site in sites.values()), amount, abs_tol=1e-10):
            errors.append('Внутренняя ошибка баланса распределения по позициям.')
            return result
    for site, target in (('X', 3), ('Y', 2), ('Z', 3)):
        total = sum(sites[site].values())
        if abs(total - target) > .001:
            warnings.append(f'Сумма {site}={total:.5f} отличается от {target}; позиции не подогнаны к идеалу.')
            result['structural_warning'] = 'Суммы позиций отличаются от модели 3/2/3; эмпирическая формула не исправляет состав.'
    charge = sum(amount * next(oxide[4] for oxide in OXIDES.values() if oxide[3] == element)
                 for element, amount in cations.items())
    result.update(status='current', assumptions=assumptions, sites=sites,
                  values={**{f'{name}_apfu': value for name, value in cations.items()},
                          **{f'{site}_{name}_apfu': value for site, entries in sites.items() for name, value in entries.items()},
                          **{f'{site}_sum': sum(entries.values()) for site, entries in sites.items()},
                          'cation_sum': sum(cations.values()), 'oxide_total': oxide_total,
                          'charge_sum': charge, 'structural_formula': _formula(sites)})
    warnings.append('Метод draft; структурная формула и позиции модельные, не определение вида.')
    if result['unmeasured']:
        warnings.append('Неизмеренные компоненты перечислены отдельно; безводность является допущением модели.')
    return result
