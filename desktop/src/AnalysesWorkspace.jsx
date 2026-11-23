import { useEffect, useMemo, useRef, useState } from "react";
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
import "./analysesWorkspace.css";
import { EditDraftPanel } from "./EditDraftPanel";
import { GenerationAssignment } from "./GenerationAssignment";

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

const MINERAL_STATUS_LABELS = {
  consistent: "совпадает",
  verified: "принято",
  stale: "нужно перепроверить",
  conflict: "конфликт",
  missing_reported: "нет названия",
  low_confidence: "неоднозначно",
  insufficient_input: "мало данных",
  unrecognized_reported: "нужно проверить",
  not_checked: "не проверен",
  reported_only: "только исходное название",
};

const MINERAL_CONFIDENCE_LABELS = {
  high: "высокая",
  medium: "средняя",
  ambiguous: "неоднозначная",
  unresolved: "не определена",
  insufficient_input: "недостаточно данных",
};

function confidenceLabel(value) {
  return MINERAL_CONFIDENCE_LABELS[value] || value || "—";
}

function reportedMineral(analysis) {
  const value = analysis.reported_mineral;
  if (value && typeof value === "object") return value.value || "";
  return value || analysis.mineral_verification?.reported_mineral || analysis.source_metadata?.Mineral || "";
}

function mineralLabel(analysis) {
  const verification = analysis.mineral_verification;
  return verification?.accepted?.target || verification?.prediction || reportedMineral(analysis) || "Не определён";
}

function mineralStatus(analysis) {
  return analysis.mineral_verification?.status || (reportedMineral(analysis) ? "reported_only" : "not_checked");
}

