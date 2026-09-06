"""Transient ADR-0014 review sessions. No batch commit or disk draft persistence."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from contextlib import closing

from .clean_table import classify_clean_table
from .desktop_workflow import (suggest_import_recipe, bulk_unit_scopes, bulk_ignore_scopes,
                               apply_bulk_unit_scope, apply_bulk_ignore_scope)
from .import_apply import _require_mapping_review, _require_duplicate_review, _require_non_empty_plan
from .import_preview import (ImportCommandError, inspect_source, create_import_plan,
                             preview_source_window, semantic_fingerprint)
from .manual_mapping import revise_import_mappings, revise_import_sections, review_duplicate_candidates
from .semantic_import import apply_semantic_decision, SEMANTIC_ACTIONS
from .analyte_dictionary import CANONICAL, confirmed_alias


def now():
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def empty_plan():
    return {'planned_records': [], 'warnings': [], 'issues': [], 'summary': {
        'planned_analysis_count': 0, 'planned_measurement_count': 0,
        'enabled_block_count': 0, 'duplicate_candidate_groups': 0}}


class ImportWorkspaceStore:
    def __init__(self):
        self.sessions: dict[str, dict[str, Any]] = {}

    def _source(self, session, source_id):
        source = next((s for s in session['sources'] if s['source_id'] == source_id), None)
        if source is None:
            raise ImportCommandError('WORKSPACE_SOURCE_NOT_FOUND', 'Источник не найден в этой очереди.')
        return source

    def _check(self, source):
        inspection = inspect_source(source['staged_path'])
        if inspection.fingerprint != source['sha256']:
            raise ImportCommandError('SOURCE_FINGERPRINT_MISMATCH', 'Файл изменился после добавления. Добавьте его заново.', {'source_id': source['source_id']})
        return inspection

    def _add(self, session, descriptors):
        if not isinstance(descriptors, list) or not descriptors:
            raise ValueError('sources')
        for descriptor in descriptors:
            path = descriptor.get('staged_path') if isinstance(descriptor, dict) else None
            if not isinstance(path, str) or not path:
                raise ValueError('staged_path')
            if any(Path(s['staged_path']).resolve() == Path(path).resolve() for s in session['sources']):
                raise ImportCommandError('WORKSPACE_SOURCE_EXISTS', 'Этот файл уже есть в очереди.')
            inspection = inspect_source(path)
            classification = classify_clean_table(inspection)
            suggestion = ({'recipe': classification['recipe'], 'warnings': []}
                          if classification['mode'] == 'clean_table_fast' else suggest_import_recipe(path))
            aliases = session.get('project_aliases', {})
            if aliases:
                from .import_recognition import mapping_for_header
                suggestion['recipe']['global_decisions']['project_aliases'] = deepcopy(aliases)
                for section in suggestion['recipe']['sections']:
                    for index, field in enumerate(section['mappings']):
                        if field.get('review_decision') != 'unresolved' or not field.get('source_header'):
                            continue
                        axis = field.get('source_axis', 'column')
                        revised, _ = mapping_for_header(field.get('source_column_index', field.get('source_row_index')), field['source_header'], source_axis=axis, project_aliases=aliases, context_unit=(section.get('unit_context') or {}).get('unit'))
                        section['mappings'][index] = revised
                suggestion['recipe']['semantic_fingerprint'] = semantic_fingerprint(suggestion['recipe'])
            source = {
                'source_id': str(uuid4()), 'original_display_path': descriptor.get('original_display_path') or path,
                'staged_path': path, 'sha256': inspection.fingerprint,
                'size_bytes': Path(path).stat().st_size,
                'modified_at': datetime.fromtimestamp(Path(path).stat().st_mtime, UTC).isoformat(),
                'source_kind': inspection.source_format, 'adapter_version': 'tabular-review-v1',
                'inspection_status': 'inspected', 'included': True, 'exclusion_reason': None,
                'recipe': suggestion['recipe'], 'classification': classification,
                'inspection': inspection.projection(), 'decisions': [],
                'active_block_id': suggestion['recipe']['sections'][0]['block_id'],
            }
            session['sources'].append(source)
            session['active_source_id'] = source['source_id']

    def command(self, operation, params):
        if operation == 'create':
            timestamp = now()
            session = {'workspace_id': str(uuid4()), 'draft_revision': 0,
                       'created_at': timestamp, 'updated_at': timestamp, 'sources': [], 'active_source_id': None}
            session['database_path'] = params.get('project_database_path')
            session['project_aliases'] = {}
            if session['database_path']:
                from .import_apply import open_project
                with closing(open_project(session['database_path'])) as connection:
                    session['project_aliases'] = {row['normalized_header']: json.loads(row['alias_json']) for row in connection.execute('SELECT * FROM project_analyte_alias')}
            self._add(session, params.get('sources'))
        else:
            stored = self.sessions.get(params.get('workspace_id'))
            if stored is None:
                raise ImportCommandError('WORKSPACE_NOT_FOUND', 'Очередь недоступна. Создайте новый импорт.')
            session = deepcopy(stored)
            if operation not in {'get', 'preview_window'}:
                expected = params.get('expected_revision')
                if type(expected) is not int or expected != session['draft_revision']:
                    raise ImportCommandError('STALE_WORKSPACE_REVISION', 'Очередь уже изменилась. Обновите состояние перед повтором.',
                                             {'expected_revision': expected, 'current_revision': session['draft_revision']})
            if operation == 'discard':
                del self.sessions[session['workspace_id']]
                return {'workspace_id': session['workspace_id'], 'status': 'discarded',
                        'staged_paths': [s['staged_path'] for s in session['sources']]}
            if operation == 'preview_window':
                source = self._source(session, params.get('source_id'))
                self._check(source)
                if params.get('semantic_extension'):
                    return apply_semantic_decision(source['staged_path'], source['recipe'], params['semantic_extension'], preview=True)
                result = preview_source_window(source['staged_path'], params['sheet_name'], params.get('start_row', 1),
                                               params.get('row_count', 30), params.get('start_column', 0), params.get('column_count', 24))
                return {**result, 'source_path': source['staged_path']}
            if operation == 'add_sources':
                self._add(session, params.get('sources'))
            elif operation in {'apply_decision', 'apply_bulk_decision'}:
                source = self._source(session, params.get('source_id'))
                decision = params.get('decision')
                if not isinstance(decision, dict):
                    raise ValueError('decision')
                kind = decision.get('kind')
                if kind != 'activate':
                    self._check(source)
                if operation == 'apply_bulk_decision':
                    prefix = f"{session['draft_revision']}:{source['source_id']}:"
                    scope_id = decision.get('bulk_scope_id', '')
                    if not scope_id.startswith(prefix):
                        raise ImportCommandError('STALE_BULK_SCOPE', 'Группа решений устарела. Выберите текущую группу.')
                    scope_id = scope_id[len(prefix):]
                    if kind == 'unit':
                        revised = apply_bulk_unit_scope(source['staged_path'], source['recipe'], scope_id, decision['unit'])
                    elif kind == 'ignore':
                        revised = apply_bulk_ignore_scope(source['staged_path'], source['recipe'], scope_id)
                    else:
                        raise ValueError('decision.kind')
                    source['recipe'] = revised['recipe']
                elif kind == 'activate':
                    block_id = decision.get('block_id') or source['active_block_id']
                    if not any(s['block_id'] == block_id for s in source['recipe']['sections']):
                        raise ValueError('block_id')
                    session['active_source_id'] = source['source_id']
                    source['active_block_id'] = block_id
                elif kind in {'mappings', 'sections'}:
                    fn = revise_import_mappings if kind == 'mappings' else revise_import_sections
                    source['recipe'] = fn(source['staged_path'], source['recipe'], decision['decisions'])['recipe']
                    if kind == 'sections':
                        for item in decision['decisions']:
                            if item.get('enabled') is False:
                                section = next(s for s in source['recipe']['sections'] if s['block_id'] == item['block_id'])
                                section['exclusion_reason'] = item.get('exclusion_reason') or 'Исключено пользователем'
                        source['recipe']['semantic_fingerprint'] = semantic_fingerprint(source['recipe'])
                elif kind == 'verify_minerals':
                    review = self._review(source)
                    if any(i.get('blocking') for i in review['issues']):
                        raise ImportCommandError('STRUCTURE_REVIEW_REQUIRED', 'Сначала завершите обязательные решения по структуре.')
                    source['recipe']['global_decisions']['mineral_verification_enabled'] = True
                    source['recipe']['semantic_fingerprint'] = semantic_fingerprint(source['recipe'])
                elif kind == 'accept_mineral':
                    from .mineral_verification import acceptance_scopes
                    review = self._review(source)
                    if any(i.get('blocking') for i in review['issues']):
                        raise ImportCommandError('STRUCTURE_REVIEW_REQUIRED', 'Структура изменилась. Сначала устраните обязательные вопросы.')
                    if decision.get('scope_id'):
                        scope = next((s for s in acceptance_scopes(review['plan'], source['recipe']) if s['scope_id'] == decision['scope_id']), None)
                        if scope is None:
                            raise ImportCommandError('STALE_BULK_SCOPE', 'Группа минералов устарела.')
                        ids = scope['preview_ids']
                    else:
                        ids = [decision.get('preview_id')]
                    records = [r for r in review['plan']['planned_records'] if r['preview_id'] in ids]
                    if len(records) != len(ids):
                        raise ValueError('preview_id')
                    accepted = source['recipe']['global_decisions'].setdefault('mineral_acceptances', {})
                    for record in records:
                        verification = record.get('mineral_verification')
                        if not verification or not verification['prediction'] or verification['confidence'] not in {'high', 'medium'}:
                            raise ImportCommandError('MINERAL_UNRESOLVED', 'Нет однозначного предложения для принятия.')
                        if decision.get('input_fingerprint') and decision['input_fingerprint'] != verification['input_fingerprint']:
                            raise ImportCommandError('STALE_MINERAL_INPUT', 'Состав изменился после проверки.')
                        accepted[record['preview_id']] = {'target': verification['prediction'], 'origin': 'user_accepted',
                            'decided_at': now(), 'input_fingerprint': verification['input_fingerprint'], 'ruleset_version': verification['ruleset_version']}
                    source['recipe']['semantic_fingerprint'] = semantic_fingerprint(source['recipe'])
                elif kind == 'semantic':
                    source['recipe'] = apply_semantic_decision(source['staged_path'], source['recipe'], decision)
                    if decision.get('role') == 'component' and decision.get('remember_alias') is True:
                        section = next(s for s in source['recipe']['sections'] if s['block_id'] == decision['block_id'])
                        bounds = decision['range']
                        field = next(f for f in section['mappings'] if (f.get('source_column_index') == bounds['start_column'] if section.get('orientation') != 'columns_are_analyses' else f.get('source_row_index') == bounds['start_row'] - 1))
                        key, alias = confirmed_alias(field['source_header'], field['canonical_field'])
                        self._remember_alias(session, source, key, alias)
                elif kind == 'alias':
                    if decision.get('confirmed') is not True:
                        raise ValueError('confirmed')
                    key, alias = confirmed_alias(decision['raw_header'], decision['canonical_field'])
                    self._remember_alias(session, source, key, alias)
                elif kind == 'duplicates':
                    source['recipe'] = review_duplicate_candidates(source['staged_path'], source['recipe'], 'keep_all')['recipe']
                elif kind == 'source_inclusion':
                    if type(decision.get('included')) is not bool:
                        raise ValueError('included')
                    reason = decision.get('reason')
                    if not decision['included'] and (not isinstance(reason, str) or not reason.strip()):
                        raise ValueError('reason')
                    source['included'] = decision['included']
                    source['exclusion_reason'] = None if decision['included'] else reason.strip()
                else:
                    raise ValueError('decision.kind')
                if kind != 'activate':
                    source['decisions'].append({'decision': deepcopy(decision), 'decided_at': now()})
            elif operation not in {'get', 'replan'}:
                raise ImportCommandError('WORKSPACE_COMMAND_UNAVAILABLE', 'Эта операция очереди пока недоступна.')
            if operation != 'get':
                session['draft_revision'] += 1
                session['updated_at'] = now()
        result = self._project(session)
        if operation != 'get':
            self.sessions[session['workspace_id']] = session
        return result

    def _remember_alias(self, session, source, key, alias):
        if not session.get('database_path'):
            raise ImportCommandError('PROJECT_REQUIRED', 'Выберите проект для сохранения обозначения.')
        from .import_apply import open_project
        with closing(open_project(session['database_path'])) as connection, connection:
            old = connection.execute('SELECT alias_json FROM project_analyte_alias WHERE normalized_header = ?', (key,)).fetchone()
            if old and json.loads(old['alias_json'])['canonical_field'] != alias['canonical_field']:
                raise ImportCommandError('ALIAS_CONFLICT', 'Это обозначение уже связано с другим компонентом в проекте.')
            connection.execute('INSERT OR IGNORE INTO project_analyte_alias VALUES (?, ?, ?)', (key, json.dumps(alias, ensure_ascii=False), now()))
        session['project_aliases'][key] = alias
        source['recipe']['global_decisions'].setdefault('project_aliases', {})[key] = alias
        source['recipe']['semantic_fingerprint'] = semantic_fingerprint(source['recipe'])

    def _review(self, source):
        plan, issues, units, ignores = empty_plan(), [], [], []
        try:
            inspection = self._check(source)
            plan = create_import_plan(inspection, source['recipe'])
            issues = list(plan.get('issues', [])) + list(plan['warnings'])
            # Clean Table rejection used its own tentative header, not the user's
            # current block header. Reusing those blank-header warnings creates
            # false questions for instrument preambles and already skipped sheets.
            enabled_sheets = {s['sheet_name'] for s in source['recipe']['sections'] if s.get('enabled', True)}
            issues.extend(item for item in source['inspection'].get('warnings', [])
                          if item['code'] in {'MERGED_HEADERS', 'HIDDEN_ROWS', 'FORMULA_WITHOUT_CACHED_VALUE', 'EMBEDDED_DRAWINGS_NOT_PREVIEWED'}
                          and item.get('sheet_name') in enabled_sheets)
            for section in source['recipe']['sections']:
                if not section.get('enabled', True):
                    continue
                for field in section['mappings']:
                    if field.get('target_role') == 'ignore' and field.get('review_decision') == 'unresolved':
                        issues.append({'code': 'UNIT_REQUIRES_REVIEW' if field.get('suggested_target') == 'measurement' else 'UNMAPPED_FIELD_REQUIRES_REVIEW',
                                       'severity': 'error', 'blocking': True, 'sheet_name': section['sheet_name'],
                                       'block_id': section['block_id'], 'row_number': section['header_row'], **field})
            for check, args in [(_require_non_empty_plan, (plan,)), (_require_duplicate_review, (plan, source['recipe']))]:
                try:
                    check(*args)
                except ImportCommandError as error:
                    issues.append({'code': error.code, 'message': error.message, 'severity': 'error', 'blocking': True})
            units = bulk_unit_scopes(source['staged_path'], source['recipe'])['scopes']
            ignores = bulk_ignore_scopes(source['staged_path'], source['recipe'])['scopes']
        except ImportCommandError as error:
            issues.append({'code': error.code, 'message': error.message, 'severity': 'error', 'blocking': True})
        if not source['included']:
            issues = []
        ready = source['included'] and not any(i.get('blocking') for i in issues)
        plan['ready_to_commit'] = ready
        return {'inspection': source['inspection'], 'recipe': source['recipe'], 'plan': plan,
                'classification': source['classification'], 'issues': issues,
                'bulk_unit_scopes': units, 'bulk_ignore_scopes': ignores, 'ready': ready,
                'decisions': source['decisions'], 'source_id': source['source_id']}

    def _project(self, state):
        sources, issues, plans, reviews, scopes = [], [], [], {}, []
        for source in state['sources']:
            review = self._review(source)
            for scope in review['bulk_unit_scopes'] + review['bulk_ignore_scopes']:
                scope['bulk_scope_id'] = f"{state['draft_revision']}:{source['source_id']}:{scope['bulk_scope_id']}"
                targets = []
                for target in scope['targets']:
                    section = next(s for s in source['recipe']['sections'] if s['block_id'] == target['block_id'])
                    targets.append({'source_id': source['source_id'], 'sheet_key': f"{source['source_id']}:{section['sheet_name']}",
                                    'source_axis': target['source_axis'], 'source_index': target['source_index']})
                scopes.append({'bulk_scope_id': scope['bulk_scope_id'], 'decision_kind': scope['decision_kind'], 'targets': targets,
                               'signature': {'normalized_source_header': '|'.join(scope['fields']), 'source_unit': None,
                                             'target_role': None, 'canonical_field': None,
                                             'orientation': 'analyses_in_columns' if scope.get('orientation') == 'columns_are_analyses' else 'analyses_in_rows',
                                             'adapter_version': source['adapter_version']},
                               'scope_summary': f"{scope['field_count']} полей в одном источнике",
                               'source_fingerprints': {source['source_id']: source['sha256']}, 'draft_revision': state['draft_revision']})
            reviews[source['source_id']] = review
            recipe = source['recipe']
            for item in review['issues']:
                section = next((s for s in recipe['sections'] if s['block_id'] == item.get('block_id')), None)
                row = item.get('row_number') or (item.get('source_row_index', -1) + 1) or (section['header_row'] if section else None)
                column = item.get('source_column_index', 0)
                issues.append({
                    'issue_id': digest([source['source_id'], item['code'], item.get('sheet_name'), item.get('block_id'), row, column, item.get('source_header')]),
                    'code': item['code'], 'severity': item.get('severity', 'warning'), 'blocking': bool(item.get('blocking')),
                    'source_id': source['source_id'], 'sheet_key': f"{source['source_id']}:{item['sheet_name']}" if item.get('sheet_name') else None,
                    'physical_range': {'start_row': row, 'end_row': row, 'start_column': column, 'end_column': column} if row else None,
                    'logical_block_id': item.get('block_id'), 'message_params': {k: v for k, v in item.items() if isinstance(v, (str, int, float, bool)) or v is None},
                    'allowed_decisions': ['mappings', 'sections', 'source_inclusion'], 'current_decision': None, 'bulk_scope_id': None,
                })
            source_issues = [i for i in issues if i['source_id'] == source['source_id']]
            sheets = []
            for sheet in source['inspection']['sheets']:
                sections = [s for s in recipe['sections'] if s['sheet_name'] == sheet['name']]
                included = source['included'] and any(s.get('enabled', True) for s in sections)
                first = sections[0] if sections else None
                sheet_key = f"{source['source_id']}:{sheet['name']}"
                sheet_issues = [i['issue_id'] for i in source_issues if i['sheet_key'] == sheet_key]
                sheets.append({'sheet_key': sheet_key, 'physical_sheet_name': sheet['name'], 'included': included,
                    'exclusion_reason': None if included else source['exclusion_reason'] or (first.get('exclusion_reason') if first else None) or 'Пустой или служебный лист',
                    'classification': 'ignored_empty' if not sections else 'review_required' if sheet_issues else 'clean',
                    'header_row': first['header_row'] if first else None,
                    'orientation': ('analyses_in_columns' if first.get('orientation') == 'columns_are_analyses' else 'analyses_in_rows') if first else None,
                    'blocks': [{'block_id': s['block_id'], 'start_row': s['header_row'], 'end_row': s['data_end_row'], 'start_column': 0, 'end_column': None} for s in sections],
                    'field_mappings': [{'source_axis': f.get('source_axis', 'column'), 'source_index': f.get('source_column_index', f.get('source_row_index', 0)),
                        'source_header': f.get('source_header') or '', 'target_role': f['target_role'], 'canonical_field': f.get('canonical_field'),
                        'unit': f.get('unit'), 'measurement_semantics': f['measurement_semantics'],
                        'decision_state': 'confirmed' if f.get('review_decision') in {'assigned', 'explicit_ignore'} else 'suggested'} for s in sections for f in s['mappings']],
                    'mineral_default': None, 'method_default': None, 'unresolved_issue_ids': sheet_issues,
                    'recipe_fragment_fingerprint': digest(sections) if sections else None})
            sources.append({k: source[k] for k in ('source_id', 'original_display_path', 'staged_path', 'sha256', 'size_bytes', 'modified_at', 'source_kind', 'adapter_version', 'inspection_status', 'included', 'exclusion_reason')} | {'sheets': sheets})
            summary = review['plan']['summary']
            plans.append({'source_id': source['source_id'], 'status': 'ready' if review['ready'] else 'invalid',
                          'recipe_fingerprint': semantic_fingerprint(recipe), 'plan_fingerprint': digest(review['plan']),
                          'planned_analysis_count': summary['planned_analysis_count'] if source['included'] else 0,
                          'planned_measurement_count': summary['planned_measurement_count'] if source['included'] else 0})
        active = self._source(state, state['active_source_id'])
        section = next(s for s in active['recipe']['sections'] if s['block_id'] == active['active_block_id'])
        blockers = [i for i in issues if i['blocking']]
        reasons = sorted({i['code'] for i in blockers})
        if len(sources) > 1:
            reasons.append('MULTI_SOURCE_COMMIT_UNAVAILABLE')
        if not any(s['included'] for s in sources):
            reasons.append('NO_INCLUDED_SOURCES')
        session = {k: state[k] for k in ('workspace_id', 'draft_revision', 'created_at', 'updated_at', 'active_source_id')}
        session.update({'schema_version': 1, 'active_sheet_key': f"{active['source_id']}:{section['sheet_name']}",
                        'active_block_id': active['active_block_id'], 'sources': sources, 'issues': issues, 'bulk_scopes': scopes, 'plans': plans,
                        'readiness': {'ready_to_commit': not reasons, 'blocking_issue_count': len(blockers),
                                      'warning_count': len(issues) - len(blockers), 'included_source_count': sum(s['included'] for s in sources),
                                      'included_sheet_count': sum(s['included'] for src in sources for s in src['sheets']),
                                      'skipped_sheet_count': sum(not s['included'] for src in sources for s in src['sheets']),
                                      'planned_analysis_count': sum(p['planned_analysis_count'] for p in plans),
                                      'planned_measurement_count': sum(p['planned_measurement_count'] for p in plans),
                                      'blocking_reason_codes': reasons}})
        active_review = deepcopy(reviews[active['source_id']])
        active_review['semantic_actions'] = SEMANTIC_ACTIONS
        active_review['canonical_analytes'] = CANONICAL
        if active['recipe']['global_decisions'].get('mineral_verification_enabled'):
            from .mineral_verification import acceptance_scopes
            active_review['mineral_acceptance_scopes'] = acceptance_scopes(active_review['plan'], active['recipe'])
        return {'session': session, 'active': active_review}
