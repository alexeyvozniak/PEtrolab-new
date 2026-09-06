import { useState } from 'react';

const statusLabels = { consistent: 'Совпадает на уровне химической группы', conflict: 'Расхождение с источником',
  missing_reported: 'Минерал не указан в источнике', low_confidence: 'Неоднозначное предложение',
  insufficient_input: 'Недостаточно надёжных данных', unrecognized_reported: 'Проверьте исходное название', verified: 'Принято пользователем' };

export function MineralVerificationPanel({ records, scopes, busy, onAccept, onReveal }) {
  const [showAll, setShowAll] = useState(false);
  const [visibleCount, setVisibleCount] = useState(100);
  const evaluated = records.filter((r) => r.mineral_verification);
  const attention = evaluated.filter((r) => !['consistent', 'verified'].includes(r.mineral_verification.status));
  const visible = showAll ? evaluated : attention;
  return <div className="mineral-verification-panel">
    <div className="import-inspector-title"><span>2 · Проверка минералов</span><b>{attention.length} требуют внимания из {evaluated.length}</b><small>Предложение классификатора не заменяет название из источника.</small></div>
    {scopes.map((scope) => <div className="mineral-review-item" key={scope.scope_id}><b>{scope.target} · {scope.count} совпадений</b><button type="button" disabled={busy} onClick={() => onAccept({ scope_id: scope.scope_id })}>Принять группу совпадений</button></div>)}
    <label className="mineral-show-all"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Показать все результаты</label>
    {visible.slice(0, visibleCount).map((record) => {
      const result = record.mineral_verification;
      return <div className="mineral-review-item" key={record.preview_id}>
        <button type="button" className="mineral-origin" onClick={() => onReveal(record)} disabled={busy}>{record.identity.join(' · ')} · {record.sheet_name}, строка {record.row_number}</button>
        <b>{statusLabels[result.status] || result.status}</b>
        <dl><dt>В источнике</dt><dd>{result.reported_mineral || 'Не указан'}</dd><dt>Предложение</dt><dd>{result.prediction || 'Не определено'} · {result.confidence}</dd><dt>Принято</dt><dd>{result.accepted?.target || 'Не принято'}</dd></dl>
        {result.issues.length > 0 && <p>Проверьте полноту состава, единицы, пропуски и форму Fe. Догадки не подставляются вместо измерений.</p>}
        <details><summary>Основания и версия</summary><small>{result.ruleset_version}</small>{(result.reasons || result.issues).map((reason) => <p key={reason}>{reason}</p>)}</details>
        {result.prediction && !result.accepted && <button type="button" disabled={busy} onClick={() => onAccept({ preview_id: record.preview_id, input_fingerprint: result.input_fingerprint })}>Принять предложение</button>}
      </div>;
    })}
    {visible.length > visibleCount && <button type="button" onClick={() => setVisibleCount((count) => count + 100)}>Показать ещё · осталось {visible.length - visibleCount}</button>}
    {visible.length === 0 && <p className="mineral-show-all">Нет отдельных конфликтов для просмотра.</p>}
  </div>;
}