function valueFor(analysis, column) {
  if (column.kind === "source") return analysis.source_name || "";
  if (column.kind === "sheet") return analysis.sheet_name || "";
  if (column.kind === "origin") return originLabel(analysis);
  if (column.kind === "mineral") return mineralLabel(analysis);
  if (column.kind === "generation") return analysis.generation?.name || "";
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

function selectionRange(order, start, end) {
  const first = order.indexOf(start);
  const last = order.indexOf(end);
  return first < 0 || last < 0 ? [] : order.slice(Math.min(first, last), Math.max(first, last) + 1);
}

const FILTER_NUMBER = "[+-]?(?:\\d+(?:[.,]\\d+)?|[.,]\\d+)(?:e[+-]?\\d+)?";
const MEASUREMENT_FILTER = new RegExp(`^(>=|<=|>|<|=)?\\s*(${FILTER_NUMBER})(?:\\s*\\.\\.\\s*(${FILTER_NUMBER}))?(?:\\s+(.+))?$`, "i");

function measurementFilter(expression, units) {
  if (expression.toLowerCase() === "пусто") {
    return (measurement) => !String(measurement?.raw_token ?? "").trim();
  }
  if (expression.toLowerCase() === "ниже предела") {
    return (measurement) => measurement?.qualifier === "below_detection_limit";
  }
  const match = expression.match(MEASUREMENT_FILTER);
  if (!match) return null;
  const [, operator, firstToken, secondToken, unit] = match;
  const first = Number(firstToken.replace(",", "."));
  const second = secondToken === undefined ? null : Number(secondToken.replace(",", "."));
  const underflow = (token, number) => number === 0 && /[1-9]/.test(token.split(/e/i)[0]);
  if (!Number.isFinite(first) || (second !== null && (!Number.isFinite(second) || second < first || operator))
      || underflow(firstToken, first) || (second !== null && underflow(secondToken, second))
      || (units.length > 1 && !unit) || (unit && !units.includes(unit))) return null;
  return (measurement) => {
    const value = measurement?.numeric_value;
    if (!Number.isFinite(value) || (unit && measurement.unit !== unit)) return false;
    if (second !== null) return value >= first && value <= second;
    if (operator === ">") return value > first;
    if (operator === ">=") return value >= first;
    if (operator === "<") return value < first;
    if (operator === "<=") return value <= first;
    return value === first;
  };
}

function AnalysisCompositionSummary({ summary }) {
  if (!summary) return null;
  return (
    <section className="analysis-composition-summary">
      <div className="analysis-detail-section-head"><h3>Сводка состава</h3><span>{summary.measurement_count}</span></div>
      <div className="analysis-composition-grid">
        <div><b>{summary.numeric_count}</b><small>числовых</small></div>
        <div><b>{summary.weight_percent_count}</b><small>wt.%</small></div>
        <div><b>{summary.non_numeric_count}</b><small>нечисловых</small></div>
      </div>
      {summary.weight_percent_count > 0 && summary.reported_weight_percent_total !== null && <p>Сумма сообщённых wt.%: <b>{summary.reported_weight_percent_total.toFixed(2)}</b>. Справочно, без нормализации исходных значений.</p>}
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
      {verification.previous_acceptance && <div><dt>Ранее принято</dt><dd>{verification.previous_acceptance.target}
        {` · правила ${verification.previous_acceptance.ruleset_version}`}</dd></div>}
    </dl>
    {(verification.candidates || []).length > 0 && <div className="analysis-mineral-candidates">
      <b>Кандидаты</b>
      {verification.candidates.slice(0, 5).map((candidate) => <div key={candidate.target}><span>{candidate.target}</span><small>{candidate.score}</small></div>)}
    </div>}
    {evidence.length > 0 && <details>
      <summary>Почему так</summary>
      {evidence.map((reason) => <p key={reason}>{reason}</p>)}
    </details>}
    <small className="analysis-mineral-version">Правила: {verification.ruleset_version || "—"}</small>
  </section>;
}

function AnalysisDetail({ analysis, editDraftActions, hiddenPlotAnalysisIds, onSetPlotVisibility, busy }) {
  if (!analysis) {
    return <aside className="analysis-detail empty"><SquaresFour size={24} /><span>Выбери строку, чтобы увидеть все поля и происхождение значений.</span></aside>;
  }
  const identities = Object.entries(analysis.identity || {});
  const hiddenOnPlots = hiddenPlotAnalysisIds.includes(analysis.analysis_id);
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
        {onSetPlotVisibility && <button className="outline-button" type="button" disabled={busy}
          onClick={() => onSetPlotVisibility([analysis.analysis_id], !hiddenOnPlots)}>
          {hiddenOnPlots ? "Вернуть этот анализ на графики" : "Скрыть этот анализ на графиках"}
        </button>}
      </div>

      <section>
        <h3>Идентичность</h3>
        <dl className="analysis-detail-list">
          {identities.map(([field, value]) => <div key={field}><dt>{field}</dt><dd>{value || "—"}</dd></div>)}
          {analysis.sample_association?.assignment && <div><dt>Физический образец</dt><dd title={analysis.sample_association.sample_id}>{analysis.sample_association.assignment.sample_name}</dd></div>}
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

      <AnalysisCompositionSummary summary={analysis.composition_summary} />
      {editDraftActions && <EditDraftPanel key={analysis.analysis_id} analysisId={analysis.analysis_id}
        measurements={measurements} actions={editDraftActions} />}

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

export function AnalysesWorkspace({ project, initialFocusedId, selectedIds, setSelectedIds, onListWorkGroups, onCreateWorkGroup, generationActions, onExportSelection, onPublishSelection, onOpenPlots, onListTableViews, onSaveTableView, editDraftActions, hiddenPlotAnalysisIds = [], onSetPlotVisibility, busy, onRefresh, onRetract, onAddData, onLoadMore }) {
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
    { id: "generation", kind: "generation", label: "Generation" },
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
    "generation",
    "mineral-status",
    ...identityFields.map((field) => columnId("identity", field)),
    ...metadataFields.slice(0, 2).map((field) => columnId("metadata", field)),
    ...measurementFields.slice(0, 8).map((field) => columnId("measurement", field)),
  ]), [identityFields, metadataFields, measurementFields]);

  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sheetFilter, setSheetFilter] = useState("all");
  const [mineralStatusFilter, setMineralStatusFilter] = useState([]);
  const [statusQuery, setStatusQuery] = useState("");
  const [sampleLinkFilter, setSampleLinkFilter] = useState("all");
  const [columnFilters, setColumnFilters] = useState({});
  const [visibleColumnIds, setVisibleColumnIds] = useState([]);
  const [dragIds, setDragIds] = useState([]);
  const [workGroups, setWorkGroups] = useState(null);
  const [groupForm, setGroupForm] = useState(false);
  const [groupBusy, setGroupBusy] = useState(false);
  const [groupError, setGroupError] = useState("");
  const [groupNotice, setGroupNotice] = useState("");
  const [tableViews, setTableViews] = useState([]);
  const [viewBusy, setViewBusy] = useState(false);
  const [viewMessage, setViewMessage] = useState(null);
  const selectionAnchor = useRef(null);
  const selectionDrag = useRef(null);
  const [focusedId, setFocusedId] = useState(initialFocusedId || "");
  const [sort, setSort] = useState({ id: "source", direction: "asc" });

  useEffect(() => {
    const finish = (event) => {
      const drag = selectionDrag.current;
      if (!drag || (event.type !== "blur" && event.pointerId !== drag.pointerId)) return;
      selectionDrag.current = null;
      setDragIds([]);
      if (event.type === "pointerup" && drag.range.length > 1) {
        selectionAnchor.current = drag;
        setSelectedIds([...new Set([...drag.base, ...drag.range])]);
      }
    };
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    window.addEventListener("blur", finish);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      window.removeEventListener("blur", finish);
    };
  }, []);

  useEffect(() => {
    setVisibleColumnIds((current) => {
      const available = new Set(availableColumns.map((column) => column.id));
      const retained = current.filter((id) => available.has(id));
      return retained.length ? retained : [...defaultColumns];
    });
  }, [availableColumns, defaultColumns]);

  useEffect(() => {
    if (!project.has_more) {
      const available = new Set(analyses.map((analysis) => analysis.analysis_id));
      setSelectedIds((current) => current.every((id) => available.has(id)) ? current : current.filter((id) => available.has(id)));
    }
    if (focusedId && !analyses.some((analysis) => analysis.analysis_id === focusedId)) setFocusedId("");
  }, [analyses, focusedId, project.has_more, setSelectedIds]);

  const sources = useMemo(() => {
    const counts = new Map();
    analyses.forEach((analysis) => {
      const source = counts.get(analysis.source_id) || { id: analysis.source_id, name: analysis.source_name, count: 0 };
      source.count += 1;
      counts.set(analysis.source_id, source);
    });
    const entries = [...counts.values()];
    return entries.map((source) => ({ ...source, label: entries.some((other) => other.id !== source.id && other.name === source.name) ? `${source.name} · ${source.id}` : source.name }))
      .sort((left, right) => left.label.localeCompare(right.label, "ru"));
  }, [analyses]);
  const sheets = useMemo(() => [...new Set(analyses.filter((analysis) => sourceFilter === "all" || analysis.source_id === sourceFilter).map((analysis) => analysis.sheet_name))].sort((a, b) => a.localeCompare(b, "ru")), [analyses, sourceFilter]);
  const visibleColumns = availableColumns.filter((column) => visibleColumnIds.includes(column.id));
  const mineralStatuses = useMemo(() => [...new Set(analyses.map(mineralStatus))].sort(), [analyses]);
  const toggleMineralStatus = (status) => setMineralStatusFilter((current) =>
    current.includes(status) ? current.filter((item) => item !== status) : [...current, status]);

  const measurementUnits = useMemo(() => {
    const fields = new Map();
    for (const analysis of analyses) {
      for (const [field, measurement] of Object.entries(analysis.measurements || {})) {
        if (!fields.has(field)) fields.set(field, new Set());
        fields.get(field).add(measurement.unit);
      }
    }
    return new Map([...fields].map(([field, units]) => [field, [...units]]));
  }, [analyses]);
  const activeColumnFilters = useMemo(() => availableColumns.flatMap((column) => {
    const expression = (columnFilters[column.id] || "").trim();
    if (!expression) return [];
    const testMeasurement = column.kind === "measurement" ? measurementFilter(expression, measurementUnits.get(column.field) || []) : null;
    return [{ column, expression, testMeasurement, invalid: column.kind === "measurement" && !testMeasurement }];
  }), [availableColumns, columnFilters, measurementUnits]);
  const invalidFilters = new Set(activeColumnFilters.filter((condition) => condition.invalid).map(({ column }) => column.id));

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return analyses.filter((analysis) => {
      if (sourceFilter !== "all" && analysis.source_id !== sourceFilter) return false;
      if (sheetFilter !== "all" && analysis.sheet_name !== sheetFilter) return false;
      if (mineralStatusFilter.length && !mineralStatusFilter.includes(mineralStatus(analysis))) return false;
      if (sampleLinkFilter !== "all" && Boolean(analysis.sample_association?.sample_id) !== (sampleLinkFilter === "linked")) return false;
      if (needle && !JSON.stringify(analysis).toLowerCase().includes(needle)) return false;
      return activeColumnFilters.every(({ column, expression, testMeasurement, invalid }) =>
        invalid || (testMeasurement
          ? testMeasurement(analysis.measurements?.[column.field])
          : String(valueFor(analysis, column)).toLowerCase().includes(expression.toLowerCase())));
    });
  }, [analyses, activeColumnFilters, mineralStatusFilter, sampleLinkFilter, query, sheetFilter, sourceFilter]);

  const ordered = useMemo(() => {
    const selected = new Set(selectedIds);
    const column = availableColumns.find((item) => item.id === sort.id) || availableColumns[0];
    return [...filtered].sort((left, right) => {
      const selectedDifference = Number(selected.has(right.analysis_id)) - Number(selected.has(left.analysis_id));
      if (selectedDifference) return selectedDifference;
      if (column?.kind === "measurement") {
        const leftMeasurement = left.measurements?.[column.field];
        const rightMeasurement = right.measurements?.[column.field];
        const leftNumeric = Number.isFinite(leftMeasurement?.numeric_value);
        const rightNumeric = Number.isFinite(rightMeasurement?.numeric_value);
        if (leftNumeric !== rightNumeric) return Number(rightNumeric) - Number(leftNumeric);
        if (leftNumeric) {
          const unitOrder = leftMeasurement.unit.localeCompare(rightMeasurement.unit);
          if (unitOrder) return unitOrder;
          const comparison = leftMeasurement.numeric_value - rightMeasurement.numeric_value;
          return sort.direction === "asc" ? comparison : -comparison;
        }
      }
      const comparison = column
        ? String(valueFor(left, column)).localeCompare(String(valueFor(right, column)), "ru", { numeric: true })
        : 0;
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [availableColumns, filtered, selectedIds, sort]);

  const focused = analyses.find((analysis) => analysis.analysis_id === focusedId) || ordered[0] || null;
  const filteredIds = ordered.map((analysis) => analysis.analysis_id);
  const hiddenSelectionCount = selectedIds.filter((id) => !filteredIds.includes(id)).length;
  const allVisibleSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedIds.includes(id));

  const toggleSelection = (id, extend = false) => {
    const anchor = selectionAnchor.current;
    if (extend && anchor?.filtered === filtered && anchor.sort === sort) {
      const range = selectionRange(anchor.order, anchor.id, id);
      if (range.length) {
        setSelectedIds([...new Set([...anchor.base, ...range])]);
        return;
      }
    }
    const checked = selectedIds.includes(id);
    selectionAnchor.current = checked ? null : { id, order: filteredIds, base: selectedIds, filtered, sort };
    setSelectedIds(checked ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]);
  };
  const startSelectionDrag = (event, id) => {
    if (event.button !== 0 || event.pointerType === "touch" || event.shiftKey || event.ctrlKey || event.metaKey) return;
    selectionDrag.current = { id, order: filteredIds, base: selectedIds, filtered, sort, range: [], pointerId: event.pointerId };
  };
  const extendSelectionDrag = (event, id) => {
    const drag = selectionDrag.current;
    if (!drag || event.pointerId !== drag.pointerId || !(event.buttons & 1)) return;
    drag.range = selectionRange(drag.order, drag.id, id);
    setDragIds(drag.range);
  };
  const toggleAllVisible = () => {
    selectionAnchor.current = null;
    setSelectedIds((current) => {
      if (allVisibleSelected) return current.filter((id) => !filteredIds.includes(id));
      return [...new Set([...current, ...filteredIds])];
    });
  };
  const changeSort = (id) => setSort((current) => ({ id, direction: current.id === id && current.direction === "asc" ? "desc" : "asc" }));
  const toggleColumn = (id) => setVisibleColumnIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const clearFilters = () => {
    setQuery("");
    setSourceFilter("all");
    setSheetFilter("all");
    setMineralStatusFilter([]);
    setStatusQuery("");
    setSampleLinkFilter("all");
    setColumnFilters({});
  };
  const hasFilters = Boolean(activeColumnFilters.length || mineralStatusFilter.length || query.trim()
    || sourceFilter !== "all" || sheetFilter !== "all" || sampleLinkFilter !== "all");

  const saveView = async (event) => {
    event.preventDefault();
    if (viewBusy || invalidFilters.size) return;
    const name = new FormData(event.currentTarget).get("view_name");
    const rule = (field, operator, value) => ({ id: crypto.randomUUID(), field, operator, value, enabled: true });
    const filters = activeColumnFilters.map(({ column, expression }) =>
      rule(`column:${column.id}`, column.kind === "measurement" ? "measurement_expression" : "contains", expression));
    if (query.trim()) filters.push(rule("query", "contains", query.trim()));
    if (sourceFilter !== "all") filters.push(rule("source", "equals", sourceFilter));
    if (sheetFilter !== "all") filters.push(rule("sheet", "equals", sheetFilter));
    if (sampleLinkFilter !== "all") filters.push(rule("sample-link", "equals", sampleLinkFilter));
    if (mineralStatusFilter.length) filters.push(rule("mineral-status", "in", mineralStatusFilter));
    const columns = availableColumns.map((column, order) => ({
      field: column.id, order, visible: visibleColumnIds.includes(column.id), width_px: null,
    }));
    setViewBusy(true);
    setViewMessage(null);
    try {
      const saved = await onSaveTableView({
        name, columns, filters,
        sort: [{ field: sort.id, direction: sort.direction === "asc" ? "ascending" : "descending" }],
      });
      setTableViews((current) => [...current, saved]);
      setViewMessage({ text: `Сохранено представление «${saved.name}».` });
    } catch (error) {
      setViewMessage({ error: true, text: error.message });
    } finally {
      setViewBusy(false);
    }
  };

  const loadViews = async (viewId) => {
    if (viewBusy) return;
    setViewBusy(true);
    setViewMessage(null);
    try {
      const result = await onListTableViews();
      setTableViews(result.views);
      if (!viewId) return;
      const view = result.views.find((item) => item.id === viewId);
      if (!view || view.data_universe_fingerprint !== result.data_universe_fingerprint) {
        throw new Error("Набор анализов изменился. Сохранённое представление оставлено без изменений.");
      }
      const available = new Set(availableColumns.map((column) => column.id));
      const required = [
        ...view.columns.filter((column) => column.visible).map((column) => column.field),
        view.sort[0].field,
        ...view.filters.filter((condition) => condition.field.startsWith("column:")).map((condition) => condition.field.slice(7)),
      ];
      if (required.some((field) => !available.has(field))) {
        throw new Error(project.has_more ? "Загрузите остальные страницы, чтобы открыть представление." : "В таблице отсутствуют поля сохранённого представления.");
      }
      const rules = new Map(view.filters.map(({ field, value }) => [field, value]));
      if (project.has_more && rules.has("source") && !sources.some((source) => source.id === rules.get("source"))) {
        throw new Error("Загрузите страницы с источником сохранённого представления.");
      }
      setQuery(rules.get("query") || "");
      setSourceFilter(rules.get("source") || "all");
      setSheetFilter(rules.get("sheet") || "all");
      setMineralStatusFilter(rules.get("mineral-status") || []);
      setStatusQuery("");
      setSampleLinkFilter(rules.get("sample-link") || "all");
      setColumnFilters(Object.fromEntries(view.filters.filter(({ field }) => field.startsWith("column:"))
        .map(({ field, value }) => [field.slice(7), value])));
      setVisibleColumnIds(view.columns.filter((column) => column.visible).map((column) => column.field));
      setSort({ id: view.sort[0].field, direction: view.sort[0].direction === "ascending" ? "asc" : "desc" });
      setViewMessage({ text: `Открыто представление «${view.name}».` });
    } catch (error) {
      setViewMessage({ error: true, text: error.message });
    } finally {
      setViewBusy(false);
    }
  };

  const loadWorkGroups = async () => {
    if (groupBusy || !onListWorkGroups) return;
    setGroupBusy(true);
    setGroupError("");
    try {
      setWorkGroups((await onListWorkGroups()).groups);
    } catch (error) {
      setGroupError(error.message);
    } finally {
      setGroupBusy(false);
    }
  };
  const saveWorkGroup = async (event) => {
    event.preventDefault();
    if (groupBusy || !selectedIds.length) return;
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    setGroupBusy(true);
    setGroupError("");
    setGroupNotice("");
    try {
      const group = await onCreateWorkGroup({ ...fields, analysis_ids: selectedIds });
      setWorkGroups((current) => [{ group, unavailable_analysis_ids: [] }, ...(current || [])]);
      setGroupForm(false);
      setGroupNotice(`Сохранена группа «${group.name}» · записей: ${group.analysis_ids.length}.`);
    } catch (error) {
      setGroupError(error.message);
    } finally {
      setGroupBusy(false);
    }
  };
  const openWorkGroup = async (groupId) => {
    if (groupBusy) return;
    setGroupBusy(true);
    setGroupError("");
    try {
      const { groups } = await onListWorkGroups();
      setWorkGroups(groups);
      const item = groups.find(({ group }) => group.id === groupId);
      if (!item) throw new Error("Рабочая группа недоступна.");
      const { group, unavailable_analysis_ids } = item;
      const unavailable = new Set(unavailable_analysis_ids);
      selectionAnchor.current = null;
      clearFilters();
      setSelectedIds(group.analysis_ids.filter((id) => !unavailable.has(id)));
      setGroupNotice(`Открыта группа «${group.name}»${unavailable.size ? ` · недоступно: ${unavailable.size}` : ""}.`);
    } catch (error) {
      setGroupError(error.message);
    } finally {
      setGroupBusy(false);
    }
  };

  if (project.total === 0 && !project.has_work_groups && !project.has_table_views) return <EmptyAnalyses onAddData={onAddData} />;

  return (
    <div className="analyses-workspace">
      <aside className="analyses-sources">
        <div className="analyses-pane-title"><span>Источники</span><b>{project.source_count}</b></div>
        <button className={`analysis-source-row${sourceFilter === "all" ? " active" : ""}`} type="button" onClick={() => { setSourceFilter("all"); setSheetFilter("all"); }}><span>Все источники</span><b>{analyses.length}</b></button>
        {sources.map((source) => (
          <button className={`analysis-source-row${sourceFilter === source.id ? " active" : ""}`} type="button" key={source.id} onClick={() => { setSourceFilter(source.id); setSheetFilter("all"); }} title={source.label}><span>{source.label}</span><b>{source.count}</b></button>
        ))}
        <div className="analyses-filter-block">
          <label htmlFor="analysis-sheet-filter">Лист</label>
          <select id="analysis-sheet-filter" value={sheetFilter} onChange={(event) => setSheetFilter(event.target.value)}>
            <option value="all">Все листы</option>
            {sheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}
          </select>
        </div>
        <div className="analyses-filter-block">
          <label htmlFor="analysis-sample-link-filter">Связь с физическим образцом</label>
          <select id="analysis-sample-link-filter" value={sampleLinkFilter} onChange={(event) => setSampleLinkFilter(event.target.value)}>
            <option value="all">Все анализы</option>
            <option value="linked">Связь назначена</option>
            <option value="unlinked">Без связи</option>
          </select>
        </div>
        <details className="analyses-filter-block analysis-category-filter">
          <summary>Статус минерала{mineralStatusFilter.length > 0 && ` · ${mineralStatusFilter.length}`}</summary>
          <div aria-label="Статус идентификации минерала">
            <input type="search" aria-label="Поиск статусов минерала" placeholder="Найти статус" value={statusQuery} onChange={(event) => setStatusQuery(event.target.value)} />
            {mineralStatuses.filter((status) => (MINERAL_STATUS_LABELS[status] || status).toLowerCase().includes(statusQuery.trim().toLowerCase())).map((status) =>
              <label key={status}><input type="checkbox" checked={mineralStatusFilter.includes(status)} onChange={() => toggleMineralStatus(status)} /> {MINERAL_STATUS_LABELS[status] || status}</label>
            )}
          </div>
        </details>
        {onListTableViews && <details className="analyses-filter-block analysis-category-filter analysis-work-groups"
          onToggle={(event) => { if (event.currentTarget.open) loadViews(); }}>
          <summary>Представления таблицы</summary>
          <div>
            {tableViews.map((view) => <button type="button" className="outline-button" key={view.id}
              disabled={busy || viewBusy} onClick={() => loadViews(view.id)}>{view.name}</button>)}
            <form onSubmit={saveView} aria-label="Новое представление таблицы">
              <label>Название представления<input name="view_name" required maxLength={120} /></label>
              <button type="submit" className="outline-button" disabled={busy || viewBusy || invalidFilters.size > 0}>Сохранить представление</button>
            </form>
            {viewMessage && <small role={viewMessage.error ? "alert" : "status"}>{viewMessage.text}</small>}
          </div>
        </details>}
        {onListWorkGroups && <section className="analyses-filter-block analysis-work-groups" aria-label="Рабочие группы">
          <button type="button" className="outline-button" onClick={loadWorkGroups} disabled={busy || groupBusy}>Рабочие группы</button>
          {workGroups?.length === 0 && <small>Рабочих групп пока нет.</small>}
          {workGroups?.map((item) => <button key={item.group.id} type="button" className="outline-button"
            disabled={busy || groupBusy} onClick={() => openWorkGroup(item.group.id)}
            title={item.group.description || item.group.created_by}>
            {item.group.name} · {item.group.analysis_ids.length}
          </button>)}
          {groupForm && <form onSubmit={saveWorkGroup} aria-label="Новая рабочая группа">
            <label>Название<input name="name" required maxLength={120} autoFocus /></label>
            <label>Автор<input name="created_by" required /></label>
            <label>Описание<textarea name="description" maxLength={2000} rows={2} /></label>
            <button type="submit" className="primary-button" disabled={groupBusy || !selectedIds.length}>Сохранить группу</button>
            <button type="button" className="outline-button" disabled={groupBusy} onClick={() => setGroupForm(false)}>Отмена</button>
          </form>}
          {groupError && <small role="alert">{groupError}</small>}
          {groupNotice && <small role="status">{groupNotice}</small>}
        </section>}
        <div className="analyses-source-note"><Funnel size={16} /><span>Поиск работает по всем полям, даже если колонка сейчас скрыта.</span></div>
      </aside>

      <main className="analyses-table-pane">
        <div>
        <div className="analyses-toolbar">
          <div className="analysis-search"><MagnifyingGlass size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Sample, Mineral, Generation, значение…" aria-label="Поиск анализов" /></div>
          <span className="analyses-result-count">{project.has_more ? `${ordered.length} из ${analyses.length} загруженных` : `${ordered.length} из ${project.total}`}</span>
          <span className={`analysis-mineral-health ${mineralReviewedCount === 0 || mineralAttentionCount ? "attention" : "ok"}`} title={`Проверено для ${mineralReviewedCount} загруженных анализов`}>
            {mineralReviewedCount === 0
              ? "Проверка минералов ожидает данных"
              : mineralAttentionCount
                ? `Нужно проверить · ${mineralAttentionCount}`
                : "Все загруженные минералы проверены"}
          </span>
          <details className="analysis-columns-menu">
            <summary><SquaresFour size={17} /> Колонки <span>{visibleColumns.length}</span></summary>
            <div>
              <p>Показывать в таблице</p>
              {availableColumns.map((column) => <label key={column.id}><input type="checkbox" checked={visibleColumnIds.includes(column.id)} onChange={() => toggleColumn(column.id)} /> {column.label}</label>)}
            </div>
          </details>
          <button className="outline-button" type="button" onClick={onRefresh} disabled={busy}>Обновить</button>
        </div>

        {hasFilters && <div className="analysis-filter-chips" aria-label="Активные фильтры">
          {query.trim() && <button type="button" onClick={() => setQuery("")}>Поиск: {query}<X size={12} /></button>}
          {sourceFilter !== "all" && <button type="button" aria-label="Снять фильтр источника" onClick={() => setSourceFilter("all")}>{sources.find((source) => source.id === sourceFilter)?.label}<X size={12} /></button>}
          {sheetFilter !== "all" && <button type="button" onClick={() => setSheetFilter("all")}>Лист: {sheetFilter}<X size={12} /></button>}
          {sampleLinkFilter !== "all" && <button type="button" onClick={() => setSampleLinkFilter("all")}>{sampleLinkFilter === "linked" ? "Связь назначена" : "Без связи"}<X size={12} /></button>}
          {mineralStatusFilter.map((status) => <button type="button" key={status} onClick={() => toggleMineralStatus(status)}>{MINERAL_STATUS_LABELS[status] || status}<X size={12} /></button>)}
          {activeColumnFilters.map(({ column, expression, invalid }) => <button type="button" key={column.id}
            aria-label={`Снять фильтр ${column.label}`} className={invalid ? "invalid" : undefined}
            onClick={() => setColumnFilters((current) => ({ ...current, [column.id]: "" }))}>
            {column.label}: {expression}{invalid ? " · условие не применено" : ""}<X size={12} />
          </button>)}
          <button type="button" onClick={clearFilters}>Сбросить фильтры</button>
        </div>}
        </div>

        <div className="analyses-table-scroll">
          <table className={`analyses-data-table${dragIds.length ? " selecting-range" : ""}`}>
            <thead>
              <tr>
                <th className="analysis-select-cell"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} aria-label="Выбрать показанные анализы" /></th>
                {visibleColumns.map((column) => (
                  <th key={column.id}><button type="button" onClick={() => changeSort(column.id)}>{column.label}{sort.id === column.id ? (sort.direction === "asc" ? <CaretUp size={12} /> : <CaretDown size={12} />) : null}</button></th>
                ))}
              </tr>
              <tr className="analysis-filter-row">
                <th />
                {visibleColumns.map((column) => {
                  const units = measurementUnits.get(column.field) || [];
                  const hint = column.kind === "measurement"
                    ? `Число, >10, 5..20, пусто, ниже предела${units.length > 1 ? `. Укажите единицу: ${units.join(", ")}` : ""}`
                    : "Поиск по фрагменту";
                  return <th key={column.id}><input value={columnFilters[column.id] || ""} onChange={(event) => setColumnFilters((current) => ({ ...current, [column.id]: event.target.value }))} placeholder={column.kind === "measurement" ? ">10, 5..20" : "Фильтр"} title={hint} aria-invalid={invalidFilters.has(column.id)} aria-label={`Фильтр ${column.label}`} /></th>;
                })}
              </tr>
            </thead>
            <tbody>
              {ordered.map((analysis) => {
                const selected = selectedIds.includes(analysis.analysis_id);
                const focusedRow = focused?.analysis_id === analysis.analysis_id;
                return (
                  <tr className={`${selected || dragIds.includes(analysis.analysis_id) ? "selected " : ""}${focusedRow ? "focused" : ""}`} key={analysis.analysis_id}
                    onPointerEnter={(event) => extendSelectionDrag(event, analysis.analysis_id)}
                    onClick={(event) => {
                      if (event.shiftKey || event.ctrlKey || event.metaKey) {
                        toggleSelection(analysis.analysis_id, event.shiftKey);
                      }
                      setFocusedId(analysis.analysis_id);
                    }}>
                    <td className="analysis-select-cell" onPointerDown={(event) => startSelectionDrag(event, analysis.analysis_id)}>
                      <input type="checkbox" checked={selected} onChange={(event) => toggleSelection(analysis.analysis_id, event.nativeEvent.shiftKey)} onClick={(event) => event.stopPropagation()} aria-label={`Выбрать ${mainIdentity(analysis)}`} />
                    </td>
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

      <AnalysisDetail analysis={focused} editDraftActions={editDraftActions} hiddenPlotAnalysisIds={hiddenPlotAnalysisIds}
        onSetPlotVisibility={onSetPlotVisibility} busy={busy} />

      {selectedIds.length > 0 && (
        <div className="analysis-selection-tray">
          <div><CheckSquare size={20} weight="fill" /><b>{selectedIds.length} выбрано</b><span>{hiddenSelectionCount ? `Скрыто фильтром: ${hiddenSelectionCount}` : "Выбранные строки закреплены сверху."}</span></div>
          <div className="analysis-selection-chips">
            {selectedIds.slice(0, 5).map((id) => {
              const analysis = analyses.find((item) => item.analysis_id === id);
              return <button type="button" key={id} onClick={() => toggleSelection(id)}>{analysis ? mainIdentity(analysis) : "Анализ вне загруженных страниц"} <X size={13} /></button>;
            })}
            {selectedIds.length > 5 && <span>+{selectedIds.length - 5}</span>}
          </div>
          <div className="analysis-selection-actions">
            {onCreateWorkGroup && <button className="primary-button" type="button" disabled={busy || groupBusy} onClick={() => setGroupForm(true)}>Сохранить как рабочую группу</button>}
            {generationActions && <GenerationAssignment actions={generationActions} selectedIds={selectedIds} busy={busy} />}
            {onOpenPlots && <button className="outline-button" type="button" disabled={busy} onClick={onOpenPlots}>Построить диаграммы</button>}
            {onExportSelection && <>
              <button className="outline-button" type="button" disabled={busy} onClick={() => onExportSelection("xlsx")}>Экспорт отбора XLSX</button>
              <button className="outline-button" type="button" disabled={busy} onClick={() => onExportSelection("csv")}>Экспорт отбора CSV</button>
            </>}
            {onPublishSelection && <button className="outline-button" type="button" disabled={busy} onClick={onPublishSelection}>Добавить таблицу в пакет</button>}
            <button className="outline-button" type="button" onClick={() => { selectionAnchor.current = null; setSelectedIds([]); }}>Очистить выбор</button>
          </div>
        </div>
      )}

      {project.latest_import && <button className="analysis-retract-link" type="button" onClick={onRetract} disabled={busy}>Отменить последний импорт</button>}
    </div>
  );
}
