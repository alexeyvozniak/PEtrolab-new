"""Oxygen-normalized olivine APFU; no site allocation or inferred ferric iron."""
import math

# CIAAW Abridged Standard Atomic Weights 2024, accessed 2026-09-11.
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Ti': 47.867, 'Al': 26.982,
                 'Cr': 51.996, 'Fe': 55.845, 'Mn': 54.938, 'Mg': 24.305,
                 'Ni': 58.693, 'Ca': 40.078, 'Na': 22.990, 'K': 39.098}
# field: (element, cations, oxygen, result field)
OXIDES = {'SiO2': ('Si', 1, 2, 'Si'), 'TiO2': ('Ti', 1, 2, 'Ti'),
          'Al2O3': ('Al', 2, 3, 'Al'), 'Cr2O3': ('Cr', 2, 3, 'Cr'),
          'FeO': ('Fe', 1, 1, 'Fe2'), 'FeOt': ('Fe', 1, 1, 'Fe2'),
          'Fe2O3': ('Fe', 2, 3, 'Fe3'), 'MnO': ('Mn', 1, 1, 'Mn'),
          'MgO': ('Mg', 1, 1, 'Mg'), 'NiO': ('Ni', 1, 1, 'Ni'),
          'CaO': ('Ca', 1, 1, 'Ca'), 'Na2O': ('Na', 2, 1, 'Na'),
          'K2O': ('K', 2, 1, 'K')}
FE_MODES = {'all_fe2': 'Всё железо как Fe²⁺ (FeO или FeOt)',
            'reported_split': 'Раздельные FeO и Fe₂O₃ из измерений'}


def calculate_olivine(measurements, fe_mode):
    """Return diagnostics for every supplied component, never substitute values."""
    errors, warnings, excluded, used = [], [], [], []
    values, seen = {}, set()
    if fe_mode not in FE_MODES:
        return {'status': 'failed', 'errors': ['Выберите поддерживаемый режим Fe.'],
                'warnings': [], 'values': {}, 'used': [], 'excluded': [], 'unmeasured': []}
    for m in measurements:
        field = m.get('field')
        if not isinstance(field, str) or not field:
            errors.append('Компонент без канонического названия.')
            continue
        if field in seen:
            errors.append(f'{field}: несколько измерений; выберите один набор до расчёта.')
        seen.add(field)
        if field not in OXIDES:
            if m.get('unit') == 'wt.%' or field.startswith('Fe'):
                errors.append(f'{field}: компонент не поддерживается этим методом.')
            else:
                excluded.append({'field': field, 'measurement_id': m.get('measurement_id'),
                                 'reason': 'Вне оксидного домена метода.'})
            continue
        if m.get('unit') != 'wt.%':
            errors.append(f'{field}: требуется wt.%, получено {m.get("unit")}.')
            continue
        if m.get('value_status') != 'numeric' or m.get('qualifier'):
            errors.append(f'{field}: пропуск или censored-значение не заменяется нулём.')
            continue
        if field.startswith('Fe') and m.get('reported_fe_form') == 'unresolved':
            errors.append(f'{field}: исходная форма железа не определена.')
            continue
        if field.startswith('Fe') and m.get('reported_fe_form'):
            allowed_forms = {'FeO', 'FeOt'} if fe_mode == 'all_fe2' and field in {'FeO', 'FeOt'} else {field}
            if m['reported_fe_form'] not in allowed_forms:
                errors.append(f'{field}: исходная форма {m["reported_fe_form"]} несовместима с выбранным режимом.')
                continue
        try:
            value = float(str(m.get('raw_token')).replace(',', '.'))
        except (ValueError, TypeError):
            value = float('nan')
        if not math.isfinite(value) or value < 0:
            errors.append(f'{field}: требуется конечное неотрицательное число.')
            continue
        values[field] = value
        used.append(dict(m))
    required = {'SiO2', 'MgO'}
    if fe_mode == 'all_fe2':
        if len({'FeO', 'FeOt'} & seen) != 1 or {'Fe2O3', 'Fe2O3t'} & seen:
            errors.append('Режим Fe²⁺ требует ровно одну колонку FeO/FeOt без Fe₂O₃ или Fe₂O₃t.')
        required |= ({'FeOt'} if 'FeOt' in seen else {'FeO'})
    else:
        required |= {'FeO', 'Fe2O3'}
        if {'FeOt', 'Fe2O3t'} & seen:
            errors.append('Раздельное железо несовместимо с суммарным FeOt/Fe₂O₃t.')
    for field in sorted(required - values.keys()):
        errors.append(f'{field}: нет пригодного обязательного измерения (явный ноль допустим).')
    unmeasured = sorted(set(OXIDES) - seen - {'FeO', 'FeOt', 'Fe2O3'})
    result = {'status': 'failed', 'errors': errors, 'warnings': warnings,
              'values': {}, 'used': used, 'excluded': excluded, 'unmeasured': unmeasured}
    if errors:
        return result
    if values['SiO2'] <= 0:
        errors.append('SiO2 должен быть больше нуля для формулы оливина.')
        return result
    oxygen, cations = 0.0, {}
    for field, value in values.items():
        element, count, oxygens, output = OXIDES[field]
        moles = value / (ATOMIC_MASSES[element] * count + ATOMIC_MASSES['O'] * oxygens)
        oxygen += moles * oxygens
        cations[output] = moles * count
    if not math.isfinite(oxygen) or oxygen <= 0:
        errors.append('Недопустимая сумма кислорода.')
        return result
    apfu = {field: value / oxygen * 4 for field, value in cations.items()}
    denominator = apfu['Mg'] + apfu['Fe2']
    if denominator <= 0:
        errors.append('Mg + Fe²⁺ равны нулю: Fo–Fa не определены.')
        return result
    total = sum(values.values())
    if not math.isfinite(total):
        errors.append('Сумма состава выходит за числовой диапазон.')
        return result
    if not 95 <= total <= 105:
        warnings.append('Сумма использованных оксидов вне 95–105 wt.%; нормировка к 100% не выполнялась.')
    if abs(apfu['Si'] - 1) > 0.05 or abs(sum(apfu.values()) - 3) > 0.05:
        warnings.append('Отклонение от Si = 1 или суммы катионов = 3 превышает 0,05 APFU; проверьте состав и фазу.')
    if unmeasured:
        warnings.append('Неизмеренные дополнительные оксиды не включены; APFU относится к доступному составу.')
    if excluded:
        warnings.append('Компоненты вне оксидного домена перечислены отдельно и не участвовали в расчёте.')
    assumptions = ['Нормировка на 4 O; сумма wt.% не приводилась к 100%.',
                   'Fo–Fa: только Mg и Fe²⁺; Mn/Ca/Ni не входят в знаменатель.',
                   'Без распределения по позициям, оценки OH и неопределённости.']
    assumptions.append('Всё исходное железо принято двухвалентным; Fe³⁺ не измерен этим расчётом.'
                       if fe_mode == 'all_fe2' else 'Fe²⁺ и Fe³⁺ взяты из раздельных FeO и Fe₂O₃; переоценка не выполнялась.')
    result.update(status='current', values={**{f'{key}_apfu': val for key, val in apfu.items()},
                  'Fo': 100 * apfu['Mg'] / denominator, 'Fa': 100 * apfu['Fe2'] / denominator,
                  'cation_sum': sum(apfu.values()), 'oxide_total': total}, assumptions=assumptions)
    return result
