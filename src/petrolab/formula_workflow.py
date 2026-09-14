"""Explicit previews and immutable, stale-aware formula runs in project SQLite."""
import json
import platform
from contextlib import closing

from .desktop_workflow import list_project_analyses
from .formula_methods import executable_method, fingerprint, method_definition
from .import_apply import _id, _now, open_project
from .import_preview import ImportCommandError
from .mineral_verification import reported_target, verify_record


def _inputs(connection, database_path, ids):
    records = []
    for analysis_id in ids:
        rows = list_project_analyses(database_path, limit=1, analysis_id=analysis_id,
                                     _connection=connection)['analyses']
        if not rows:
            records.append({'analysis_id': analysis_id, 'unavailable': True})
            continue
        a = rows[0]
        reported = a.get('reported_mineral') or a.get('source_metadata', {}).get('Mineral')
        verification = verify_record({'preview_id': analysis_id, 'reported_mineral': reported,
                                      'measurements': a['measurement_list']}, a.get('mineral_assignment'))
        records.append({'analysis_id': analysis_id, 'identity': a['identity'],
                        'source_id': a['source_id'], 'source_name': a['source_name'],
                        'measurements': a['measurement_list'],
                        'assignment': verification.get('accepted'),
                        'assignment_status': verification['status']})
    return records


def _validate(ids, method_id, version, parameters):
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids)):
        raise ImportCommandError('FORMULA_SCOPE_INVALID', 'Выберите 1–100 различных Analysis ID.')
    try:
        registration = executable_method(method_id, version)
    except KeyError:
        raise ImportCommandError('FORMULA_METHOD_UNAVAILABLE', 'Метод или версия недоступны; обновите список методов.')
    choices = registration['parameter_choices']
    if (not isinstance(parameters, dict) or set(parameters) != set(choices)
            or any(not isinstance(parameters[name], str) or parameters[name] not in allowed
                   for name, allowed in choices.items())):
        raise ImportCommandError('FORMULA_PARAMETERS_INVALID',
                                 'Перед расчётом явно выберите все параметры установленного метода.')
    return registration


def _preview(connection, database_path, ids, method_id, version, parameters):
    registration = _validate(ids, method_id, version, parameters)
    definition = registration['definition']
    snapshots = _inputs(connection, database_path, ids)
    results = []
    for record in snapshots:
        assignment = record.get('assignment') or {}
        if record.get('unavailable'):
            result = {'status': 'failed', 'errors': ['Анализ отсутствует или импорт отозван.'], 'values': {}}
        elif reported_target(assignment.get('target')) not in registration['accepted_targets']:
            result = {'status': 'failed',
                      'errors': [f'Сначала явно примите назначение {registration["target_label"]}.'],
                      'values': {}}
        else:
            result = registration['calculate'](record['measurements'], parameters)
        results.append({'analysis_id': record['analysis_id'], **result})
    input_hash = fingerprint({'inputs': snapshots, 'method': definition['definition_fingerprint'],
                              'parameters': parameters})
    return {'method': definition, 'parameters': parameters, 'analysis_ids': ids,
            'input_fingerprint': input_hash, 'input_snapshots': snapshots, 'results': results,
            'can_save': all(r['status'] == 'current' for r in results)}


def preview_formula(database_path, analysis_ids, method_id, method_version, parameters):
    with closing(open_project(database_path)) as connection:
        connection.execute('BEGIN')
        return _preview(connection, database_path, analysis_ids, method_id, method_version, parameters)


