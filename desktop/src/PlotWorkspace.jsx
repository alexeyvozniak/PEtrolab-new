import { useCallback, useEffect, useRef, useState } from "react";
import { PLOT_SIZE, buildPlotSvg, plotPanelLabel } from "./plotSvg";
import "./plotWorkspace.css";

const VIEW = { ...PLOT_SIZE, left: 55, right: 425, top: 22, bottom: 235 };
const px = (value) => VIEW.left + value * (VIEW.right - VIEW.left);
const py = (value) => VIEW.bottom - value * (VIEW.bottom - VIEW.top);
const axisKey = (axis) => JSON.stringify([axis.field, axis.unit, axis.measurement_set, axis.method]);
const axisLabel = (axis) => [axis.field, axis.unit, axis.measurement_set, axis.method].filter(Boolean).join(" · ");
const SERIES_COLORS = ["#3b70a0", "#a75d32", "#7654a3", "#34796d", "#ae4563", "#755b36", "#4a6584", "#84506d"];

function sourceColor(id = "") {
  const hash = Array.from(id).reduce((current, character) => (current * 31 + character.charCodeAt(0)) >>> 0, 0);
  return SERIES_COLORS[hash % SERIES_COLORS.length];
}

function insidePolygon(point, vertices) {
  let hit = false;
  for (let index = 0, previous = vertices.length - 1; index < vertices.length; previous = index++) {
    const a = vertices[index];
    const b = vertices[previous];
    if ((a.y > point.y) !== (b.y > point.y) && point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

function initialPanels(axes) {
  if (axes.length < 2) return [];
  const compatible = axes.find((axis) => ["wt.%", "ppm", "ppb"].includes(axis.unit) &&
    axes.filter((item) => item.unit === axis.unit && item.measurement_set === axis.measurement_set && item.method === axis.method).length >= 3);
  const make = (kind, selected) => ({ id: crypto.randomUUID(), kind, axes: selected });
  return [make("binary", axes.slice(0, 2)), compatible
    ? make("ternary", axes.filter((item) => item.unit === compatible.unit && item.measurement_set === compatible.measurement_set && item.method === compatible.method).slice(0, 3))
    : make("binary", [axes[1], axes[0]])];
}

function PlotCanvas({ data, selected, onSelect, shape, colorFor, points }) {
  const drag = useRef(null);
  const [rubber, setRubber] = useState(null);
  const position = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: (event.clientX - bounds.left) * VIEW.width / bounds.width,
      y: (event.clientY - bounds.top) * VIEW.height / bounds.height };
  };
  const start = (event) => {
    if (event.button !== 0 || (event.pointerType === "touch" && !event.isPrimary)) return;
    const point = position(event);
    drag.current = { origin: point, pointer: event.pointerId, trail: [point] };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const move = (event) => {
    if (drag.current?.pointer !== event.pointerId) return;
    const first = drag.current.origin;
    const last = position(event);
    if (shape === "lasso") {
      const trail = drag.current.trail;
      const head = trail.at(-1);
      if (Math.hypot(last.x - head.x, last.y - head.y) >= 2) {
        trail.push(last);
        setRubber({ path: trail.map(({ x, y }) => `${x},${y}`).join(" ") });
      }
      return;
    }
    setRubber({ x: Math.min(first.x, last.x), y: Math.min(first.y, last.y),
      width: Math.abs(last.x - first.x), height: Math.abs(last.y - first.y) });
  };
  const end = (event) => {
    if (drag.current?.pointer !== event.pointerId) return;
    const first = drag.current.origin;
    const trail = drag.current.trail;
    const last = position(event);
    drag.current = null;
    setRubber(null);
    const freehand = shape === "lasso" && trail.length >= 3;
    if (!freehand && Math.hypot(first.x - last.x, first.y - last.y) < 4) {
      const hit = points.findLast((point) => Math.hypot(px(point.u) - last.x, py(point.v) - last.y) <= 7);
      if (hit) onSelect([hit.analysis_id]);
      return;
    }
    if (shape === "lasso" && !freehand) return;
    const inside = (current, a, b) => current >= Math.min(a, b) && current <= Math.max(a, b);
    onSelect(points.filter((point) => freehand
      ? insidePolygon({ x: px(point.u), y: py(point.v) }, [...trail, last])
      : inside(px(point.u), first.x, last.x) && inside(py(point.v), first.y, last.y))
      .map((point) => point.analysis_id));
  };
  const clear = () => { drag.current = null; setRubber(null); };
  return <svg className="plot-canvas" viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} aria-label="Диаграмма"
    data-plot-projection={data.projection_sha256}
    onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={clear} onLostPointerCapture={clear}>
    {data.kind === "ternary" ? <>
      <path className="plot-frame" d={`M ${VIEW.left} ${VIEW.bottom} L ${px(0.5)} ${VIEW.top} L ${VIEW.right} ${VIEW.bottom} Z`} />
      {[[0, 0, "start"], [1, 0, "end"], [0.5, 1, "middle"]].map(([u, v, align], index) =>
        <text key={data.axes[index].field} x={px(u)} y={v ? py(v) - 6 : py(v) + 18} textAnchor={align}>{data.axes[index].field}</text>)}
    </> : <>
      <path className="plot-frame" d={`M ${VIEW.left} ${VIEW.top} V ${VIEW.bottom} H ${VIEW.right}`} />
      {(data.ticks[0] || []).map(({ at, label }) => <g key={at}>
        <line x1={px(at)} x2={px(at)} y1={VIEW.top} y2={VIEW.bottom} />
        <text x={px(at)} y={VIEW.bottom + 14} textAnchor="middle">{label}</text>
      </g>)}
      {(data.ticks[1] || []).map(({ at, label }) => <g key={at}>
        <line x1={VIEW.left} x2={VIEW.right} y1={py(at)} y2={py(at)} />
        <text x={VIEW.left - 5} y={py(at) + 3} textAnchor="end">{label}</text>
      </g>)}
      <text x={px(0.5)} y={VIEW.bottom + 34} textAnchor="middle">{data.axes[0].field} ({data.axes[0].unit})</text>
      <text transform={`translate(12 ${py(0.5)}) rotate(-90)`} textAnchor="middle">{data.axes[1].field} ({data.axes[1].unit})</text>
    </>}
    {(data.fields || []).filter((field) => field.vertices.length >= 3).map((field) =>
      <polygon key={field.layer_id} className="plot-field" fill="#99b9a0" fillOpacity={0.26}
        stroke="#5c7d66" strokeWidth={1} points={field.vertices.map(([u, v]) => `${px(u)},${py(v)}`).join(" ")} />)}
    {points.map((point) => <g key={point.analysis_id}>
      <circle className="plot-point" fill={colorFor(point.source_id)} cx={px(point.u)} cy={py(point.v)} r={3.5} role="button" tabIndex={0}
        opacity={point.opacity}
        aria-label={`Выбрать точку ${point.label}`} aria-pressed={selected.has(point.analysis_id)}
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect([point.analysis_id]); } }}>
        <title>{point.label} · {point.source_name} · {point.values.join(" / ")}</title>
      </circle>
    </g>)}
    {points.filter((point) => selected.has(point.analysis_id)).map((point) =>
      <circle key={point.analysis_id} className="plot-halo" cx={px(point.u)} cy={py(point.v)} r={6} />)}
    {rubber && (rubber.path ? <polygon className="plot-rubber" points={rubber.path} /> : <rect className="plot-rubber" {...rubber} />)}
  </svg>;
}

