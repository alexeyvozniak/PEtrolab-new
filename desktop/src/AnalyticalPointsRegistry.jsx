import { useEffect, useMemo, useState } from "react";
import { ArrowCounterClockwise, ArrowLeft, CheckSquare, Database, LinkBreak, LinkSimple, MagnifyingGlass, MapPin, Minus, PencilSimple, Plus, Warning, X } from "@phosphor-icons/react";
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

function coordinate(value) {
  return Number.isInteger(Number(value)) ? String(Number(value)) : Number(value).toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function geometryLabel(placement) {
  const geometry = placement?.geometry;
  if (!geometry) return "Геометрия недоступна";
  const kind = { point: "Point", rectangle: "Rectangle", square: "Square" }[geometry.kind] || geometry.kind;
  const size = geometry.kind === "point" ? "" : ` · ${coordinate(geometry.width_px)} × ${coordinate(geometry.height_px)} px`;
  return `${kind} · X ${coordinate(geometry.x_px)} · Y ${coordinate(geometry.y_px)} px${size}`;
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

function journalActionLabel(action) {
  return {
    "analytical_point.create": "Создание связи",
    "analytical_point.retire": "Снятие связи",
    "analytical_point.analysis.add": "Analysis добавлена",
    "analytical_point.analysis.remove": "Analysis снята",
    "analytical_point.annotation.remove": "Размещение снято",
    "operation.undo": "Отмена операции",
  }[action] || action;
}

function scopeCount(operation, field) {
  return operation?.entity_ids?.[field]?.length || 0;
}

function PointCompositionDialog({ point, analyses, busy, onCancel, onConfirm }) {
  const linked = new Set(point.analysis_ids || []);
  const addCandidates = analyses.filter((analysis) => !linked.has(analysis.analysis_id));
  const removeCandidates = (point.analysis_ids || []).map((id) => ({ id, analysis: analyses.find((item) => item.analysis_id === id) }));
  const [mode, setMode] = useState("add");
  const [analysisId, setAnalysisId] = useState(addCandidates[0]?.analysis_id || "");
  const [linkType, setLinkType] = useState("same_point");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [localError, setLocalError] = useState("");
  const selectedAnalysis = analyses.find((analysis) => analysis.analysis_id === analysisId);
  const selectedSample = selectedAnalysis?.identity?.Sample;
  const crossSample = mode === "add" && selectedSample && selectedSample !== point.sample_name;
  const removalBlocked = (point.analysis_ids || []).length <= 2;
  const canConfirm = Boolean(analysisId && reason.trim() && confirmed && !busy && !(mode === "remove" && removalBlocked));

  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onCancel]);

  const changeMode = (nextMode) => {
    setMode(nextMode);
    setAnalysisId(nextMode === "add" ? addCandidates[0]?.analysis_id || "" : removeCandidates[0]?.id || "");
    setReason("");
    setConfirmed(false);
    setLocalError("");
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!canConfirm) return;
    setLocalError("");
    try {
      await onConfirm({ point, action: mode, analysisId, linkType, reason: reason.trim() });
      onCancel();
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  return <div className="point-retire-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section className="point-retire-dialog point-composition-dialog" role="dialog" aria-modal="true" aria-labelledby="point-composition-title">
      <header><div><span>Одна обратимая операция</span><h2 id="point-composition-title">Изменить состав {point.point_name}</h2></div><button className="icon-button" type="button" onClick={onCancel} disabled={busy} aria-label="Закрыть изменение состава"><X size={19} /></button></header>
      <section className="point-retire-scope" aria-label="Точный текущий состав"><div><span>Sample</span><b>{point.sample_name}</b></div><div><span>Analyses</span><b>{(point.analysis_ids || []).length}</b></div><div><span>Spatial Annotations</span><b>{(point.placements || []).length}</b></div><code title={point.analytical_point_id}>{point.analytical_point_id}</code></section>
      <form onSubmit={submit}>
        <div className="point-composition-modes" role="group" aria-label="Операция с составом"><button type="button" aria-label="Выбрать добавление Analysis" className={mode === "add" ? "active" : ""} onClick={() => changeMode("add")}><Plus size={16} /> Добавить Analysis</button><button type="button" aria-label="Выбрать снятие Analysis" className={mode === "remove" ? "active" : ""} onClick={() => changeMode("remove")}><Minus size={16} /> Снять Analysis</button></div>
        {mode === "add" ? <>
          <label>Analysis из загруженной таблицы<select aria-label="Analysis для добавления" value={analysisId} onChange={(event) => { setAnalysisId(event.target.value); setConfirmed(false); }}><option value="">Выбери Analysis</option>{addCandidates.map((analysis) => <option value={analysis.analysis_id} key={analysis.analysis_id}>{analysisName(analysis, analysis.analysis_id)} · {analysisMethods(analysis)}</option>)}</select></label>
          <small className="point-composition-hint">Показаны только загруженные Analyses проекта. Если нужной нет, сначала загрузи её в таблице Analyses.</small>
          <label>Смысл связи<select aria-label="Тип связи добавляемой Analysis" value={linkType} onChange={(event) => { setLinkType(event.target.value); setConfirmed(false); }}>{Object.entries(LINK_TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          {crossSample && <div className="point-composition-warning"><Warning size={18} weight="fill" /><span>Analysis относится к Sample «{selectedSample}», а точка — к «{point.sample_name}». Причина ниже должна явно объяснять эту связь.</span></div>}
          {!addCandidates.length && <p className="point-composition-empty">Все загруженные Analyses уже входят в эту точку.</p>}
        </> : <>
          <label>Analysis в текущем составе<select aria-label="Analysis для снятия" value={analysisId} disabled={removalBlocked} onChange={(event) => { setAnalysisId(event.target.value); setConfirmed(false); }}>{removeCandidates.map(({ id, analysis }) => <option value={id} key={id}>{analysisName(analysis, id)} · {analysisMethods(analysis)}</option>)}</select></label>
          {removalBlocked && <div className="point-composition-warning"><Warning size={18} weight="fill" /><span>Снять Analysis нельзя: в Analytical Point должны остаться минимум две Analyses.</span></div>}
        </>}
        <label>Причина<textarea aria-label="Причина изменения состава" value={reason} maxLength={500} onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} placeholder={mode === "add" ? "Почему эта Analysis относится к той же физической точке?" : "Почему Analysis нужно снять с этой точки?"} /></label>
        <label className="point-retire-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>Подтверждаю изменение одной Analysis в показанном составе. Analysis, Measurements и Source не удаляются.</span></label>
        {localError && <p className="point-retire-error" role="alert">{localError}</p>}
        <footer><button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отмена</button><button className="point-composition-submit" type="submit" disabled={!canConfirm}>{mode === "add" ? <Plus size={18} /> : <Minus size={18} />} {mode === "add" ? "Добавить Analysis" : "Снять Analysis"}</button></footer>
      </form>
    </section>
  </div>;
}

function RetirePointDialog({ point, busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [localError, setLocalError] = useState("");
  const canConfirm = reason.trim() && confirmed && !busy;

  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onCancel]);

  const submit = async (event) => {
    event.preventDefault();
    if (!canConfirm) return;
    setLocalError("");
    try {
      await onConfirm(point, reason.trim());
      onCancel();
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  return <div className="point-retire-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section className="point-retire-dialog" role="dialog" aria-modal="true" aria-labelledby="point-retire-title">
      <header><div><span>Обратимая операция</span><h2 id="point-retire-title">Разорвать связь {point.point_name}</h2></div><button className="icon-button" type="button" onClick={onCancel} disabled={busy} aria-label="Закрыть разрыв связи"><X size={19} /></button></header>
      <div className="point-retire-warning"><Warning size={20} weight="fill" /><p><b>Analytical Point исчезнет из активного реестра.</b><span>Исходные Analyses, Measurements, Source, Spatial Annotation и Media Asset останутся в проекте.</span></p></div>
      <section className="point-retire-scope" aria-label="Точный состав операции">
        <div><span>Sample</span><b>{point.sample_name}</b></div><div><span>Analyses</span><b>{(point.analysis_ids || []).length}</b></div><div><span>Spatial Annotations</span><b>{(point.placements || []).length}</b></div>
        <code title={point.analytical_point_id}>{point.analytical_point_id}</code>
      </section>
      <form onSubmit={submit}>
        <label>Причина<textarea aria-label="Причина разрыва связи" value={reason} maxLength={500} onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} placeholder="Например: связаны разные физические точки" autoFocus /></label>
        <label className="point-retire-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>Подтверждаю снятие только этой связи с указанным точным составом. Исходные научные данные не удаляются.</span></label>
        {localError && <p className="point-retire-error" role="alert">{localError}</p>}
        <footer><button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отмена</button><button className="point-retire-submit" type="submit" disabled={!canConfirm}><LinkBreak size={18} /> Разорвать связь</button></footer>
      </form>
    </section>
  </div>;
}

function RemovePlacementDialog({ point, placement, busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [localError, setLocalError] = useState("");
  const canConfirm = Boolean(reason.trim() && confirmed && !busy);

  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onCancel]);

  const submit = async (event) => {
    event.preventDefault();
    if (!canConfirm) return;
    setLocalError("");
    try {
      await onConfirm(point, placement, reason.trim());
      onCancel();
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  return <div className="point-retire-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section className="point-retire-dialog point-placement-dialog" role="dialog" aria-modal="true" aria-labelledby="point-placement-remove-title">
      <header><div><span>Обратимая пространственная связь</span><h2 id="point-placement-remove-title">Снять размещение {point.point_name}</h2></div><button className="icon-button" type="button" onClick={onCancel} disabled={busy} aria-label="Закрыть снятие размещения"><X size={19} /></button></header>
      <div className="point-retire-warning"><Warning size={20} weight="fill" /><p><b>С точки будет снята только эта метка.</b><span>Spatial Annotation, Media Asset, Analytical Point, Analyses и Measurements останутся в проекте.</span></p></div>
      <section className="point-retire-scope" aria-label="Точный состав пространственной операции"><div><span>Sample</span><b>{point.sample_name}</b></div><div><span>Analyses</span><b>{(point.analysis_ids || []).length}</b></div><div><span>Размещений сейчас</span><b>{(point.placements || []).length}</b></div><code title={point.analytical_point_id}>{point.analytical_point_id}</code></section>
      <section className="point-placement-target"><header><b>{placement.media_display_name}</b><span>{placement.media_type}</span></header><p>{placement.thin_section_name} · {geometryLabel(placement)}</p><dl><div><dt>Spatial Annotation</dt><dd>{placement.spatial_annotation_id}</dd></div><div><dt>Media Asset</dt><dd>{placement.media_asset_id}</dd></div></dl></section>
      <form onSubmit={submit}>
        <label>Причина<textarea aria-label="Причина снятия размещения" value={reason} maxLength={500} onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} placeholder="Например: метка поставлена не на ту физическую точку" autoFocus /></label>
        <label className="point-retire-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>Подтверждаю снятие только показанной связи Point ↔ Spatial Annotation. Исходные объекты не удаляются.</span></label>
        {localError && <p className="point-retire-error" role="alert">{localError}</p>}
        <footer><button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отмена</button><button className="point-retire-submit" type="submit" disabled={!canConfirm}><LinkBreak size={18} /> Снять размещение</button></footer>
      </form>
    </section>
  </div>;
}

export function AnalyticalPointsRegistry({
  projection = { total: 0, items: [] },
  analyses = [],
  operationJournal = { total: 0, items: [] },
  operationNotice = null,
  busy,
  initialPointId = "",
  onBack,
  onShowAnalyses,
  onRefresh,
  onChangeMembership,
  onRemovePlacement,
  onRetire,
  onUndo,
}) {
  const items = projection.items || [];
  const [query, setQuery] = useState("");
  const [sampleFilter, setSampleFilter] = useState("all");
  const [methodFilter, setMethodFilter] = useState("all");
  const [placementFilter, setPlacementFilter] = useState("all");
  const [selectedPointIds, setSelectedPointIds] = useState(initialPointId ? [initialPointId] : []);
  const [focusedPointId, setFocusedPointId] = useState(initialPointId);
  const [retirePoint, setRetirePoint] = useState(null);
  const [compositionPoint, setCompositionPoint] = useState(null);
  const [placementTarget, setPlacementTarget] = useState(null);
  const [undoError, setUndoError] = useState("");
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
  const recentOperations = (operationJournal.items || []).filter((item) => item.entity_type === "analytical_point").slice(0, 4);

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

    <main className={`point-registry-main${operationNotice ? " has-operation" : ""}`}>
      <div className="point-registry-toolbar">
        <button className="outline-button" type="button" onClick={onBack}><ArrowLeft size={17} /> Analyses</button>
        <div className="point-registry-search"><MagnifyingGlass size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Точка, Sample или Analysis ID…" aria-label="Поиск Analytical Points" /></div>
        <span>{ordered.length} из {projection.total || items.length}</span>
        <button className="outline-button" type="button" onClick={onRefresh} disabled={busy}>Обновить</button>
      </div>

      {operationNotice && <div className="point-operation-banner" role="status">
        <div><ArrowCounterClockwise size={20} /><p><b>{operationNotice.message}</b><span>Scope: {scopeCount(operationNotice.operation, "analysis_ids")} Analyses · {scopeCount(operationNotice.operation, "spatial_annotation_ids")} Spatial Annotations. Исходные данные сохранены.</span></p></div>
        <button type="button" disabled={busy} onClick={async () => { setUndoError(""); try { await onUndo(operationNotice.operation.operation_id); } catch (caught) { setUndoError(caught instanceof Error ? caught.message : String(caught)); } }}><ArrowCounterClockwise size={17} /> Отменить</button>
        {undoError && <small role="alert">{undoError}</small>}
      </div>}

      <div className="point-registry-table-scroll">
        <table className="point-registry-table">
          <thead><tr><th><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="Выбрать показанные Analytical Points" /></th><th>Sample</th><th>Analytical Point</th><th>Тип связи</th><th>Методы</th><th>Analyses</th><th>Пространственная связь</th><th>Создано</th></tr></thead>
          <tbody>{ordered.map((point) => {
            const selected = selectedPointIds.includes(point.analytical_point_id);
            const focused = focusedPoint?.analytical_point_id === point.analytical_point_id;
            const firstPlacement = point.placements?.[0];
            return <tr className={`${selected ? "selected " : ""}${focused ? "focused" : ""}`} key={point.analytical_point_id} onClick={() => setFocusedPointId(point.analytical_point_id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setFocusedPointId(point.analytical_point_id); }}>
              <td><input type="checkbox" checked={selected} onChange={() => togglePoint(point.analytical_point_id)} onClick={(event) => event.stopPropagation()} aria-label={`Выбрать Analytical Point ${point.point_name}`} /></td>
              <td>{point.sample_name}</td><td><b>{point.point_name}</b><code title={point.analytical_point_id}>{point.analytical_point_id}</code></td><td>{pointLinkLabel(point)}</td><td>{(point.methods || []).join(", ") || "—"}</td><td>{(point.analysis_ids || []).length}</td><td><div className="point-spatial-summary"><span className={Number(point.placement_count || 0) ? "point-status placed" : "point-status"}>{pointStatus(point)}{Number(point.placement_count || 0) ? ` · ${point.placement_count}` : ""}</span>{firstPlacement && <small title={`${firstPlacement.media_display_name} · ${geometryLabel(firstPlacement)}`}>{firstPlacement.media_display_name} · {geometryLabel(firstPlacement)}</small>}</div></td><td>{createdLabel(point.created_at)}</td>
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
        <section><h3>Пространственная привязка</h3><p className={Number(focusedPoint.placement_count || 0) ? "point-inspector-status placed" : "point-inspector-status"}><MapPin size={18} /> {pointStatus(focusedPoint)}{Number(focusedPoint.placement_count || 0) ? ` (${focusedPoint.placement_count})` : ""}</p>
          {(focusedPoint.placements || []).map((placement) => <article className="point-placement-card" key={placement.spatial_annotation_id}>
            <header><b>{placement.media_display_name}</b><span>{placement.media_type}</span></header>
            <p>{placement.thin_section_name}</p>
            <strong>{geometryLabel(placement)}</strong>
            <small>Изображение: {placement.image_width_px} × {placement.image_height_px} px</small>
            <dl><div><dt>Spatial Annotation</dt><dd title={placement.spatial_annotation_id}>{placement.spatial_annotation_id}</dd></div><div><dt>Media Asset</dt><dd title={placement.media_asset_id}>{placement.media_asset_id}</dd></div></dl>
            {placement.cross_sample_exception && <em>Межобразцовое исключение: {placement.exception_reason}</em>}
            <button className="point-placement-unlink" type="button" disabled={busy || !onRemovePlacement} onClick={() => setPlacementTarget({ point: focusedPoint, placement })}><LinkBreak size={14} /> Снять размещение</button>
          </article>)}
        </section>
        <section><h3>Устойчивый ID</h3><code>{focusedPoint.analytical_point_id}</code><small>Создано: {createdLabel(focusedPoint.created_at)}</small></section>
        <section className="point-registry-actions"><h3>Действия со связью</h3><button className="point-composition-action" type="button" disabled={busy || !onChangeMembership} onClick={() => setCompositionPoint(focusedPoint)}><PencilSimple size={17} /> Изменить состав</button><button type="button" disabled={busy || !onRetire} onClick={() => setRetirePoint(focusedPoint)}><LinkBreak size={17} /> Разорвать связь</button><small>Каждое изменение попадёт в журнал и сможет быть отменено, пока точный состав точки не изменился.</small></section>
        <section className="point-journal"><h3>Operation Journal</h3>{recentOperations.length ? recentOperations.map((operation) => <article key={operation.operation_id}><div><b>{journalActionLabel(operation.action_kind)}</b><span className={operation.outcome === "undone" ? "undone" : ""}>{operation.outcome === "undone" ? "отменено" : "применено"}</span></div><small>{createdLabel(operation.created_at)} · {operation.actor}</small><p>{scopeCount(operation, "analysis_ids")} Analyses · {scopeCount(operation, "spatial_annotation_ids")} пространственных связей</p><code title={operation.operation_id}>{operation.operation_id}</code></article>) : <p>Операций пока нет.</p>}</section>
      </> : <div className="point-registry-inspector-empty"><LinkSimple size={25} /><span>Выбери строку реестра, чтобы проверить состав связи.</span></div>}
    </aside>

    {selectedPointIds.length > 0 && <div className="point-registry-selection">
      <div><CheckSquare size={20} weight="fill" /><b>{selectedPoints.length} Analytical Points / {selectedAnalysisIds.length} Analyses</b><span>Selection содержит исходные Analysis ID, а не объединённые измерения.</span></div>
      <div>{selectedPoints.slice(0, 4).map((point) => <button type="button" key={point.analytical_point_id} onClick={() => togglePoint(point.analytical_point_id)}>{point.point_name} <X size={13} /></button>)}</div>
      <button className="primary-button" type="button" onClick={() => onShowAnalyses(selectedAnalysisIds)} disabled={!selectedAnalysisIds.length}>Показать исходные Analyses</button>
    </div>}
    {compositionPoint && <PointCompositionDialog point={compositionPoint} analyses={analyses} busy={busy} onCancel={() => setCompositionPoint(null)} onConfirm={onChangeMembership} />}
    {placementTarget && <RemovePlacementDialog point={placementTarget.point} placement={placementTarget.placement} busy={busy} onCancel={() => setPlacementTarget(null)} onConfirm={onRemovePlacement} />}
    {retirePoint && <RetirePointDialog point={retirePoint} busy={busy} onCancel={() => setRetirePoint(null)} onConfirm={onRetire} />}
  </div>;
}
