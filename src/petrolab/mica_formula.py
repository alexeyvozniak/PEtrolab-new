"""Draft bulk mica APFU on 22 positive charges; see ADR 0020 for scope."""
import math

METHOD_ID = 'mica.charge22'
METHOD_VERSION = '0.1.0'
# CIAAW abridged 2024, accessed 2026-09-14. Independent of olivine's definition.
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Al': 26.982, 'Ti': 47.867,
                 'Cr': 51.996, 'Fe': 55.845, 'Mg': 24.305, 'Mn': 54.938,
                 'Ni': 58.693, 'Ca': 40.078, 'Na': 22.990, 'K': 39.098,
                 'Li': 6.94, 'Ba': 137.33, 'F': 18.998, 'Cl': 35.45}
# field: element, number of cations, number of oxygens, valence, output label
OXIDES = {'SiO2': ('Si', 1, 2, 4, 'Si'), 'Al2O3': ('Al', 2, 3, 3, 'Al'),
          'TiO2': ('Ti', 1, 2, 4, 'Ti'), 'Cr2O3': ('Cr', 2, 3, 3, 'Cr'),
          'FeO': ('Fe', 1, 1, 2, 'Fe2'), 'FeOt': ('Fe', 1, 1, 2, 'Fe2'),
          'Fe2O3': ('Fe', 2, 3, 3, 'Fe3'), 'MgO': ('Mg', 1, 1, 2, 'Mg'),
          'MnO': ('Mn', 1, 1, 2, 'Mn'), 'NiO': ('Ni', 1, 1, 2, 'Ni'),
          'CaO': ('Ca', 1, 1, 2, 'Ca'), 'Na2O': ('Na', 2, 1, 1, 'Na'),
          'K2O': ('K', 2, 1, 1, 'K'), 'Li2O': ('Li', 2, 1, 1, 'Li'),
          'BaO': ('Ba', 1, 1, 2, 'Ba')}
FE_MODES = {'all_fe2', 'reported_split'}
OH_MODES = {'not_calculated', 'ideal_2_minus_f_cl'}


