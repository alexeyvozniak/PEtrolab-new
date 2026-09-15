import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckSquare, Database, LinkSimple, MagnifyingGlass, MapPin, X } from "@phosphor-icons/react";
import "./analyticalPointsRegistry.css";

const LINK_TYPE_LABELS = {
  same_point: "Та же аналитическая точка",
  same_grain: "То же зерно",
  same_zone: "Та же зона",
  repeat_measurement: "Повторное измерение",
};

function pointLinkLabel(point) {
  const labels = (point.link_types || []).map((type) => LINK_TYPE_LABELS[type] || type);
  return labels.length ? labels.join(", ") : "Тип не указан";
}

function pointStatus(point) {
  return Number(point.placement_count || 0) > 0 ? "Размещена" : "Без изображения";
}

function analysisName(analysis, fallback) {
  const identity = analysis?.identity || {};
  return identity.Analysis || identity.Point || fallback;
}

function analysisMethods(analysis) {
  const methods = [...new Set((analysis?.measurement_list || []).map((measurement) => measurement.method).filter(Boolean))];
  return methods.length ? methods.join(", ") : "Метод не указан";
}

function analysisOrigin(analysis) {
  if (!analysis) return "Analysis ещё не загружен в таблицу";
  const parts = [analysis.source_name, analysis.sheet_name && `лист ${analysis.sheet_name}`];
  if (analysis.source_row_number) parts.push(`строка ${analysis.source_row_number}`);
  return parts.filter(Boolean).join(" · ");
}

