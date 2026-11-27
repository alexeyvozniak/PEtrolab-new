import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { PLOT_SIZE, buildPlotSvg, plotPanelLabel } from "./plotSvg";
import { ContextActions } from "./ContextActions";
import {duplicatePanel,selectionView} from "./plotQuickActions";
import { CalculatedAxisEditor } from "./CalculatedAxisEditor";
import { SYMBOL_LABELS,symbolGeometry,symbolPaint } from "./plotSymbols";
function PointMarker({symbol,x,y,r,children,fill,...props}) {
  const {tag:Tag,attrs}=symbolGeometry(symbol,x,y,r);
  const paint=symbolPaint(symbol,fill);
  return <Tag {...attrs} {...props} fill={paint.fill} stroke={paint.stroke} strokeWidth={paint["stroke-width"]}>{children}</Tag>;
}
import { makePreset, presetKey, rememberPreset, resolvePreset, templateGroups, MINERAL_TEMPLATES } from "./plotPresets";
import { mergeLayoutColors } from "./workspaceCheckpoint";
import "./plotWorkspace.css";
import {PhotoPlot} from "./PhotoPlot";
import {GrainPreview} from "./GrainPreview";

const VIEW = { ...PLOT_SIZE, left: 55, right: 425, top: 22, bottom: 235 };
const EMPTY_BINS = [];
const DEFAULT_POINT_STYLE = Object.freeze({opacity:1, size_scale:1});
const DEFAULT_FIELD_STYLE = Object.freeze({mode:"both",color:"#5c7d66",fill_opacity:0.26,stroke_width:1});
const COLOR_MODES = { source: "Источник", sample: "Физический образец", mineral: "Минерал (исходное название)", generation: "Generation" };
const CATEGORY_COLORS = ["#356ca2","#ae5431","#39856b","#8c56a1","#bf8a28","#be456e","#367f91","#75643c","#647a2c","#485496","#ad675c","#7a7294","#248277","#a43d91","#66533f","#b67513"];
const MISSING_COLOR = "#8c9590";
function categoryStyle(rows, mode, overrides, symbols) {
  if (mode === "source" || !rows) return null;
  const byId = new Map(), groups = new Map();
  for (const row of rows) {
    const raw = mode === "sample" ? row.sample_id : mode === "generation" ? row.generation_id : row.reported_mineral;
    const name = mode === "sample" ? row.sample_name : mode === "generation" ? row.generation_name : row.reported_mineral;
    const key = raw == null || String(raw).trim() === "" ? null : String(raw);
    byId.set(row.analysis_id, key);
    if (!groups.has(key)) groups.set(key, { key, label: key === null ? "Не указано" : String(name || raw), count: 0 });
    groups.get(key).count++;
  }
  const entries = [...groups.values()].sort((a,b) => a.key === null ? 1 : b.key === null ? -1 : a.label.localeCompare(b.label,"ru") || a.key.localeCompare(b.key));
  const names = new Map();
  entries.forEach(entry => names.set(entry.label,(names.get(entry.label)||0)+1));
  entries.forEach((entry,index) => {
    if (entry.key !== null && names.get(entry.label)>1) entry.label += " · " + entry.key.slice(0,8);
    entry.color = entry.key === null ? MISSING_COLOR : overrides.get(JSON.stringify([mode,entry.key])) || CATEGORY_COLORS[index % CATEGORY_COLORS.length];
    const symbol=entry.key===null ? undefined : symbols.get(JSON.stringify([mode,entry.key]));
    if(symbol)entry.symbol=symbol;
  });
  const colors = new Map(entries.map(entry => [entry.key,entry.color]));
  const shapes=new Map(entries.map(entry=>[entry.key,entry.symbol||"circle"]));
  return {entries, snapshot: {mode,entries,assignments:Object.fromEntries(byId)}, colorFor: id => colors.get(byId.get(id) ?? null) || MISSING_COLOR,
    symbolFor:id=>shapes.get(byId.get(id)??null)||"circle"};
}
const AXIS_DRAG_TYPE = "application/x-petrolab-axis";
const KDE_METHOD = "gaussian_kde_v1";
const KDE_DEFAULTS = { bandwidth_x: 0.10, bandwidth_y: 0.10, level: 0.50 };
const hasFieldGeometry = (field) => field.vertices.length >= 3 || Boolean(field.rings?.length);
function PointTooltip({ hover, detail, shift, loadAnalysis, grain }) {
  if (!hover) return null;
  const { point, x, y } = hover;
  const analysis = detail?.analysis;
  const rows = analysis?.measurement_list || Object.entries(analysis?.measurements || {}).map(([field, value]) => ({ field, ...value }));
  return <div className="plot-point-tooltip" role="tooltip" style={{
    left: Math.max(8, Math.min(x + 12, window.innerWidth - 328)),
    top: Math.max(8, Math.min(y + 12, window.innerHeight - (shift ? 370 : grain?.loadPhotos ? 240 : 130))),
  }}>
    <b>{point.label}</b><small>{point.source_name || ""}</small>
    {point.axisValues?.map((item, index) => <div key={index}>{item}</div>)}
    {grain?.loadPhotos && <GrainPreview key={point.analysis_id + ":" + grain.mediaId} id={point.analysis_id} {...grain}/>}
    {shift && loadAnalysis ? <>
      {detail?.error ? <small>Состав недоступен: {detail.error}</small> : !analysis ? <small>Загружаю состав…</small> : <>
        {analysis.identity?.Sample && <small>Образец: {analysis.identity.Sample}</small>}
        <small>Исходные измерения (без пересчёта)</small>
        <div className="plot-tooltip-measurements">{rows.slice(0, 20).map((row, index) =>
          <span key={index} title={row.source_cell || ""}>{row.field}: {row.raw_token ?? "∅"} {row.unit}</span>)}</div>
        {rows.length > 20 && <small>Ещё {rows.length - 20} измерений — в карточке анализа.</small>}
      </>}
    </> : <small>Shift — исходный состав; двойной клик — анализ</small>}
  </div>;
}
const selectionModifier = (event) => event.altKey ? "subtract" : event.ctrlKey || event.metaKey ? "toggle" : event.shiftKey ? "union" : undefined;
const FULL_VIEW = { x: 0, y: 0, width: VIEW.width, height: VIEW.height };
const px = (value) => VIEW.left + value * (VIEW.right - VIEW.left);
const py = (value) => VIEW.bottom - value * (VIEW.bottom - VIEW.top);
const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
const axisKey = (axis) => JSON.stringify([axis.field, axis.unit, axis.measurement_set, axis.method]);
const isCalculatedAxis = (axis) => Boolean(axis?.calculation || axis?.formula);
const axisLabel = (axis) => [axis.field, axis.unit, axis.measurement_set, axis.method,
  axis.formula && `версия ${axis.formula.method_version}`].filter(Boolean).join(" · ");
const exclusionLabels = {
  missing: "отсутствует измерение", no_matching_axes: "отсутствуют поля осей",
  duplicate_measurements: "несколько измерений", incompatible_iron_form: "другая форма железа",
  below_detection_limit: "ниже предела обнаружения", not_determined: "значение не определено",
  zero_denominator: "нулевой знаменатель", negative_operand: "отрицательный операнд",
  negative_component: "отрицательная компонента", zero_component_sum: "нулевая сумма компонент",
  formula_run_missing: "нет выбранной формулы", formula_run_stale: "формула устарела",
  formula_component_missing: "компонента нет в формуле", calculation_out_of_range: "значение вне диапазона",
};
const SERIES_COLORS = ["#3b70a0", "#a75d32", "#7654a3", "#34796d", "#ae4563", "#755b36", "#4a6584", "#84506d"];
const PATTERN_LABELS = { ree_pattern: "Диаграмма РЗЭ", spider: "Спайдер-диаграмма" };
const REFERENCE_LABELS = { "C1 chondrite": "Хондрит C1", "Primitive mantle (diagram values)": "Примитивная мантия" };
const referenceLabel = (reference) => REFERENCE_LABELS[reference.label] || reference.label;
const measurementGroup = (axis) => JSON.stringify([axis.method, axis.measurement_set]);
const panelTitle = (panel) => PATTERN_LABELS[panel.kind] || (panel.kind === "histogram"
  ? `Гистограмма · ${panel.axes[0].field}` : panel.axes.map((axis) => axis.field).join(" / "));

function patternGroups(axes, pattern) {
  const groups = new Map();
  for (const axis of axes) {
    if (!["ppm", "ppb"].includes(axis.unit) || !pattern.elements.includes(axis.field)) continue;
    const key = measurementGroup(axis);
    if (!groups.has(key)) groups.set(key, { key, label: [axis.method, axis.measurement_set].filter(Boolean).join(" · ") || "Без обозначения", fields: new Map() });
    const { fields } = groups.get(key);
    if (!fields.has(axis.field)) fields.set(axis.field, []);
    fields.get(axis.field).push(axis);
  }
  return [...groups.values()].filter(({ fields }) => fields.size >= 2).map((group) => ({ ...group,
    axes: pattern.elements.flatMap((element) => {
      const candidates = group.fields.get(element);
      return candidates ? [candidates.find((axis) => axis.unit === "ppm") || candidates[0]] : [];
    }),
  }));
}

function patternPath(vertices) {
  let connected = false;
  return vertices.map(({ u, v }) => {
    if (v === null) {
      connected = false;
      return "";
    }
    const command = connected ? "L" : "M";
    connected = true;
    return `${command} ${px(u)} ${py(v)}`;
  }).filter(Boolean).join(" ");
}

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
  if (axes.length === 0) return [];
  if (axes.length === 1) return [{ id: crypto.randomUUID(), kind: "histogram", axes: [axes[0]] }];
  const compatible = axes.find((axis) => ["wt.%", "ppm", "ppb"].includes(axis.unit) &&
    axes.filter((item) => item.unit === axis.unit && item.measurement_set === axis.measurement_set && item.method === axis.method).length >= 3);
  const make = (kind, selected) => ({ id: crypto.randomUUID(), kind, axes: selected });
  return [make("binary", axes.slice(0, 2)), compatible
    ? make("ternary", axes.filter((item) => item.unit === compatible.unit && item.measurement_set === compatible.measurement_set && item.method === compatible.method).slice(0, 3))
    : make("binary", [axes[1], axes[0]])];
}