function PlotPanel({ panel, axes, load, update, remove, selected, onSelect, canRemove, shape, colorFor, openExport, layers }) {
  const [projection, setProjection] = useState(null);
  const current = projection?.load === load && projection.panel === panel ? projection : null;
  const data = current?.data;
  const styles = new Map();
  layers.forEach(({ analysis_ids, opacity, show_points }, order) => {
    for (const id of analysis_ids) styles.set(id, { order, opacity: show_points ? opacity : 0 });
  });
  const points = (data?.points || []).map((point) => ({ ...point, ...(styles.get(point.analysis_id) || { opacity: 1, order: -1 }) }))
    .filter((point) => point.opacity > 0).sort((a, b) => a.order - b.order);
  const status = current ? current.error : "Загружаю диаграмму…";
  useEffect(() => {
    let active = true;
    load(panel.kind, panel.axes).then((result) => {
      if (active) setProjection({ load, panel, data: result });
    }).catch((error) => { if (active) setProjection({ load, panel, error: error.message }); });
    return () => { active = false; };
  }, [load, panel]);
  const updateKind = (kind) => {
    const next = initialPanels(axes).find((item) => item.kind === kind);
    update({ ...panel, kind, axes: next ? next.axes : axes.slice(0, 3) });
  };

  return <article className="plot-panel" id={`plot-${panel.id}`}>
    <header><b>{panel.axes.map((axis) => axis.field).join(" / ")}</b>
      <div className="plot-panel-actions">
        {openExport && <button type="button" className="outline-button" disabled={!data} onClick={openExport}>Выгрузить панель</button>}
        {canRemove && <button type="button" className="outline-button" onClick={remove}>Убрать панель</button>}
      </div>
    </header>
    <div className="plot-panel-controls">
      <select aria-label="Тип диаграммы" value={panel.kind} onChange={(event) => updateKind(event.target.value)}>
        <option value="binary">Бинарная</option>
        <option value="ternary" disabled={axes.length < 3}>Тройная</option>
      </select>
      {panel.axes.map((axis, index) => <select key={index} aria-label={`Ось ${index + 1}`} value={axisKey(axis)}
        onChange={(event) => update({ ...panel, axes: panel.axes.map((value, position) => position === index
          ? axes.find((item) => axisKey(item) === event.target.value) : value) })}>
        {axes.map((item) => <option key={axisKey(item)} value={axisKey(item)}>{axisLabel(item)}</option>)}
      </select>)}
    </div>
    {status && <p role="status">{status}</p>}
    {data && <>
      <PlotCanvas data={data} selected={selected} onSelect={onSelect} shape={shape} colorFor={colorFor} points={points} />
      <small>Точек: {points.length} из {data.input_count}{data.excluded_count ? ` · пропущено: ${data.excluded_count}` : ""}
        {data.hidden_count ? ` · скрыто: ${data.hidden_count}` : ""}
        {data.points.length > points.length ? ` · скрыто стилем слоя: ${data.points.length - points.length}` : ""}
        {data.kind === "ternary" ? " · доли от суммы трёх компонентов" : ""}</small>
      {(data.fields || []).filter((field) => field.message).map((field) =>
        <p key={field.layer_id}><small>{layers.find((layer) => layer.id === field.layer_id)?.name}: {field.message}</small></p>)}
    </>}
  </article>;
}

