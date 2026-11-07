"""Draft orthopyroxene bulk APFU on six oxygens, without site allocation.

This implementation is frozen independently of clinopyroxene. Its numerical
scheme is similar, but the two versioned methods must not silently change one
another's implementation fingerprints.
"""
import math

METHOD_ID = 'orthopyroxene.oxygen6'
METHOD_VERSION = '0.1.0'
# CIAAW abridged 2024; pinned for this method version.
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Ti': 47.867, 'Al': 26.982,
                 'Cr': 51.996, 'Fe': 55.845, 'Mg': 24.305, 'Mn': 54.938,
                 'Ni': 58.693, 'Ca': 40.078, 'Na': 22.990, 'K': 39.098}
# field: element, cations per oxide, oxygens per oxide, output label
OXIDES = {'SiO2': ('Si', 1, 2, 'Si'), 'TiO2': ('Ti', 1, 2, 'Ti'),
          'Al2O3': ('Al', 2, 3, 'Al'), 'Cr2O3': ('Cr', 2, 3, 'Cr'),
          'FeO': ('Fe', 1, 1, 'Fe2'), 'FeOt': ('Fe', 1, 1, 'Fe2'),
          'Fe2O3': ('Fe', 2, 3, 'Fe3'), 'MgO': ('Mg', 1, 1, 'Mg'),
          'MnO': ('Mn', 1, 1, 'Mn'), 'NiO': ('Ni', 1, 1, 'Ni'),
          'CaO': ('Ca', 1, 1, 'Ca'), 'Na2O': ('Na', 2, 1, 'Na'),
          'K2O': ('K', 2, 1, 'K')}
FE_MODES = {'all_fe2': 'Всё железо как Fe²⁺ (FeO или FeOt)',
            'reported_split': 'Раздельные измеренные FeO и Fe₂O₃'}


def calculate_orthopyroxene(measurements, fe_mode):
    """Calculate only bulk six-oxygen APFU and Ca-Mg-Fe2 proportions."""
    errors, warnings, used, excluded, seen, values = [], [], [], [], set(), {}
    result = {'method_id': METHOD_ID, 'method_version': METHOD_VERSION,
              'method_status': 'draft', 'status': 'failed', 'errors': errors,
              'warnings': warnings, 'values': {}, 'used': used, 'excluded': excluded,
              'unmeasured': [], 'assumptions': []}
    if not isinstance(fe_mode, str) or fe_mode not in FE_MODES:
        errors.append('Явно выберите all_fe2 или reported_split для железа.')
        return result
    result['parameters'] = {'fe_mode': fe_mode}
    for measurement in measurements:
        field = measurement.get('field')
        if not isinstance(field, str) or not field:
            errors.append('Компонент без канонического названия.')
            continue
        if field in seen:
            errors.append(f'{field}: несколько измерений; выберите один набор до расчёта.')
        seen.add(field)
        if field not in OXIDES:
            if measurement.get('unit') == 'wt.%' or field.startswith(('Fe', 'H2O')):
                errors.append(f'{field}: не поддерживается этим методом; компонент нельзя отбросить молча.')
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
        if field.startswith('Fe'):
            allowed = {'FeO', 'FeOt'} if fe_mode == 'all_fe2' and field in {'FeO', 'FeOt'} else {field}
            if measurement.get('reported_fe_form') not in {None, '', *allowed}:
                errors.append(f'{field}: исходная форма железа несовместима с выбранным режимом.')
                continue
        try:
            value = float(str(measurement.get('raw_token')).replace(',', '.'))
        except (ValueError, TypeError):
            value = float('nan')
        if not math.isfinite(value) or value < 0:
            errors.append(f'{field}: требуется конечное неотрицательное число.')
            continue
        values[field] = value
        used.append(dict(measurement))
    # An explicit numeric CaO zero is required to compute Wo: absent is not zero.
    required = {'SiO2', 'MgO', 'CaO'}
    if fe_mode == 'all_fe2':
        if len({'FeO', 'FeOt'} & seen) != 1 or {'Fe2O3', 'Fe2O3t'} & seen:
            errors.append('Fe²⁺: нужна ровно одна колонка FeO/FeOt без Fe₂O₃/Fe₂O₃t.')
        required.add('FeOt' if 'FeOt' in seen else 'FeO')
    else:
        required |= {'FeO', 'Fe2O3'}
        if {'FeOt', 'Fe2O3t'} & seen:
            errors.append('Раздельное железо несовместимо с суммарным FeOt/Fe₂O₃t.')
    for field in sorted(required - values.keys()):
        errors.append(f'{field}: нет пригодного обязательного измерения (явный ноль допустим).')
    result['unmeasured'] = sorted(set(OXIDES) - seen - {'FeO', 'FeOt', 'Fe2O3'})
    if errors:
        return result
    if values['SiO2'] <= 0:
        errors.append('SiO2 должен быть больше нуля для формулы ортопироксена.')
        return result
    cations, oxygen_moles, oxide_total = {}, 0.0, 0.0
    for field, value in values.items():
        element, count, oxygens, output = OXIDES[field]
        moles = value / (ATOMIC_MASSES[element] * count + ATOMIC_MASSES['O'] * oxygens)
        cations[output] = moles * count
        oxygen_moles += moles * oxygens
        oxide_total += value
    if not math.isfinite(oxygen_moles) or oxygen_moles <= 0 or not math.isfinite(oxide_total):
        errors.append('Сумма кислорода или оксидов вне допустимого числового диапазона.')
        return result
    apfu = {name: amount / oxygen_moles * 6 for name, amount in cations.items()}
    if any(not math.isfinite(value) for value in apfu.values()):
        errors.append('APFU выходит за допустимый числовой диапазон.')
        return result
    denominator = sum(apfu.get(name, 0.0) for name in ('Ca', 'Mg', 'Fe2'))
    if denominator <= 0:
        errors.append('Ca + Mg + Fe²⁺ равно нулю: Wo–En–Fs не определены.')
        return result
    ternary = {'Wo': apfu['Ca'] / denominator * 100,
               'En': apfu['Mg'] / denominator * 100,
               'Fs': apfu['Fe2'] / denominator * 100}
    assumptions = ['6 атомов O; сумма wt.% не нормировалась к 100%.',
                   'Wo–En–Fs = доли Ca, Mg и Fe²⁺ только в их сумме; не название минерала.',
                   'Без распределения по позициям M2/M1/T, оценки Fe³⁺ по Droop и номенклатуры.',
                   'Всё железо принято Fe²⁺; Fe³⁺ не определён.' if fe_mode == 'all_fe2' else
                   'Fe²⁺ и Fe³⁺ взяты из раздельных измерений; переоценки нет.']
    if result['unmeasured']:
        warnings.append('Неизмеренные дополнительные оксиды перечислены отдельно; APFU относится к доступному составу.')
    if abs(sum(apfu.values()) - 4) > 0.05:
        warnings.append('Сумма катионов отличается от 4 более чем на 0,05 APFU; проверьте состав и Fe-базис.')
    warnings.append('Метод draft: bulk APFU и Wo–En–Fs не устанавливают вид пироксена.')
    result.update(status='current', values={**{f'{name}_apfu': value for name, value in apfu.items()},
                  **ternary, 'cation_sum': sum(apfu.values()), 'oxide_total': oxide_total},
                  assumptions=assumptions)
    return result