function PlotCanvas({ data, selected, onSelect, onOpenAnalysis, onOpenPhotos, loadAnalysis, grain, shape, colorFor, categoryColor, categorySymbol, points, fieldStyles, pointStyle = DEFAULT_POINT_STYLE, rememberedView, rememberView }) {
  const drag = useRef(null);
  const canvas = useRef(null);
  const hovered = useRef(false);
  const space = useRef(false);
  const [rubber, setRubber] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [hover, setHover] = useState(null);
  const [shift, setShift] = useState(false);
  const [detail, setDetail] = useState(null);
  const hoveredId = hover?.point.analysis_id;
  useEffect(() => {
    if (!hoveredId) return;
    const down = event => { if (event.key === "Shift") setShift(true); };
    const up = event => { if (event.key === "Shift") setShift(false); };
    const clear = () => { setHover(null); setShift(false); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    window.addEventListener("scroll", clear, true);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
      window.removeEventListener("scroll", clear, true);
    };
  }, [hoveredId]);
  useEffect(() => {
    setDetail(null);
    if (!hoveredId || !shift || !loadAnalysis) return;
    let active = true;
    loadAnalysis(hoveredId).then(analysis => {
      if (active) setDetail({ id: hoveredId, analysis });
    }, error => { if (active) setDetail({ id: hoveredId, error: error.message || String(error) }); });
    return () => { active = false; };
  }, [hoveredId, shift, loadAnalysis]);
  const showPoint = (event, point) => {
    if (drag.current || contextMenu) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setShift(Boolean(event.shiftKey));
    setHover({ point, x: rect.right, y: rect.top });
  };
  const [view, setView] = useState(rememberedView || FULL_VIEW);
  useLayoutEffect(() => { rememberView?.(view); }, [view, rememberView]);
  const zoomed = view.width < FULL_VIEW.width;
  useEffect(() => {
    const svg = canvas.current;
    const wheel = (event) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      if (!event.deltaY || drag.current) return;
      const bounds = svg.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      const x = clamp((event.clientX - bounds.left) / bounds.width, 0, 1);
      const y = clamp((event.clientY - bounds.top) / bounds.height, 0, 1);
      setView((current) => {
        const width = clamp(current.width * (event.deltaY > 0 ? 1.25 : 0.8), FULL_VIEW.width / 8, FULL_VIEW.width);
        const height = width * FULL_VIEW.height / FULL_VIEW.width;
        return {
          x: clamp(current.x + x * (current.width - width), 0, FULL_VIEW.width - width),
          y: clamp(current.y + y * (current.height - height), 0, FULL_VIEW.height - height),
          width, height,
        };
      });
    };
    const keyDown = (event) => {
      if (!event.ctrlKey && !event.altKey && !event.metaKey && event.code === "Space" && (hovered.current || event.target === svg)
          && !event.target.closest?.("button, input, select, textarea, [role=button], [contenteditable=true]")) {
        event.preventDefault();
        space.current = true;
      }
    };
    const releaseSpace = () => { space.current = false; };
    const keyUp = (event) => { if (event.code === "Space") releaseSpace(); };
    svg.addEventListener("wheel", wheel, { passive: false });
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    window.addEventListener("blur", releaseSpace);
    return () => {
      svg.removeEventListener("wheel", wheel);
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      window.removeEventListener("blur", releaseSpace);
    };
  }, []);
  const isPattern = Boolean(data.normalization);
  const isHistogram = data.kind === "histogram";
  const denseLabels = isPattern && data.axes.length > 20;
  const bins = data.bins || EMPTY_BINS;
  const bars = useMemo(() => bins.flatMap((bin) => bin.series.map((series) => ({
    ...series, ...bin, u: (bin.left + bin.right) / 2, v: series.base + series.height / 2,
    label: `${bin.lower}–${bin.upper} · ${series.analysis_ids.length} анализов`,
  }))), [bins]);
  const maximumCount = useMemo(() => bins.reduce((max, bin) => Math.max(max, bin.count), 1), [bins]);
  const selectedCounts = bins.map((bin) => bin.series.flatMap((series) => series.analysis_ids)
    .filter((id) => selected.has(id)).length);
  const selectedOutline = selectedCounts.some(Boolean)
    ? `M ${px(bins[0].left)} ${VIEW.bottom} ${bins.map((bin, index) =>
      `V ${py(selectedCounts[index] / maximumCount)} H ${px(bin.right)}`).join(" ")} V ${VIEW.bottom}`
    : "";
  const markers = useMemo(() => isHistogram ? bars : points.flatMap((point) => isPattern ? point.vertices.filter(({ v }) => v !== null).map((vertex, index) => ({
    ...vertex, analysis_id: point.analysis_id, source_id: point.source_id, source_name: point.source_name, opacity: point.opacity,
    axisValues: [`${vertex.element}: ${vertex.ratio.toPrecision(5)} · отношение к эталону`],
    tabIndex: index === 0 ? 0 : -1,
    label: `${point.label} · ${vertex.element}`, title: `${point.label} · ${point.source_name} · ${vertex.element}: ${vertex.ratio.toPrecision(5)}`,
  })) : [{ ...point, axisValues: data.axes.map((axis, index) => `${axis.field}: ${point.values[index]} ${axis.unit}`),
    title: `${point.label} · ${point.source_name} · ${point.values.join(" / ")}` }]), [isHistogram, bars, points, isPattern, data.axes]);
  const contains = (x, y) => x >= view.x && x <= view.x + view.width && y >= view.y && y <= view.y + view.height;
  const visibleMarkers = useMemo(() => zoomed ? markers.filter((point) => contains(px(point.u), py(point.v))) : markers, [markers, view, zoomed]);
  const paths = useMemo(() => isPattern ? points.map(point => ({ point, path: patternPath(point.vertices) })) : [], [isPattern, points]);
  const position = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: view.x + (event.clientX - bounds.left) * view.width / bounds.width,
      y: view.y + (event.clientY - bounds.top) * view.height / bounds.height };
  };
  const start = (event) => {
    setHover(null);
    if (event.button === 1 || (event.button === 0 && space.current)) {
      event.preventDefault();
      if (!zoomed) return;
      drag.current = { pointer: event.pointerId, pan: view, x: event.clientX, y: event.clientY };
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (event.button !== 0 || (event.pointerType === "touch" && !event.isPrimary)) return;
    const point = position(event);
    drag.current = { origin: point, pointer: event.pointerId, trail: [point], analysisId: event.target.dataset?.analysisId,
      barIndex: event.target.dataset?.plotBar, modifier: selectionModifier(event) };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const move = (event) => {
    if (drag.current?.pointer !== event.pointerId) return;
    if (drag.current.pan) {
      const { pan, x, y } = drag.current;
      const bounds = event.currentTarget.getBoundingClientRect();
      setView({ ...pan,
        x: clamp(pan.x + (x - event.clientX) * pan.width / bounds.width, 0, FULL_VIEW.width - pan.width),
        y: clamp(pan.y + (y - event.clientY) * pan.height / bounds.height, 0, FULL_VIEW.height - pan.height),
      });
      return;
    }
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
    if (drag.current.pan) { drag.current = null; return; }
    const first = drag.current.origin;
    const trail = drag.current.trail;
    const pressedAnalysisId = drag.current.analysisId;
    const pressedBar = bars[drag.current.barIndex];
    const modifier = drag.current.modifier;
    const last = position(event);
    drag.current = null;
    setRubber(null);
    const freehand = shape === "lasso" && trail.length >= 3;
    if (!freehand && Math.hypot(first.x - last.x, first.y - last.y) < 4 * view.width / VIEW.width) {
      if (isHistogram) {
        if (pressedBar) onSelect(pressedBar.analysis_ids, modifier);
        else if (!modifier) onSelect([], "replace");
        return;
      }
      const hit = visibleMarkers.findLast((point) => Math.hypot(px(point.u) - last.x, py(point.v) - last.y) <= Math.max(7 * view.width / VIEW.width, (isPattern ? 2.5 : 3.5) * pointStyle.size_scale));
      const id = hit?.analysis_id || pressedAnalysisId;
      if (id) onSelect([id], modifier);
      else if (!modifier) onSelect([], "replace");
      return;
    }
    if (shape === "lasso" && !freehand) return;
    const inside = (current, a, b) => current >= Math.min(a, b) && current <= Math.max(a, b);
    onSelect([...new Set(visibleMarkers.filter((point) => freehand
      ? insidePolygon({ x: px(point.u), y: py(point.v) }, [...trail, last])
      : inside(px(point.u), first.x, last.x) && inside(py(point.v), first.y, last.y))
      .flatMap((point) => point.analysis_ids || [point.analysis_id]))], modifier);
  };
  const clear = () => { drag.current = null; setRubber(null); };
  const zoomTarget=useMemo(()=>["binary","ternary"].includes(data.kind)?selectionView(
    markers.filter(point=>selected.has(point.analysis_id)).map(point=>({x:px(point.u),y:py(point.v)})),FULL_VIEW):null,[data.kind,markers,selected]);
  return <>
  {zoomTarget&&<button type="button" className="outline-button" onClick={()=>{clear();setHover(null);setView(zoomTarget);}}>Приблизить выделенные точки</button>}
  {zoomed && <button type="button" className="outline-button plot-reset-zoom" onClick={() => setView(FULL_VIEW)}>Автомасштаб</button>}
  <svg ref={canvas} className="plot-canvas" viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} aria-label="Диаграмма"
    tabIndex={0} onPointerEnter={() => { hovered.current = true; }} onPointerLeave={() => { hovered.current = false; setHover(null); }}
    onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (drag.current) clear();
        else if (zoomed) setView(FULL_VIEW);
        else onSelect([], "replace");
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a" && !event.altKey) {
        event.preventDefault();
        onSelect([...new Set(visibleMarkers.flatMap(point => point.analysis_ids || [point.analysis_id]))], "replace");
      } else if (event.key === "Home" && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        setView(FULL_VIEW);
      }
    }}
    onContextMenu={event => {
      if (isHistogram) return;
      const id = event.target.closest?.("[data-analysis-id]")?.dataset.analysisId;
      if (!id) return;
      event.preventDefault();
      setHover(null);
      setContextMenu({ id, label: points.find(point => point.analysis_id === id)?.label || "Анализ", x: event.clientX, y: event.clientY });
    }}
    onDoubleClick={(event) => {
      if (isHistogram || selectionModifier(event)) return;
      const last = position(event);
      const hit = visibleMarkers.findLast(point => Math.hypot(px(point.u) - last.x, py(point.v) - last.y) <= Math.max(7 * view.width / VIEW.width, (isPattern ? 2.5 : 3.5) * pointStyle.size_scale));
      const id = hit?.analysis_id || event.target.closest?.("[data-analysis-id]")?.dataset.analysisId;
      if (id) onOpenAnalysis?.(id);
      else setView(FULL_VIEW);
    }}
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
        <text x={px(at)} y={VIEW.bottom + 14} textAnchor={denseLabels ? "end" : "middle"}
          transform={denseLabels ? `rotate(-45 ${px(at)} ${VIEW.bottom + 14})` : undefined}>{label}</text>
      </g>)}
      {(data.ticks[1] || []).map(({ at, label }) => <g key={at}>
        <line x1={VIEW.left} x2={VIEW.right} y1={py(at)} y2={py(at)} />
        <text x={VIEW.left - 5} y={py(at) + 3} textAnchor="end">{label}</text>
      </g>)}
      <text x={px(0.5)} y={VIEW.bottom + (isPattern ? 39 : 34)} textAnchor="middle">{isPattern ? `${referenceLabel(data.normalization)} · Sun и McDonough, 1989`
        : `${data.axes[0].field} (${data.axes[0].unit})`}</text>
      <text transform={`translate(12 ${py(0.5)}) rotate(-90)`} textAnchor="middle">{isPattern ? "Отношение к эталону"
        : isHistogram ? "Число анализов" : `${data.axes[1].field} (${data.axes[1].unit})`}</text>
    </>}
    {(data.fields || []).filter(hasFieldGeometry).map(field=>{
      const style=fieldStyles?.get(field.layer_id);
      const paint = {
        fill: style?.mode === "outline" ? "none" : style?.color || "#99b9a0",
        fillOpacity: style?.fill_opacity ?? 0.26,
        stroke: style?.mode === "fill" ? "none" : style?.color || "#5c7d66",
        strokeWidth: style?.stroke_width ?? 1,
      };
      const coordinates = (ring) => ring.map(([u, v]) => `${px(u)},${py(v)}`).join(" ");
      return field.rings
        ? <path key={field.layer_id} className="plot-field" {...paint} fillRule="evenodd"
            d={field.rings.map((ring) => `M ${coordinates(ring)} Z`).join(" ")} />
        : <polygon key={field.layer_id} className="plot-field" {...paint} points={coordinates(field.vertices)} />;
    })}
    {paths.map(({ point, path }) => <path key={point.analysis_id} className="plot-series" data-analysis-id={point.analysis_id}
      d={path} fill="none" stroke={categoryColor ? categoryColor(point.analysis_id) : colorFor(point.source_id)} strokeWidth={1.25} opacity={point.opacity * pointStyle.opacity} />)}
    {bars.map((bar, index) => {
      const highlighted = bar.analysis_ids.some((id) => selected.has(id));
      const rect = { x: px(bar.left), y: py(bar.base + bar.height), width: px(bar.right) - px(bar.left),
        height: py(bar.base) - py(bar.base + bar.height) };
      const inView = rect.x < view.x + view.width && rect.x + rect.width > view.x
        && rect.y < view.y + view.height && rect.y + rect.height > view.y;
      return <g key={`${bar.lower}:${bar.source_id}`}>
        <rect className="plot-point" data-plot-bar={index} {...rect} fill={colorFor(bar.source_id)} role="button"
          tabIndex={inView ? 0 : -1} aria-hidden={inView ? undefined : true}
          aria-label={`Выбрать интервал ${bar.label}`} aria-pressed={highlighted}
          onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(bar.analysis_ids, selectionModifier(event)); } }}>
          <title>{bar.label}</title>
        </rect>
      </g>;
    })}
    {selectedOutline && <path className="plot-halo" d={selectedOutline} />}
    {!isHistogram && markers.map((point) => <g key={`${point.analysis_id}:${point.element || ""}`}>
      <PointMarker className="plot-point" data-analysis-id={point.analysis_id} fill={categoryColor ? categoryColor(point.analysis_id) : colorFor(point.source_id)}
        symbol={categorySymbol ? categorySymbol(point.analysis_id) : pointStyle.symbol || "circle"} x={px(point.u)} y={py(point.v)} r={(isPattern ? 2.5 : 3.5) * pointStyle.size_scale} role="button"
        tabIndex={!zoomed || contains(px(point.u), py(point.v)) ? point.tabIndex ?? 0 : -1}
        aria-hidden={zoomed && !contains(px(point.u), py(point.v)) ? true : undefined}
        opacity={point.opacity * pointStyle.opacity}
        aria-label={`Выбрать точку ${point.label}`} aria-pressed={selected.has(point.analysis_id)}
        onMouseEnter={event => showPoint(event, point)} onMouseLeave={() => setHover(null)}
        onFocus={event => showPoint(event, point)} onBlur={() => setHover(null)}
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect([point.analysis_id], selectionModifier(event)); } }}>
        <title>{point.title}</title>
      </PointMarker>
    </g>)}
    {!isHistogram && markers.filter((point) => selected.has(point.analysis_id)).map((point) =>
      <circle key={`${point.analysis_id}:${point.element || ""}`} className="plot-halo" cx={px(point.u)} cy={py(point.v)} r={(isPattern ? 2.5 : 3.5) * pointStyle.size_scale + 2.5} />)}
    {rubber && (rubber.path ? <polygon className="plot-rubber" points={rubber.path} /> : <rect className="plot-rubber" {...rubber} />)}
  </svg>
  <PointTooltip hover={hover} shift={shift} detail={detail?.id === hoveredId ? detail : null} loadAnalysis={loadAnalysis} grain={grain}/>
  <ContextActions menu={contextMenu} onClose={() => setContextMenu(null)} actions={contextMenu ? [
    { label: "Открыть анализ", disabled: !onOpenAnalysis, run: () => onOpenAnalysis(contextMenu.id) },
    ...(onOpenPhotos?[{label:"Показать фотографии анализа",run:()=>onOpenPhotos(contextMenu.id)}]:[]),
    { label: selected.has(contextMenu.id) ? "Снять выделение" : "Добавить к отбору", run: () => onSelect([contextMenu.id], "toggle") },
    { label: "Выбрать только этот анализ", run: () => onSelect([contextMenu.id], "replace") },
  ] : []} /></>;
}

