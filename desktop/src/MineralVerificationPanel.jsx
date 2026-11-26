import { useState } from 'react';

const statusLabels = { consistent: 'Совпадает на уровне химической группы', conflict: 'Расхождение с источником',
  missing_reported: 'Минерал не указан в источнике', low_confidence: 'Неоднозначное предложение',
  insufficient_input: 'Недостаточно надёжных данных', unrecognized_reported: 'Проверьте исходное название',
  not_checked: 'Проверка не запускалась', reported_only: 'Только исходное название', verified: 'Принято пользователем' };

const excludedLabels = { unsupported_component: 'Вне выбранного метода', non_quantitative: 'Нет количественного значения',
  incompatible_unit: 'Несовместимая единица', incompatible_iron_form: 'Несовместимая форма железа' };
const diagnosticLabels = {
  oxide_sum_wt_pct: 'Сумма оксидов вне диапазона', cation_sum_apfu: 'Сумма катионов вне диапазона',
  end_member_mol_percent: 'Недостаточно данных для расчёта долей', calcium_partition: 'Недостаточно данных для распределения Ca',
  'droop_Fe3+': 'Оценка по Droop вне области применимости',
  nepheline_cavity: 'Недостаточно измерений для Qxs', nepheline_stoichiometry: 'Проверьте стехиометрию нефелина',
  apatite_OH_estimate: 'Для оценки OH нужны F и Cl', apatite_X_site: 'Сумма F и Cl превышает вместимость X-позиции',
  titanite_OH_estimate: 'Проверьте вход для оценки OH', mica_tetrahedral_site: 'Проверьте состав тетраэдрической позиции',
  mica_OH_upper_bound: 'Для оценки верхней границы OH нужны F и Cl', mica_W_site: 'Сумма F и Cl превышает вместимость W-позиции',
};
const number = new Intl.NumberFormat('ru', { maximumSignificantDigits: 6 });

