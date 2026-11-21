import { useEffect, useState } from "react";

const PAGE_SIZE = 20;
const EMPTY_QUERY = { query: "", method: "", mineral: "" };
const MANUAL_FIELDS = ["SiO2", "MgO", "TiO2", "Al2O3", "FeO"];

function ManualAnalysisForm({ point, pending, onSave, onCancel }) {
  const [fields, setFields] = useState({ method: "EPMA", identity: "", measurement_date: "", operator: "", comment: "" });
  const [measurements, setMeasurements] = useState({});
  const update = (name) => (event) => setFields({ ...fields, [name]: event.target.value });
  return <form className="sample-form manual-analysis-form" onSubmit={(event) => {
    event.preventDefault();
    onSave({ ...fields, measurements: Object.fromEntries(Object.entries(measurements).filter(([, token]) => token.trim())) });
  }}>
    <label>Метод<select value={fields.method} onChange={update("method")} disabled={pending}>
      <option>EPMA</option><option>SEM-EDS</option>
    </select></label>
    <label>ID / номер анализа<input value={fields.identity} onChange={update("identity")} required maxLength={120} disabled={pending} /></label>
    <label>Дата измерения<input type="date" value={fields.measurement_date} onChange={update("measurement_date")} required disabled={pending} /></label>
    <label className="manual-analysis-wide">Оператор<input value={fields.operator} onChange={update("operator")} required maxLength={120} disabled={pending} /></label>
    <fieldset className="manual-analysis-wide"><legend>Состав (wt.%)</legend>
      {MANUAL_FIELDS.map((field) => <label key={field}>{field}<input maxLength={64} value={measurements[field] ?? ""} disabled={pending}
        onChange={(event) => setMeasurements({ ...measurements, [field]: event.target.value })} /></label>)}
    </fieldset>
    <label className="manual-analysis-wide">Комментарий<textarea value={fields.comment} onChange={update("comment")} maxLength={200} disabled={pending} /></label>
    <p className="manual-analysis-wide">Источник анализа — ручной ввод.</p>
    <button className="primary-button" disabled={pending || !Object.values(measurements).some((token) => token.trim())}>Создать и связать с {point.point_name}</button>
    <button className="outline-button" type="button" disabled={pending} onClick={onCancel}>Отмена</button>
  </form>;
}