function createdLabel(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

export function AnalyticalPointsRegistry({ projection = { total: 0, items: [] }, analyses = [], busy, initialPointId = "", onBack, onShowAnalyses, onRefresh }) {
  const items = projection.items || [];
  const [query, setQuery] = useState("");
  const [sampleFilter, setSampleFilter] = useState("all");
  const [methodFilter, setMethodFilter] = useState("all");
  const [placementFilter, setPlacementFilter] = useState("all");
  const [selectedPointIds, setSelectedPointIds] = useState(initialPointId ? [initialPointId] : []);
  const [focusedPointId, setFocusedPointId] = useState(initialPointId);
  const analysisById = useMemo(() => new Map(analyses.map((analysis) => [analysis.analysis_id, analysis])), [analyses]);
  const methods = useMemo(() => [...new Set(items.flatMap((point) => point.methods || []))].sort((a, b) => a.localeCompare(b, "ru")), [items]);

  useEffect(() => {
    const available = new Set(items.map((point) => point.analytical_point_id));
    setSelectedPointIds((current) => current.filter((id) => available.has(id)));
    if (focusedPointId && !available.has(focusedPointId)) setFocusedPointId("");
  }, [focusedPointId, items]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return items.filter((point) => {
      if (sampleFilter !== "all" && point.sample_name !== sampleFilter) return false;
      if (methodFilter !== "all" && !(point.methods || []).includes(methodFilter)) return false;
      if (placementFilter === "placed" && Number(point.placement_count || 0) === 0) return false;
      if (placementFilter === "unplaced" && Number(point.placement_count || 0) > 0) return false;
      if (needle && ![point.point_name, point.sample_name, point.analytical_point_id, ...(point.analysis_ids || [])].join(" ").toLocaleLowerCase().includes(needle)) return false;
      return true;
    });
  }, [items, methodFilter, placementFilter, query, sampleFilter]);

  const ordered = useMemo(() => {
    const selected = new Set(selectedPointIds);
    return [...filtered].sort((left, right) => {
      const selectedDifference = Number(selected.has(right.analytical_point_id)) - Number(selected.has(left.analytical_point_id));
      if (selectedDifference) return selectedDifference;
      return `${left.sample_name}\u0000${left.point_name}`.localeCompare(`${right.sample_name}\u0000${right.point_name}`, "ru", { numeric: true });
    });
  }, [filtered, selectedPointIds]);

  const focusedPoint = items.find((point) => point.analytical_point_id === focusedPointId) || ordered[0] || null;
  const focusedAnalyses = (focusedPoint?.analysis_ids || []).map((id) => ({ id, analysis: analysisById.get(id) }));
  const selectedPoints = selectedPointIds.map((id) => items.find((point) => point.analytical_point_id === id)).filter(Boolean);
  const selectedAnalysisIds = [...new Set(selectedPoints.flatMap((point) => point.analysis_ids || []))];
  const visibleIds = ordered.map((point) => point.analytical_point_id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedPointIds.includes(id));

  const togglePoint = (id) => setSelectedPointIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleVisible = () => setSelectedPointIds((current) => allVisibleSelected ? current.filter((id) => !visibleIds.includes(id)) : [...new Set([...current, ...visibleIds])]);

  return <div className="point-registry">
    <aside className="point-registry-filters">
      <div className="point-registry-pane-title"><span>Analytical Points</span><b>{projection.total || items.length}</b></div>
      <label>Sample<select aria-label="Фильтр Sample Analytical Points" value={sampleFilter} onChange={(event) => setSampleFilter(event.target.value)}><option value="all">Все Sample</option>{(projection.sample_names || []).map((sample) => <option value={sample} key={sample}>{sample}</option>)}</select></label>
      <label>Метод<select aria-label="Фильтр метода Analytical Points" value={methodFilter} onChange={(event) => setMethodFilter(event.target.value)}><option value="all">Все методы</option>{methods.map((method) => <option value={method} key={method}>{method}</option>)}</select></label>
      <label>Изображение<select aria-label="Фильтр размещения Analytical Points" value={placementFilter} onChange={(event) => setPlacementFilter(event.target.value)}><option value="all">Любой статус</option><option value="placed">Есть размещение</option><option value="unplaced">Без изображения</option></select></label>
      <div className="point-registry-note"><Database size={17} /><span>Реестр показывает сохранённые связи. Фильтры и фокус не изменяют Analyses.</span></div>
    </aside>

    <main className="point-registry-main">
      <div className="point-registry-toolbar">
        <button className="outline-button" type="button" onClick={onBack}><ArrowLeft size={17} /> Analyses</button>
        <div className="point-registry-search"><MagnifyingGlass size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Точка, Sample или Analysis ID…" aria-label="Поиск Analytical Points" /></div>
        <span>{ordered.length} из {projection.total || items.length}</span>
        <button className="outline-button" type="button" onClick={onRefresh} disabled={busy}>Обновить</button>
      </div>

      <div className="point-registry-table-scroll">
        <table className="point-registry-table">
          <thead><tr><th><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="Выбрать показанные Analytical Points" /></th><th>Sample</th><th>Analytical Point</th><th>Тип связи</th><th>Методы</th><th>Analyses</th><th>Пространственная связь</th><th>Создано</th></tr></thead>
          <tbody>{ordered.map((point) => {
            const selected = selectedPointIds.includes(point.analytical_point_id);
            const focused = focusedPoint?.analytical_point_id === point.analytical_point_id;
            return <tr className={`${selected ? "selected " : ""}${focused ? "focused" : ""}`} key={point.analytical_point_id} onClick={() => setFocusedPointId(point.analytical_point_id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setFocusedPointId(point.analytical_point_id); }}>
              <td><input type="checkbox" checked={selected} onChange={() => togglePoint(point.analytical_point_id)} onClick={(event) => event.stopPropagation()} aria-label={`Выбрать Analytical Point ${point.point_name}`} /></td>
              <td>{point.sample_name}</td><td><b>{point.point_name}</b><code title={point.analytical_point_id}>{point.analytical_point_id}</code></td><td>{pointLinkLabel(point)}</td><td>{(point.methods || []).join(", ") || "—"}</td><td>{(point.analysis_ids || []).length}</td><td><span className={Number(point.placement_count || 0) ? "point-status placed" : "point-status"}>{pointStatus(point)}{Number(point.placement_count || 0) ? ` · ${point.placement_count}` : ""}</span></td><td>{createdLabel(point.created_at)}</td>
            </tr>;
          })}</tbody>
        </table>
        {ordered.length === 0 && <div className="point-registry-empty"><MapPin size={28} /><b>Analytical Points не найдены</b><span>Измени фильтры или создай точку из выбранных Analyses.</span></div>}
      </div>

      {focusedPoint && <section className="point-registry-analyses" aria-label={`Исходные Analyses точки ${focusedPoint.point_name}`}>
        <header><div><span>Исходные Analyses</span><h3>{focusedPoint.point_name}</h3></div><b>{focusedAnalyses.length}</b></header>
        <div>{focusedAnalyses.map(({ id, analysis }) => <article key={id}><strong>{analysisName(analysis, id)}</strong><span>{analysisMethods(analysis)}</span><small>{analysisOrigin(analysis)}</small><code title={id}>{id}</code></article>)}</div>
      </section>}
    </main>

    <aside className="point-registry-inspector" aria-label="Подробности Analytical Point">
      {focusedPoint ? <>
        <header><span>Точка</span><h2>{focusedPoint.point_name}</h2><p>{focusedPoint.sample_name}</p></header>
        <section><h3>Связь</h3><dl><div><dt>Тип</dt><dd>{pointLinkLabel(focusedPoint)}</dd></div><div><dt>Методы</dt><dd>{(focusedPoint.methods || []).join(", ") || "—"}</dd></div><div><dt>Analyses</dt><dd>{(focusedPoint.analysis_ids || []).length}</dd></div></dl></section>
        <section><h3>Пространственная привязка</h3><p className={Number(focusedPoint.placement_count || 0) ? "point-inspector-status placed" : "point-inspector-status"}><MapPin size={18} /> {pointStatus(focusedPoint)}{Number(focusedPoint.placement_count || 0) ? ` (${focusedPoint.placement_count})` : ""}</p></section>
        <section><h3>Устойчивый ID</h3><code>{focusedPoint.analytical_point_id}</code><small>Создано: {createdLabel(focusedPoint.created_at)}</small></section>
      </> : <div className="point-registry-inspector-empty"><LinkSimple size={25} /><span>Выбери строку реестра, чтобы проверить состав связи.</span></div>}
    </aside>

    {selectedPointIds.length > 0 && <div className="point-registry-selection">
      <div><CheckSquare size={20} weight="fill" /><b>{selectedPoints.length} Analytical Points / {selectedAnalysisIds.length} Analyses</b><span>Selection содержит исходные Analysis ID, а не объединённые измерения.</span></div>
      <div>{selectedPoints.slice(0, 4).map((point) => <button type="button" key={point.analytical_point_id} onClick={() => togglePoint(point.analytical_point_id)}>{point.point_name} <X size={13} /></button>)}</div>
      <button className="primary-button" type="button" onClick={() => onShowAnalyses(selectedAnalysisIds)} disabled={!selectedAnalysisIds.length}>Показать исходные Analyses</button>
    </div>}
  </div>;
}
