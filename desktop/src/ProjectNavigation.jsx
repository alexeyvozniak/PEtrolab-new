import { useEffect, useState } from "react";
import { Database, FileArrowUp, MagnifyingGlass, SquaresFour, X } from "@phosphor-icons/react";
import "./projectNavigation.css";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function ProjectOverview({ load, project, workspace, selectionCount, busy, canImport, onImport, onResume, onSource, onGroup }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    load().then((result) => { if (active) setData(result); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [load]);

  const imports = data?.recent_imports || [];
  const groups = data?.recent_groups || [];
  const events = [
    ...imports.map((item) => ({ ...item, key: item.import_batch_id, time: item.applied_at, kind: "import" })),
    ...groups.map((item) => ({ ...item, key: item.id, time: item.created_at, kind: "group" })),
  ].sort((left, right) => right.time.localeCompare(left.time));

  return <section className="project-navigation overview-navigation">
    <main>
      <p className="project-name">Проект: <b>{data?.project_name || "Локальный проект PetroLab"}</b></p>
      <h2>Сегодня в проекте</h2>
      {error && <p role="alert">История проекта недоступна: {error}</p>}
      {workspace && <article className="overview-event">
        <FileArrowUp size={21} /><div><b>Черновик импорта</b><p>{workspace.sources.length} источников в очереди</p></div>
        <button className="primary-button" onClick={onResume} disabled={busy}>Продолжить импорт</button>
      </article>}
      {project.total === 0 && !workspace && <>
        <p>Импортируйте таблицу, чтобы начать работу с анализами.</p>
        <button className="primary-button" onClick={onImport} disabled={busy || !canImport}>Выбрать файл</button>
      </>}
      {events.map((event) => <article className="overview-event" key={event.key}>
        {event.kind === "import" ? <FileArrowUp size={21} /> : <SquaresFour size={21} />}
        <div><small>{formatDate(event.time)}</small>
          <b>{event.kind === "import" ? `Импорт «${event.source_name}» завершён` : `Рабочая группа «${event.name}»`}</b>
          <p>Анализов: {event.analysis_count}</p>
        </div>
        <button className="outline-button" type="button" disabled={busy}
          onClick={() => event.kind === "import" ? onSource(event) : onGroup(event.id)}
          aria-label={event.kind === "import" ? `Открыть источник ${event.source_name}` : `Открыть группу ${event.name}`}>Открыть</button>
      </article>)}
    </main>
    <aside>
      <h3>Состояние данных</h3>
      <dl><div><dt>Источники</dt><dd>{project.source_count}</dd></div>
        <div><dt>Анализы</dt><dd>{project.total}</dd></div>
        {selectionCount > 0 && <div><dt>Текущий отбор</dt><dd>{selectionCount}</dd></div>}</dl>
      {groups.length > 0 && <section><h3>Рабочие группы</h3>
        {groups.map((group) => <button className="outline-button" type="button" key={group.id}
          disabled={busy} onClick={() => onGroup(group.id)}>{group.name} · {group.analysis_count}</button>)}
      </section>}
    </aside>
  </section>;
}

const SEARCH_FIELDS = { query: "Анализ или образец", mineral: "Минерал", source: "Источник", method: "Метод" };
const EMPTY_SEARCH = { query: "", mineral: "", source: "", method: "", source_id: "", sample_id: "" };
const PAGE = 50;

export function ProjectSearch({ seed, queryProject, onOpenAnalysis, onAddSelection, onPlot, selectionCount, busy }) {
  const initial = { ...EMPTY_SEARCH, ...seed };
  const [fields, setFields] = useState(initial);
  const [applied, setApplied] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [marked, setMarked] = useState([]);
  const [focused, setFocused] = useState(null);
  useEffect(() => {
    let active = true;
    setPending(true);
    setError("");
    queryProject({ ...applied, offset, limit: PAGE })
      .then((page) => { if (active) { setResult(page); setFocused(page.analyses[0] || null); } })
      .catch((caught) => { if (active) { setResult(null); setFocused(null); setError(caught.message); } })
      .finally(() => { if (active) setPending(false); });
    return () => { active = false; };
  }, [applied, offset, queryProject]);

  const apply = (next) => {
    setOffset(0);
    setMarked([]);
    setApplied({ ...next });
  };
  const remove = (key) => {
    const next = { ...applied, [key]: "", ...(key === "source" ? { source_id: "" } : {}) };
    setFields(next);
    apply(next);
  };
  const toggle = (id) => setMarked((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const rows = [...(result?.analyses || [])].sort((a, b) => Number(marked.includes(b.analysis_id)) - Number(marked.includes(a.analysis_id)));

  return <section className="project-navigation search-navigation">
    <main>
      <h2>Поиск по проекту</h2>
      <form className="project-search-form" onSubmit={(event) => { event.preventDefault(); apply(fields); }}>
        {Object.entries(SEARCH_FIELDS).map(([key, label]) => <label key={key}>{label}
          <input value={fields[key]} maxLength={300} onChange={(event) => setFields({
            ...fields, [key]: event.target.value, ...(key === "source" ? { source_id: "" } : {}),
          })} />
        </label>)}
        <button className="primary-button" disabled={pending || busy}><MagnifyingGlass size={17} /> Найти</button>
      </form>
      <div className="project-search-chips" aria-label="Условия поиска">
        {applied.sample_id && <button type="button" className="outline-button" onClick={() => remove("sample_id")} disabled={pending}>
          Образец: {seed?.sample_label || applied.sample_id} <X size={12} />
        </button>}
        {Object.entries(SEARCH_FIELDS).filter(([key]) => applied[key]).map(([key, label]) =>
          <button type="button" className="outline-button" key={key} onClick={() => remove(key)} disabled={pending}>
            {label}: {applied[key]} <X size={12} />
          </button>)}
      </div>
      {error && <p role="alert">{error}</p>}
      <p role="status">{pending ? "Ищу анализы…" : `Найдено анализов: ${result?.total || 0}. Отмечено: ${marked.length}. В отборе: ${selectionCount}.`}</p>
      {marked.length > 0 && <div className="project-search-chips">
        <button type="button" className="outline-button" disabled={pending || busy}
          onClick={() => onAddSelection(marked)}>Добавить отмеченные в отбор</button>
        {onPlot && <button type="button" className="primary-button" disabled={pending || busy}
          onClick={() => onPlot(marked)}>Построить диаграммы</button>}
      </div>}
      {!pending && !rows.length && !error && <p>Совпадений нет. Измените условия поиска.</p>}
      {rows.length > 0 && <div className="project-search-table">
        <table>
          <thead><tr><th>Отметка</th><th>Анализ</th><th>Образец</th><th>Минерал</th><th>Метод</th><th>Источник</th><th /></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.analysis_id} className={marked.includes(row.analysis_id) ? "marked" : ""}
            onFocus={() => setFocused(row)} onClick={() => setFocused(row)}>
            <td><input type="checkbox" aria-label={`Отметить ${row.identity}`} checked={marked.includes(row.analysis_id)}
              disabled={pending || busy} onChange={() => toggle(row.analysis_id)} /></td>
            <td>{row.identity || "Анализ"}</td><td>{row.sample_name || "—"}</td><td>{row.mineral || "—"}</td>
            <td>{row.method || "—"}</td><td>{row.source_name}</td>
            <td><button className="outline-button" type="button" disabled={pending || busy}
              onClick={() => onOpenAnalysis(row.analysis_id)} aria-label={`Открыть анализ ${row.identity}`}>Открыть</button></td>
          </tr>)}</tbody>
        </table>
      </div>}
      {result && (offset > 0 || result.has_more) && <div className="project-search-page">
        <button type="button" className="outline-button" disabled={pending || offset === 0} onClick={() => setOffset(offset - PAGE)}>Назад</button>
        <span>Страница {offset / PAGE + 1}</span>
        <button type="button" className="outline-button" disabled={pending || !result.has_more} onClick={() => setOffset(offset + PAGE)}>Далее</button>
      </div>}
    </main>
    <aside>
      <h3>Источник совпадения</h3>
      {focused ? <>
        <p><Database size={16} /> <b>{focused.source_name}</b></p>
        <p>{focused.sheet_name} · {focused.source_column_number ? `колонка ${focused.source_column_number}` : `строка ${focused.source_row_number}`}</p>
        {focused.sample_name && <p>Образец: {focused.sample_name}</p>}
        <details><summary>Контрольная сумма источника</summary><p className="project-fingerprint">{focused.source_sha256}</p></details>
      </> : <p>Контекст появится после поиска.</p>}
    </aside>
  </section>;
}
