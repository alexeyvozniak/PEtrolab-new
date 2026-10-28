import { useEffect, useState } from 'react';

export function SemanticRangeActions({ records, selection, setSelection, actions, analytes, annotations, onDecision, onPreview, busy, blockId, requestedRole }) {
  const [role, setRole] = useState('sample');
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState('');
  const [extension, setExtension] = useState(null);
  const [error, setError] = useState('');
  const [remember, setRemember] = useState(false);
  useEffect(() => { if (requestedRole) setRole(requestedRole); }, [requestedRole]);
  useEffect(() => { setExtension(null); setError(''); }, [selection, annotations]);
  const selectedAction = actions.find((a) => a.role === role);
  const lastAnnotation = annotations.at(-1);
  const selectedRecords = selection ? records.filter((record) => record.block_id === blockId && (record.orientation === 'columns_are_analyses'
    ? record.source_column_number - 1 >= selection.start_column && record.source_column_number - 1 <= selection.end_column
    : record.row_number >= selection.start_row && record.row_number <= selection.end_row)) : [];
  async function previewExtension() {
    if (!lastAnnotation) return;
    setError('');
    try {
      const decision = { action: 'extend', annotation_id: lastAnnotation.id, range: selection };
      await onPreview(decision);
      setExtension(decision);
    } catch (caught) { setError(caught.message); }
  }
  return <div className="semantic-actions" aria-label="Действия с выделением">
    <div className="semantic-selection-head"><b>{selection ? `Строки ${selection.start_row}–${selection.end_row} · колонки ${selection.start_column + 1}–${selection.end_column + 1}` : 'Выделите ячейки, строку или колонку'}</b>
      <button type="button" disabled={busy || !annotations.length} onClick={() => onDecision({ action: 'undo' })}>Отменить последнее назначение</button></div>
    {selection && <>
      {selectedRecords.length > 0 && <details className="semantic-sample-evidence"><summary>Образцы в выделении · {selectedRecords.length} анализов · физические связи не объединяются по имени</summary>{selectedRecords.slice(0, 8).map((record) => {
        const association = record.sample_association;
        return <div key={record.preview_id}><b>{record.identity.join(' · ')}</b>: {association?.reported ? `${association.reported.value} · ${association.reported.origin}` : 'Образец не определён'}{association?.reported && <small> · связь с физическим Sample не подтверждена</small>}{(association?.candidates || []).map((candidate, index) => <button type="button" key={index} disabled={busy} title={`Неподтверждённая подсказка: ${candidate.confidence}; ${candidate.sheet_name}, строка ${candidate.row}`} onClick={() => { setRole('sample'); setValue(candidate.value); }}>Предложить {candidate.value}</button>)}</div>;
      })}{selectedRecords.length > 8 && <small>Показаны первые 8; сузьте выделение для остальных.</small>}</details>}
      <div className="semantic-bounds">
        {[['start_row', 'От строки', 1], ['end_row', 'До строки', 1], ['start_column', 'От колонки', 0], ['end_column', 'До колонки', 0]].map(([key, label, offset]) => <label key={key}>{label}<input type="number" min="1" aria-label={label} value={selection[key] + (offset === 0 ? 1 : 0)} onChange={(event) => { setSelection({ ...selection, [key]: Number(event.target.value) - (offset === 0 ? 1 : 0) }); setExtension(null); }} disabled={busy} /></label>)}
      </div>
      <div className="semantic-assignment-controls">
        <select aria-label="Роль выделенного диапазона" value={role} onChange={(event) => { setRole(event.target.value); setExtension(null); }} disabled={busy}>{actions.map((action) => <option key={action.role} value={action.role}>{action.label}</option>)}</select>
        {selectedAction?.value_required && <input aria-label="Значение назначения" placeholder={role === 'component' ? 'Например, SiO2' : 'Название или ID'} value={value} onChange={(event) => setValue(event.target.value)} list={role === 'component' ? 'canonical-analytes' : undefined} disabled={busy} />}
        <datalist id="canonical-analytes">{analytes.map((analyte) => <option key={analyte} value={analyte} />)}</datalist>
        {role === 'component' && <input aria-label="Единица компонента" placeholder="wt.%, ppm…" value={unit} onChange={(event) => setUnit(event.target.value)} disabled={busy} />}
        <button type="button" disabled={busy || (selectedAction?.value_required && !value.trim())} onClick={() => onDecision({ role, value, unit, block_id: blockId, range: selection, remember_alias: remember })}>Назначить диапазону</button>
      </div>
      {role === 'component' && <label><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} /> Запомнить исходный заголовок как обозначение в этом проекте</label>}
      {lastAnnotation && <div className="semantic-extension"><span>{lastAnnotation.value || lastAnnotation.role} · назначение {lastAnnotation.range.start_row}–{lastAnnotation.range.end_row}</span>
        <button type="button" onClick={previewExtension} disabled={busy}>Проверить расширение до выделения</button>
        {extension && <><b role="status">{lastAnnotation.value} → строки {extension.range.start_row}–{extension.range.end_row}. Исходные значения сохранятся.</b><button type="button" disabled={busy} onClick={() => { onDecision(extension); setExtension(null); }}>Подтвердить расширение</button><button type="button" onClick={() => setExtension(null)}>Отмена расширения</button></>}
      </div>}
    </>}
    {error && <p role="alert">{error}</p>}
    <small>Разметка поверх исходника · перетаскивание или Shift для диапазона · правый клик для действий</small>
  </div>;
}
