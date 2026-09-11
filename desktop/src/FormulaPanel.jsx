import { useEffect, useRef, useState } from 'react';
import { invokePetrolab } from './desktopApi';
import './formulaPanel.css';

const format = value => typeof value === 'number' ? value.toLocaleString('ru', { maximumFractionDigits: 5 }) : String(value ?? '—');
const fieldLabel = field => ({ cation_sum: 'Сумма катионов', oxide_total: 'Сумма оксидов', Fe2_apfu: 'Fe²⁺', Fe3_apfu: 'Fe³⁺' }[field] || field.replace('_apfu', ''));

function Result({ result }) {
  return <div className="formula-result">
    {(result.errors || []).map(text => <p className="formula-error" key={text}>{text}</p>)}
    {(result.warnings || []).map(text => <p className="formula-warning" key={text}>{text}</p>)}
    {Object.keys(result.values || {}).length > 0 && <table aria-label="Рассчитанные значения"><caption>Рассчитано · не исходные измерения</caption>
      <thead><tr><th>Показатель</th><th>Значение</th><th>Единица</th></tr></thead>
      <tbody>{Object.entries(result.values).sort(([a], [b]) => Number(['Fo', 'Fa'].includes(b)) - Number(['Fo', 'Fa'].includes(a))).map(([field, value]) => <tr key={field}><th>{fieldLabel(field)}</th><td>{format(value)}</td><td>{field === 'oxide_total' ? 'wt.%' : ['Fo', 'Fa'].includes(field) ? 'mol.%' : 'APFU'}</td></tr>)}</tbody>
    </table>}
    {(result.assumptions || []).map(text => <p key={text}>{text}</p>)}
    {result.unmeasured?.length > 0 && <p>Нет входных измерений: {result.unmeasured.join(', ')}.</p>}
    {result.excluded?.length > 0 && <p>Исключены: {result.excluded.map(item => `${item.field}: ${item.reason}`).join('; ')}</p>}
    {result.used?.length > 0 && <details><summary>Использованные измерения · wt.%</summary><table aria-label="Исходные измерения">
      <thead><tr><th>Оксид</th><th>Исходное значение</th></tr></thead><tbody>{result.used.map(m => <tr key={m.measurement_id || m.field}><th>{m.field}</th><td>{m.raw_token}</td></tr>)}</tbody>
    </table></details>}
  </div>;
}

export function FormulaPanel({ analysis, databasePath }) {
  const [method, setMethod] = useState(null);
  const [feMode, setFeMode] = useState('');
  const [preview, setPreview] = useState(null);
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const active = useRef(false);
  const analysisId = analysis.analysis_id;
  async function request(command, payload = {}) {
    const response = await invokePetrolab(command, { project_database_path: databasePath, ...payload });
    if (response.error) throw Object.assign(new Error(response.error.message), { code: response.error.code });
    return response.result;
  }
  useEffect(() => {
    active.current = true;
    if (!databasePath) return () => { active.current = false; };
    setBusy(true); setError('');
    Promise.all([request('formula.methods.list'), request('formula.runs.list', { analysis_id: analysisId })])
      .then(([catalog, history]) => { if (active.current) { setMethod(catalog.methods[0]); setRuns(history.runs); } })
      .catch(e => { if (active.current) setError(e.message); })
      .finally(() => { if (active.current) setBusy(false); });
    return () => { active.current = false; };
  }, [analysisId, databasePath, reloadKey]);
  async function calculate(save = false) {
    setBusy(true); setError(''); setMessage('');
    try {
      const payload = { analysis_ids: [analysisId], method_id: method.method_id,
        method_version: method.version, parameters: { fe_mode: feMode } };
      if (save) payload.preview_fingerprint = preview.input_fingerprint;
      const result = await request(save ? 'formula.save' : 'formula.preview', payload);
      if (!active.current) return;
      if (save) {
        setMessage(result.reused ? 'Этот результат уже сохранён.' : 'Результат сохранён отдельно от измерений.');
        setPreview(null);
        const history = await request('formula.runs.list', { analysis_id: analysisId });
        if (active.current) setRuns(history.runs);
      } else setPreview(result);
    } catch (e) { if (active.current) { setError(e.message); if (e.code === 'FORMULA_PREVIEW_STALE') setPreview(null); } }
    finally { if (active.current) setBusy(false); }
  }
  return <section className="formula-panel" aria-label="Пересчёт формулы">
    <h3>Формула минерала</h3>
    <p>Один анализ: <strong>{analysis.identity?.Analysis || analysisId}</strong>. Назначение не запускает расчёт.</p>
    {!databasePath && <p>Откройте сохранённый проект для расчёта.</p>}
    {busy && <p role="status">Проверяю данные…</p>}
    {error && <p role="alert" className="formula-error">{error}</p>}
    {error && !method && <button type="button" className="outline-button" disabled={busy} onClick={() => setReloadKey(key => key + 1)}>Повторить загрузку методов</button>}
    {method && <>
      <label>Метод<select aria-label="Метод формулы" value={method.method_id} disabled={busy} onChange={() => {}}><option value={method.method_id}>{method.name} · v{method.version}</option></select></label>
      <p>Версия {method.version} · нормировка на 4 O. Первый метод: требуется внешняя проверка на природных анализах.</p>
      <label>Режим железа<select aria-label="Режим железа" value={feMode} disabled={busy} onChange={e => { setFeMode(e.target.value); setPreview(null); setMessage(''); }}>
        <option value="">Выберите явно</option>{Object.entries(method.fe_modes).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select></label>
      {!feMode && <p>До расчёта нужно указать, как трактовать железо.</p>}
      <button type="button" className="outline-button" disabled={busy || !feMode} onClick={() => calculate()}>Рассчитать этот анализ</button>
      <details><summary>Метод и источники</summary>{method.citations.map(c => <p key={c.url}><a href={c.url} target="_blank" rel="noreferrer">{c.title}</a></p>)}{method.assumptions.map(a => <p key={a}>{a}</p>)}</details>
    </>}
    {preview && <div aria-label="Предпросмотр формулы"><h4>Предпросмотр · ещё не сохранён</h4>
      <Result result={preview.results[0]} />
      <button type="button" className="primary-button" disabled={busy || !preview.can_save} onClick={() => calculate(true)}>Сохранить результат формулы</button>
      {!preview.can_save && <p>Сохранение недоступно: исправьте указанные входы или назначение.</p>}
    </div>}
    {message && <p role="status">{message}</p>}
    <h4>Сохранённые расчёты · {runs.length}</h4>
    {runs.map(({ run }) => <details key={run.id} className="formula-history"><summary>{run.status === 'stale' ? 'Устарел' : 'Сохранён'} · {run.method_version} · {run.created_at}</summary>
      {run.stale_reasons.map(reason => <p className="formula-warning" key={reason}>{reason}</p>)}
      <p>Режим: {method?.fe_modes[run.parameters.fe_mode] || run.parameters.fe_mode}</p>
      <Result result={run.result_manifest.results.find(r => r.analysis_id === analysisId)} />
      <small>Run ID: {run.id}<br />Fingerprint: {run.input_fingerprint}</small>
    </details>)}
  </section>;
}
