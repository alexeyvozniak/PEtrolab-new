"""Unregistered draft Opx core: ideal allocation, NOT physical site occupancy.

Frozen independently from Cpx and the existing Opx oxygen6 method. A published
ferric En-or-Cen reference tests the generic ideal pyroxene model only.
The independent natural Tariat reference checks bulk APFU and demonstrates
limits of stoichiometric Fe3 estimates and ideal Fe/Mg ordering. Neither
reference establishes symmetry or scientifically validates the method.
"""
import math

METHOD_ID = 'orthopyroxene.structural6'
METHOD_VERSION = '0.1.0'
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Ti': 47.867, 'Al': 26.982,
                 'Cr': 51.996, 'Fe': 55.845, 'Mg': 24.305, 'Mn': 54.938,
                 'Ni': 58.693, 'Ca': 40.078, 'Na': 22.990, 'K': 39.098,
                 'V': 50.942, 'Zr': 91.222, 'Sc': 44.956, 'Zn': 65.38,
                 'Co': 58.933, 'Li': 6.94}
# element, cation count, oxygen count, output cation, declared valence
OXIDES = {'SiO2': ('Si', 1, 2, 'Si', 4), 'TiO2': ('Ti', 1, 2, 'Ti', 4),
          'Al2O3': ('Al', 2, 3, 'Al', 3), 'Cr2O3': ('Cr', 2, 3, 'Cr', 3),
          'FeO': ('Fe', 1, 1, 'Fe2', 2), 'FeOt': ('Fe', 1, 1, 'Fe2', 2),
          'Fe2O3': ('Fe', 2, 3, 'Fe3', 3), 'MgO': ('Mg', 1, 1, 'Mg', 2),
          'MnO': ('Mn', 1, 1, 'Mn', 2), 'NiO': ('Ni', 1, 1, 'Ni', 2),
          'CaO': ('Ca', 1, 1, 'Ca', 2), 'Na2O': ('Na', 2, 1, 'Na', 1),
          'K2O': ('K', 2, 1, 'K', 1), 'V2O3': ('V', 2, 3, 'V', 3),
          'ZrO2': ('Zr', 1, 2, 'Zr', 4), 'Sc2O3': ('Sc', 2, 3, 'Sc', 3),
          'ZnO': ('Zn', 1, 1, 'Zn', 2), 'CoO': ('Co', 1, 1, 'Co', 2),
          'Li2O': ('Li', 2, 1, 'Li', 1)}
REQUIRED = {'SiO2', 'Al2O3', 'MgO', 'MnO', 'CaO', 'Na2O'}
ZERO_ANIONS = {'F', 'Cl', 'H2O'}
FE_MODES = {'all_fe2': '6 O; всё измеренное Fe принято Fe²⁺, Fe³⁺ не оценено',
            'reported_split': '6 O; раздельные FeO и Fe₂O₃ из входных данных',
            'stoichiometric_droop': '6 O / 4 катиона; Fe³⁺ оценено по Droop (1987)'}
ROUNDING_TOLERANCE = 1e-10


def _sites(cations):
    """Ideal pyroxene allocation, Yavuz 2013 p1339; not real Opx Fe/Mg ordering."""
    remaining = dict(cations)
    sites = {'T': {}, 'M1': {}, 'M2': {}}

    def put(site, element, limit=None):
        if element not in remaining:
            return
        available = remaining[element]
        amount = available if limit is None else min(available, max(0.0, limit))
        sites[site][element] = sites[site].get(element, 0.0) + amount
        remaining[element] = max(0.0, available - amount)

    for element in ('Si', 'Al', 'Fe3'):
        put('T', element, 2 - sum(sites['T'].values()))
    # Fixed-valence M1 constituents are retained even if they overfill M1.
    for element in ('Al', 'Fe3', 'Ti', 'Cr', 'V', 'Zr', 'Sc', 'Zn', 'Ni', 'Co'):
        put('M1', element)
    for element in ('Mg', 'Fe2', 'Mn'):
        put('M1', element, 1 - sum(sites['M1'].values()))
        put('M2', element)
    for element in ('Li', 'Ca', 'Na', 'K'):
        put('M2', element)
    return sites


def _formula(sites):
    labels = {'Fe2': 'Fe²⁺', 'Fe3': 'Fe³⁺'}
    parts = []
    for site, brackets in (('M2', '{}'), ('M1', '[]'), ('T', '()')):
        text = ' '.join(labels.get(element, element) + f'{amount:.3f}'.rstrip('0').rstrip('.')
                        for element, amount in sorted(sites[site].items(), key=lambda item: (-item[1], item[0]))
                        if round(amount, 3) > 0)
        parts.append(brackets[0] + text + brackets[1])
    return ''.join(parts) + 'O6'


