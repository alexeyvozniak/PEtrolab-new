import { useCallback, useEffect, useRef, useState } from "react";
import { PLOT_SIZE, buildPlotSvg, plotPanelLabel } from "./plotSvg";
import "./plotWorkspace.css";

const VIEW = { ...PLOT_SIZE, left: 55, right: 425, top: 22, bottom: 235 };
const FULL_VIEW = { x: 0, y: 0, width: VIEW.width, height: VIEW.height };
const px = (value) => VIEW.left + value * (VIEW.right - VIEW.left);
const py = (value) => VIEW.bottom - value * (VIEW.bottom - VIEW.top);
const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
const axisKey = (axis) => JSON.stringify([axis.field, axis.unit, axis.measurement_set, axis.method]);
const axisLabel = (axis) => [axis.field, axis.unit, axis.measurement_set, axis.method].filter(Boolean).join(" · ");
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

function PlotCanvas({ data, selected, onSelect, shape, colorFor, points }) {
  const drag = useRef(null);
  const canvas = useRef(null);
  const hovered = useRef(false);
  const space = useRef(false);
  const [rubber, setRubber] = useState(null);
  const [view, setView] = useState(FULL_VIEW);
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
  const bins = data.bins || [];
  const bars = bins.flatMap((bin) => bin.series.map((series) => ({
    ...series, ...bin, u: (bin.left + bin.right) / 2, v: series.base + series.height / 2,
    label: `${bin.lower}–${bin.upper} · ${series.analysis_ids.length} анализов`,
  })));
  const maximumCount = Math.max(1, ...bins.map((bin) => bin.count));
  const selectedCounts = bins.map((bin) => bin.series.flatMap((series) => series.analysis_ids)
    .filter((id) => selected.has(id)).length);
  const selectedOutline = selectedCounts.some(Boolean)
    ? `M ${px(bins[0].left)} ${VIEW.bottom} ${bins.map((bin, index) =>
      `V ${py(selectedCounts[index] / maximumCount)} H ${px(bin.right)}`).join(" ")} V ${VIEW.bottom}`
    : "";
  const markers = isHistogram ? bars : points.flatMap((point) => isPattern ? point.vertices.filter(({ v }) => v !== null).map((vertex, index) => ({
    ...vertex, analysis_id: point.analysis_id, source_id: point.source_id, opacity: point.opacity,
    tabIndex: index === 0 ? 0 : -1,
    label: `${point.label} · ${vertex.element}`, title: `${point.label} · ${point.source_name} · ${vertex.element}: ${vertex.ratio.toPrecision(5)}`,
  })) : [{ ...point, title: `${point.label} · ${point.source_name} · ${point.values.join(" / ")}` }]);
  const contains = (x, y) => x >= view.x && x <= view.x + view.width && y >= view.y && y <= view.y + view.height;
  const visibleMarkers = zoomed ? markers.filter((point) => contains(px(point.u), py(point.v))) : markers;
  const position = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: view.x + (event.clientX - bounds.left) * view.width / bounds.width,
      y: view.y + (event.clientY - bounds.top) * view.height / bounds.height };
  };
  const start = (event) => {
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
      barIndex: event.target.dataset?.plotBar };
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
    const last = position(event);
    drag.current = null;
    setRubber(null);
    const freehand = shape === "lasso" && trail.length >= 3;
    if (!freehand && Math.hypot(first.x - last.x, first.y - last.y) < 4 * view.width / VIEW.width) {
      if (isHistogram) {
        if (pressedBar) onSelect(pressedBar.analysis_ids);
        return;
      }
      const hit = visibleMarkers.findLast((point) => Math.hypot(px(point.u) - last.x, py(point.v) - last.y) <= 7 * view.width / VIEW.width);
      const id = hit?.analysis_id || pressedAnalysisId;
      if (id) onSelect([id]);
      return;
    }
    if (shape === "lasso" && !freehand) return;
    const inside = (current, a, b) => current >= Math.min(a, b) && current <= Math.max(a, b);
    onSelect([...new Set(visibleMarkers.filter((point) => freehand
      ? insidePolygon({ x: px(point.u), y: py(point.v) }, [...trail, last])
      : inside(px(point.u), first.x, last.x) && inside(py(point.v), first.y, last.y))
      .flatMap((point) => point.analysis_ids || [point.analysis_id]))]);
  };
  const clear = () => { drag.current = null; setRubber(null); };
  return <>
  {zoomed && <button type="button" className="outline-button plot-reset-zoom" onClick={() => setView(FULL_VIEW)}>Автомасштаб</button>}
  <svg ref={canvas} className="plot-canvas" viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} aria-label="Диаграмма"
    tabIndex={0} onPointerEnter={() => { hovered.current = true; }} onPointerLeave={() => { hovered.current = false; }}
    onKeyDown={(event) => { if (event.key === "Escape" && zoomed) setView(FULL_VIEW); }}
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
    {(data.fields || []).filter((field) => field.vertices.length >= 3).map((field) =>
      <polygon key={field.layer_id} className="plot-field" fill="#99b9a0" fillOpacity={0.26}
        stroke="#5c7d66" strokeWidth={1} points={field.vertices.map(([u, v]) => `${px(u)},${py(v)}`).join(" ")} />)}
    {isPattern && points.map((point) => <path key={point.analysis_id} className="plot-series" data-analysis-id={point.analysis_id}
      d={patternPath(point.vertices)} fill="none" stroke={colorFor(point.source_id)} strokeWidth={1.25} opacity={point.opacity} />)}
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
          onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(bar.analysis_ids); } }}>
          <title>{bar.label}</title>
        </rect>
      </g>;
    })}
    {selectedOutline && <path className="plot-halo" d={selectedOutline} />}
    {!isHistogram && markers.map((point) => <g key={`${point.analysis_id}:${point.element || ""}`}>
      <circle className="plot-point" data-analysis-id={point.analysis_id} fill={colorFor(point.source_id)}
        cx={px(point.u)} cy={py(point.v)} r={isPattern ? 2.5 : 3.5} role="button"
        tabIndex={!zoomed || contains(px(point.u), py(point.v)) ? point.tabIndex ?? 0 : -1}
        aria-hidden={zoomed && !contains(px(point.u), py(point.v)) ? true : undefined}
        opacity={point.opacity}
        aria-label={`Выбрать точку ${point.label}`} aria-pressed={selected.has(point.analysis_id)}
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect([point.analysis_id]); } }}>
        <title>{point.title}</title>
      </circle>
    </g>)}
    {!isHistogram && markers.filter((point) => selected.has(point.analysis_id)).map((point) =>
      <circle key={`${point.analysis_id}:${point.element || ""}`} className="plot-halo" cx={px(point.u)} cy={py(point.v)} r={isPattern ? 4.5 : 6} />)}
    {rubber && (rubber.path ? <polygon className="plot-rubber" points={rubber.path} /> : <rect className="plot-rubber" {...rubber} />)}
  </svg></>;
}