function PlotExport({ options, onChange, panels, pending, close, submit, canAddPublication }) {
  const raster = ["png", "tiff"].includes(options.format);
  const panelIndex = panels.findIndex(({ id }) => id === options.panelId);
  const visibleCount = panels.filter(({ id }) => options.visibleIds.includes(id)).length;
  const count = options.scope === "panel" ? Number(panelIndex >= 0) : options.scope === "visible" ? visibleCount : panels.length;
  return <form className="plot-export" aria-label="Выгрузить графики" onSubmit={submit}>
    <header><h3>Выгрузить графики</h3><button className="outline-button" type="button" disabled={pending}
      onClick={close} aria-label="Закрыть экспорт">×</button></header>
    <fieldset disabled={pending}>
      <legend>Область выгрузки</legend>
      {panelIndex >= 0 && <label><input type="radio" name="plot-export-scope" checked={options.scope === "panel"}
        onChange={() => onChange({ scope: "panel" })} />Текущая панель · {plotPanelLabel(panelIndex, options.labels.split("-")[0], options.labels.endsWith("-upper"))}</label>}
      <label><input type="radio" name="plot-export-scope" checked={options.scope === "visible"} disabled={!visibleCount}
        onChange={() => onChange({ scope: "visible" })} />Видимые панели · {visibleCount}</label>
      <label><input type="radio" name="plot-export-scope" checked={options.scope === "layout"}
        onChange={() => onChange({ scope: "layout" })} />Вся раскладка · {panels.length}</label>
    </fieldset>
    <fieldset disabled={pending}>
      <legend>Формат</legend>
      {Object.entries({ svg: "SVG · Corel-safe", pdf: "PDF · векторный", png: "PNG", tiff: "TIFF" }).map(([value, label]) =>
        <label key={value}><input type="radio" name="plot-export-format" checked={options.format === value}
          onChange={() => onChange({ format: value })} />{label}</label>)}
      {options.format !== "svg" && <label>Ширина
        <select value={options.width} onChange={(event) => onChange({ width: Number(event.target.value) })}>
          <option value={90}>90 мм</option><option value={180}>180 мм</option>
        </select>
      </label>}
      {raster && <label>Разрешение
        <select value={options.dpi} onChange={(event) => onChange({ dpi: Number(event.target.value) })}>
          {[300, 500, 600, 1000].map((dpi) => <option value={dpi} key={dpi}>{dpi} dpi</option>)}
        </select>
      </label>}
    </fieldset>
    <fieldset disabled={pending}>
      <legend>Подписи панелей</legend>
      {count === 1 && <label><input type="checkbox" checked={options.showLabel}
        onChange={(event) => onChange({ showLabel: event.target.checked })} />Сохранить букву панели</label>}
      {(count !== 1 || options.showLabel) && <>
        <label>Алфавит и регистр<select value={options.labels} onChange={(event) => onChange({ labels: event.target.value })}>
          <option value="latin">a, b, c</option><option value="latin-upper">A, B, C</option>
          <option value="cyrillic">а, б, в</option><option value="cyrillic-upper">А, Б, В</option>
        </select></label>
        <label>Положение буквы<select value={options.labelPosition} onChange={(event) => onChange({ labelPosition: event.target.value })}>
          <option value="left">Сверху слева</option><option value="right">Сверху справа</option>
        </select></label>
      </>}
    </fieldset>
    {canAddPublication && <fieldset disabled={pending}>
      <legend>Для пакета публикации</legend>
      <label><input type="checkbox" checked={options.includeCsv}
        onChange={(event) => onChange({ includeCsv: event.target.checked })} />Добавить данные CSV</label>
      <label>Подпись фигуры<textarea maxLength={2000} value={options.caption}
        onChange={(event) => onChange({ caption: event.target.value })} /></label>
    </fieldset>}
    <label>Имя файла<input value={options.name} maxLength={100} disabled={pending}
      onChange={(event) => onChange({ name: event.target.value })} /></label>
    <div className="plot-export-actions">
      <button type="submit" className="primary-button" disabled={pending || !options.name.trim() || count === 0}>
        {pending ? "Подготавливаю…" : "Сохранить графики"}
      </button>
      {canAddPublication && <button type="submit" value="package" className="outline-button"
        disabled={pending || !options.name.trim() || count === 0}>Добавить в пакет</button>}
    </div>
  </form>;
}