function PlotPanel({ panel, axes, patterns, load, loadCatalog, update, remove, duplicate, selected, onSelect, onOpenAnalysis, onOpenPhotos, loadAnalysis, grain, canRemove, shape, colorFor, openExport, layers, viewMemory, favorite, onFavorite, categoryColor, categorySymbol, onApplyStyle }) {
  const [projection, setProjection] = useState(null);
  const projectionPanel = useMemo(() => ({kind:panel.kind, axes:panel.axes, normalization:panel.normalization}), [panel.kind, panel.axes, panel.normalization]);
  const current = projection?.load === load && projection.panel === projectionPanel ? projection : null;
  const pointStyle = panel.point_style || DEFAULT_POINT_STYLE;
  const setPointStyle = values => update({...panel,point_style:{...pointStyle,...values}});
  const data = current?.data;
  const calculated = panel.axes.some(isCalculatedAxis);
  const exclusions = {};
  if (calculated) {
    for (const { reason } of data?.exclusions || []) {
      const label = exclusionLabels[reason] || "непригодное измерение";
      exclusions[label] = (exclusions[label] || 0) + 1;
    }
  }
  const styles = useMemo(() => {
    const result = new Map();
    const available = new Set((data?.fields || []).filter(hasFieldGeometry).map(field=>field.layer_id));
    layers.forEach(({ id:layerId, analysis_ids, opacity, show_points, field }, order) => {
      const fallback = field?.visible && !available.has(layerId);
      for (const id of analysis_ids) result.set(id, { order, opacity: show_points || fallback ? (fallback && !show_points ? 1 : opacity) : 0 });
    });
    return result;
  }, [layers,data]);
  const fieldStyles = useMemo(()=>new Map(layers.filter(layer=>layer.field?.style).map(layer=>[layer.id,layer.field.style])),[layers]);
  const points = useMemo(() => panel.kind === "histogram" ? data?.points || [] : (data?.points || []).map((point) => ({ ...point, ...(styles.get(point.analysis_id) || { opacity: 1, order: -1 }) }))
    .filter((point) => point.opacity > 0).sort((a, b) => a.order - b.order), [panel.kind, data, styles]);
  const status = current ? current.error : "Загружаю диаграмму…";
  const pattern = patterns[panel.kind];
  const group = pattern?.groups.find(({ key }) => key === measurementGroup(panel.axes[0]));
  useEffect(() => {
    let active = true;
    load(projectionPanel.kind, projectionPanel.axes, projectionPanel.normalization).then((result) => {
      if (active) setProjection({ load, panel:projectionPanel, data: result });
    }).catch((error) => { if (active) setProjection({ load, panel:projectionPanel, error: error.message }); });
    return () => { active = false; };
  }, [load, projectionPanel]);
  const updateKind = (kind) => {
    if (kind === "histogram") {
      update({ id: panel.id, kind, axes: [isCalculatedAxis(panel.axes[0]) ? axes[0] : panel.axes[0]] });
      return;
    }
    if (patterns[kind]) {
      const { groups, default_normalization } = patterns[kind];
      update({ id: panel.id, kind, axes: groups[0].axes, normalization: default_normalization, ...(panel.point_style ? {point_style:panel.point_style} : {}) });
      return;
    }
    const next = initialPanels(axes).find((item) => item.kind === kind);
    update({ id: panel.id, kind, axes: next ? next.axes : axes.slice(0, 3), ...(panel.point_style ? {point_style:panel.point_style} : {}) });
  };
  const updateAxis = (index, axis) => {
    if (!axis) return;
    update({ ...panel, axes: panel.axes.map((value, position) => position === index ? axis : value) });
  };

  return <article className="plot-panel" id={`plot-${panel.id}`}>
    <header><b>{panelTitle(panel)}</b>
      <div className="plot-panel-actions">
        {onFavorite && <button type="button" className="outline-button" aria-label={favorite ? "Убрать диаграмму из избранного" : "Добавить диаграмму в избранное"}
          aria-pressed={favorite} disabled={!makePreset(panel)} title="Избранное сохраняет комбинацию осей, а не исходные данные" onClick={onFavorite}>{favorite ? "★" : "☆"}</button>}
        {openExport && <button type="button" className="outline-button" disabled={!data} onClick={openExport}>Выгрузить панель</button>}
        {duplicate&&<button type="button" className="outline-button" onClick={duplicate} title="Копирует оси и оформление, но не текущий масштаб">Дублировать диаграмму</button>}
        {canRemove && <button type="button" className="outline-button" onClick={remove}>Убрать панель</button>}
      </div>
    </header>
    <div className="plot-panel-controls">
      <select aria-label="Тип диаграммы" value={panel.kind} onChange={(event) => updateKind(event.target.value)}>
        <option value="binary" disabled={axes.length < 2}>Бинарная</option>
        <option value="ternary" disabled={axes.length < 3}>Тройная</option>
        <option value="histogram" disabled={isCalculatedAxis(panel.axes[0]) && !axes.length}>Гистограмма</option>
        {Object.entries(PATTERN_LABELS).map(([kind, label]) =>
          <option key={kind} value={kind} disabled={!patterns[kind]?.groups.length}>{label}</option>)}
      </select>
      {pattern && <select aria-label="Эталон нормировки" value={panel.normalization}
        onChange={(event) => update({ ...panel, normalization: event.target.value })}>
        {pattern.normalizations.map((reference) => <option key={reference.id} value={reference.id}>{referenceLabel(reference)}</option>)}
      </select>}
      {pattern && pattern.groups.length > 1 && <select aria-label="Аналитический набор спектра" value={group?.key}
        onChange={(event) => update({ ...panel, axes: pattern.groups.find(({ key }) => key === event.target.value).axes })}>
        {pattern.groups.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
      </select>}
      {panel.axes.map((axis, index) => {
        const locked = isCalculatedAxis(axis);
        const candidates = locked ? [axis,...axes.filter(item=>axisKey(item)!==axisKey(axis))] : pattern ? group?.fields.get(axis.field) || [] : axes;
        if (pattern && candidates.length < 2) return null;
        return <select key={index} aria-label={pattern ? `Предпочтительная единица ${axis.field}` : `Ось ${index + 1}`} value={axisKey(axis)}
          title={locked ? axisLabel(axis) : "Выберите поле или перетащите его из каталога осей"}
          onDragOver={event => {
            if (!locked && event.dataTransfer.types.includes(AXIS_DRAG_TYPE)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }
          }}
          onDrop={event => {
            if (locked) return;
            const key = event.dataTransfer.getData(AXIS_DRAG_TYPE);
            if (!key) return;
            event.preventDefault();
            updateAxis(index, candidates.find(item => axisKey(item) === key));
          }}
          onChange={(event) => updateAxis(index, candidates.find((item) => axisKey(item) === event.target.value))}>
          {candidates.map((item) => <option key={axisKey(item)} value={axisKey(item)}>{axisLabel(item)}</option>)}
        </select>;
      })}
    </div>
    {["binary","ternary"].includes(panel.kind)&&<CalculatedAxisEditor key={panel.kind} axes={axes} loadCatalog={loadCatalog} panel={panel} apply={updateAxis}/>}
    {panel.kind !== "histogram" && <details className="plot-point-style">
      <summary>Оформление точек · {Math.round(pointStyle.opacity*100)}%</summary>
      <label>Непрозрачность · {Math.round(pointStyle.opacity*100)}%
        <input type="range" aria-label="Непрозрачность точек панели" min="0.05" max="1" step="0.05" value={pointStyle.opacity}
          onChange={event=>setPointStyle({opacity:Number(event.target.value)})}/></label>
      <label>Размер · {Math.round(pointStyle.size_scale*100)}%
        <input type="range" aria-label="Размер точек панели" min="0.5" max="2" step="0.1" value={pointStyle.size_scale}
          onChange={event=>setPointStyle({size_scale:Number(event.target.value)})}/></label>
      <label>Форма точек <select aria-label="Форма точек панели" disabled={Boolean(categorySymbol)} value={pointStyle.symbol || "circle"}
        onChange={event=>setPointStyle({symbol:event.target.value})}>
        {Object.entries(SYMBOL_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}
      </select></label>
      {categorySymbol && <small>Форма определяется категориями в легенде.</small>}
      <div className="plot-style-actions">
        <button type="button" className="outline-button" onClick={()=>update({...panel,point_style:{...DEFAULT_POINT_STYLE}})}>Сбросить оформление точек</button>
        {onApplyStyle && <button type="button" className="outline-button" onClick={()=>onApplyStyle(pointStyle)}>Применить оформление ко всем диаграммам</button>}
      </div>
      <small>Прозрачность умножается на непрозрачность слоя. Выделение остаётся контуром; гистограммы не изменяются.</small>
    </details>}
    {status && <p role="status">{status}</p>}
    {data && <>
      <PlotCanvas key={data.projection_sha256} data={data} selected={selected} onSelect={onSelect} onOpenAnalysis={onOpenAnalysis} onOpenPhotos={onOpenPhotos} loadAnalysis={loadAnalysis} grain={grain} shape={shape} colorFor={colorFor} categoryColor={categoryColor} categorySymbol={categorySymbol} points={points} fieldStyles={fieldStyles} pointStyle={pointStyle}
        rememberedView={viewMemory?.views.get(panel.id)?.fingerprint === data.projection_sha256 ? viewMemory.views.get(panel.id).view : undefined}
        rememberView={view => viewMemory?.views.set(panel.id, { fingerprint: data.projection_sha256, view })} />
      <small>{pattern ? "Спектров" : panel.kind === "histogram" ? "Анализов" : "Точек"}: {points.length} из {data.input_count}{data.excluded_count ? ` · пропущено: ${data.excluded_count}` : ""}
        {data.hidden_count ? ` · скрыто: ${data.hidden_count}` : ""}
        {data.points.length > points.length ? ` · скрыто стилем слоя: ${data.points.length - points.length}` : ""}
        {data.kind === "ternary" ? " · доли от суммы трёх компонентов" : ""}</small>
      {Object.keys(exclusions).length > 0 && <small className="plot-exclusion-summary">{Object.entries(exclusions)
        .map(([reason, count]) => `${reason} (${count})`).join(" · ")}</small>}
      {(data.fields || []).filter((field) => field.message).map((field) =>
        <p key={field.layer_id}><small>{layers.find((layer) => layer.id === field.layer_id)?.name}: {field.message}{!hasFieldGeometry(field) && layers.some(layer=>layer.id===field.layer_id && !layer.show_points) ? " Маркеры показаны вместо поля." : ""}</small></p>)}
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

function PlotSelectionTable({ ids, load, hiddenAnalysisIds, hiddenSourceIds }) {
  const limit = 25;
  const [page, setPage] = useState(null);
  const [response, setResponse] = useState(null);
  const offset = page?.ids === ids ? page.offset : 0;
  useEffect(() => {
    if (!ids.length) return;
    let active = true;
    load(ids, offset, limit)
      .then((result) => { if (active) setResponse({ ids, offset, result }); })
      .catch((error) => { if (active) setResponse({ ids, offset, error: error.message || String(error) }); });
    return () => { active = false; };
  }, [ids, offset, load]);
  if (!ids.length) return <p>В отборе пока нет анализов.</p>;
  const current = response?.ids === ids && response.offset === offset ? response : null;
  if (!current) return <p role="status">Загружаю выбранные анализы…</p>;
  if (current.error) return <p role="alert">{current.error}</p>;
  const { analyses, total, has_more: hasMore } = current.result;
  const hiddenAnalyses = new Set(hiddenAnalysisIds);
  const hiddenSources = new Set(hiddenSourceIds);
  return <>
    {total < ids.length && <p role="status">Недоступно анализов: {ids.length - total}.</p>}
    {analyses.length > 0 && <div className="plot-selection-scroll">
      <table aria-label="Таблица выбранных анализов">
        <thead><tr><th>Анализ</th><th>Образец</th><th>Минерал</th><th>Метод</th><th>Источник</th><th>На графиках</th></tr></thead>
        <tbody>{analyses.map((row) => <tr key={row.analysis_id} data-analysis-id={row.analysis_id}>
          <th scope="row" title={row.analysis_id}>{row.identity}</th>
          <td>{row.sample_name || "—"}</td><td>{row.mineral || "—"}</td><td>{row.method || "—"}</td>
          <td title={row.source_id}>{row.source_name} · {row.sheet_name} · {row.source_column_number
            ? `колонка ${row.source_column_number}` : `строка ${row.source_row_number}`}</td>
          <td>{hiddenAnalyses.has(row.analysis_id) || hiddenSources.has(row.source_id) ? "Скрыт" : "Не скрыт"}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    {(offset > 0 || hasMore) && <div className="plot-selection-pages">
      <button type="button" className="outline-button" disabled={offset === 0}
        onClick={() => setPage({ ids, offset: Math.max(0, offset - limit) })}>Назад</button>
      <span>{analyses.length ? `${offset + 1}–${offset + analyses.length} из ${total}` : "На этой странице нет доступных анализов"}</span>
      <button type="button" className="outline-button" disabled={!hasMore}
        onClick={() => setPage({ ids, offset: offset + limit })}>Далее</button>
    </div>}
  </>;
}

export function PlotWorkspace({ loadPhotos, previewPhoto, loadProfile, viewMemory, loadCatalog, loadData, loadSelection, loadAnalysis, selectedIds, setSelectedIds, inputIds, onBack,
  hiddenSourceIds = [], hiddenAnalysisIds = [], onToggleSource, onIsolateSource, onOpenAnalysis, onOpenPhotos, onSetVisibility, onUndoVisibility, busy, loadLayouts, saveLayout, openLayout,
  onExport, onAddPublication, loadColorScheme, saveColorScheme, onSummary, loadPresets, savePresets }) {
  const [photoView,setPhotoView]=useState(()=>viewMemory?.photoView||null);
  const [focusedIds,setFocusedIds]=useState([]);
  useLayoutEffect(()=>{if(viewMemory)viewMemory.photoView=photoView;},[viewMemory,photoView]);
  const [axes, setAxes] = useState([]);
  const [axisQuery, setAxisQuery] = useState("");
  const [axisCatalogOpen, setAxisCatalogOpen] = useState(false);
  const [recentPresets, setRecentPresets] = useState(() => viewMemory?.recentPresets || []);
  const [favoritePresets, setFavoritePresets] = useState(() => viewMemory?.favoritePresets || []);
  const [presetRevision,setPresetRevision] = useState(() => viewMemory?.presetRevision ?? null);
  const [presetBusy,setPresetBusy] = useState(false);
  const [presetStatus,setPresetStatus] = useState("");
  const applyPreferences = result => {
    setRecentPresets(result.preferences.recent);
    setFavoritePresets(result.preferences.favorites);
    setPresetRevision(result.revision);
  };
  useEffect(()=>{
    if (!loadPresets || viewMemory?.presetRevision != null) return;
    let active=true;
    loadPresets().then(result=>{if(active)applyPreferences(result);},
      error=>{if(active)setPresetStatus(error.message || String(error));});
    return ()=>{active=false;};
  },[loadPresets,viewMemory]);
  const persistPresets = async () => {
    setPresetBusy(true);setPresetStatus("");
    try {
      // Recipes must remain exact. The Python validator rejects invalid
      // combinations; unavailable but previously saved recipes are retained.
      const result=await savePresets({favorites:favoritePresets,recent:recentPresets},presetRevision);
      applyPreferences(result);
      setPresetStatus("Избранное и недавние оси сохранены в проекте.");
    } catch(error){setPresetStatus(error.message || String(error));}
    finally{setPresetBusy(false);}
  };
  const reloadPresets = async () => {
    setPresetBusy(true);setPresetStatus("");
    try{applyPreferences(await loadPresets());setPresetStatus("Загружены сохранённые комбинации.");}
    catch(error){setPresetStatus(error.message || String(error));}
    finally{setPresetBusy(false);}
  };
  const [templateName, setTemplateName] = useState(MINERAL_TEMPLATES[0].name);
  const [templateGroupKey, setTemplateGroupKey] = useState("");
  const mineralGroups = useMemo(() => templateGroups(MINERAL_TEMPLATES.find(item => item.name === templateName), axes), [templateName, axes]);
  const mineralGroup = mineralGroups.find(item => item.key === templateGroupKey) || mineralGroups[0];
  useLayoutEffect(() => {
    if (viewMemory) Object.assign(viewMemory, { recentPresets, favoritePresets, presetRevision });
  }, [viewMemory, recentPresets, favoritePresets, presetRevision]);
  const cachedAnalysis = useMemo(() => {
    if (!loadAnalysis) return undefined;
    const cache = new Map();
    return id => {
      if (cache.has(id)) {
        const request = cache.get(id);
        cache.delete(id);
        cache.set(id, request);
        return request;
      }
      const request = Promise.resolve().then(() => loadAnalysis(id));
      cache.set(id, request);
      while (cache.size > 16) cache.delete(cache.keys().next().value);
      request.then(analysis => {
        if ((analysis.measurement_list?.length || Object.keys(analysis.measurements || {}).length) > 1000 && cache.get(id) === request) cache.delete(id);
      }, () => { if (cache.get(id) === request) cache.delete(id); });
      return request;
    };
  }, [loadAnalysis, loadData]);
  const [patterns, setPatterns] = useState({});
  const [panels, setPanels] = useState(() => viewMemory?.panels ?? []);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState(() => viewMemory?.mode ?? "union");
  const [shape, setShape] = useState(() => viewMemory?.shape ?? "rectangle");
  const [selectionExpanded, setSelectionExpanded] = useState(() => viewMemory?.selectionExpanded ?? false);
  const [sources, setSources] = useState([]);
  const [layouts, setLayouts] = useState([]);
  const [layoutName, setLayoutName] = useState("");
  const [layoutStatus, setLayoutStatus] = useState(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [savedColors, setSavedColors] = useState(() => viewMemory?.savedColors ?? {});
  const [colorMode, setColorMode] = useState(() => viewMemory?.colorMode || "source");
  const [categoryResult, setCategoryResult] = useState(null);
  const [schemeColors, setSchemeColors] = useState(() => viewMemory?.schemeColors || []);
  const [schemeRevision, setSchemeRevision] = useState(() => viewMemory?.schemeRevision ?? null);
  const [schemeStatus, setSchemeStatus] = useState("");
  const [schemeBusy,setSchemeBusy] = useState(false);
  const overrides = useMemo(() => new Map(schemeColors.map(entry=>[JSON.stringify([entry.mode,entry.key]),entry.color])),[schemeColors]);
  const applyScheme = result => {
    setColorMode(result.scheme.mode);
    setSchemeColors(result.scheme.colors);
    setSchemeRevision(result.revision);
  };
  useEffect(() => {
    if (!loadColorScheme) return;
    let active = true;
    loadColorScheme().then(result => {
      if (!active) return;
      if (!viewMemory?.schemeLoaded) {
        applyScheme(result);
        if (viewMemory) viewMemory.schemeLoaded = true;
      } else setSchemeRevision(viewMemory.schemeRevision ?? result.revision);
    },error=>{if(active)setSchemeStatus(error.message || String(error));});
    return ()=>{active=false;};
  },[loadColorScheme,viewMemory]);
  useLayoutEffect(()=>{if(viewMemory)Object.assign(viewMemory,{schemeColors,schemeRevision});},[viewMemory,schemeColors,schemeRevision]);
  const symbols=useMemo(()=>new Map(schemeColors.filter(entry=>entry.symbol).map(entry=>[JSON.stringify([entry.mode,entry.key]),entry.symbol])),[schemeColors]);
  const changeColor = (mode,key,color) => setSchemeColors(current=>[...current.filter(entry=>entry.mode!==mode||entry.key!==key),{...current.find(entry=>entry.mode===mode&&entry.key===key),mode,key,color}]);
  const changeSymbol=(entry,symbol)=>setSchemeColors(current=>[...current.filter(item=>item.mode!==colorMode||item.key!==entry.key),
    {mode:colorMode,key:entry.key,color:entry.color,symbol}]);
  const storeScheme = async () => {
    setSchemeBusy(true);setSchemeStatus("");
    try {
      const colors = new Map(schemeColors.map(entry=>[JSON.stringify([entry.mode,entry.key]),entry]));
      for(const source of sources) colors.set(JSON.stringify(["source",source.source_id]),{mode:"source",key:source.source_id,color:colorFor(source.source_id)});
      for(const entry of category?.entries||[]) if(entry.key!==null) colors.set(JSON.stringify([colorMode,entry.key]),{mode:colorMode,key:entry.key,color:entry.color,...(entry.symbol?{symbol:entry.symbol}:{})});
      const result=await saveColorScheme({mode:colorMode,colors:[...colors.values()]},schemeRevision);
      applyScheme(result);
      setSchemeStatus("Цветовая схема сохранена в проекте.");
    } catch(error){setSchemeStatus(error.message || String(error));}
    finally{setSchemeBusy(false);}
  };
  const reloadScheme = async () => {
    setSchemeBusy(true);setSchemeStatus("");
    try{applyScheme(await loadColorScheme());setSchemeStatus("Загружена сохранённая цветовая схема.");}
    catch(error){setSchemeStatus(error.message || String(error));}
    finally{setSchemeBusy(false);}
  };
  useEffect(() => {
    if (colorMode === "source" || categoryResult?.load === loadCatalog) return;
    let active = true;
    loadCatalog(true).then(catalog => {
      if (active) setCategoryResult({load:loadCatalog, rows:catalog.categories || []});
    }, error => { if (active) setCategoryResult({load:loadCatalog, error:error.message || String(error)}); });
    return () => { active = false; };
  }, [colorMode, loadCatalog, categoryResult]);
  const categoryData = categoryResult?.load === loadCatalog ? categoryResult : null;
  const category = useMemo(() => categoryStyle(categoryData?.rows, colorMode, overrides,symbols), [categoryData, colorMode, overrides,symbols]);
  const colorReady = (!loadColorScheme || schemeRevision !== null) && (colorMode === "source" || Boolean(category && !categoryData?.error));
  useLayoutEffect(() => { if (viewMemory) viewMemory.colorMode = colorMode; }, [viewMemory, colorMode]);
  const [layers, setLayers] = useState(() => viewMemory?.layers ?? []);
  const [layerName, setLayerName] = useState("");
  const layerInput = inputIds ? selectedIds.filter((id) => inputIds.includes(id)) : selectedIds;
  // Cache only within this mounted workspace and exact data/visibility/layer
  // scope. Deduplicate in-flight requests; rejected or oversized entries are
  // never retained. No persistent cache across project changes or edits.
  const geometrySignature = JSON.stringify(layers.map((layer) => {
    if (!layer.field) return layer;
    const { style, ...field } = layer.field;
    return { ...layer, field };
  }));
  const geometryLayers=useMemo(()=>JSON.parse(geometrySignature),[geometrySignature]);
  const loadWithLayers = useMemo(() => {
    const cache = new Map();
    return (kind, axes, normalization) => {
      const key = JSON.stringify([kind, axes, normalization]);
      if (cache.has(key)) {
        const entry = cache.get(key);
        cache.delete(key);
        cache.set(key, entry);
        return entry;
      }
      const entry = Promise.resolve().then(() => loadData(kind, axes, geometryLayers, normalization));
      cache.set(key, entry);
      while (cache.size > 4) cache.delete(cache.keys().next().value);
      entry.then(data => {
        const vertices = (data.points || []).reduce((n, point) => n + (point.vertices?.length || 1), 0);
        if (vertices > 30000 && cache.get(key) === entry) cache.delete(key);
      }, () => { if (cache.get(key) === entry) cache.delete(key); });
      return entry;
    };
  }, [loadData, geometryLayers]);
  const [exportStatus, setExportStatus] = useState(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportOptions, setExportOptions] = useState(null);
  const grid = useRef(null);
  const content = useRef(null);
  useLayoutEffect(() => {
    if (!viewMemory) return;
    Object.assign(viewMemory, { opened: true, panels, mode, shape, selectionExpanded, savedColors, layers });
    const ids = new Set(panels.map(panel => panel.id));
    for (const id of viewMemory.views.keys()) if (!ids.has(id)) viewMemory.views.delete(id);
  }, [viewMemory, panels, mode, shape, selectionExpanded, savedColors, layers]);
  useLayoutEffect(() => {
    if (!content.current || !viewMemory || loading) return;
    content.current.scrollTop = viewMemory.scrollTop || 0;
    content.current.scrollLeft = viewMemory.scrollLeft || 0;
  }, [viewMemory, loading]);
  const colorFor = (sourceId) => overrides.get(JSON.stringify(["source",sourceId])) || savedColors[sourceId] || sourceColor(sourceId);
  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    loadCatalog().then((catalog) => {
      if (active) {
        setAxes(catalog.axes);
        setPatterns(Object.fromEntries(Object.entries(catalog.patterns || {}).map(([kind, definition]) =>
          [kind, { ...definition, groups: patternGroups(catalog.axes, definition) }])));
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
      if (!colorReady) throw new Error("Дождитесь загрузки категорий окрашивания.");
      const saved = await saveLayout({
        name: layoutName, analysis_ids: inputIds, panels,
        ...(photoView?{photo_view:photoView}:{}),
        colors: Object.fromEntries(sources.map(({ source_id }) => [source_id, colorFor(source_id)])),
        hidden_analysis_ids: hiddenAnalysisIds, hidden_source_ids: hiddenSourceIds,
        layers, ...(category ? {category_style:category.snapshot} : {}),
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
      setPhotoView(saved.photo_view||null);setFocusedIds([]);
      setColorMode(saved.category_style?.mode || "source");
      setPanels(saved.panels.map(({ id: panelId, kind, axes: savedAxes, normalization, point_style }) => ({
        id: panelId, kind, axes: savedAxes.map(({ scale, manual_range, ...axis }) => axis),
        ...(PATTERN_LABELS[kind] ? { normalization } : {}),
        ...(point_style ? {point_style} : {}),
      })));
      setSavedColors(Object.fromEntries(saved.legend.entries.map(({ value, color }) => [value, color])));
      setSchemeColors(current => mergeLayoutColors(current, saved));
      setLayers(saved.layers || []);
      setLayoutStatus({ notice: `Открыта раскладка «${saved.name}».` });
    } catch (caught) {
      setLayoutStatus({ error: caught.message });
    } finally {
      setLayoutBusy(false);
    }
  };
  const select = (ids, override) => setSelectedIds((current) => {
    const action = override || mode;
    const incoming = new Set(ids);
    if (action === "replace") return [...incoming];
    if (action === "subtract") return current.filter(id => !incoming.has(id));
    if (action === "toggle") {
      const before = new Set(current);
      return [...current.filter(id => !incoming.has(id)), ...[...incoming].filter(id => !before.has(id))];
    }
    return [...new Set([...current, ...incoming])];
  });
  const add = () => setPanels((current) => [...current, initialPanels(axes)[0]]);
  const addPresets = presets => {
    const resolved = presets.map(preset => resolvePreset(preset, axes, patterns));
    if (resolved.some(panel => !panel) || panels.length + resolved.length > 32) return;
    setPanels(current => [...current, ...resolved.map(panel => ({...panel, id:crypto.randomUUID()}))]);
    setRecentPresets(current => presets.reduce((items, preset) => rememberPreset(items, preset), current));
  };
  const toggleFavorite = panel => {
    const preset = makePreset(panel);
    if (!preset || !resolvePreset(preset,axes,patterns) || presetBusy || (loadPresets && presetRevision===null)) return;
    setFavoritePresets(current => current.some(item => presetKey(item) === presetKey(preset))
      ? current.filter(item => presetKey(item) !== presetKey(preset)) : rememberPreset(current,preset,24));
  };
  const presetTitle = preset => {
    const resolved = resolvePreset(preset,axes,patterns);
    return resolved ? panelTitle(resolved) + " · " + resolved.axes.map(axisLabel).join(" / ")
      : preset.keys.map(key => { try { return JSON.parse(key).filter(Boolean).join(" · "); } catch { return key; } }).join(" / ") + " · поля недоступны";
  };
  const movePanel = (fromId, toId) => {
    if (fromId === toId) return;
    setPanels(current => {
      const from = current.findIndex(panel => panel.id === fromId);
      const to = current.findIndex(panel => panel.id === toId);
      if (from < 0 || to < 0) return current;
      const next = [...current];
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  };
  const addLayer = (event) => {
    event.preventDefault();
    setLayers((current) => [...current, { id: crypto.randomUUID(), name: layerName.trim(), analysis_ids: layerInput,
      show_points: true, opacity: 1, field: null }]);
    setLayerName("");
  };
  const addCloud = (ids=layerInput, label=layerName.trim() || "Облако "+(layers.length+1), color=DEFAULT_FIELD_STYLE.color) => {
    if (!ids.length || layers.length>=32) return;
    setLayers(current=>current.length>=32 ? current : [...current,{id:crypto.randomUUID(),name:label.slice(0,120),analysis_ids:[...ids],
      show_points:false,opacity:1,field:{method:"convex_hull",visible:true,probability:null,style:{...DEFAULT_FIELD_STYLE,color}}}]);
    setLayerName("");
  };
  const addCategoryCloud = entry => {
    if (!category) return;
    const ids=Object.entries(category.snapshot.assignments).filter(([,key])=>key===entry.key).map(([id])=>id);
    addCloud(ids,entry.label,entry.color);
  };
  const updateLayer = (id, changes) => setLayers((current) => current.map((layer) => layer.id === id ? { ...layer, ...changes } : layer));
  const moveLayer = (index, offset) => setLayers((current) => {
    const ordered = current.slice();
    [ordered[index], ordered[index + offset]] = [ordered[index + offset], ordered[index]];
    return ordered;
  });
  const hasVisibleFields = layers.some((layer) => layer.field?.visible);
  const displayedPanels = photoView ? panels.filter(panel => photoView.panel_ids.includes(panel.id)) : panels;
  const openExport = (panelId) => {
    if (!colorReady) return;
    const visibleIds = Array.from(grid.current.children).flatMap((node, index) => {
      const area = node.getBoundingClientRect();
      return area.right > 0 && area.left < window.innerWidth && area.bottom > 0 && area.top < window.innerHeight
        ? [displayedPanels[index].id] : [];
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
      id: displayedPanels[panelIndex].id, svg: node.querySelector(".plot-canvas"), panelIndex,
    })).filter(({ id }) => scope === "layout" || (scope === "panel" ? id === panelId : visibleIds.includes(id)));
    if (!requested.length || requested.some(({ svg }) => !svg)) {
      setExportStatus({ error: "Дождитесь загрузки выбранных панелей и проверьте настройки их осей." });
      return;
    }
    setExportBusy(true);
    setExportStatus(null);
    try {
      if (!colorReady) throw new Error("Дождитесь загрузки категорий окрашивания.");
      const hasCategoryPanels = requested.some(({panelIndex}) => displayedPanels[panelIndex].kind !== "histogram");
      const legend = category && hasCategoryPanels ? { title: COLOR_MODES[colorMode] + " · категории входного набора",
        entries: category.entries, histogramNote: requested.some(({panelIndex}) => displayedPanels[panelIndex].kind === "histogram") } : null;
      if (legend && legend.entries.length > 60) throw new Error("Слишком много категорий для читаемой легенды. Сузьте входной набор или выберите окрашивание по источнику.");
      const svg = buildPlotSvg(requested, { ...options, showLabel: requested.length > 1 || options.showLabel,
        alphabet: labels.split("-")[0], uppercase: labels.endsWith("-upper"), legend });
      const base = name.trim().replace(/\.(svg|pdf|png|tiff?)$/i, "");
      if (addToPackage) {
        await onAddPublication({
          name: base || "PetroLab-plot", format, svg, width_mm: options.width, dpi: options.dpi, include_csv: includeCsv,
          analysis_ids: inputIds, layers, hidden_analysis_ids: hiddenAnalysisIds, hidden_source_ids: hiddenSourceIds,
          colors: Object.fromEntries(sources.map(({ source_id }) => [source_id, colorFor(source_id)])),
          ...(legend ? {category_style:category.snapshot} : {}),
          panels: requested.map(({ panelIndex, svg: canvas }) => ({
            ...displayedPanels[panelIndex], projection_sha256: canvas.dataset.plotProjection,
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
      {loadPhotos&&<button type="button" disabled={!panels.length} className="outline-button" onClick={()=>setPhotoView(current=>current?null:{media_asset_id:null,panel_ids:panels.slice(0,3).map(p=>p.id)})}>{photoView?"Закрыть фото":"Фото + диаграммы"}</button>}
      {panels.map((panel, index) => <div className="plot-panel-order" key={panel.id}
        onDragOver={event => { if (event.dataTransfer.types.includes("application/x-petrolab-panel")) event.preventDefault(); }}
        onDrop={event => { const id = event.dataTransfer.getData("application/x-petrolab-panel"); if (id) { event.preventDefault(); movePanel(id, panel.id); } }}>
        <a href={`#plot-${panel.id}`} draggable title="Перетащить для изменения порядка"
          onDragStart={event => { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("application/x-petrolab-panel", panel.id); }}
          onKeyDown={event => {
            if (!event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault();
            const target = panels[index + (event.key === "ArrowUp" ? -1 : 1)];
            if (target) movePanel(panel.id, target.id);
          }}>{index + 1}. {panelTitle(panel)}</a>
        <button type="button" disabled={!index} aria-label={`Переместить панель ${index + 1} выше`} title="Выше · Alt+↑"
          onClick={() => movePanel(panel.id, panels[index - 1].id)}>↑</button>
        <button type="button" disabled={index === panels.length - 1} aria-label={`Переместить панель ${index + 1} ниже`} title="Ниже · Alt+↓"
          onClick={() => movePanel(panel.id, panels[index + 1].id)}>↓</button>
      </div>)}
      <p>{inputIds ? `Входной набор: ${inputIds.length} анализов` : "Входной набор: проект"}</p>
      <details className="plot-axis-catalog" onToggle={event => setAxisCatalogOpen(event.currentTarget.open)}>
        <summary>Каталог осей · {axes.length}</summary>
        {axisCatalogOpen && <>
          <small>Перетащите поле на список выбора оси панели.</small>
          <input aria-label="Поиск полей осей" value={axisQuery} onChange={event => setAxisQuery(event.target.value)} placeholder="SiO2, MgO, La…" />
          <div className="plot-axis-catalog-list">
            {axes.filter(axis => !isCalculatedAxis(axis) && axisLabel(axis).toLowerCase().includes(axisQuery.trim().toLowerCase())).map(axis =>
              <div key={axisKey(axis)} draggable tabIndex={0} title="Перетащить на ось"
                onDragStart={event => { event.dataTransfer.effectAllowed = "copy"; event.dataTransfer.setData(AXIS_DRAG_TYPE, axisKey(axis)); }}>{axisLabel(axis)}</div>)}
          </div>
        </>}
      </details>
      <details className="plot-presets">
        <summary>Избранное и недавние оси</summary>
        <small>Сохраните комбинации осей, чтобы использовать их при следующем открытии проекта. Недоступные поля не заменяются.</small>
        {loadPresets && savePresets && <>
          <button type="button" className="outline-button" disabled={presetBusy || presetRevision===null} onClick={persistPresets}>Сохранить комбинации в проекте</button>
          <button type="button" className="outline-button" disabled={presetBusy} onClick={reloadPresets}>Загрузить сохранённые комбинации</button>
          {presetStatus && <small role="status">{presetStatus}</small>}
        </>}
        <b>Избранные комбинации</b>
        {!favoritePresets.length && <small>Нажмите ☆ на панели.</small>}
        {favoritePresets.map(preset => <div key={presetKey(preset)} className="plot-preset-row">
          <button type="button" className="outline-button" disabled={loading || panels.length >= 32 || !resolvePreset(preset,axes,patterns)}
            onClick={() => addPresets([preset])}>{presetTitle(preset)}</button>
          <button type="button" aria-label="Удалить избранную комбинацию" disabled={presetBusy || (loadPresets && presetRevision===null)} onClick={() => setFavoritePresets(current => current.filter(item => presetKey(item) !== presetKey(preset)))}>×</button>
        </div>)}
        <b>Недавние комбинации</b>
        {!recentPresets.length && <small>Появятся после изменения осей.</small>}
        {recentPresets.map(preset => <button key={presetKey(preset)} type="button" className="outline-button"
          disabled={loading || panels.length >= 32 || !resolvePreset(preset,axes,patterns)} onClick={() => addPresets([preset])}>{presetTitle(preset)}</button>)}
      </details>
      <details className="plot-presets">
        <summary>Минеральные шаблоны</summary>
        <small>Наборы бинарных графиков по исходным wt.%; не определяют минерал и не фильтруют анализы автоматически.</small>
        <select aria-label="Минеральный шаблон" value={templateName} onChange={event => {setTemplateName(event.target.value);setTemplateGroupKey("");}}>
          {MINERAL_TEMPLATES.map(template => <option key={template.name}>{template.name}</option>)}
        </select>
        {mineralGroups.length > 1 && <select aria-label="Аналитический набор шаблона" value={mineralGroup?.key || ""} onChange={event => setTemplateGroupKey(event.target.value)}>
          {mineralGroups.map(group => <option key={group.key} value={group.key}>{group.label}</option>)}
        </select>}
        {mineralGroup ? <>
          <small>{mineralGroup.label}</small>
          {mineralGroup.presets.map(preset => <small key={presetKey(preset)}>{presetTitle(preset)}</small>)}
        </> : <small>Нет совместимых пар полей в одном аналитическом наборе.</small>}
        <button type="button" className="outline-button" disabled={loading || !mineralGroup || panels.length + mineralGroup.presets.length > 32}
          onClick={() => addPresets(mineralGroup.presets)}>Добавить графики шаблона</button>
      </details>
      <section className="plot-source-legend" aria-label="Окрашивание точек">
        <h3>Окрашивание</h3>
        <select aria-label="Окрашивать по" value={colorMode} disabled={loading || busy || exportBusy || schemeBusy || (loadColorScheme && schemeRevision === null)}
          onChange={event => {setColorMode(event.target.value);setExportOptions(null);}}>
          {Object.entries(COLOR_MODES).map(([key,label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        {colorMode !== "source" && <>
          {!colorReady && <small role="status">{categoryData?.error ? "Не удалось загрузить категории: " + categoryData.error : "Загружаю категории…"}</small>}
          {categoryData?.error && <button type="button" className="outline-button" onClick={() => setCategoryResult(null)}>Повторить</button>}
          {category && <div className="plot-category-legend" aria-label="Легенда категорий">
            {category.entries.map(entry => <div key={entry.key === null ? "missing" : "value:" + entry.key}>
              {entry.key === null ? <i style={{backgroundColor:entry.color}} aria-hidden="true"/> : <input type="color" aria-label={"Цвет: "+entry.label} value={entry.color} disabled={schemeBusy} onChange={event=>changeColor(colorMode,entry.key,event.target.value)}/>}
              <span>{entry.label}</span><small>{entry.count}</small>
              {entry.key!==null&&<select className="category-symbol" aria-label={"Символ: "+entry.label} value={entry.symbol||"circle"} disabled={schemeBusy}
                onChange={event=>changeSymbol(entry,event.target.value)}>
                {Object.entries(SYMBOL_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}
              </select>}
              <button type="button" className="outline-button category-cloud-button" disabled={layers.length>=32 || loading || busy}
                aria-label={"Создать облако: "+entry.label+" · "+entry.count+" анализов"} title="Только облако этой категории" onClick={()=>addCategoryCloud(entry)}>Облако</button></div>)}
          </div>}
          {category?.entries.length > CATEGORY_COLORS.length && <small>Цвета могут повторяться; сузьте набор для различения групп.</small>}
          <small>Гистограммы и управление видимостью источников сохраняют исходные цвета. Раскладка и пакет фиксируют категории и цвета на момент сохранения.</small>
        </>}
        {loadColorScheme && saveColorScheme && <>
          <button type="button" className="outline-button" disabled={schemeBusy || busy || !colorReady || schemeRevision===null} onClick={storeScheme}>Сохранить цветовую схему проекта</button>
          <button type="button" className="outline-button" disabled={schemeBusy || busy} onClick={reloadScheme}>Загрузить сохранённую схему</button>
          {schemeStatus && <small role="status">{schemeStatus}</small>}
        </>}
      </section>
      <section className="plot-source-legend" aria-label="Легенда источников">
        <h3>Источники</h3>
        {sources.map((source) => {
          const repeated = sources.some((other) => other.source_id !== source.source_id && other.source_name === source.source_name);
          const label = repeated ? `${source.source_name} · ${source.source_id.slice(0, 8)}` : source.source_name;
          return <div className="plot-source-color-row" key={source.source_id}>
            <label title="Ctrl+клик — изолировать источник; повтор — показать все" onClick={event => {
              if ((event.ctrlKey || event.metaKey) && onIsolateSource && !busy) {
                event.preventDefault();
                onIsolateSource(source.source_id, sources.map(item => item.source_id));
              }
            }}>
              <input type="checkbox" aria-label={label} checked={!hiddenSourceIds.includes(source.source_id)}
                disabled={!onToggleSource || busy} onChange={() => onToggleSource(source.source_id)} />
              <span>{label}</span>
            </label>
            <input type="color" aria-label={"Цвет источника: "+label} value={colorFor(source.source_id)} disabled={schemeBusy}
              onChange={event=>changeColor("source",source.source_id,event.target.value)}/>
          </div>;
        })}
        <p>Зелёный контур — текущий отбор</p>
        <p title="Ctrl+колесо — масштаб, пробел+перетаскивание — панорама, Home — автомасштаб">Пустое поле — снять отбор. Shift — добавить, Ctrl — переключить, Alt — исключить. Esc — отмена жеста, масштаба или отбора.</p>
        {hiddenAnalysisIds.length > 0 && <button className="outline-button" type="button" disabled={busy || !onSetVisibility}
          onClick={() => onSetVisibility(hiddenAnalysisIds, false)}>Вернуть скрытые точки · {hiddenAnalysisIds.length}</button>}
        {onUndoVisibility && <button className="outline-button" type="button" disabled={busy} onClick={onUndoVisibility}>
          Отменить изменение видимости
        </button>}
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
            updateLayer(layer.id, { field: method ? { method, visible: true,
              probability: method === "normal_probability_ellipse" ? 0.95 : null,
              ...(method === KDE_METHOD ? KDE_DEFAULTS : {}),
              ...(layer.field?.style ? { style: layer.field.style } : {}),
            } : null });
          }}>
            <option value="">Без поля</option><option value="convex_hull">Выпуклая оболочка</option>
            <option value="normal_probability_ellipse">Эллипс вероятности</option>
            <option value={KDE_METHOD}>KDE-контур</option>
          </select></label>
          {layer.field?.method === KDE_METHOD && <>
            {[
              ["bandwidth_x", "Ширина ядра X", 0.02, 0.5],
              ["bandwidth_y", "Ширина ядра Y", 0.02, 0.5],
              ["level", "Доля максимума плотности", 0.01, 0.99],
            ].map(([parameter, label, min, max]) => <label key={parameter}>{label}
              <input type="range" min={min} max={max} step={0.01} aria-label={label}
                value={layer.field[parameter]} onChange={(event) =>
                  updateLayer(layer.id, { field: { ...layer.field, [parameter]: Number(event.target.value) } })} />
              <output>{layer.field[parameter].toFixed(2)}</output>
            </label>)}
            <small>Для бинарной диаграммы. Ширина ядра задана в долях диапазона соответствующей оси.</small>
          </>}
          {layer.field && <label><input type="checkbox" checked={layer.field.visible}
            onChange={(event) => updateLayer(layer.id, { field: { ...layer.field, visible: event.target.checked } })} /> Поле</label>}
          {layer.field && <div className="plot-cloud-style">
            <label>Оформление облака <select value={(layer.field.style || DEFAULT_FIELD_STYLE).mode}
              onChange={event=>updateLayer(layer.id,{field:{...layer.field,style:{...(layer.field.style || DEFAULT_FIELD_STYLE),mode:event.target.value}}})}>
              <option value="outline">Только контур</option><option value="fill">Только заливка</option><option value="both">Контур и заливка</option>
            </select></label>
            <label>Цвет облака <input type="color" value={(layer.field.style || DEFAULT_FIELD_STYLE).color}
              onChange={event=>updateLayer(layer.id,{field:{...layer.field,style:{...(layer.field.style || DEFAULT_FIELD_STYLE),color:event.target.value}}})}/></label>
            <label>Непрозрачность заливки <input type="range" min="0.05" max="1" step="0.05" value={(layer.field.style || DEFAULT_FIELD_STYLE).fill_opacity}
              disabled={layer.field.style?.mode==="outline"} onChange={event=>updateLayer(layer.id,{field:{...layer.field,style:{...(layer.field.style || DEFAULT_FIELD_STYLE),fill_opacity:Number(event.target.value)}}})}/></label>
            <label>Толщина контура <input type="range" min="0.5" max="4" step="0.5" value={(layer.field.style || DEFAULT_FIELD_STYLE).stroke_width}
              disabled={layer.field.style?.mode==="fill"} onChange={event=>updateLayer(layer.id,{field:{...layer.field,style:{...(layer.field.style || DEFAULT_FIELD_STYLE),stroke_width:Number(event.target.value)}}})}/></label>
          </div>}
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
          <button className="outline-button" type="button" disabled={!layerInput.length || layers.length>=32} onClick={()=>addCloud()}>Только облако выделения · {layerInput.length}</button>
        </form>
      </details>
      {loadLayouts && <details className="plot-saved-layouts">
        <summary>Сохранённые раскладки</summary>
        {layouts.map(({ id, name }) => <button key={id} className="outline-button" type="button"
          disabled={layoutBusy || busy} onClick={() => restore(id)}>Открыть «{name}»</button>)}
        <form onSubmit={save}>
          <label>Название раскладки<input value={layoutName} maxLength={120}
            onChange={(event) => setLayoutName(event.target.value)} /></label>
          <button className="outline-button" type="submit" disabled={layoutBusy || busy || loading || !colorReady || !layoutName.trim() || !panels.length}>
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
        <button className="primary-button" type="button" onClick={add} disabled={!axes.length || panels.length >= 32}>Добавить диаграмму</button>
        {onExport && <button className="outline-button" type="button" disabled={exportBusy || loading || !colorReady || !panels.length}
          onClick={() => openExport(null)}>Выгрузить раскладку</button>}
      </header>
      {exportStatus && <p role={exportStatus.error ? "alert" : "status"}>{exportStatus.error || exportStatus.notice}</p>}
      {loading && <p role="status">Загружаю поля проекта…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && !panels.length && <p>Для построения нужно хотя бы одно поле измерений.</p>}
      <div ref={content} className={exportOptions ? "plot-content plot-content-export" : "plot-content"} onScroll={event => {
        if (viewMemory) Object.assign(viewMemory, { scrollTop: event.currentTarget.scrollTop, scrollLeft: event.currentTarget.scrollLeft });
      }}>
        <div className={photoView?"photo-plot-body":undefined}>
        {photoView&&<PhotoPlot inputIds={inputIds} loadCatalog={loadCatalog} loadPhotos={loadPhotos} preview={previewPhoto} loadProfile={loadProfile} view={photoView} setView={setPhotoView}
          panels={panels} focusedIds={focusedIds} setFocusedIds={setFocusedIds}
          addToSelection={ids=>setSelectedIds(current=>[...new Set([...current,...ids])])}/>}
        <div className="plot-grid" ref={grid}>
          {!loading && !error && displayedPanels.map((panel) => <PlotPanel key={panel.id} panel={panel} axes={axes} patterns={patterns} load={loadWithLayers} loadCatalog={loadCatalog} selected={photoView?new Set(focusedIds):selected} onSelect={photoView?setFocusedIds:select} onOpenAnalysis={onOpenAnalysis} onOpenPhotos={onOpenPhotos} loadAnalysis={cachedAnalysis} shape={shape} colorFor={colorFor} categoryColor={category?.colorFor} categorySymbol={category?.symbolFor} layers={layers} viewMemory={viewMemory}
            grain={{loadPhotos,previewPhoto,mediaId:photoView?.media_asset_id}}
            openExport={onExport && !exportBusy && colorReady ? () => openExport(panel.id) : undefined}
            favorite={Boolean(makePreset(panel) && favoritePresets.some(item => presetKey(item) === presetKey(makePreset(panel))))}
            onFavorite={!presetBusy && (!loadPresets || presetRevision!==null) ? () => toggleFavorite(panel) : undefined}
            onApplyStyle={style=>setPanels(current=>current.map(item=>item.kind==="histogram" ? item : {...item,point_style:{...style}}))}
            update={(next) => {
              setPanels(current => current.map(item => item.id === panel.id ? next : item));
              const preset = makePreset(next);
              if ((next.kind!==panel.kind || next.axes!==panel.axes || next.normalization!==panel.normalization) && preset && resolvePreset(preset,axes,patterns) && !presetBusy && (!loadPresets || presetRevision!==null))
                setRecentPresets(current => rememberPreset(current,preset));
            }}
            duplicate={panels.length<32?()=>{const id=crypto.randomUUID();setPanels(current=>duplicatePanel(current,panel.id,id));}:undefined}
            canRemove={panels.length > 1} remove={() => {
              setPanels(current=>current.filter(item=>item.id!==panel.id));
              if(photoView){const remaining=photoView.panel_ids.filter(id=>id!==panel.id);
                setPhotoView({...photoView,panel_ids:remaining.length?remaining:[panels.find(item=>item.id!==panel.id).id]});}
            }} />)}
        </div>
        </div>
        {exportOptions && <PlotExport options={exportOptions} panels={displayedPanels} pending={exportBusy} submit={submitExport}
          canAddPublication={Boolean(onAddPublication) && colorReady}
          close={() => setExportOptions(null)} onChange={(values) => setExportOptions((current) => ({ ...current, ...values }))} />}
      </div>
      <footer className="plot-selection-footer"><b>Выбранные анализы · {selectedIds.length}</b>
        {onSummary && selectedIds.length>0 && <button type="button" className="outline-button" disabled={busy||selectedIds.length>50000} onClick={onSummary}>{selectedIds.length===2?"Сравнить составы":"Статистика отбора"}</button>}
        {loadSelection && <button type="button" className="outline-button" aria-expanded={selectionExpanded}
          aria-controls="plot-selection-table" onClick={() => setSelectionExpanded(!selectionExpanded)}>
          {selectionExpanded ? "Свернуть таблицу" : "Развернуть таблицу"}
        </button>}
        {onSetVisibility && selectedIds.some((id) => !hiddenAnalysisIds.includes(id)) &&
          <button type="button" className="outline-button" disabled={busy}
            onClick={() => onSetVisibility(selectedIds, true)}>Скрыть отбор на графиках</button>}
        <button type="button" className="outline-button" onClick={onBack}>Открыть в анализах</button>
        <section id="plot-selection-table" hidden={!selectionExpanded} className="plot-selection-table">
          {selectionExpanded && <PlotSelectionTable ids={selectedIds} load={loadSelection}
            hiddenAnalysisIds={hiddenAnalysisIds} hiddenSourceIds={hiddenSourceIds} />}
        </section>
      </footer>
    </main>
  </section>;
}
