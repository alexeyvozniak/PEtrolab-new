import { useEffect, useMemo, useState } from "react";
import {
  CaretDown,
  CaretUp,
  CheckSquare,
  Database,
  Funnel,
  MagnifyingGlass,
  Plus,
  SquaresFour,
  X,
} from "@phosphor-icons/react";
import {
  MINERAL_STATUS_LABELS,
  mineralConfidenceLabel,
  mineralReasonLabel,
  mineralStatus,
  reportedMineral,
} from "./mineralUi";
import "./analysesWorkspace.css";

function originLabel(analysis) {
  return analysis.source_orientation === "columns_are_analyses"
    ? `Колонка ${analysis.source_column_number ?? "?"}`
    : `Строка ${analysis.source_row_number ?? "?"}`;
}

function uniqueFields(analyses, key) {
  const fields = new Set();
  analyses.forEach((analysis) => Object.keys(analysis[key] || {}).forEach((field) => fields.add(field)));
  return [...fields];
}

function columnId(kind, field) {
  return `${kind}:${field}`;
}

function confidenceLabel(value) {
  return mineralConfidenceLabel(value);
}

function mineralLabel(analysis) {
  const verification = analysis.mineral_verification;
  return verification?.accepted?.target || verification?.prediction || reportedMineral(analysis) || "Не определён";
}

function valueFor(analysis, column) {
  if (column.kind === "source") return analysis.source_name || "";
  if (column.kind === "sheet") return analysis.sheet_name || "";
  if (column.kind === "origin") return originLabel(analysis);
  if (column.kind === "mineral") return mineralLabel(analysis);
  if (column.kind === "mineral-status") return MINERAL_STATUS_LABELS[mineralStatus(analysis)] || mineralStatus(analysis);
  if (column.kind === "identity") return analysis.identity?.[column.field] || "";
  if (column.kind === "metadata") return analysis.source_metadata?.[column.field] || "";
  if (column.kind === "measurement") return analysis.measurements?.[column.field]?.raw_token ?? "";
  return "";
}

function mainIdentity(analysis) {
  const identity = analysis?.identity || {};
  return identity.Analysis || identity.Point || identity.Sample || Object.values(identity).find(Boolean) || "Analysis без имени";
}

function measurementContext(measurement) {
  return measurement.method || measurement.measurement_set || "";
}