export function PlotWorkspace({ loadCatalog, loadData, selectedIds, setSelectedIds, inputIds, onBack,
  hiddenSourceIds = [], hiddenAnalysisIds = [], onToggleSource, onSetVisibility, busy, loadLayouts, saveLayout, openLayout,
  onExport, onAddPublication }) {
  const [axes, setAxes] = useState([]);
  const [panels, setPanels] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("union");
  const [shape, setShape] = useState("rectangle");
  const [sources, setSources] = useState([]);
  const [layouts, setLayouts] = useState([]);
  const [layoutName, setLayoutName] = useState("");
  const [layoutStatus, setLayoutStatus] = useState(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [savedColors, setSavedColors] = useState({});
  const [layers, setLayers] = useState([]);
  const [layerName, setLayerName] = useState("");
  const layerInput = inputIds ? selectedIds.filter((id) => inputIds.includes(id)) : selectedIds;
  const loadWithLayers = useCallback((kind, axes) => loadData(kind, axes, layers), [loadData, layers]);
  const [exportStatus, setExportStatus] = useState(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportOptions, setExportOptions] = useState(null);
  const grid = useRef(null);
  const colorFor = (sourceId) => savedColors[sourceId] || sourceColor(sourceId);
  const selected = new Set(selectedIds);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    loadCatalog().then((catalog) => {
      if (active) {
        setAxes(catalog.axes);
        setSources(catalog.sources || []);
        setPanels((current) => current.length ? current : initialPanels(catalog.axes));
      }
    }).catch((caught) => { if (active) setError(caught.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loadCatalog]);
  useEffect(() => {
    if (!loadLayouts) return;
    let active = true;
    loadLayouts().then((items) => { if (active) setLayouts(items); })
      .catch((caught) => { if (active) setLayoutStatus({ error: caught.message }); });
    return () => { active = false; };
  }, [loadLayouts]);
  const save = async (event) => {
    event.preventDefault();
    setLayoutBusy(true);
    setLayoutStatus(null);
    try {
      const saved = await saveLayout({
        name: layoutName, analysis_ids: inputIds, panels,
        colors: Object.fromEntries(sources.map(({ source_id }) => [source_id, colorFor(source_id)])),
        hidden_analysis_ids: hiddenAnalysisIds, hidden_source_ids: hiddenSourceIds,
        layers,
      });
      setLayouts((current) => [...current, { id: saved.id, name: saved.name }]);
      setLayoutName("");
      setLayoutStatus({ notice: `Сохранена раскладка «${saved.name}».` });
    } catch (caught) {
      setLayoutStatus({ error: caught.message });
    } finally {
      setLayoutBusy(false);
    }
  };
  const restore = async (id) => {
    setLayoutBusy(true);
    setLayoutStatus(null);
    try {
      const saved = await openLayout(id);
      setPanels(saved.panels.map(({ id: panelId, kind, axes: savedAxes }) => ({
        id: panelId, kind, axes: savedAxes.map(({ field, unit, method, measurement_set }) => ({ field, unit, method, measurement_set })),
      })));
      setSavedColors(Object.fromEntries(saved.legend.entries.map(({ value, color }) => [value, color])));
      setLayers(saved.layers || []);
      setLayoutStatus({ notice: `Открыта раскладка «${saved.name}».` });
    } catch (caught) {
      setLayoutStatus({ error: caught.message });
    } finally {
      setLayoutBusy(false);
    }
  };
  const select = (ids) => setSelectedIds((current) => mode === "replace" ? [...new Set(ids)]
    : mode === "subtract" ? current.filter((id) => !ids.includes(id)) : [...new Set([...current, ...ids])]);
  const add = () => setPanels((current) => [...current, initialPanels(axes)[0]]);
  const addLayer = (event) => {
    event.preventDefault();
    setLayers((current) => [...current, { id: crypto.randomUUID(), name: layerName.trim(), analysis_ids: layerInput,
      show_points: true, opacity: 1, field: null }]);
    setLayerName("");
  };
  const updateLayer = (id, changes) => setLayers((current) => current.map((layer) => layer.id === id ? { ...layer, ...changes } : layer));
  const moveLayer = (index, offset) => setLayers((current) => {
    const ordered = current.slice();
    [ordered[index], ordered[index + offset]] = [ordered[index + offset], ordered[index]];
    return ordered;
  });
  const hasVisibleFields = layers.some((layer) => layer.field?.visible);
  const openExport = (panelId) => {
    const visibleIds = Array.from(grid.current.children).flatMap((node, index) => {
      const area = node.getBoundingClientRect();
      return area.right > 0 && area.left < window.innerWidth && area.bottom > 0 && area.top < window.innerHeight
        ? [panels[index].id] : [];
    });
    setExportStatus(null);
    setExportOptions({ panelId, visibleIds, scope: panelId ? "panel" : "layout", format: "svg",
      width: panelId ? 90 : 180, dpi: 600, name: "PetroLab-plot", showLabel: true, labels: "latin",
      labelPosition: "left", includeCsv: false, caption: "" });
  };
  const submitExport = async (event) => {
    event.preventDefault();
    const addToPackage = event.nativeEvent.submitter?.value === "package";
    const { scope, panelId, visibleIds, name, format, labels, caption, includeCsv, ...options } = exportOptions;
    const requested = Array.from(grid.current.children, (node, panelIndex) => ({
      id: panels[panelIndex].id, svg: node.querySelector(".plot-canvas"), panelIndex,
    })).filter(({ id }) => scope === "layout" || (scope === "panel" ? id === panelId : visibleIds.includes(id)));
    if (!requested.length || requested.some(({ svg }) => !svg)) {
      setExportStatus({ error: "Дождитесь загрузки выбранных панелей и проверьте настройки их осей." });
      return;
    }
    setExportBusy(true);
    setExportStatus(null);
    try {
      const svg = buildPlotSvg(requested, { ...options, showLabel: requested.length > 1 || options.showLabel,
        alphabet: labels.split("-")[0], uppercase: labels.endsWith("-upper") });
      const base = name.trim().replace(/\.(svg|pdf|png|tiff?)$/i, "");
      if (addToPackage) {
        await onAddPublication({
          name: base || "PetroLab-plot", format, svg, width_mm: options.width, dpi: options.dpi, include_csv: includeCsv,
          analysis_ids: inputIds, layers, hidden_analysis_ids: hiddenAnalysisIds, hidden_source_ids: hiddenSourceIds,
          colors: Object.fromEntries(sources.map(({ source_id }) => [source_id, colorFor(source_id)])),
          panels: requested.map(({ panelIndex, svg: canvas }) => ({
            ...panels[panelIndex], projection_sha256: canvas.dataset.plotProjection,
          })),
        }, caption);
        setExportStatus({ notice: "Фигура добавлена в пакет." });
        setExportOptions(null);
        return;
      }
      const file = await onExport(svg, { ...options, format, name: `${base || "PetroLab-plot"}.${format}` });
      if (file) {
        setExportStatus({ notice: `Сохранено: ${file}` });
        setExportOptions(null);
      }
    } catch (caught) {
      setExportStatus({ error: caught.message || String(caught) });
    } finally {
      setExportBusy(false);
    }
  };

  return <section className="plot-workspace">
    <aside>
      <button className="outline-button" type="button" onClick={onBack}>Назад к анализам</button>
      <h3>Раскладка</h3>
      {panels.map((panel, index) => <a href={`#plot-${panel.id}`} key={panel.id}>{index + 1}. {panel.axes.map((axis) => axis.field).join(" / ")}</a>)}
      <p>{inputIds ? `Входной набор: ${inputIds.length} анализов` : "Входной набор: проект"}</p>
      <section className="plot-source-legend" aria-label="Легенда источников">
        <h3>Источники</h3>
        {sources.map((source) => {
          const repeated = sources.some((other) => other.source_id !== source.source_id && other.source_name === source.source_name);
          const label = repeated ? `${source.source_name} · ${source.source_id.slice(0, 8)}` : source.source_name;
          return <label key={source.source_id}>
            <input type="checkbox" checked={!hiddenSourceIds.includes(source.source_id)}
              disabled={!onToggleSource || busy} onChange={() => onToggleSource(source.source_id)} />
            <i style={{ backgroundColor: colorFor(source.source_id) }} aria-hidden="true" />{label}
          </label>;
        })}
        <p>Зелёный контур — текущий отбор</p>
        {hiddenAnalysisIds.length > 0 && <button className="outline-button" type="button" disabled={busy || !onSetVisibility}
          onClick={() => onSetVisibility(hiddenAnalysisIds, false)}>Вернуть скрытые точки · {hiddenAnalysisIds.length}</button>}
      </section>
      <details className="plot-layers">
        <summary>Слои и поля</summary>
        {layers.some((layer) => layer.field) && <button className="outline-button" type="button" onClick={() =>
          setLayers((current) => current.map((layer) => layer.field
            ? { ...layer, field: { ...layer.field, visible: !hasVisibleFields } } : layer))}>
          {hasVisibleFields ? "Скрыть все поля" : "Показать все поля"}
        </button>}
        {layers.map((layer, index) => <fieldset key={layer.id}>
          <legend>{layer.name} · {layer.analysis_ids.length}</legend>
          <label><input type="checkbox" checked={layer.show_points} onChange={(event) => updateLayer(layer.id, { show_points: event.target.checked })} /> Точки</label>
          <label>Непрозрачность точек <input type="range" min="0" max="1" step="0.05" value={layer.opacity}
            onChange={(event) => updateLayer(layer.id, { opacity: Number(event.target.value) })} /></label>
          <label>Метод поля <select value={layer.field?.method || ""} onChange={(event) => {
            const method = event.target.value;
            updateLayer(layer.id, { field: method ? { method, visible: true, probability: method === "convex_hull" ? null : 0.95 } : null });
          }}>
            <option value="">Без поля</option><option value="convex_hull">Выпуклая оболочка</option>
            <option value="normal_probability_ellipse">Эллипс вероятности</option>
          </select></label>
          {layer.field && <label><input type="checkbox" checked={layer.field.visible}
            onChange={(event) => updateLayer(layer.id, { field: { ...layer.field, visible: event.target.checked } })} /> Поле</label>}
          {layer.field?.method === "normal_probability_ellipse" && <label>Вероятность <select value={layer.field.probability}
            onChange={(event) => updateLayer(layer.id, { field: { ...layer.field, probability: Number(event.target.value) } })}>
            <option value={0.90}>90%</option><option value={0.95}>95%</option><option value={0.99}>99%</option>
          </select></label>}
          <button className="outline-button" type="button" disabled={index === 0} onClick={() => moveLayer(index, -1)}>Назад</button>
          <button className="outline-button" type="button" disabled={index === layers.length - 1} onClick={() => moveLayer(index, 1)}>Вперёд</button>
          <button className="outline-button" type="button" onClick={() => setLayers((current) => current.filter(({ id }) => id !== layer.id))}>Убрать слой</button>
        </fieldset>)}
        <form onSubmit={addLayer}>
          <label>Название слоя<input value={layerName} maxLength={120} onChange={(event) => setLayerName(event.target.value)} /></label>
          <button className="outline-button" type="submit" disabled={!layerName.trim() || !layerInput.length || layers.length >= 32}>Добавить слой из отбора</button>
        </form>
      </details>
      {loadLayouts && <details className="plot-saved-layouts">
        <summary>Сохранённые раскладки</summary>
        {layouts.map(({ id, name }) => <button key={id} className="outline-button" type="button"
          disabled={layoutBusy || busy} onClick={() => restore(id)}>Открыть «{name}»</button>)}
        <form onSubmit={save}>
          <label>Название раскладки<input value={layoutName} maxLength={120}
            onChange={(event) => setLayoutName(event.target.value)} /></label>
          <button className="outline-button" type="submit" disabled={layoutBusy || busy || loading || !layoutName.trim() || !panels.length}>
            Сохранить раскладку
          </button>
        </form>
        {layoutStatus && <p role={layoutStatus.error ? "alert" : "status"}>{layoutStatus.error || layoutStatus.notice}</p>}
      </details>}
    </aside>
    <main>
      <header className="plot-toolbar">
        <label>Область <select value={shape} onChange={(event) => setShape(event.target.value)}>
          <option value="rectangle">Прямоугольник</option><option value="lasso">Лассо</option>
        </select></label>
        <label>Действие <select value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="replace">Новый отбор</option><option value="union">Добавить к отбору</option><option value="subtract">Исключить из отбора</option>
        </select></label>
        <button className="primary-button" type="button" onClick={add} disabled={axes.length < 2 || panels.length >= 32}>Добавить диаграмму</button>
        {onExport && <button className="outline-button" type="button" disabled={exportBusy || loading || !panels.length}
          onClick={() => openExport(null)}>Выгрузить раскладку</button>}
      </header>
      {exportStatus && <p role={exportStatus.error ? "alert" : "status"}>{exportStatus.error || exportStatus.notice}</p>}
      {loading && <p role="status">Загружаю поля проекта…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && !panels.length && <p>Для построения нужны как минимум два поля измерений.</p>}
      <div className={exportOptions ? "plot-content plot-content-export" : "plot-content"}>
        <div className="plot-grid" ref={grid}>
          {!loading && !error && panels.map((panel) => <PlotPanel key={panel.id} panel={panel} axes={axes} load={loadWithLayers} selected={selected} onSelect={select} shape={shape} colorFor={colorFor} layers={layers}
            openExport={onExport && !exportBusy ? () => openExport(panel.id) : undefined}
            update={(next) => setPanels((current) => current.map((item) => item.id === panel.id ? next : item))}
            canRemove={panels.length > 1} remove={() => setPanels((current) => current.filter((item) => item.id !== panel.id))} />)}
        </div>
        {exportOptions && <PlotExport options={exportOptions} panels={panels} pending={exportBusy} submit={submitExport}
          canAddPublication={Boolean(onAddPublication)}
          close={() => setExportOptions(null)} onChange={(values) => setExportOptions((current) => ({ ...current, ...values }))} />}
      </div>
      <footer className="plot-selection-footer"><b>Выбранные анализы · {selectedIds.length}</b>
        {onSetVisibility && selectedIds.some((id) => !hiddenAnalysisIds.includes(id)) &&
          <button type="button" className="outline-button" disabled={busy}
            onClick={() => onSetVisibility(selectedIds, true)}>Скрыть отбор на графиках</button>}
        <button type="button" className="outline-button" onClick={onBack}>Открыть в анализах</button>
      </footer>
    </main>
  </section>;
}