def save_formula(database_path, analysis_ids, method_id, method_version, parameters, preview_fingerprint):
    with closing(open_project(database_path)) as connection:
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            preview = _preview(connection, database_path, analysis_ids, method_id, method_version, parameters)
            if preview['input_fingerprint'] != preview_fingerprint:
                raise ImportCommandError('FORMULA_PREVIEW_STALE', 'Входы, назначение или метод изменились; повторите предпросмотр.')
            if not preview['can_save']:
                raise ImportCommandError('FORMULA_INPUT_INVALID', 'Есть непригодные анализы; ни один результат не сохранён.')
            old = connection.execute('SELECT payload_json FROM formula_run WHERE input_fingerprint = ?',
                                     (preview_fingerprint,)).fetchone()
            if old:
                return {'run': json.loads(old[0]), 'reused': True}
            connection.execute('INSERT OR IGNORE INTO formula_project VALUES (1, ?)', (_id(),))
            project_id = connection.execute('SELECT project_id FROM formula_project').fetchone()[0]
            timestamp, run_id = _now(), _id()
            method = preview['method']
            measurement_ids = [m['measurement_id'] for record in preview['input_snapshots'] for m in record['measurements']]
            run = {'id': run_id, 'project_id': project_id, 'method_id': method_id, 'method_version': method_version,
                   'method_definition_fingerprint': method['definition_fingerprint'],
                   'input': {'kind': 'analysis_snapshot', 'analysis_ids': analysis_ids},
                   'input_measurement_ids': measurement_ids, 'input_fingerprint': preview_fingerprint,
                   'parameters': parameters, 'excluded': [], 'result_manifest': preview,
                   'status': 'current', 'stale_reasons': [], 'created_at': timestamp,
                   'software_versions': {'python': platform.python_version(),
                                         'petrolab_formula': method_version}}
            connection.execute('INSERT INTO formula_run VALUES (?, ?, ?, ?)',
                               (run_id, preview_fingerprint, json.dumps(run, ensure_ascii=False), timestamp))
            for result in preview['results']:
                used_ids = [m['measurement_id'] for m in result['used']]
                for field, value in result['values'].items():
                    unit = 'mol.%' if field in {'Fo', 'Fa'} else 'wt.%' if field == 'oxide_total' else 'apfu'
                    assumptions = list(result['assumptions'])
                    if field == 'OH_est_apfu' and result.get('OH_est_basis'):
                        assumptions.append('OH_est_basis: ' + json.dumps(result['OH_est_basis'],
                                                                          sort_keys=True, ensure_ascii=False))
                    derived = {'id': _id(), 'analysis_id': result['analysis_id'], 'field': field, 'value': value,
                               'unit': unit, 'method_id': method_id, 'method_version': method_version,
                               'method_definition_fingerprint': method['definition_fingerprint'],
                               'input_measurement_ids': used_ids, 'input_fingerprint': preview_fingerprint,
                               'assumptions': assumptions, 'status': 'current',
                               'stale_reasons': [], 'created_at': timestamp}
                    connection.execute('INSERT INTO formula_derived_value VALUES (?, ?, ?, ?)',
                                       (derived['id'], run_id, result['analysis_id'], json.dumps(derived, ensure_ascii=False)))
            return {'run': run, 'reused': False}


def list_formula_runs(database_path, analysis_id):
    with closing(open_project(database_path)) as connection:
        connection.execute('BEGIN')
        rows = connection.execute('''SELECT DISTINCT r.payload_json, r.rowid FROM formula_run r
            JOIN formula_derived_value d ON d.run_id = r.run_id WHERE d.analysis_id = ?
            ORDER BY r.rowid DESC''', (analysis_id,)).fetchall()
        runs = []
        for row in rows:
            run = json.loads(row[0])
            reasons = []
            try:
                current_definition = method_definition(run['method_id'], run['method_version'])
            except KeyError:
                current_definition = None
                reasons.append('Метод или версия больше не установлены.')
            if (current_definition is not None and
                    run['method_definition_fingerprint'] != current_definition['definition_fingerprint']):
                reasons.append('Определение или реализация метода изменились.')
            snapshots = _inputs(connection, database_path, run['input']['analysis_ids'])
            expected = fingerprint({'inputs': snapshots, 'method': run['method_definition_fingerprint'],
                                    'parameters': run['parameters']})
            if expected != run['input_fingerprint']:
                reasons.append('Измерения, доступность анализа или принятое назначение изменились.')
            run.update(status='stale' if reasons else 'current', stale_reasons=reasons)
            derived = [json.loads(r[0]) for r in connection.execute(
                'SELECT payload_json FROM formula_derived_value WHERE run_id = ? ORDER BY rowid', (run['id'],))]
            for value in derived:
                value.update(status=run['status'], stale_reasons=reasons)
            runs.append({'run': run, 'derived_values': derived})
        return {'runs': runs}