function numericMeasurementValue(measurement) {
  if (!measurement || (measurement.value_status && measurement.value_status !== "numeric")) return null;
  const value = Number(String(measurement.raw_token ?? "").replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

function AnalysisCompositionSummary({ measurements }) {
  const numeric = measurements.map(numericMeasurementValue).filter((value) => value !== null);
  const wtPercent = measurements
    .map((measurement) => ({ measurement, value: numericMeasurementValue(measurement) }))
    .filter(({ measurement, value }) => measurement.unit === "wt.%" && value !== null);
  const reportedTotal = wtPercent.reduce((total, item) => total + item.value, 0);
  const nonNumeric = Math.max(0, measurements.length - numeric.length);
  return (
    <section className="analysis-composition-summary">
      <div className="analysis-detail-section-head"><h3>Сводка состава</h3><span>{measurements.length}</span></div>
      <div className="analysis-composition-grid">
        <div><b>{numeric.length}</b><small>числовых</small></div>
        <div><b>{wtPercent.length}</b><small>wt.%</small></div>
        <div><b>{nonNumeric}</b><small>нечисловых</small></div>
      </div>
      {wtPercent.length > 0 && <p>Сумма сообщённых wt.%: <b>{reportedTotal.toFixed(2)}</b>. Справочно, без нормализации исходных значений.</p>}
    </section>
  );
}

function EmptyAnalyses({ onAddData }) {
  return (
    <div className="analyses-empty">
      <Database size={48} weight="duotone" />
      <h2>В проекте пока нет анализов</h2>
      <p>Импортируй первую таблицу — здесь появятся составы, исходные подписи и точные координаты каждой ячейки.</p>
      <button className="primary-button" type="button" onClick={onAddData}><Plus size={18} /> Добавить данные</button>
    </div>
  );
}

function AnalysisMineralReview({ analysis }) {
  const verification = analysis?.mineral_verification;
  const reported = reportedMineral(analysis);
  if (!verification) {
    return <section className="analysis-mineral-review">
      <div className="analysis-detail-section-head"><h3>Идентификация минерала</h3><span>не запускалась</span></div>
      <p>Для этой записи сохранено исходное название, но химическая проверка ещё не выполнялась.</p>
      {reported && <dl className="analysis-mineral-facts"><div><dt>В источнике</dt><dd>{reported}</dd></div></dl>}
    </section>;
  }
  const status = MINERAL_STATUS_LABELS[verification.status] || verification.status;
  const evidence = verification.reasons?.length ? verification.reasons : (verification.issues || []);
  return <section className="analysis-mineral-review">
    <div className="analysis-detail-section-head"><h3>Идентификация минерала</h3><span>{status}</span></div>
    <dl className="analysis-mineral-facts">
      <div><dt>В источнике</dt><dd>{reported || "Не указан"}</dd></div>
      <div><dt>Предложение</dt><dd>{verification.prediction || "Не определено"} · {confidenceLabel(verification.confidence)}</dd></div>
      <div><dt>Принято</dt><dd>{verification.accepted?.target || "Не принято"}</dd></div>
    </dl>
    {(verification.candidates || []).length > 0 && <div className="analysis-mineral-candidates">
      <b>Кандидаты</b>
      {verification.candidates.slice(0, 5).map((candidate) => <div key={candidate.target}><span>{candidate.target}</span><small>{candidate.score} баллов</small></div>)}
    </div>}
    {evidence.length > 0 && <details>
      <summary>Почему так</summary>
      {evidence.map((reason) => <p key={reason}>{mineralReasonLabel(reason)}</p>)}
    </details>}
    <small className="analysis-mineral-version">Правила: {verification.ruleset_version || "—"}</small>
  </section>;
}

function AnalysisDetail({ analysis }) {
  if (!analysis) {
    return <aside className="analysis-detail empty"><SquaresFour size={24} /><span>Выбери строку, чтобы увидеть все поля и происхождение значений.</span></aside>;
  }
  const identities = Object.entries(analysis.identity || {});
  const metadata = analysis.source_metadata_list?.length
    ? analysis.source_metadata_list.map((item) => [item.field, item.raw_token, item.source_cell])
    : Object.entries(analysis.source_metadata || {}).map(([field, value]) => [field, value, ""]);
  const measurements = analysis.measurement_list || Object.entries(analysis.measurements || {}).map(([field, item]) => ({ field, ...item }));
  return (
    <aside className="analysis-detail" aria-label="Подробности анализа">
      <div className="analysis-detail-head">
        <span>Выбранный анализ</span>
        <h2>{mainIdentity(analysis)}</h2>
        <p>{analysis.source_name} · {analysis.sheet_name} · {originLabel(analysis)}</p>
      </div>

      <section>
        <h3>Идентичность</h3>
        <dl className="analysis-detail-list">
          {identities.map(([field, value]) => <div key={field}><dt>{field}</dt><dd>{value || "—"}</dd></div>)}
        </dl>
      </section>

      <AnalysisMineralReview analysis={analysis} />

      {metadata.length > 0 && (
        <section>
          <h3>Исходные сведения</h3>
          <dl className="analysis-detail-list">
            {metadata.map(([field, value, cell], index) => (
              <div key={`${field}-${cell}-${index}`}><dt>{field}{cell ? <small>{cell}</small> : null}</dt><dd>{value ?? "—"}</dd></div>
            ))}
          </dl>
        </section>
      )}

      <AnalysisCompositionSummary measurements={measurements} />

      <section className="analysis-measurements-section">
        <div className="analysis-detail-section-head"><h3>Все измерения</h3><span>{measurements.length}</span></div>
        <div className="analysis-measurement-list">
          {measurements.map((measurement, index) => (
            <div className="analysis-measurement" key={`${measurement.field}-${measurement.source_cell}-${index}`}>
              <div><b>{measurement.field}</b><small>{measurement.source_header || "Без исходного заголовка"}{measurement.source_cell ? ` · ${measurement.source_cell}` : ""}</small></div>
              <div><b>{measurement.raw_token ?? "∅"}</b><small>{measurement.unit}{measurementContext(measurement) ? ` · ${measurementContext(measurement)}` : ""}</small></div>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}

export function AnalysesWorkspace({ project, busy, onRefresh, onRetract, onAddData, onLoadMore }) {
  const analyses = project.analyses || [];
  const mineralStatusCounts = project.mineral_status_counts || {};
  const mineralReviewedCount = Object.values(mineralStatusCounts).reduce((total, count) => total + Number(count || 0), 0);
  const mineralAttentionCount = Object.entries(mineralStatusCounts)
    .filter(([status]) => !["consistent", "verified"].includes(status))
    .reduce((total, [, count]) => total + Number(count || 0), 0);
  const identityFields = useMemo(() => uniqueFields(analyses, "identity"), [analyses]);
  const metadataFields = useMemo(() => uniqueFields(analyses, "source_metadata"), [analyses]);
  const measurementFields = useMemo(() => uniqueFields(analyses, "measurements"), [analyses]);
  const availableColumns = useMemo(() => [
    { id: "source", kind: "source", label: "Источник" },
    { id: "sheet", kind: "sheet", label: "Лист" },
    { id: "origin", kind: "origin", label: "В файле" },
    { id: "mineral", kind: "mineral", label: "Минерал" },
    { id: "mineral-status", kind: "mineral-status", label: "Проверка минерала" },
    ...identityFields.map((field) => ({ id: columnId("identity", field), kind: "identity", field, label: field })),
    ...metadataFields.map((field) => ({ id: columnId("metadata", field), kind: "metadata", field, label: `${field} · исходное` })),
    ...measurementFields.map((field) => ({ id: columnId("measurement", field), kind: "measurement", field, label: field })),
  ], [identityFields, metadataFields, measurementFields]);
  const defaultColumns = useMemo(() => new Set([
    "source",
    "sheet",
    "origin",
    "mineral",
    "mineral-status",
    ...identityFields.map((field) => columnId("identity", field)),
    ...metadataFields.slice(0, 2).map((field) => columnId("metadata", field)),
    ...measurementFields.slice(0, 8).map((field) => columnId("measurement", field)),
  ]), [identityFields, metadataFields, measurementFields]);

  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sheetFilter, setSheetFilter] = useState("all");
  const [mineralStatusFilter, setMineralStatusFilter] = useState("all");
  const [columnFilters, setColumnFilters] = useState({});
  const [visibleColumnIds, setVisibleColumnIds] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [focusedId, setFocusedId] = useState("");
  const [sort, setSort] = useState({ id: "source", direction: "asc" });

  useEffect(() => {
    setVisibleColumnIds((current) => {
      const available = new Set(availableColumns.map((column) => column.id));
      const retained = current.filter((id) => available.has(id));
      return retained.length ? retained : [...defaultColumns];
    });
  }, [availableColumns, defaultColumns]);

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => analyses.some((analysis) => analysis.analysis_id === id)));
    if (focusedId && !analyses.some((analysis) => analysis.analysis_id === focusedId)) setFocusedId("");
  }, [analyses, focusedId]);

  const sources = useMemo(() => {
    const counts = new Map();
    analyses.forEach((analysis) => counts.set(analysis.source_name, (counts.get(analysis.source_name) || 0) + 1));
    return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right, "ru"));
  }, [analyses]);
  const sheets = useMemo(() => [...new Set(analyses.filter((analysis) => sourceFilter === "all" || analysis.source_name === sourceFilter).map((analysis) => analysis.sheet_name))].sort((a, b) => a.localeCompare(b, "ru")), [analyses, sourceFilter]);
  const visibleColumns = availableColumns.filter((column) => visibleColumnIds.includes(column.id));
  const mineralStatuses = useMemo(() => [...new Set(analyses.map(mineralStatus))].sort(), [analyses]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return analyses.filter((analysis) => {
      if (sourceFilter !== "all" && analysis.source_name !== sourceFilter) return false;
      if (sheetFilter !== "all" && analysis.sheet_name !== sheetFilter) return false;
      if (mineralStatusFilter !== "all" && mineralStatus(analysis) !== mineralStatusFilter) return false;
      if (needle && !JSON.stringify(analysis).toLowerCase().includes(needle)) return false;
      return availableColumns.every((column) => {
        const filter = (columnFilters[column.id] || "").trim().toLowerCase();
        return !filter || String(valueFor(analysis, column)).toLowerCase().includes(filter);
      });
    });
  }, [analyses, availableColumns, columnFilters, mineralStatusFilter, query, sheetFilter, sourceFilter]);

  const ordered = useMemo(() => {
    const selected = new Set(selectedIds);
    const column = availableColumns.find((item) => item.id === sort.id) || availableColumns[0];
    return [...filtered].sort((left, right) => {
      const selectedDifference = Number(selected.has(right.analysis_id)) - Number(selected.has(left.analysis_id));
      if (selectedDifference) return selectedDifference;
      const comparison = column
        ? String(valueFor(left, column)).localeCompare(String(valueFor(right, column)), "ru", { numeric: true })
        : 0;
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [availableColumns, filtered, selectedIds, sort]);

  const focused = analyses.find((analysis) => analysis.analysis_id === focusedId) || ordered[0] || null;
  const filteredIds = ordered.map((analysis) => analysis.analysis_id);
  const allVisibleSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedIds.includes(id));

  const toggleSelection = (id) => {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };
  const toggleAllVisible = () => {
    setSelectedIds((current) => {
      if (allVisibleSelected) return current.filter((id) => !filteredIds.includes(id));
      return [...new Set([...current, ...filteredIds])];
    });
  };
  const changeSort = (id) => setSort((current) => ({ id, direction: current.id === id && current.direction === "asc" ? "desc" : "asc" }));
  const toggleColumn = (id) => setVisibleColumnIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  if (project.total === 0) return <EmptyAnalyses onAddData={onAddData} />;

  return (
    <div className="analyses-workspace">
      <aside className="analyses-sources">
        <div className="analyses-pane-title"><span>Источники</span><b>{project.source_count}</b></div>
        <button className={`analysis-source-row${sourceFilter === "all" ? " active" : ""}`} type="button" onClick={() => { setSourceFilter("all"); setSheetFilter("all"); }}><span>Все источники</span><b>{analyses.length}</b></button>
        {sources.map(([source, count]) => (
          <button className={`analysis-source-row${sourceFilter === source ? " active" : ""}`} type="button" key={source} onClick={() => { setSourceFilter(source); setSheetFilter("all"); }} title={source}><span>{source}</span><b>{count}</b></button>
        ))}
        <div className="analyses-filter-block">
          <label htmlFor="analysis-sheet-filter">Лист</label>
          <select id="analysis-sheet-filter" value={sheetFilter} onChange={(event) => setSheetFilter(event.target.value)}>
            <option value="all">Все листы</option>
            {sheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}
          </select>
        </div>
        <div className="analyses-source-note"><Funnel size={16} /><span>Поиск работает по всем полям, даже если колонка сейчас скрыта.</span></div>
      </aside>

      <main className="analyses-table-pane">
        <div className="analyses-toolbar">
          <div className="analysis-search"><MagnifyingGlass size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Sample, Mineral, Generation, значение…" aria-label="Поиск анализов" /></div>
          <span className="analyses-result-count">{ordered.length} из {project.total}</span>
          <span className={`analysis-mineral-health ${mineralReviewedCount === 0 || mineralAttentionCount ? "attention" : "ok"}`} title={`Проверено для ${mineralReviewedCount} загруженных анализов`}>
            {mineralReviewedCount === 0
              ? "Проверка минералов ожидает данных"
              : mineralAttentionCount
                ? `${mineralAttentionCount} требуют проверки`
                : "Все загруженные минералы проверены"}
          </span>
          <label className="analysis-status-filter">Минерал
            <select value={mineralStatusFilter} onChange={(event) => setMineralStatusFilter(event.target.value)} aria-label="Статус идентификации минерала">
              <option value="all">Все статусы</option>
              {mineralStatuses.map((status) => <option key={status} value={status}>{MINERAL_STATUS_LABELS[status] || status}</option>)}
            </select>
          </label>
          <details className="analysis-columns-menu">
            <summary><SquaresFour size={17} /> Колонки <span>{visibleColumns.length}</span></summary>
            <div>
              <p>Показывать в таблице</p>
              {availableColumns.map((column) => <label key={column.id}><input type="checkbox" checked={visibleColumnIds.includes(column.id)} onChange={() => toggleColumn(column.id)} /> {column.label}</label>)}
            </div>
          </details>
          <button className="outline-button" type="button" onClick={onRefresh} disabled={busy}>Обновить</button>
        </div>

        <div className="analyses-table-scroll">
          <table className="analyses-data-table">
            <thead>
              <tr>
                <th className="analysis-select-cell"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} aria-label="Выбрать показанные анализы" /></th>
                {visibleColumns.map((column) => (
                  <th key={column.id}><button type="button" onClick={() => changeSort(column.id)}>{column.label}{sort.id === column.id ? (sort.direction === "asc" ? <CaretUp size={12} /> : <CaretDown size={12} />) : null}</button></th>
                ))}
              </tr>
              <tr className="analysis-filter-row">
                <th />
                {visibleColumns.map((column) => <th key={column.id}><input value={columnFilters[column.id] || ""} onChange={(event) => setColumnFilters((current) => ({ ...current, [column.id]: event.target.value }))} placeholder="Фильтр" aria-label={`Фильтр ${column.label}`} /></th>)}
              </tr>
            </thead>
            <tbody>
              {ordered.map((analysis) => {
                const selected = selectedIds.includes(analysis.analysis_id);
                const focusedRow = focused?.analysis_id === analysis.analysis_id;
                return (
                  <tr className={`${selected ? "selected " : ""}${focusedRow ? "focused" : ""}`} key={analysis.analysis_id} onClick={() => setFocusedId(analysis.analysis_id)}>
                    <td className="analysis-select-cell"><input type="checkbox" checked={selected} onChange={() => toggleSelection(analysis.analysis_id)} onClick={(event) => event.stopPropagation()} aria-label={`Выбрать ${mainIdentity(analysis)}`} /></td>
                    {visibleColumns.map((column) => {
                      const measurement = column.kind === "measurement" ? analysis.measurements?.[column.field] : null;
                      return (
                        <td key={column.id} title={String(valueFor(analysis, column))}>
                          <span>{valueFor(analysis, column)}</span>
                          {measurement ? <small>{measurement.unit}{measurementContext(measurement) ? ` · ${measurementContext(measurement)}` : ""}</small> : null}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {ordered.length === 0 && <div className="analyses-no-results"><MagnifyingGlass size={25} /><b>Ничего не найдено</b><span>Сбрось поиск или фильтры колонок.</span></div>}
        </div>

        {project.has_more && <button className="analyses-load-more" type="button" onClick={onLoadMore} disabled={busy}>Загрузить ещё анализы</button>}
      </main>

      <AnalysisDetail analysis={focused} />

      {selectedIds.length > 0 && (
        <div className="analysis-selection-tray">
          <div><CheckSquare size={20} weight="fill" /><b>{selectedIds.length} выбрано</b><span>Выбранные строки закреплены сверху.</span></div>
          <div className="analysis-selection-chips">
            {selectedIds.slice(0, 5).map((id) => {
              const analysis = analyses.find((item) => item.analysis_id === id);
              return <button type="button" key={id} onClick={() => toggleSelection(id)}>{mainIdentity(analysis)} <X size={13} /></button>;
            })}
            {selectedIds.length > 5 && <span>+{selectedIds.length - 5}</span>}
          </div>
          <button className="outline-button" type="button" onClick={() => setSelectedIds([])}>Очистить выбор</button>
        </div>
      )}

      {project.latest_import && <button className="analysis-retract-link" type="button" onClick={onRetract} disabled={busy}>Отменить последний импорт</button>}
    </div>
  );
}