def calculate_mica(measurements, fe_mode, *, anion_basis, oh_mode):
    """Calculate without changing inputs or interpreting the mineral's identity."""
    errors, warnings, used, excluded, seen, values = [], [], [], [], set(), {}
    result = {'method_id': METHOD_ID, 'method_version': METHOD_VERSION,
              'method_status': 'draft', 'status': 'failed', 'errors': errors,
              'warnings': warnings, 'values': {}, 'used': used, 'excluded': excluded,
              'unmeasured': [], 'assumptions': []}
    if not isinstance(fe_mode, str) or fe_mode not in FE_MODES:
        errors.append('Явно выберите all_fe2 или reported_split для железа.')
    if anion_basis != 'ideal_O10_W2':
        errors.append('Этот метод требует явного допущения ideal_O10_W2; окисленный базис 22+z не поддерживается.')
    if not isinstance(oh_mode, str) or oh_mode not in OH_MODES:
        errors.append('Явно выберите, оценивать ли OH по идеальной анионной группе.')
    if errors:
        return result
    result['parameters'] = {'fe_mode': fe_mode, 'anion_basis': anion_basis, 'oh_mode': oh_mode}
    supported = set(OXIDES) | {'F', 'Cl'}
    for measurement in measurements:
        field = measurement.get('field')
        if not isinstance(field, str) or not field:
            errors.append('Компонент без канонического названия.')
            continue
        if field in seen:
            errors.append(f'{field}: несколько измерений; выберите один набор до расчёта.')
        seen.add(field)
        if field not in supported:
            if measurement.get('unit') == 'wt.%' or field.startswith(('Fe', 'H2O')):
                errors.append(f'{field}: не поддерживается методом 22 charges без измеренного H₂O.')
            else:
                excluded.append({'field': field, 'measurement_id': measurement.get('measurement_id'),
                                 'reason': 'Вне композиционного домена метода.'})
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
    required = {'SiO2', 'Al2O3', 'MgO', 'K2O'}
    if fe_mode == 'all_fe2':
        if len({'FeO', 'FeOt'} & seen) != 1 or {'Fe2O3', 'Fe2O3t'} & seen:
            errors.append('Fe²⁺: нужна ровно одна колонка FeO/FeOt без Fe₂O₃/Fe₂O₃t.')
        required.add('FeOt' if 'FeOt' in seen else 'FeO')
    else:
        required |= {'FeO', 'Fe2O3'}
        if {'FeOt', 'Fe2O3t'} & seen:
            errors.append('Раздельное железо несовместимо с суммарным FeOt/Fe₂O₃t.')
    if oh_mode == 'ideal_2_minus_f_cl':
        required |= {'F', 'Cl'}
    for field in sorted(required - values.keys()):
        errors.append(f'{field}: нет пригодного обязательного измерения (явный ноль допустим).')
    result['unmeasured'] = sorted(supported - seen - {'FeO', 'FeOt', 'Fe2O3'})
    if errors:
        return result
    if values['SiO2'] <= 0:
        errors.append('SiO2 должен быть больше нуля для формулы слюды.')
        return result
    cations, charge, oxide_total = {}, 0.0, 0.0
    for field, value in values.items():
        if field not in OXIDES:
            continue
        element, count, oxygens, valence, output = OXIDES[field]
        moles = value / (ATOMIC_MASSES[element] * count + ATOMIC_MASSES['O'] * oxygens)
        cations[output] = moles * count
        charge += moles * count * valence
        oxide_total += value
    if not math.isfinite(charge) or charge <= 0 or not math.isfinite(oxide_total):
        errors.append('Сумма заряда или оксидов вне допустимого числового диапазона.')
        return result
    apfu = {name: amount / charge * 22 for name, amount in cations.items()}
    halogens = {field: values[field] / ATOMIC_MASSES[field] / charge * 22
                for field in ('F', 'Cl') if field in values}
    if any(not math.isfinite(value) for value in [*apfu.values(), *halogens.values()]):
        errors.append('APFU выходит за допустимый числовой диапазон.')
        return result
    halogen_sum = sum(halogens.values())
    if halogen_sum > 2 + 1e-10:
        errors.append('Измеренные F + Cl превышают 2 APFU: несовместимо с ideal_O10_W2.')
        return result
    outputs = {f'{name}_apfu': value for name, value in {**apfu, **halogens}.items()}
    if oh_mode == 'ideal_2_minus_f_cl':
        outputs['OH_est_apfu'] = max(0.0, 2 - halogen_sum)
        result['OH_est_basis'] = {'formula': '2 - F_apfu - Cl_apfu',
                                  'anion_basis': anion_basis, 'normalization': '22 positive charges',
                                  'input_measurement_ids': [m.get('measurement_id') for m in used]}
        if halogen_sum > 2:
            warnings.append('OH округлён до нуля: превышение F + Cl над 2 не более 1e-10 APFU.')
    assumptions = ['Идеальная анионная группа O₁₀W₂, W = OH/F/Cl; 22 положительных заряда.',
                   'Сумма wt.% не нормировалась к 100%; F/Cl не входят в сумму катионных зарядов.',
                   'Без распределения по позициям, оценки вакансий, Li, номенклатуры и неопределённости.',
                   'Всё железо принято Fe²⁺; Fe³⁺ не определён.' if fe_mode == 'all_fe2' else
                   'Fe²⁺ и Fe³⁺ взяты из раздельных измерений; автоматической переоценки нет.',
                   'OH оценён по идеальной группе, не измерен.' if oh_mode == 'ideal_2_minus_f_cl' else
                   'OH не рассчитывался; неизвестные F/Cl не заменялись нулём.']
    if result['unmeasured']:
        warnings.append('Неизмеренные дополнительные компоненты перечислены отдельно; APFU относится к доступному составу.')
    if 'Li2O' not in seen:
        warnings.append('Li не измерен; Li-содержащие слюды могут иметь неполную формулу.')
    if apfu['Si'] > 4 + 0.05 or sum(apfu.values()) > 8 + 0.05:
        warnings.append('Si > 4,05 или сумма катионов > 8,05 APFU; проверьте состав и выбранный базис.')
    warnings.append('Метод draft: независимая проверка на природных составах ещё не выполнена.')
    result.update(status='current', values={**outputs, 'cation_sum': sum(apfu.values()),
                  'oxide_total': oxide_total}, assumptions=assumptions)
    return result