function PlotPanel({ panel, axes, patterns, load, update, remove, selected, onSelect, canRemove, shape, colorFor, openExport, layers }) {
  const [projection, setProjection] = useState(null);
  const current = projection?.load === load && projection.panel === panel ? projection : null;
  const data = current?.data;
  const styles = new Map();
  layers.forEach(({ analysis_ids, opacity, show_points }, order) => {
    for (const id of analysis_ids) styles.set(id, { order, opacity: show_points ? opacity : 0 });
  });
  const points = panel.kind === "histogram" ? data?.points || [] : (data?.points || []).map((point) => ({ ...point, ...(styles.get(point.analysis_id) || { opacity: 1, order: -1 }) }))
    .filter((point) => point.opacity > 0).sort((a, b) => a.order - b.order);
  const status = current ? current.error : "Загружаю диаграмму…";
  const pattern = patterns[panel.kind];
  const group = pattern?.groups.find(({ key }) => key === measurementGroup(panel.axes[0]));
  useEffect(() => {
    let active = true;
    load(panel.kind, panel.axes, panel.normalization).then((result) => {
      if (active) setProjection({ load, panel, data: result });
    }).catch((error) => { if (active) setProjection({ load, panel, error: error.message }); });
    return () => { active = false; };
  }, [load, panel]);
  const updateKind = (kind) => {
    if (kind === "histogram") {
      update({ id: panel.id, kind, axes: [panel.axes[0]] });
      return;
    }
    if (patterns[kind]) {
      const { groups, default_normalization } = patterns[kind];
      update({ id: panel.id, kind, axes: groups[0].axes, normalization: default_normalization });
      return;
    }
    const next = initialPanels(axes).find((item) => item.kind === kind);
    update({ id: panel.id, kind, axes: next ? next.axes : axes.slice(0, 3) });
  };
  const updateAxis = (index, axis) => update({ ...panel, axes: panel.axes.map((value, position) => position === index ? axis : value) });

  return <article className="plot-panel" id={`plot-${panel.id}`}>
    <header><b>{panelTitle(panel)}</b>
      <div className="plot-panel-actions">
        {openExport && <button type="button" className="outline-button" disabled={!data} onClick={openExport}>Выгрузить панель</button>}
        {canRemove && <button type="button" className="outline-button" onClick={remove}>Убрать панель</button>}
      </div>
    </header>
    <div className="plot-panel-controls">
      <select aria-label="Тип диаграммы" value={panel.kind} onChange={(event) => updateKind(event.target.value)}>
        <option value="binary" disabled={axes.length < 2}>Бинарная</option>
        <option value="ternary" disabled={axes.length < 3}>Тройная</option>
        <option value="histogram">Гистограмма</option>
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
        const candidates = pattern ? group?.fields.get(axis.field) || [] : axes;
        if (pattern && candidates.length < 2) return null;
        return <select key={index} aria-label={pattern ? `Предпочтительная единица ${axis.field}` : `Ось ${index + 1}`} value={axisKey(axis)}
          onChange={(event) => updateAxis(index, candidates.find((item) => axisKey(item) === event.target.value))}>
          {candidates.map((item) => <option key={axisKey(item)} value={axisKey(item)}>{axisLabel(item)}</option>)}
        </select>;
      })}
    </div>
    {status && <p role="status">{status}</p>}
    {data && <>
      <PlotCanvas data={data} selected={selected} onSelect={onSelect} shape={shape} colorFor={colorFor} points={points} />
      <small>{pattern ? "Спектров" : panel.kind === "histogram" ? "Анализов" : "Точек"}: {points.length} из {data.input_count}{data.excluded_count ? ` · пропущено: ${data.excluded_count}` : ""}
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

export function PlotWorkspace({ loadCatalog, loadData, loadSelection, selectedIds, setSelectedIds, inputIds, onBack,
  hiddenSourceIds = [], hiddenAnalysisIds = [], onToggleSource, onSetVisibility, onUndoVisibility, busy, loadLayouts, saveLayout, openLayout,
  onExport, onAddPublication }) {
  const [axes, setAxes] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [panels, setPanels] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("union");
  const [shape, setShape] = useState("rectangle");
  const [selectionExpanded, setSelectionExpanded] = useState(false);
  const [sources, setSources] = useState([]);
  const [layouts, setLayouts] = useState([]);
  const [layoutName, setLayoutName] = useState("");
  const [layoutStatus, setLayoutStatus] = useState(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [savedColors, setSavedColors] = useState({});
  const [layers, setLayers] = useState([]);
  const [layerName, setLayerName] = useState("");
  const layerInput = inputIds ? selectedIds.filter((id) => inputIds.includes(id)) : selectedIds;
  const loadWithLayers = useCallback((kind, axes, normalization) => loadData(kind, axes, layers, normalization), [loadData, layers]);
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
      setPanels(saved.panels.map(({ id: panelId, kind, axes: savedAxes, normalization }) => ({
        id: panelId, kind, axes: savedAxes.map(({ field, unit, method, measurement_set }) => ({ field, unit, method, measurement_set })),
        ...(PATTERN_LABELS[kind] ? { normalization } : {}),
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
      {panels.map((panel, index) => <a href={`#plot-${panel.id}`} key={panel.id}>{index + 1}. {panelTitle(panel)}</a>)}
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
        <button className="primary-button" type="button" onClick={add} disabled={!axes.length || panels.length >= 32}>Добавить диаграмму</button>
        {onExport && <button className="outline-button" type="button" disabled={exportBusy || loading || !panels.length}
          onClick={() => openExport(null)}>Выгрузить раскладку</button>}
      </header>
      {exportStatus && <p role={exportStatus.error ? "alert" : "status"}>{exportStatus.error || exportStatus.notice}</p>}
      {loading && <p role="status">Загружаю поля проекта…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && !panels.length && <p>Для построения нужно хотя бы одно поле измерений.</p>}
      <div className={exportOptions ? "plot-content plot-content-export" : "plot-content"}>
        <div className="plot-grid" ref={grid}>
          {!loading && !error && panels.map((panel) => <PlotPanel key={panel.id} panel={panel} axes={axes} patterns={patterns} load={loadWithLayers} selected={selected} onSelect={select} shape={shape} colorFor={colorFor} layers={layers}
            openExport={onExport && !exportBusy ? () => openExport(panel.id) : undefined}
            update={(next) => setPanels((current) => current.map((item) => item.id === panel.id ? next : item))}
            canRemove={panels.length > 1} remove={() => setPanels((current) => current.filter((item) => item.id !== panel.id))} />)}
        </div>
        {exportOptions && <PlotExport options={exportOptions} panels={panels} pending={exportBusy} submit={submitExport}
          canAddPublication={Boolean(onAddPublication)}
          close={() => setExportOptions(null)} onChange={(values) => setExportOptions((current) => ({ ...current, ...values }))} />}
      </div>
      <footer className="plot-selection-footer"><b>Выбранные анализы · {selectedIds.length}</b>
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