function FormulaPreview({ record, methods, busy, onPreview, onAccept, onClose }) {
  const [methodId, setMethodId] = useState('');
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const method = methods.find((item) => item.method_id === methodId);
  async function calculate(event) {
    event.preventDefault();
    if (!method || busy || pending) return;
    setPending(true);
    setResult(null);
    setError('');
    try {
      setResult(await onPreview(record.preview_id, methodId));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  }
  const series = result && [
    ['APFU', result.preview.apfu],
    ['Молярные доли, %', result.preview.end_member_mol_percent ?? result.preview.divalent_component_mol_percent],
    ['Индексы', result.preview.indices],
    ['Оценка анионов, APFU', result.preview.estimated_anions_apfu],
  ].filter(([, values]) => values && Object.keys(values).length);
  return <form aria-label="Предпросмотр формулы" className="mineral-formula-preview" onSubmit={calculate}>
    <label>Метод пересчёта<select value={methodId} disabled={busy || pending} onChange={(event) => {
      setMethodId(event.target.value);
      setResult(null);
      setError('');
    }}>
      <option value="">Выберите метод</option>
      {methods.map((item) => <option key={item.method_id} value={item.method_id}>{item.name}</option>)}
    </select></label>
    {method && <p>Версия {method.version} · {method.oxygen_basis ? `${method.oxygen_basis} O` : `${method.cation_basis} кат.`}</p>}
    <div className="mineral-formula-actions">
      <button type="submit" disabled={!method || busy || pending}>{pending ? 'Вычисление…' : 'Рассчитать'}</button>
      <button type="button" onClick={onClose}>Закрыть формулу</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {result && <div>
      <b role="status">Предварительный расчёт</b>
      {series.map(([label, values]) => <section key={label}><b>{label}</b><dl>
        {Object.entries(values).map(([field, value]) => <div key={field}><dt>{field}</dt><dd>{number.format(value)}</dd></div>)}
      </dl></section>)}
      {result.preview.warnings.map(({ field, missing_species }) =>
        <p key={field}>{diagnosticLabels[field] || field}{missing_species?.length ? ` · ${missing_species.join(', ')}` : ''}</p>)}
      <details><summary>Исходные измерения и допущения</summary>
        <p>{method.iron_policy}</p><p>{method.oh_basis}</p>
        {result.measurements.map(({ source_cell, field, raw_token, unit }) =>
          <p key={source_cell}>{source_cell} · {field} · {raw_token} {unit}</p>)}
        {result.excluded_measurements.map(({ source_cell, field, raw_token, reason }) =>
          <p key={source_cell}>{source_cell} · {field} · {raw_token || 'пусто'} · {excludedLabels[reason]}</p>)}
      </details>
      {onAccept && <div className="mineral-formula-accept">
        <button type="button" disabled={busy || pending} onClick={() => onAccept({ preview_id: result.preview_id,
          method_id: result.method_definition.method_id, confirmation_fingerprint: result.confirmation_fingerprint })}>Принять расчёт</button>
        <small>Сохранится при добавлении анализов в проект.</small>
      </div>}
    </div>}
  </form>;
}

export function MineralVerificationPanel({ records, scopes, busy, onAccept, onReveal, formulaScope, onListFormulaMethods, onPreviewFormula, onAcceptFormula }) {
  const [showAll, setShowAll] = useState(false);
  const [visibleCount, setVisibleCount] = useState(100);
  const [formula, setFormula] = useState(null);
  const [methods, setMethods] = useState(null);
  const [methodsPending, setMethodsPending] = useState(false);
  const [methodsError, setMethodsError] = useState('');
  async function openFormula(record) {
    setFormula({ previewId: record.preview_id, scope: formulaScope });
    if (methods || methodsPending) return;
    setMethodsPending(true);
    setMethodsError('');
    try {
      setMethods(await onListFormulaMethods());
    } catch (failure) {
      setMethodsError(failure.message);
    } finally {
      setMethodsPending(false);
    }
  }
  const evaluated = records.filter((r) => r.mineral_verification);
  const attention = evaluated.filter((r) => !['consistent', 'verified'].includes(r.mineral_verification.status));
  const visible = showAll ? evaluated : attention;
  return <div className="mineral-verification-panel">
    <div className="import-inspector-title"><span>2 · Проверка минералов</span><b>{attention.length} требуют внимания из {evaluated.length}</b><small>Предложение классификатора не заменяет название из источника.</small></div>
    {scopes.map((scope) => <div className="mineral-review-item" key={scope.scope_id}><b>{scope.target} · {scope.count} совпадений</b><button type="button" disabled={busy} onClick={() => onAccept({ scope_id: scope.scope_id })}>Принять группу совпадений</button></div>)}
    <label className="mineral-show-all"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Показать все результаты</label>
    {visible.slice(0, visibleCount).map((record) => {
      const result = record.mineral_verification;
      const evidence = result.reasons?.length ? result.reasons : (result.issues || []);
      return <div className="mineral-review-item" key={record.preview_id}>
        <button type="button" className="mineral-origin" onClick={() => onReveal(record)} disabled={busy}>{record.identity.join(' · ')} · {record.sheet_name}, строка {record.row_number}</button>
        <b>{statusLabels[result.status] || result.status}</b>
        <dl><dt>В источнике</dt><dd>{result.reported_mineral || 'Не указан'}</dd><dt>Предложение</dt><dd>{result.prediction || 'Не определено'} · {result.confidence}</dd><dt>Принято</dt><dd>{result.accepted?.target || 'Не принято'}</dd></dl>
        {result.issues.length > 0 && <p>Проверьте полноту состава, единицы, пропуски и форму Fe. Догадки не подставляются вместо измерений.</p>}
        <details><summary>Основания и версия</summary><small>{result.ruleset_version}</small>{evidence.map((reason) => <p key={reason}>{reason}</p>)}</details>
        {result.prediction && !result.accepted && <button type="button" disabled={busy} onClick={() => onAccept({ preview_id: record.preview_id, input_fingerprint: result.input_fingerprint })}>Принять предложение</button>}
        {onPreviewFormula && <button type="button" disabled={busy || methodsPending} onClick={() => openFormula(record)}>Рассчитать формулу</button>}
        {formula && formula.scope === formulaScope && formula.previewId === record.preview_id && <>
          {methodsPending && <p role="status">Загрузка методов…</p>}
          {methodsError && <p role="alert">{methodsError}</p>}
          {methods && <FormulaPreview key={formulaScope} record={record} methods={methods} busy={busy}
            onPreview={onPreviewFormula} onAccept={onAcceptFormula} onClose={() => setFormula(null)} />}
        </>}
      </div>;
    })}
    {visible.length > visibleCount && <button type="button" onClick={() => setVisibleCount((count) => count + 100)}>Показать ещё · осталось {visible.length - visibleCount}</button>}
    {visible.length === 0 && <p className="mineral-show-all">Нет отдельных конфликтов для просмотра.</p>}
  </div>;
}