def calculate_orthopyroxene_structural(measurements, fe_mode):
    errors, warnings, used, excluded = [], [], [], []
    result = {'method_id': METHOD_ID, 'method_version': METHOD_VERSION, 'method_status': 'draft',
              'status': 'failed', 'errors': errors, 'warnings': warnings, 'used': used,
              'excluded': excluded, 'unmeasured': [], 'assumptions': [], 'values': {},
              'parameters': {'fe_mode': fe_mode}}
    if not isinstance(fe_mode, str) or fe_mode not in FE_MODES:
        errors.append('Явно выберите установленный режим железа для структурного ортопироксена.')
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
            errors.append(f'{field}: ненулевой анион несовместим с безводным 6 O методом.')
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
        errors.append('SiO2 должен быть больше нуля для силикатного ортопироксена.')
        return result
    amounts, oxygen_moles, oxide_total = {}, 0.0, 0.0
    for field, value in values.items():
        oxide_total += value
        if field in ZERO_ANIONS:
            continue
        element, count, oxygens, output, _ = OXIDES[field]
        moles = value / (ATOMIC_MASSES[element] * count + ATOMIC_MASSES['O'] * oxygens)
        amounts[output] = moles * count
        oxygen_moles += moles * oxygens
    if not math.isfinite(oxygen_moles) or oxygen_moles <= 0 or not math.isfinite(oxide_total):
        errors.append('Сумма кислорода/оксидов вне допустимого числового диапазона.')
        return result
    cations = {name: amount / oxygen_moles * 6 for name, amount in amounts.items()}
    if any(not math.isfinite(value) for value in cations.values()):
        errors.append('APFU вне допустимого числового диапазона.')
        return result
    assumptions = ['Безводная модель O6; неизвестные H/F/Cl не считаются измеренным нулём.',
                   'Сумма wt.% не нормировалась к 100%.',
                   'T/M1/M2 — идеальная оценка Morimoto/WinPyrox, не измеренная заселённость и не Fe-Mg ordering ортопироксена.',
                   'Ti4+/Cr3+/V3+/Zr4+/Sc3+/Zn2+/Ni2+/Co2+/Mn2+/Li1+ по выбранным оксидам, без переоценки валентностей.',
                   'Строка формулы округлена до 0,001 APFU; полные числа сохранены отдельно.',
                   'Нет определения симметрии, вида, физических Fe-Mg позиций, конечных членов, термобарометрии или неопределённости.']
    if fe_mode == 'stoichiometric_droop':
        initial_sum = sum(cations.values())
        scale = 4 / initial_sum
        cations = {name: amount * scale for name, amount in cations.items()}
        ferric, total_fe = 12 * (1 - scale), cations['Fe2']
        if ferric < -ROUNDING_TOLERANCE or ferric > total_fe + ROUNDING_TOLERANCE:
            errors.append('Droop даёт Fe³⁺ вне диапазона 0…Fe_total; проверьте состав и обоснуйте другой режим.')
            return result
        if ferric < 0 or ferric > total_fe:
            warnings.append('Fe³⁺ скорректировано только на числовое округление ≤1e-10 APFU.')
        ferric = min(total_fe, max(0.0, ferric))
        cations['Fe2'], cations['Fe3'] = total_fe - ferric, ferric
        result['fe_est_basis'] = {'formula': 'Fe3+ = 12*(1-4/S)', 'S': initial_sum,
                                  'oxygen_basis': 6, 'cation_basis': 4,
                                  'input_measurement_ids': [m['measurement_id'] for m in used if m.get('measurement_id')]}
        result['estimated_fields'] = ['Fe2_apfu', 'Fe3_apfu']
        assumptions.append('Droop: только Fe переменно-валентен, только O анион, четыре занятые катионные позиции.')
        warnings.append('Стехиометрическая оценка Fe³⁺ не заменяет независимое измерение железа.')
    else:
        assumptions.append('Fe²⁺/Fe³⁺ взяты из входных FeO/Fe₂O₃; происхождение и преобразования должны быть указаны в provenance.' if fe_mode == 'reported_split' else
                           'Всё измеренное Fe принято Fe²⁺; отсутствие Fe³⁺ в результате не является его измерением.')
    if cations['Si'] > 2 + ROUNDING_TOLERANCE:
        errors.append('Si > 2 APFU: избыточный Si не может быть молча отброшен в этой модели T/M1/M2.')
        return result
    # Keep any <=1e-10 floating Si excess in T rather than losing an input atom.
    sites = _sites(cations)
    sites['T']['Si'] = cations['Si']
    for element, amount in cations.items():
        if not math.isclose(sum(site.get(element, 0.0) for site in sites.values()), amount, abs_tol=1e-10):
            errors.append('Внутренняя ошибка баланса распределения по позициям.')
            return result
    for site, target in (('T', 2), ('M1', 1), ('M2', 1)):
        total = sum(sites[site].values())
        if abs(total - target) > .001:
            warnings.append(f'Сумма {site}={total:.5f} отличается от {target}; позиции не подогнаны к идеалу.')
            result['structural_warning'] = 'Суммы позиций отличаются от модели 2/1/1; эмпирическая формула не исправляет состав.'
    denominator = sum(cations[name] for name in ('Ca', 'Mg', 'Fe2'))
    ternary = {key: cations[name] / denominator * 100 for key, name in
               (('Wo', 'Ca'), ('En', 'Mg'), ('Fs', 'Fe2'))} if denominator > 0 else {}
    if not ternary:
        warnings.append('Ca + Mg + Fe²⁺ равно нулю: Wo–En–Fs не определены и не подставлены.')
    else:
        assumptions.append('Wo–En–Fs — доли только Ca/Mg/Fe²⁺, не полный набор конечных членов Na-содержащего пироксена.')
    charge = sum(amount * next(oxide[4] for oxide in OXIDES.values() if oxide[3] == name)
                 for name, amount in cations.items())
    result.update(status='current', assumptions=assumptions, sites=sites, site_order=['T', 'M1', 'M2'],
                  values={**{name + '_apfu': amount for name, amount in cations.items()}, **ternary,
                          **{site + '_' + name + '_apfu': amount for site, entries in sites.items() for name, amount in entries.items()},
                          **{site + '_sum': sum(entries.values()) for site, entries in sites.items()},
                          'cation_sum': sum(cations.values()), 'oxide_total': oxide_total,
                          'charge_sum': charge, 'structural_formula': _formula(sites)})
    warnings.append('Метод draft; структурная формула и позиции модельные, не определение вида.')
    if result['unmeasured']:
        warnings.append('Неизмеренные компоненты перечислены отдельно; формула относится к доступному составу.')
    return result
