import { Fragment, useEffect, useRef, useState } from "react";
import { Database, FileArrowUp, MagnifyingGlass, PencilSimple, Plus, SquaresFour, X } from "@phosphor-icons/react";
import { GenerationAssignment } from "./GenerationAssignment";
import { isPetrolabDesktop, openExternalUrl } from "./desktopApi";
import "./projectNavigation.css";
import { selectionRange } from "./selectionRange";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function ProjectOverview({ load, project, workspace, selectionCount, busy, canImport, onImport, onResume, onSource, onGroup, onSaveTask }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [editingTasks, setEditingTasks] = useState(false);
  const [taskDraft, setTaskDraft] = useState(null);
  const [savingTask, setSavingTask] = useState(false);
  const [taskError, setTaskError] = useState("");
  useEffect(() => {
    let active = true;
    load().then((result) => { if (active) setData(result); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [load]);

  const imports = data?.recent_imports || [];
  const groups = data?.recent_groups || [];
  const tasks = data?.work_plan || [];
  const taskLocked = busy || savingTask;
  async function saveTask(task) {
    setSavingTask(true);
    setTaskError("");
    try {
      const saved = await onSaveTask(task);
      setData((current) => ({ ...current, work_plan: task.id
        ? current.work_plan.map((item) => item.id === saved.id ? saved : item)
        : [...(current.work_plan || []), saved] }));
      setTaskDraft(null);
    } catch (caught) {
      setTaskError(caught.message);
    } finally {
      setSavingTask(false);
    }
  }
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
      {data && onSaveTask && <section className="overview-work-plan" aria-labelledby="overview-plan-heading">
        <header>
          <h3 id="overview-plan-heading">План работы</h3>
          {tasks.length > 0 && <button className="outline-button" type="button" aria-label="Редактировать план работы"
            aria-pressed={editingTasks} disabled={taskLocked || Boolean(taskDraft)} onClick={() => setEditingTasks(!editingTasks)}>
            <PencilSimple size={17} />
          </button>}
        </header>
        {tasks.length > 0 && <ul>{tasks.map((task) => <li key={task.id}>
          <label><input type="checkbox" checked={task.completed} disabled={taskLocked || Boolean(taskDraft)}
            onChange={(event) => saveTask({ ...task, completed: event.target.checked })} /><span>{task.title}</span></label>
          {editingTasks && <button className="outline-button" type="button" aria-label={`Изменить задачу: ${task.title}`}
            disabled={taskLocked || Boolean(taskDraft)} onClick={() => { setTaskDraft(task); setTaskError(""); }}>
            <PencilSimple size={15} />
          </button>}
        </li>)}</ul>}
        {taskDraft ? <form aria-label="Задача плана работы" onSubmit={(event) => { event.preventDefault(); saveTask(taskDraft); }}>
          <label>Задача<input autoFocus value={taskDraft.title} required maxLength={240} disabled={taskLocked}
            onChange={(event) => setTaskDraft({ ...taskDraft, title: event.target.value })} /></label>
          <div>
            <button className="primary-button" type="submit" disabled={taskLocked || !taskDraft.title.trim()}>Сохранить задачу</button>
            <button className="outline-button" type="button" disabled={taskLocked}
              onClick={() => { setTaskDraft(null); setTaskError(""); }}>Отмена</button>
          </div>
        </form> : <button className="outline-button" type="button" disabled={taskLocked}
          onClick={() => { setTaskDraft({ title: "", completed: false, revision: 0 }); setTaskError(""); }}>
          <Plus size={17} /> Добавить задачу
        </button>}
        {taskError && <p role="alert">{taskError}</p>}
      </section>}
      {groups.length > 0 && <section><h3>Рабочие группы</h3>
        {groups.map((group) => <button className="outline-button" type="button" key={group.id}
          disabled={busy} onClick={() => onGroup(group.id)}>{group.name} · {group.analysis_count}</button>)}
      </section>}
    </aside>
  </section>;
}

const SEARCH_FIELDS = { query: "Анализ или образец", mineral: "Минерал", source: "Источник", method: "Метод" };
const PUBLICATION_LABELS = {
  Source: "Источник по таблице", DOI: "DOI", "Publication authors": "Авторы", "Publication year": "Год",
  "Publication title": "Название", "Publication journal": "Издание", "Publication URL": "Ссылка",
};
const EMPTY_SEARCH = { query: "", mineral: "", source: "", method: "", source_id: "", sample_id: "" };
export function ProjectSearch({ seed, queryProject, queryAnalysisIds, onOpenAnalysis, onEditAnalysis, onOpenSample, onAddSelection, onPlot,
  selectionCount, hiddenAnalysisIds = [], onSetVisibility, onUndoVisibility, hiddenSourceIds = [], onToggleSource,
  onCreateWorkGroup, generationActions, onBeginPointLink, busy }) {
  const initial = { ...EMPTY_SEARCH, ...seed };
  const [fields, setFields] = useState(initial);
  const [applied, setApplied] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [marked, setMarked] = useState([]);
  const [groupScope, setGroupScope] = useState(null);
  const [savingGroup, setSavingGroup] = useState(false);
  const [groupNotice, setGroupNotice] = useState("");
  const [markingAll, setMarkingAll] = useState(false);
  const [dragIds, setDragIds] = useState([]);
  const [focused, setFocused] = useState(null);
  const anchor = useRef(null);
  const drag = useRef(null);
  useEffect(() => {
    let active = true;
    setPending(true);
    setError("");
    queryProject({ ...applied, offset, limit: pageSize })
      .then((page) => { if (active) { setResult(page); setFocused(page.analyses[0] || null); } })
      .catch((caught) => { if (active) { setResult(null); setFocused(null); setError(caught.message); } })
      .finally(() => { if (active) setPending(false); });
    return () => { active = false; };
  }, [applied, offset, pageSize, queryProject]);

  useEffect(() => {
    function finish(event) {
      const gesture = drag.current;
      if (!gesture || (event.type !== "blur" && gesture.pointerId !== event.pointerId)) return;
      drag.current = null;
      setDragIds([]);
      if (event.type === "pointerup" && gesture.range.length > 1) {
        anchor.current = gesture;
        setMarked([...new Set([...gesture.base, ...gesture.range])]);
      }
    }
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    window.addEventListener("blur", finish);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      window.removeEventListener("blur", finish);
    };
  }, []);

  function clearRange() {
    anchor.current = null;
    drag.current = null;
    setDragIds([]);
  }

  const apply = (next) => {
    clearRange();
    setPending(true);
    setOffset(0);
    setMarked([]);
    setGroupScope(null);
    setGroupNotice("");
    setApplied({ ...next });
  };
  const remove = (key) => {
    const next = { ...applied, [key]: "", ...(key === "source" ? { source_id: "" } : {}) };
    setFields(next);
    apply(next);
  };
  const showSource = (row) => {
    const next = { ...EMPTY_SEARCH, source_id: row.source_id, source: row.source_name };
    setFields(next);
    apply(next);
  };
  const openPublicationLink = async (event, url) => {
    if (!isPetrolabDesktop()) return;
    event.preventDefault();
    setError("");
    try {
      await openExternalUrl(url);
    } catch (caught) {
      setError(caught?.message || String(caught));
    }
  };
  const markedSet = new Set(marked);
  const hiddenSet = new Set(hiddenAnalysisIds);
  const dragSet = new Set(dragIds);
  const rows = [...(result?.analyses || [])].sort((a, b) => Number(markedSet.has(b.analysis_id)) - Number(markedSet.has(a.analysis_id)));
  const visibleMarkedCount = rows.filter((row) => markedSet.has(row.analysis_id)).length;
  const visibleIds = rows.map(({ analysis_id }) => analysis_id);
  const locked = pending || busy || markingAll || savingGroup;
  const markedHidden = marked.filter((id) => hiddenSet.has(id)).length;

  function changePage(nextOffset, nextSize = pageSize) {
    if (nextOffset === offset && nextSize === pageSize) return;
    clearRange();
    setPending(true);
    setOffset(nextOffset);
    setPageSize(nextSize);
  }

  function toggle(id, extend) {
    const previous = anchor.current;
    if (extend && previous?.page === result) {
      const range = selectionRange(previous.order, previous.id, id);
      if (range.length) {
        setMarked([...new Set([...previous.base, ...range])]);
        return;
      }
    }
    anchor.current = markedSet.has(id) ? null : { id, order: visibleIds, base: marked, page: result };
    if (markedSet.has(id) && marked.length === 1) setGroupScope(null);
    setMarked(markedSet.has(id) ? marked.filter((item) => item !== id) : [...marked, id]);
  }

  function startDrag(event, id) {
    if (locked || event.button !== 0 || event.pointerType === "touch" || event.shiftKey || event.ctrlKey || event.metaKey) return;
    drag.current = { id, order: visibleIds, base: marked, page: result, range: [], pointerId: event.pointerId };
  }

  function extendDrag(event, id) {
    const gesture = drag.current;
    if (!gesture || gesture.page !== result || gesture.pointerId !== event.pointerId || !(event.buttons & 1)) return;
    gesture.range = selectionRange(gesture.order, gesture.id, id);
    setDragIds(gesture.range);
  }

  async function markAll() {
    setMarkingAll(true);
    setError("");
    try {
      const scope = await queryAnalysisIds(applied);
      clearRange();
      setMarked(scope.analysis_ids);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setMarkingAll(false);
    }
  }

  async function saveGroup(event) {
    event.preventDefault();
    if (locked) return;
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    setSavingGroup(true);
    setError("");
    try {
      const group = await onCreateWorkGroup({ ...fields, analysis_ids: groupScope });
      setGroupScope(null);
      setGroupNotice(`Сохранена группа «${group.name}» · записей: ${group.analysis_ids.length}.`);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSavingGroup(false);
    }
  }

  return <section className="project-navigation search-navigation">
    <main>
      <h2>Поиск по проекту</h2>
      <form className="project-search-form" onSubmit={(event) => { event.preventDefault(); if (!locked) apply(fields); }}>
        {Object.entries(SEARCH_FIELDS).map(([key, label]) => <label key={key}>{label}
          <input value={fields[key]} maxLength={300} placeholder={key === "source" ? "Файл, DOI, автор, год…" : undefined} onChange={(event) => setFields({
            ...fields, [key]: event.target.value, ...(key === "source" ? { source_id: "" } : {}),
          })} />
        </label>)}
        <button className="primary-button" disabled={locked}><MagnifyingGlass size={17} /> Найти</button>
      </form>
      <div className="project-search-chips" aria-label="Условия поиска">
        {applied.sample_id && <button type="button" className="outline-button" onClick={() => remove("sample_id")} disabled={locked}>
          Образец: {seed?.sample_label || applied.sample_id} <X size={12} />
        </button>}
        {Object.entries(SEARCH_FIELDS).filter(([key]) => applied[key]).map(([key, label]) =>
          <button type="button" className="outline-button" key={key} onClick={() => remove(key)} disabled={locked}>
            {label}: {applied[key]} <X size={12} />
          </button>)}
      </div>
      {error && <p role="alert">{error}</p>}
      <p role="status">{pending ? "Ищу анализы…" : `Найдено анализов: ${result?.total || 0}. Отмечено: ${marked.length}. В отборе: ${selectionCount}.${markedHidden ? ` Скрыто на графиках из отмеченных: ${markedHidden}.` : ""}`}</p>
      {groupNotice && <p role="status">{groupNotice}</p>}
      {marked.length > 0 && <div className="project-search-chips search-marked-actions" aria-label="Действия с отмеченными анализами">
        <button type="button" className="outline-button" disabled={locked}
          onClick={() => onAddSelection(marked)}>Добавить отмеченные в отбор</button>
        {onPlot && <button type="button" className="primary-button" disabled={locked}
          onClick={() => onPlot(marked)}>Построить диаграммы</button>}
        {onSetVisibility && markedHidden < marked.length && <button type="button" className="outline-button" disabled={locked}
          onClick={() => onSetVisibility(marked, true)}>Скрыть отмеченные на графиках</button>}
        {onSetVisibility && markedHidden > 0 && <button type="button" className="outline-button" disabled={locked}
          onClick={() => onSetVisibility(marked, false)}>Вернуть отмеченные на графики</button>}
        <details className="search-marking search-bulk-menu">
          <summary aria-label="Другие действия с отмеченными">…</summary>
          <div>
            {onCreateWorkGroup && <button type="button" className="outline-button" disabled={locked || Boolean(groupScope)}
              onClick={() => { setGroupScope([...marked]); setGroupNotice(""); setError(""); }}>Сохранить как рабочую группу</button>}
            {groupScope && <form className="search-work-group" aria-label="Новая рабочая группа" onSubmit={saveGroup}>
              <b>Новая рабочая группа · {groupScope.length}</b>
              <label>Название<input name="name" required maxLength={120} autoFocus disabled={savingGroup} /></label>
              <label>Автор<input name="created_by" required disabled={savingGroup} /></label>
              <label>Описание<textarea name="description" maxLength={2000} rows={2} disabled={savingGroup} /></label>
              <div className="analysis-selection-actions">
                <button type="submit" className="primary-button" disabled={locked}>Сохранить группу</button>
                <button type="button" className="outline-button" disabled={savingGroup}
                  onClick={() => { setGroupScope(null); setError(""); }}>Отмена</button>
              </div>
            </form>}
            {generationActions && <GenerationAssignment actions={generationActions} selectedIds={marked} busy={locked} />}
            {onBeginPointLink && <button type="button" className="outline-button" disabled={locked}
              onClick={() => onBeginPointLink(marked)}>Начать массовую привязку</button>}
          </div>
        </details>
      </div>}
      {onUndoVisibility && <button type="button" className="outline-button" disabled={locked} onClick={onUndoVisibility}>
        Отменить изменение видимости
      </button>}
      {!pending && !rows.length && !error && <p>Совпадений нет. Измените условия поиска.</p>}
      {rows.length > 0 && <>
        <details className="search-marking">
          <summary>Отметки</summary>
          <div>
            <button type="button" className="outline-button" disabled={locked}
              onClick={() => { clearRange(); setMarked((current) => [...new Set([...current, ...visibleIds])]); }}>
              Выбрать видимые · {rows.length}
            </button>
            {queryAnalysisIds && <button type="button" className="outline-button" disabled={locked} onClick={markAll}>
              Выбрать весь результат · {result.total}
            </button>}
            {marked.length > 0 && <button type="button" className="outline-button" disabled={locked}
              onClick={() => { clearRange(); setMarked([]); setGroupScope(null); }}>Снять отметки</button>}
          </div>
        </details>
        <div className="project-search-table"><table>
          <thead><tr><th>Отметка</th><th>Анализ</th><th>Образец</th><th>Минерал</th><th>Метод</th><th>Источник</th><th /></tr></thead>
          <tbody>
            {visibleMarkedCount > 0 && <tr className="search-marked-heading"><td colSpan={7}>Отмеченные ({visibleMarkedCount})</td></tr>}
            {rows.map((row, index) => <Fragment key={row.analysis_id}>
              {visibleMarkedCount > 0 && index === visibleMarkedCount &&
                <tr className="search-marked-heading"><td colSpan={7}>Остальные результаты ({rows.length - visibleMarkedCount})</td></tr>}
              <tr className={markedSet.has(row.analysis_id) || dragSet.has(row.analysis_id) ? "marked" : ""}
                onPointerEnter={(event) => extendDrag(event, row.analysis_id)}
                onFocus={() => setFocused(row)} onClick={(event) => {
                  setFocused(row);
                  if (!locked && (event.ctrlKey || event.metaKey || event.shiftKey) && !event.target.closest("input,button,summary")) {
                    toggle(row.analysis_id, event.shiftKey);
                  }
                }}>
                <td><input type="checkbox" aria-label={`Отметить ${row.identity}`} checked={markedSet.has(row.analysis_id)}
                  disabled={locked} onPointerDown={(event) => startDrag(event, row.analysis_id)}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => toggle(row.analysis_id, event.nativeEvent.shiftKey)} /></td>
                <td>{row.identity || "Анализ"}</td><td>{row.sample_name || "—"}</td><td>{row.mineral || "—"}</td>
                <td>{row.method || "—"}</td><td>{row.source_name}</td>
                <td><div className="search-row-actions">
                  <button className="outline-button" type="button" disabled={locked}
                    onClick={() => onOpenAnalysis(row.analysis_id)} aria-label={`Открыть анализ ${row.identity}`}>Открыть</button>
                  <details className="search-marking">
                    <summary aria-label={`Действия для анализа ${row.identity}`}>…</summary>
                    <button className="outline-button" type="button" disabled={locked}
                      onClick={() => onEditAnalysis(row.analysis_id)}>Исправить</button>
                    {row.sample_id && <>
                      <button className="outline-button" type="button" disabled={locked}
                        onClick={() => onOpenSample(row.sample_id)}>Открыть образец</button>
                      <button className="outline-button" type="button" disabled={locked}
                        onClick={() => onBeginPointLink([row.analysis_id])}>Привязать к аналитической точке</button>
                    </>}
                  </details>
                </div></td>
              </tr>
            </Fragment>)}
          </tbody>
        </table></div>
      </>}
      {result?.total > 0 && <div className="project-search-page">
        {(offset > 0 || result.has_more) && <>
          <button type="button" className="outline-button" disabled={locked || offset === 0} onClick={() => changePage(offset - pageSize)}>Назад</button>
          <span>Страница {offset / pageSize + 1}</span>
          <button type="button" className="outline-button" disabled={locked || !result.has_more} onClick={() => changePage(offset + pageSize)}>Далее</button>
        </>}
        <label>Показывать по <select value={pageSize} disabled={locked} onChange={(event) => changePage(0, Number(event.target.value))}>
          {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
        </select></label>
      </div>}
    </main>
    <aside>
      <h3>Источник совпадения</h3>
      {focused ? <>
        <p><Database size={16} /> <b>{focused.source_name}</b></p>
        <p>{focused.sheet_name} · {focused.source_column_number ? `колонка ${focused.source_column_number}` : `строка ${focused.source_row_number}`}</p>
        {focused.sample_name && <p>Образец: {focused.sample_name}</p>}
        {focused.publication_metadata?.length > 0 && <section aria-label="Библиография">
          <h3>Библиография</h3>
          <dl className="search-publication">
            {focused.publication_metadata.map(({ field, value, source_cell, url }) =>
              <div key={`${field}:${source_cell}`} title={`Ячейка ${source_cell}`}>
                <dt>{PUBLICATION_LABELS[field]}</dt>
                <dd>{url ? <a href={url} target="_blank" rel="noreferrer"
                  onClick={(event) => openPublicationLink(event, url)}>{value}</a> : value}</dd>
              </div>)}
          </dl>
        </section>}
        <details><summary>Контрольная сумма источника</summary><p className="project-fingerprint">{focused.source_sha256}</p></details>
        <section aria-label="Действия со связанными объектами">
          <button type="button" className="outline-button" disabled={locked}
            onClick={() => showSource(focused)}>Показать анализы источника</button>
          {onToggleSource && <button type="button" className="outline-button" disabled={locked}
            onClick={() => onToggleSource(focused.source_id)}>
            {hiddenSourceIds.includes(focused.source_id) ? "Вернуть источник на графики" : "Исключить источник из графиков"}
          </button>}
          {focused.sample_id && <button type="button" className="outline-button" disabled={locked}
            onClick={() => onOpenSample(focused.sample_id)}>Открыть образец {focused.sample_name}</button>}
        </section>
      </> : <p>Контекст появится после поиска.</p>}
    </aside>
  </section>;
}
