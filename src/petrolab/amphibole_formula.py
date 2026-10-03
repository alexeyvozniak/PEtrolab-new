"""Draft bulk amphibole cations on 23 oxygen equivalents; no site allocation."""

import math

METHOD_ID = 'amphibole.oxygen23'
METHOD_VERSION = '0.1.0'
# CIAAW abridged 2024; frozen for this method version.
ATOMIC_MASSES = {'O': 15.999, 'Si': 28.085, 'Ti': 47.867, 'Al': 26.982,
                 'Cr': 51.996, 'Fe': 55.845, 'Mg': 24.305, 'Mn': 54.938,
                 'Ni': 58.693, 'Ca': 40.078, 'Na': 22.990, 'K': 39.098}
OXIDES = {'SiO2': ('Si', 1, 2, 'Si'), 'TiO2': ('Ti', 1, 2, 'Ti'),
          'Al2O3': ('Al', 2, 3, 'Al'), 'Cr2O3': ('Cr', 2, 3, 'Cr'),
          'FeO': ('Fe', 1, 1, 'Fe2'), 'FeOt': ('Fe', 1, 1, 'Fe2'),
          'MgO': ('Mg', 1, 1, 'Mg'), 'MnO': ('Mn', 1, 1, 'Mn'),
          'NiO': ('Ni', 1, 1, 'Ni'), 'CaO': ('Ca', 1, 1, 'Ca'),
          'Na2O': ('Na', 2, 1, 'Na'), 'K2O': ('K', 2, 1, 'K')}


def calculate_amphibole(measurements, fe_mode):
    """Return only measured-oxide bulk APFU for limited Mg-Ca amphiboles.

    23 O is an oxygen-equivalent convention, not a determination of OH, W-site
    occupancy, Fe oxidation, site assignment or mineral species.
    """
    errors, warnings, used, excluded, seen, values = [], [], [], [], set(), {}
    result = {'method_id': METHOD_ID, 'method_version': METHOD_VERSION,
              'method_status': 'draft', 'status': 'failed', 'errors': errors,
              'warnings': warnings, 'values': {}, 'used': used, 'excluded': excluded,
              'unmeasured': [], 'assumptions': [], 'parameters': {'fe_mode': fe_mode}}
    if fe_mode != 'all_fe2':
        errors.append('Этот draft-метод поддерживает только явный режим all_fe2; Fe³⁺ не оценивается.')
        return result
    for measurement in measurements:
        field = measurement.get('field')
        if not isinstance(field, str) or not field:
            errors.append('Компонент без канонического названия.')
            continue
        if field in seen:
            errors.append(f'{field}: несколько измерений; выберите один набор до расчёта.')
        seen.add(field)
        if field not in OXIDES:
            if measurement.get('unit') == 'wt.%' or field.startswith(('Fe', 'H2O')) or field in {'F', 'Cl'}:
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
        if field in {'FeO', 'FeOt'} and measurement.get('reported_fe_form') not in {None, '', field}:
            errors.append(f'{field}: исходная форма железа несовместима с all_fe2.')
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
    if {'FeO', 'FeOt'} <= seen:
        errors.append('FeO и FeOt нельзя суммировать: выберите одну исходную форму.')
    for field in sorted({'SiO2', 'MgO', 'CaO'} - values.keys()):
        errors.append(f'{field}: нет пригодного обязательного измерения (явный ноль допустим).')
    result['unmeasured'] = sorted(set(OXIDES) - seen - {'FeO', 'FeOt'})
    if not {'FeO', 'FeOt'} & seen:
        warnings.append('Железо не измерено; это не означает Fe = 0.')
    if errors:
        return result
    if values['SiO2'] <= 0:
        errors.append('SiO2 должен быть больше нуля для формулы амфибола.')
        return result
    if values['MgO'] <= 0 or values['CaO'] <= 0:
        errors.append('Ограниченный Mg-Ca метод требует MgO и CaO больше нуля; явный ноль не подменяется пропуском.')
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
    apfu = {name: amount / oxygen_moles * 23 for name, amount in cations.items()}
    if any(not math.isfinite(value) for value in apfu.values()):
        errors.append('APFU выходит за допустимый числовой диапазон.')
        return result
    result.update(status='current',
                  values={**{f'{name}_apfu': value for name, value in apfu.items()},
                          'cation_sum': sum(apfu.values()), 'oxide_total': oxide_total},
                  assumptions=['23 кислородных эквивалента; сумма wt.% не нормировалась к 100%.',
                               'Только bulk-катионы; OH, F, Cl и W-позиция не вычислялись.',
                               'Fe из FeO/FeOt считается Fe²⁺; Fe³⁺ не оценивается.',
                               'Нет распределения A/B/C/T, конечных членов или определения вида.'])
    if result['unmeasured']:
        warnings.append('Неизмеренные дополнительные оксиды перечислены отдельно; APFU относится к доступному составу.')
    if apfu['Si'] > 8.05 or abs(sum(apfu.values()) - 15) > 0.5:
        warnings.append('Сумма катионов или Si отклоняется от идеального амфибола; проверьте состав и базис.')
    warnings.append('Метод draft: bulk APFU не устанавливает вид амфибола.')
    return result