export function ThinSectionLinks({ point, actions }) {
  const { loadPoint, changeLink, queryProject, selectedIds, addToSelection, openAnalysis, createManualAnalysis } = actions;
  const [rows, setRows] = useState(null);
  const [search, setSearch] = useState(false);
  const [manual, setManual] = useState(false);
  const [fields, setFields] = useState(EMPTY_QUERY);
  const [page, setPage] = useState({ offset: 0, query: EMPTY_QUERY });
  const [results, setResults] = useState(null);
  const [marked, setMarked] = useState([]);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const id = point.analytical_point_id;

  useEffect(() => {
    let active = true;
    loadPoint(id).then((items) => { if (active) setRows(items); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [id, loadPoint]);

  useEffect(() => {
    if (!search) return;
    let active = true;
    setResults(null);
    setError("");
    queryProject({ ...page.query, sample_id: point.point_sample_id, offset: page.offset, limit: PAGE_SIZE })
      .then((value) => { if (active) setResults(value); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [search, page, point.point_sample_id, queryProject]);

  const closeSearch = () => { setSearch(false); setResults(null); setMarked([]); setError(""); };
  const change = async (ids, type) => {
    setPending(true);
    setNotice("");
    setError("");
    try {
      await changeLink(id, ids, type, "Локальный пользователь");
      if (type) closeSearch();
      setNotice(type ? `Связано анализов: ${ids.length}.` : "Связь снята.");
      try { setRows(await loadPoint(id)); }
      catch (caught) { setRows(null); setError(caught.message); }
    } catch (caught) { setError(caught.message); }
    finally { setPending(false); }
  };

  const create = async (entry) => {
    setPending(true);
    setError("");
    try {
      await createManualAnalysis(id, entry);
      setManual(false);
      setNotice(`Анализ «${entry.identity.trim()}» создан и связан с точкой.`);
      try { setRows(await loadPoint(id)); }
      catch (caught) { setRows(null); setError(caught.message); }
    } catch (caught) { setError(caught.message); }
    finally { setPending(false); }
  };

  return <aside className="sample-card thin-section-links" aria-label="Анализы точки">
    <h3>{manual ? `Новая ручная запись для ${point.point_name}` : search ? `Найти существующий анализ для ${point.point_name}` : `Анализы точки ${point.point_name}`}</h3>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {manual ? <ManualAnalysisForm point={point} pending={pending} onSave={create}
      onCancel={() => { setManual(false); setError(""); }} /> : search ? <>
      <form className="sample-form" onSubmit={(event) => {
        event.preventDefault(); setMarked([]); setPage({ offset: 0, query: fields });
      }}>
        {Object.entries({ query: "Поиск анализа", method: "Метод", mineral: "Минерал" }).map(([name, label]) =>
          <label key={name}>{label}<input maxLength={300} value={fields[name]} disabled={pending}
            onChange={(event) => setFields({ ...fields, [name]: event.target.value })} /></label>)}
        <button className="outline-button" disabled={pending}>Найти</button>
      </form>
      {!results && !error && <p role="status">Ищу анализы…</p>}
      {results?.analyses.length === 0 && <p>Совпадений нет.</p>}
      {results?.analyses.length > 0 && <div className="project-search-table"><table>
        <thead><tr><th aria-label="Отметка" /><th>Анализ</th><th>Метод</th><th>Минерал</th><th>Источник</th><th>Связь</th></tr></thead>
        <tbody>{results.analyses.map((row) => {
          const linked = rows.some(({ analysis_id }) => analysis_id === row.analysis_id);
          return <tr key={row.analysis_id}>
            <td><input type="checkbox" aria-label={`Отметить ${row.identity}`} checked={marked.includes(row.analysis_id)} disabled={pending || linked}
              onChange={(event) => setMarked(event.target.checked ? [...marked, row.analysis_id] : marked.filter((item) => item !== row.analysis_id))} /></td>
            <td>{row.identity || "—"}</td><td>{row.method || "—"}</td><td>{row.mineral || "—"}</td>
            <td>{row.source_name} · {row.sheet_name} · {row.source_column_number ? `колонка ${row.source_column_number}` : `строка ${row.source_row_number}`}</td>
            <td>{linked ? "Связан с точкой" : "Доступен"}</td>
          </tr>;
        })}</tbody>
      </table></div>}
      {(page.offset > 0 || results?.has_more) && <div className="point-row-actions">
        <button className="outline-button" disabled={pending || !results || page.offset === 0}
          onClick={() => setPage({ ...page, offset: page.offset - PAGE_SIZE })}>Назад</button>
        <button className="outline-button" disabled={pending || !results?.has_more}
          onClick={() => setPage({ ...page, offset: page.offset + PAGE_SIZE })}>Далее</button>
      </div>}
      <div className="point-row-actions">
        <button className="primary-button" disabled={pending || !marked.length} onClick={() => change(marked, "same_point")}>
          Связать отмеченные анализы ({marked.length})
        </button>
        <button className="outline-button" disabled={pending} onClick={closeSearch}>Отмена</button>
      </div>
    </> : <>
      <div className="point-row-actions">
        <button className="primary-button" disabled={!rows || pending} onClick={() => { setNotice(""); setSearch(true); }}>Найти существующие анализы</button>
        {createManualAnalysis && <button className="outline-button" disabled={!rows || pending}
          onClick={() => { setNotice(""); setManual(true); }}>Создать ручную запись</button>}
      </div>
      {!rows && !error && <p role="status">Загружаю анализы точки…</p>}
      {rows?.length === 0 && <p>У этой точки нет связанных анализов.</p>}
      {rows?.length > 0 && <ul className="sample-items">{rows.map((row) => <li key={row.analysis_id}>
        <div><b>{row.identity || row.analysis_id}</b><p>{row.method || "Метод не указан"} · {row.source_name}{!row.active && " · импорт отозван"}</p></div>
        <div className="point-row-actions">
          <button className="outline-button" disabled={!row.active || pending} onClick={() => openAnalysis(row.analysis_id)}>Открыть анализ</button>
          <button className="outline-button" disabled={!row.active || pending || selectedIds.includes(row.analysis_id)}
            onClick={() => addToSelection(row.analysis_id)}>Добавить в отбор</button>
          <button className="outline-button" disabled={pending} onClick={() => change(row.analysis_id, null)}>Снять связь</button>
        </div>
      </li>)}</ul>}
    </>}
  </aside>;
}
