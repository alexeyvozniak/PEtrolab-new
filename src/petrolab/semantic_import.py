"""Physical-range decisions and evidence. No raw-cell mutation or sample merge."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from uuid import uuid4

from .analyte_dictionary import recognize_analyte

SEMANTIC_ACTIONS = [
    {'role': 'sample', 'label': 'Назначить образец', 'value_required': True},
    {'role': 'sample_id_column', 'label': 'Колонка — Sample ID'},
    {'role': 'sample_name_column', 'label': 'Колонка — Sample name'},
    {'role': 'analysis_column', 'label': 'Колонка — Analysis ID'},
    {'role': 'mineral_column', 'label': 'Колонка — Mineral'},
    {'role': 'mineral', 'label': 'Назначить сообщённый минерал', 'value_required': True},
    {'role': 'component', 'label': 'Назначить компонент', 'value_required': True},
    {'role': 'units', 'label': 'Строка / колонка единиц'},
    {'role': 'header', 'label': 'Это заголовок'},
    {'role': 'block', 'label': 'Это блок данных'},
    {'role': 'metadata', 'label': 'Это метаданные', 'value_required': True},
    {'role': 'method', 'label': 'Назначить аналитический метод', 'value_required': True},
    {'role': 'ignore', 'label': 'Не импортировать диапазон'},
]


def fail(code, message):
    from .import_preview import ImportCommandError
    raise ImportCommandError(code, message)


def rectangle(value):
    names = ('start_row', 'end_row', 'start_column', 'end_column')
    if not isinstance(value, dict) or any(type(value.get(k)) is not int for k in names):
        fail('INVALID_SEMANTIC_RANGE', 'Выберите прямоугольный диапазон исходной таблицы.')
    result = {k: value[k] for k in names}
    if not (1 <= result['start_row'] <= result['end_row'] and 0 <= result['start_column'] <= result['end_column']):
        fail('INVALID_SEMANTIC_RANGE', 'Границы диапазона некорректны.')
    return result


def overlaps(left, right):
    return (left['start_row'] <= right['end_row'] and right['start_row'] <= left['end_row']
            and left['start_column'] <= right['end_column'] and right['start_column'] <= left['end_column'])


def _at(sheet, row, column):
    values = sheet.rows[row - 1]
    return values[column] if column < len(values) else None


def cell_ignored(recipe, block_id, row, column):
    return any(a['role'] == 'ignore' and a['block_id'] == block_id
               and a['range']['start_row'] <= row <= a['range']['end_row']
               and a['range']['start_column'] <= column <= a['range']['end_column']
               for a in recipe['global_decisions'].get('semantic_annotations', []))


def validate_annotation(inspection, recipe, annotation, *, replacing=None):
    from .import_preview import _is_repeated_header
    if not isinstance(annotation, dict) or annotation.get('role') not in {a['role'] for a in SEMANTIC_ACTIONS}:
        fail('INVALID_SEMANTIC_ROLE', 'Неизвестная роль диапазона.')
    if annotation.get('source_fingerprint') != inspection.fingerprint:
        fail('SOURCE_FINGERPRINT_MISMATCH', 'Разметка относится к другой версии источника.')
    if not isinstance(annotation.get('value'), str) or not isinstance(annotation.get('id'), str):
        fail('INVALID_SEMANTIC_RANGE', 'Некорректное назначение диапазона.')
    section = next((s for s in recipe['sections'] if s['block_id'] == annotation.get('block_id')), None)
    if section is None:
        fail('INVALID_SEMANTIC_RANGE', 'Выбранная таблица недоступна.')
    sheet = next(s for s in inspection.sheets if s.name == section['sheet_name'])
    bounds = rectangle(annotation.get('range'))
    if bounds['end_row'] > len(sheet.rows) or bounds['end_column'] >= max(map(len, sheet.rows), default=0):
        fail('INVALID_SEMANTIC_RANGE', 'Диапазон выходит за пределы исходного листа.')
    if annotation['role'] in {'sample', 'mineral', 'method', 'ignore'}:
        if section.get('orientation', 'rows_are_analyses') == 'rows_are_analyses':
            if bounds['start_row'] < section['data_start_row'] or bounds['end_row'] > section['data_end_row']:
                fail('SEMANTIC_BOUNDARY', 'Диапазон пересекает заголовок или границу таблицы.')
            if any(_is_repeated_header(sheet, section, row) for row in range(bounds['start_row'], bounds['end_row'] + 1)):
                fail('SEMANTIC_BOUNDARY', 'Внутри диапазона повторный заголовок. Разметьте части отдельно.')
            if annotation['role'] != 'ignore' and any(not any(str(v or '').strip() for v in sheet.rows[row - 1]) for row in range(bounds['start_row'], bounds['end_row'] + 1)):
                fail('SEMANTIC_BOUNDARY', 'Диапазон пересекает пустую строку-разделитель.')
            for other in recipe['sections']:
                if other['block_id'] != section['block_id'] and other['sheet_name'] == section['sheet_name'] and bounds['start_row'] <= other['header_row'] <= bounds['end_row']:
                    fail('SEMANTIC_BOUNDARY', 'Диапазон пересекает заголовок другой таблицы.')
        elif bounds['start_column'] < section['data_start_column'] - 1 or bounds['end_column'] >= section['data_end_column']:
            fail('SEMANTIC_BOUNDARY', 'Диапазон пересекает границу анализов по столбцам.')
    for old in recipe['global_decisions'].get('semantic_annotations', []):
        if old['id'] == replacing or old['block_id'] != annotation['block_id'] or old['role'] != annotation['role']:
            continue
        if overlaps(old['range'], bounds) and old.get('value') != annotation.get('value'):
            fail('SEMANTIC_CONFLICT', 'Диапазон уже содержит другое назначение. Сначала отмените его.')
    # Reported sample values are stronger evidence than positional extension.
    if annotation['role'] == 'sample' and section.get('orientation', 'rows_are_analyses') == 'rows_are_analyses':
        fields = [f for f in section['mappings'] if f.get('canonical_field') in {'Sample', 'Sample ID', 'Sample name'} and f['target_role'] != 'ignore']
        for row in range(bounds['start_row'], bounds['end_row'] + 1):
            for field in fields:
                raw = _at(sheet, row, field['source_column_index'])
                if raw is not None and str(raw).strip() and str(raw).strip() != annotation['value']:
                    fail('SEMANTIC_CONFLICT', 'В источнике указан другой Sample. Необходимо отдельное решение по конфликту.')
    return section, sheet


def merged_sample_evidence(sheet, section, row, column, fingerprint):
    """Only an explicit merged Sample cell can carry its label to covered rows."""
    from .import_preview import _column_index
    for warning in sheet.warnings:
        for reference in warning.get('ranges', []) if warning.get('code') == 'MERGED_HEADERS' else []:
            match = re.fullmatch(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', reference)
            if not match:
                continue
            left, top, right, bottom = _column_index(match[1]), int(match[2]), _column_index(match[3]), int(match[4])
            if left == right == column and section['data_start_row'] <= top <= row <= bottom <= section['data_end_row']:
                raw = _at(sheet, top, left)
                if raw is not None and str(raw).strip():
                    return {'value': str(raw), 'origin': 'automatically_inferred', 'confidence': 'explicit_merged_cell',
                            'source_fingerprint': fingerprint, 'sheet_name': sheet.name, 'row': top, 'column': left,
                            'raw_token': raw, 'merged_range': reference}
    return None


def sample_candidates(sheet, section, record, fingerprint):
    """Nearby labels and identifier patterns are proposals, never physical links."""
    candidates = []
    for row in range(max(1, section['header_row'] - 4), section['header_row']):
        for column, raw in enumerate(sheet.rows[row - 1]):
            match = re.fullmatch(r'\s*(?:sample(?:\s+(?:id|name))?|образец|проба)\s*[:=]\s*(\S.*?)\s*', str(raw or ''), re.I)
            if match:
                candidates.append({'value': match[1], 'origin': 'suggested', 'confidence': 'explicit_preamble_label',
                    'row': row, 'column': column, 'raw_token': raw, 'sheet_name': sheet.name, 'source_fingerprint': fingerprint})
            elif re.fullmatch(r'\s*(?:sample(?:\s+(?:id|name))?|образец|проба)\s*', str(raw or ''), re.I):
                value = _at(sheet, row, column + 1)
                if value is not None and str(value).strip():
                    candidates.append({'value': str(value), 'origin': 'suggested', 'confidence': 'explicit_preamble_label',
                        'row': row, 'column': column + 1, 'raw_token': value, 'label_column': column,
                        'sheet_name': sheet.name, 'source_fingerprint': fingerprint})
    if re.search(r'[A-Za-zА-Яа-я]', sheet.name) and re.search(r'\d', sheet.name):
        for row, values in enumerate(sheet.rows[:min(4, section['header_row'] - 1)], 1):
            for column, raw in enumerate(values):
                if raw == sheet.name:
                    candidates.append({'value': str(raw), 'origin': 'suggested', 'confidence': 'sheet_label_with_preamble_unconfirmed',
                        'row': row, 'column': column, 'raw_token': raw, 'sheet_name': sheet.name, 'source_fingerprint': fingerprint})
    for identity in record['identity']:
        match = re.fullmatch(r'(.+?)[_./-](?:pt|point|spot|an)?\d+', str(identity), re.I)
        if match:
            candidates.append({'value': match[1], 'origin': 'suggested', 'confidence': 'identifier_pattern_unconfirmed',
                'raw_token': identity, 'sheet_name': sheet.name, 'row': record['row_number'], 'source_fingerprint': fingerprint})
    return candidates


def apply_semantic_decision(source_path, recipe, decision, *, preview=False):
    from .import_preview import inspect_source, semantic_fingerprint, validate_recipe
    from .manual_mapping import revise_import_mappings, revise_import_sections
    inspection = inspect_source(source_path)
    validate_recipe(inspection, recipe)
    revised = deepcopy(recipe)
    global_decisions = revised['global_decisions']
    history = global_decisions.setdefault('semantic_history', [])
    annotations = global_decisions.setdefault('semantic_annotations', [])
    if decision.get('action') == 'undo':
        if not history:
            fail('NO_SEMANTIC_UNDO', 'Нет решения для отмены.')
        old = history.pop()
        revised['sections'] = old['sections']
        global_decisions['semantic_annotations'] = old['annotations']
        revised['semantic_fingerprint'] = semantic_fingerprint(revised)
        return revised
    replacing = decision.get('annotation_id') if decision.get('action') == 'extend' else None
    prior = next((a for a in annotations if a['id'] == replacing), None)
    if replacing and prior is None:
        fail('ANNOTATION_NOT_FOUND', 'Назначение для расширения недоступно.')
    role = prior['role'] if prior else decision.get('role')
    if role not in {a['role'] for a in SEMANTIC_ACTIONS}:
        fail('INVALID_SEMANTIC_ROLE', 'Неизвестная роль диапазона.')
    value = prior.get('value') if prior else str(decision.get('value') or '').strip()
    if role in {'sample', 'mineral', 'method', 'component', 'metadata'} and not value:
        fail('SEMANTIC_VALUE_REQUIRED', 'Введите значение назначения.')
    annotation = {'id': replacing or str(uuid4()), 'version': (prior['version'] + 1) if prior else 1,
                  'block_id': prior['block_id'] if prior else decision.get('block_id'),
                  'range': rectangle(decision.get('range')), 'role': role, 'value': value,
                  'origin': 'user_assigned', 'source_fingerprint': inspection.fingerprint,
                  'decided_at': datetime.now(UTC).isoformat()}
    section, sheet = validate_annotation(inspection, revised, annotation, replacing=replacing)
    annotation['sheet_name'] = sheet.name
    if preview:
        return {'annotation': annotation, 'confirmation_required': True}
    history.append({'sections': deepcopy(revised['sections']), 'annotations': deepcopy(annotations)})
    revised['semantic_fingerprint'] = semantic_fingerprint(revised)
    bounds = annotation['range']
    transposed = section.get('orientation') == 'columns_are_analyses'
    column_roles = {'sample_id_column': 'Sample', 'sample_name_column': 'Sample name',
                    'analysis_column': 'Analysis', 'mineral_column': 'Mineral', 'component': 'Measurement', 'metadata': 'Comment'}
    if role in column_roles:
        if (not transposed and bounds['start_column'] != bounds['end_column']) or (transposed and bounds['start_row'] != bounds['end_row']):
            fail('SEMANTIC_FIELD_RANGE', 'Для роли поля выделите одну колонку (или одну строку в транспонированной таблице).')
        item = {'block_id': section['block_id'], 'source_axis': 'row' if transposed else 'column',
                'source_index': bounds['start_row'] - 1 if transposed else bounds['start_column'], 'target': column_roles[role]}
        if role == 'component':
            recognized = recognize_analyte(value)
            if not recognized['automatic']:
                fail('UNKNOWN_COMPONENT', 'Не найдено однозначное обозначение компонента.')
            item.update(canonical_field=recognized['canonical_field'], unit=decision.get('unit') or recognized['unit'])
        if role == 'metadata':
            item.update(target='Metadata', canonical_field=value)
        revised = revise_import_mappings(source_path, revised, [item])['recipe']
    elif role in {'header', 'block'}:
        item = {'block_id': section['block_id'], 'rebuild_mappings': True}
        if role == 'header':
            if bounds['start_row'] != bounds['end_row']:
                fail('SEMANTIC_HEADER_RANGE', 'Заголовок должен быть одной строкой.')
            item.update(header_row=bounds['start_row'], data_start_row=bounds['start_row'] + 1)
        else:
            item.update(data_start_row=bounds['start_row'], data_end_row=bounds['end_row'])
            if transposed:
                item.update(data_start_column=bounds['start_column'] + 1, data_end_column=bounds['end_column'] + 1)
        revised = revise_import_sections(source_path, revised, [item])['recipe']
        if role == 'block' and not transposed:
            selected_section = next(s for s in revised['sections'] if s['block_id'] == section['block_id'])
            outside = [{'block_id': section['block_id'], 'source_axis': 'column', 'source_index': field['source_column_index'], 'target': 'Ignore'}
                       for field in selected_section['mappings'] if not bounds['start_column'] <= field['source_column_index'] <= bounds['end_column']]
            if outside:
                revised = revise_import_mappings(source_path, revised, outside)['recipe']
    elif role == 'units':
        from .import_recognition import unit_from_header
        items = []
        for field in section['mappings']:
            index = field.get('source_row_index') if transposed else field.get('source_column_index')
            row, col = (index + 1, bounds['start_column']) if transposed else (bounds['start_row'], index)
            if not (bounds['start_row'] <= row <= bounds['end_row'] and bounds['start_column'] <= col <= bounds['end_column']):
                continue
            unit = unit_from_header(str(_at(sheet, row, col) or ''))
            canonical = field.get('suggested_canonical_field') or field.get('canonical_field')
            if unit and recognize_analyte(canonical)['automatic']:
                items.append({'block_id': section['block_id'], 'source_axis': 'row' if transposed else 'column',
                              'source_index': index, 'target': 'Measurement', 'canonical_field': canonical, 'unit': unit})
        if not items:
            fail('UNITS_NOT_EXPLICIT', 'В выделении нет явных единиц для распознанных компонентов.')
        revised = revise_import_mappings(source_path, revised, items)['recipe']
        if not transposed and bounds['start_row'] == section['data_start_row'] and bounds['start_row'] == bounds['end_row']:
            revised = revise_import_sections(source_path, revised, [{'block_id': section['block_id'], 'data_start_row': bounds['end_row'] + 1, 'rebuild_mappings': False}])['recipe']
        elif transposed and bounds['start_column'] == section['data_start_column'] - 1 and bounds['start_column'] == bounds['end_column']:
            revised = revise_import_sections(source_path, revised, [{'block_id': section['block_id'], 'data_start_column': bounds['end_column'] + 2, 'rebuild_mappings': False}])['recipe']
    annotations = revised['global_decisions']['semantic_annotations']
    revised['global_decisions']['semantic_annotations'] = [a for a in annotations if a['id'] != replacing] + [annotation]
    revised['semantic_fingerprint'] = semantic_fingerprint(revised)
    validate_recipe(inspection, revised)
    return revised


def interpret_records(inspection, recipe, records):
    """Keep reported labels and unresolved links separate from Analysis identity."""
    annotations = recipe['global_decisions'].get('semantic_annotations', [])
    output = []
    for record in records:
        section = next(s for s in recipe['sections'] if s['block_id'] == record['block_id'])
        sheet = next(s for s in inspection.sheets if s.name == record['sheet_name'])
        transposed = record.get('orientation') == 'columns_are_analyses'
        identities = list(record['identity'])
        identity_offset = 1 if transposed and section.get('analysis_axis_role', 'Analysis') != 'Ignore' else 0
        for index, field in enumerate(f for f in section['mappings'] if f['target_role'] == 'identity'):
            row = field['source_row_index'] + 1 if transposed else record['row_number']
            col = record['source_column_number'] - 1 if transposed else field['source_column_index']
            if cell_ignored(recipe, record['block_id'], row, col):
                identities[index + identity_offset] = ''
        record['identity'] = tuple(identities)
        reported = {}
        for field in section['mappings']:
            if field['target_role'] not in {'identity', 'metadata'}:
                continue
            row = field['source_row_index'] + 1 if transposed else record['row_number']
            col = record['source_column_number'] - 1 if transposed else field['source_column_index']
            if cell_ignored(recipe, record['block_id'], row, col):
                continue
            raw = _at(sheet, row, col)
            if raw is not None and str(raw).strip():
                reported[field['canonical_field']] = {'value': str(raw), 'origin': 'explicitly_reported',
                    'confidence': 'explicit_column', 'source_fingerprint': inspection.fingerprint,
                    'sheet_name': sheet.name, 'row': row, 'column': col, 'raw_header': field.get('source_header'), 'raw_token': raw}
        sample = reported.get('Sample') or reported.get('Sample ID') or reported.get('Sample name')
        if not sample and not transposed:
            for field in section['mappings']:
                if field['target_role'] != 'ignore' and field.get('canonical_field') in {'Sample', 'Sample ID', 'Sample name'}:
                    sample = merged_sample_evidence(sheet, section, record['row_number'], field['source_column_index'], inspection.fingerprint)
                    if sample:
                        break
        mineral = reported.get('Mineral')
        method = reported.get('Method')
        excluded = False
        for annotation in annotations:
            if annotation['block_id'] != record['block_id']:
                continue
            r = annotation['range']
            belongs = r['start_column'] <= record['source_column_number'] - 1 <= r['end_column'] if transposed else r['start_row'] <= record['row_number'] <= r['end_row']
            if not belongs:
                continue
            assignment = {'value': annotation['value'], 'origin': 'user_assigned', 'confidence': 'explicit_assignment',
                          'annotation_id': annotation['id'], 'source_fingerprint': inspection.fingerprint,
                          'sheet_name': sheet.name, 'range': r}
            if annotation['role'] == 'sample': sample = assignment
            elif annotation['role'] == 'mineral': mineral = assignment
            elif annotation['role'] == 'method': method = assignment
            elif annotation['role'] == 'ignore':
                all_fields = [f for f in section['mappings'] if f['target_role'] != 'ignore']
                ignored_fields = [f for f in all_fields if (r['start_row'] - 1 <= f['source_row_index'] <= r['end_row'] - 1 if transposed else r['start_column'] <= f['source_column_index'] <= r['end_column'])]
                excluded = len(ignored_fields) == len(all_fields)
                record['measurements'] = [m for m in record['measurements'] if not (r['start_row'] <= m['physical_source_row_number'] <= r['end_row'] and r['start_column'] <= m['physical_source_column_index'] <= r['end_column'])]
        record['sample_association'] = {'sample_id': None, 'status': 'reported_unlinked' if sample else 'unresolved',
                                        'candidates': sample_candidates(sheet, section, record, inspection.fingerprint) if not sample else [],
                                        'reported': sample, 'reported_fields': {k: v for k, v in reported.items() if k in {'Sample', 'Sample ID', 'Sample name'}}}
        record['reported_mineral'] = reported.get('Mineral')
        record['mineral_assignment'] = mineral if mineral and mineral['origin'] == 'user_assigned' else None
        record['analytical_method'] = method
        if method:
            for measurement in record['measurements']:
                measurement['method'] = method['value']
        if not excluded:
            output.append(record)
    return output
