import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Copy,
  FolderOpen,
  FileImage,
  Images,
  Info,
  MagnifyingGlass,
  MapPin,
  Plus,
  Trash,
  Warning,
} from "@phosphor-icons/react";
import "./imagesWorkspace.css";

const MEDIA_TYPES = ["BSE", "PPL", "XPL", "Фото"];
const GEOMETRY_TYPES = [
  ["point", "Point"],
  ["rectangle", "Rectangle"],
  ["square", "Square"],
];
const CROSS_SAMPLE_REASONS = {
  image_covers_other_sample: "Изображение охватывает другой образец",
  sample_attribution_error: "Ошибка атрибуции Sample",
  other: "Другая причина",
};

function initialAssignment(item) {
  return {
    source_path: item.source_path,
    ownership_mode: "managed_copy",
    media_type: item.suggested_media_type || "",
    sample_name: item.suggested_sample_name || "",
    thin_section_name: item.suggested_thin_section_name || "",
    placements: [],
    confirmed: false,
    _source_fingerprint: item.source_fingerprint,
    _custom_media_type: false,
    _media_type_reviewed: false,
    _sample_section_reviewed: false,
  };
}

function assignmentReady(assignment) {
  return Boolean(
    assignment?.confirmed
    && assignment.media_type.trim()
    && assignment.sample_name.trim()
    && assignment.thin_section_name.trim(),
  );
}

function cleanAssignment(assignment) {
  const {
    confirmed: _confirmed,
    _source_fingerprint: _fingerprint,
    _custom_media_type: _custom,
    _media_type_reviewed: _mediaReviewed,
    _sample_section_reviewed: _sampleReviewed,
    ...payload
  } = assignment;
  return {
    ...payload,
    placements: payload.placements.map(({ point_name: _pointName, point_sample_name: _pointSample, ...placement }) => placement),
  };
}

function geometryStyle(geometry, item) {
  const base = {
    left: `${(geometry.x_px / item.width_px) * 100}%`,
    top: `${(geometry.y_px / item.height_px) * 100}%`,
  };
  if (geometry.kind === "point") return base;
  return {
    ...base,
    width: `${(geometry.width_px / item.width_px) * 100}%`,
    height: `${(geometry.height_px / item.height_px) * 100}%`,
  };
}

function geometryLabel(geometry) {
  if (!geometry) return "не размещена";
  const origin = `${Math.round(geometry.x_px)}, ${Math.round(geometry.y_px)} px`;
  if (geometry.kind === "point") return `Point · ${origin}`;
  return `${geometry.kind === "square" ? "Square" : "Rectangle"} · ${origin} · ${Math.round(geometry.width_px)} × ${Math.round(geometry.height_px)} px`;
}

function shortenId(value) {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function SourcePane({ items, assignments, activePath, setActivePath, phase }) {
  return <aside className="image-source-pane">
    <header><b>{phase === "review" ? "Импортируемые изображения" : "Загруженные изображения"}</b><span>{items.length}</span></header>
    <div className="image-source-list">
      {items.map((item, index) => {
        const assignment = assignments[item.source_path];
        const focused = item.source_path === activePath;
        const placementCount = assignment?.placements?.length || 0;
        return <button className={focused ? "focused" : ""} type="button" key={item.source_path} onClick={() => setActivePath(item.source_path)}>
          <span className="image-source-icon"><FileImage size={24} weight="duotone" /></span>
          <span><b>{index + 1}. {item.display_name}</b><small>{item.width_px} × {item.height_px} px · {(item.format || item.mime_type?.split("/").pop() || "image").toUpperCase()}</small><em>{phase === "assignment" ? (assignmentReady(assignment) ? "назначено" : "нужно подтвердить") : `${placementCount} размещено`}</em></span>
        </button>;
      })}
    </div>
    <div className="image-source-safety"><Info size={17} /><span>Исходные файлы не изменяются</span></div>
  </aside>;
}

function AssignmentStep({ items, inspection, changedSources, assignments, setAssignments, selected, setSelected, activeItem, activeAssignment, setActivePath, busy, onChooseFiles, onChooseFolder, onRemove, onCancel, onInvalidatePlan, onContinue }) {
  const duplicatePaths = useMemo(() => new Set((inspection?.duplicate_groups || []).flat()), [inspection]);
  const readyCount = items.filter((item) => assignmentReady(assignments[item.source_path])).length;
  const selectedItems = items.filter((item) => selected.has(item.source_path));
  const selectedSuggestionsReady = selectedItems.length > 0 && selectedItems.every((item) => (
    item.suggested_media_type && item.suggested_sample_name && item.suggested_thin_section_name
  ));
  const canContinue = items.length > 0 && readyCount === items.length && duplicatePaths.size === 0;

  const patchAssignment = (path, values) => {
    onInvalidatePlan();
    setAssignments((current) => ({
      ...current,
      [path]: {
        ...current[path],
        ...values,
        ...(Object.hasOwn(values, "media_type") ? { _media_type_reviewed: false } : {}),
        ...(Object.hasOwn(values, "sample_name") || Object.hasOwn(values, "thin_section_name") ? { _sample_section_reviewed: false } : {}),
        confirmed: false,
      },
    }));
  };
  const toggleSelected = (path) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };
  const confirmSuggestions = () => {
    onInvalidatePlan();
    setAssignments((current) => {
      const next = { ...current };
      selectedItems.forEach((item) => {
        next[item.source_path] = {
          ...next[item.source_path],
          media_type: item.suggested_media_type,
          sample_name: item.suggested_sample_name,
          thin_section_name: item.suggested_thin_section_name,
          _custom_media_type: false,
          _media_type_reviewed: true,
          _sample_section_reviewed: true,
          confirmed: true,
        };
      });
      return next;
    });
  };
  const confirmActive = () => {
    if (!activeItem || !activeAssignment?.media_type.trim() || !activeAssignment.sample_name.trim() || !activeAssignment.thin_section_name.trim()) return;
    onInvalidatePlan();
    setAssignments((current) => ({
      ...current,
      [activeItem.source_path]: {
        ...current[activeItem.source_path],
        _media_type_reviewed: true,
        _sample_section_reviewed: true,
        confirmed: true,
      },
    }));
  };
  const applySampleAndSectionToSelection = () => {
    if (!activeAssignment) return;
    const shared = {
      sample_name: activeAssignment.sample_name.trim(),
      thin_section_name: activeAssignment.thin_section_name.trim(),
    };
    if (!shared.sample_name || !shared.thin_section_name) return;
    onInvalidatePlan();
    setAssignments((current) => {
      const next = { ...current };
      selectedItems.forEach((item) => {
        const updated = { ...next[item.source_path], ...shared, _sample_section_reviewed: true };
        next[item.source_path] = { ...updated, confirmed: Boolean(updated.media_type.trim() && updated._media_type_reviewed) };
      });
      return next;
    });
  };
  const applyTypeToSelection = () => {
    if (!activeAssignment?.media_type.trim()) return;
    onInvalidatePlan();
    setAssignments((current) => {
      const next = { ...current };
      selectedItems.forEach((item) => {
        const updated = { ...next[item.source_path], media_type: activeAssignment.media_type.trim(), _custom_media_type: activeAssignment._custom_media_type, _media_type_reviewed: true };
        next[item.source_path] = { ...updated, confirmed: Boolean(updated.sample_name.trim() && updated.thin_section_name.trim() && updated._sample_section_reviewed) };
      });
      return next;
    });
  };
  const removeSelected = () => {
    if (!selected.size) return;
    onInvalidatePlan();
    onRemove([...selected]);
  };

  return <>
    <main className="image-assignment-pane">
      <header>
        <div><h2>Назначь Sample и шлиф</h2><p>Предложения из имени файла не сохраняются без подтверждения.</p></div>
        <div className="image-add-actions"><button className="outline-button" type="button" onClick={onChooseFiles} disabled={busy}><Plus size={17} /> Добавить файлы</button><button className="outline-button" type="button" onClick={onChooseFolder} disabled={busy}><FolderOpen size={17} /> Добавить папку</button></div>
      </header>
      <div className="image-bulk-toolbar">
        <label><input type="checkbox" checked={selected.size === items.length} onChange={() => setSelected(selected.size === items.length ? new Set() : new Set(items.map((item) => item.source_path)))} /> Выбрано: {selected.size} из {items.length}</label>
        <button type="button" onClick={confirmSuggestions} disabled={busy || !selectedSuggestionsReady}><CheckCircle size={17} /> Подтвердить предложения</button>
        <button className="danger-outline" type="button" onClick={removeSelected} disabled={busy || selected.size === 0}><Trash size={16} /> Убрать из очереди</button>
      </div>
      {changedSources.length > 0 && <div className="image-duplicate-warning" role="status"><Warning size={18} /><span>Исходные файлы изменились: {changedSources.join(", ")}. Их назначения и точки сброшены. Проверь изображения заново.</span></div>}
      {duplicatePaths.size > 0 && <div className="image-duplicate-warning"><Warning size={18} /><span>В очереди есть одинаковые физические изображения. Удали дубликаты перед продолжением.</span></div>}
      <div className="image-assignment-table" role="table" aria-label="Назначения импортируемых изображений">
        <div className="image-assignment-head" role="row"><span></span><span>Файл</span><span>Sample</span><span>Шлиф</span><span>Тип</span><span>Статус</span></div>
        {items.map((item) => {
          const assignment = assignments[item.source_path];
          return <div className={`${item.source_path === activeItem?.source_path ? "active " : ""}${duplicatePaths.has(item.source_path) ? "duplicate" : ""}`} role="row" key={item.source_path} onClick={() => setActivePath(item.source_path)}>
            <span><input aria-label={`Выбрать ${item.display_name}`} type="checkbox" checked={selected.has(item.source_path)} onChange={() => toggleSelected(item.source_path)} onClick={(event) => event.stopPropagation()} /></span>
            <button type="button" title={item.source_path} onClick={() => setActivePath(item.source_path)}>{item.display_name}<small className="image-source-path">{item.source_path}</small></button>
            <span>{assignment?.sample_name || "—"}</span><span>{assignment?.thin_section_name || "—"}</span>
            <span className={`image-type type-${assignment?.media_type || "unknown"}`}>{assignment?.media_type || "—"}</span>
            <span className={assignmentReady(assignment) ? "image-ready" : "image-pending"}>{duplicatePaths.has(item.source_path) ? "дубликат" : assignmentReady(assignment) ? "готово" : "проверь"}</span>
          </div>;
        })}
      </div>
      <div className="image-assignment-note"><Info size={18} /><p>Массовое назначение применяется только к отмеченным строкам. Пространственные точки создаются на следующем шаге.</p></div>
    </main>
    <aside className="image-inspector">
      <header><span>Выбрано изображение</span><h2>{activeItem?.display_name}</h2><p>{activeItem?.width_px} × {activeItem?.height_px} px · SHA-256 проверен</p></header>
      <section><h3>Предложено из имени файла</h3><dl><div><dt>Sample</dt><dd>{activeItem?.suggested_sample_name || "не определён"}</dd></div><div><dt>Шлиф</dt><dd>{activeItem?.suggested_thin_section_name || "не определён"}</dd></div><div><dt>Тип</dt><dd>{activeItem?.suggested_media_type || "не определён"}</dd></div></dl></section>
      <fieldset className="image-assignment-form" disabled={busy}>
        <h3>Назначение для выбранных</h3>
        <label>Sample<input value={activeAssignment?.sample_name || ""} onChange={(event) => patchAssignment(activeItem.source_path, { sample_name: event.target.value })} placeholder="Например, KIV-2" /></label>
        <label>Thin Section<input value={activeAssignment?.thin_section_name || ""} onChange={(event) => patchAssignment(activeItem.source_path, { thin_section_name: event.target.value })} placeholder="Например, KIV-2-A" /></label>
        <label>Тип изображения<select value={activeAssignment?._custom_media_type ? "__custom__" : (activeAssignment?.media_type || "")} onChange={(event) => patchAssignment(activeItem.source_path, event.target.value === "__custom__" ? { media_type: "", _custom_media_type: true } : { media_type: event.target.value, _custom_media_type: false })}><option value="">Выбери тип</option>{MEDIA_TYPES.map((type) => <option key={type}>{type}</option>)}<option value="__custom__">Другой тип…</option></select></label>
        {activeAssignment?._custom_media_type && <label>Название типа<input value={activeAssignment.media_type} maxLength={80} onChange={(event) => patchAssignment(activeItem.source_path, { media_type: event.target.value })} placeholder="Например, CL или карта элемента" /></label>}
        <label>Хранение<select value={activeAssignment?.ownership_mode || "managed_copy"} onChange={(event) => patchAssignment(activeItem.source_path, { ownership_mode: event.target.value })}><option value="managed_copy">Копия внутри проекта</option><option value="linked_external">Ссылка на исходный файл</option></select></label>
        <button className="primary-button inspector-action" type="button" onClick={confirmActive} disabled={busy || !activeAssignment?.media_type.trim() || !activeAssignment?.sample_name.trim() || !activeAssignment?.thin_section_name.trim()}><CheckCircle size={17} /> Подтвердить это изображение</button>
        <button className="outline-button image-bulk-apply" type="button" onClick={applySampleAndSectionToSelection} disabled={busy || selected.size === 0 || !activeAssignment?.sample_name.trim() || !activeAssignment?.thin_section_name.trim()}><Copy size={17} /> Sample и шлиф → выбранным ({selected.size})</button>
        <button className="outline-button image-bulk-apply" type="button" onClick={applyTypeToSelection} disabled={busy || selected.size === 0 || !activeAssignment?.media_type.trim()}><Copy size={17} /> Тип → выбранным ({selected.size})</button>
      </fieldset>
      <div className="image-next-note"><Info size={18} /><p><b>Дальше — точки на изображении.</b><br />Можно разместить их вручную или явно завершить импорт без точек.</p></div>
    </aside>
    <footer className="image-commit-bar">
      <button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отмена</button><div><b>{readyCount} готово</b><span>{items.length - readyCount > 0 ? ` · ${items.length - readyCount} требуют подтверждения` : " · назначения проверены"}</span></div>
      <small>Исходные файлы не изменяются</small>
      <button className="primary-button" type="button" disabled={busy || !canContinue} onClick={onContinue}>Продолжить: точки <ArrowRight size={18} /></button>
    </footer>
  </>;
}

function PlacementMarker({ placement, item, selected = false, draft = false, onSelect }) {
  const geometry = placement.geometry;
  return <button
    aria-label={`${draft ? "Предпросмотр" : "Размещение"} ${placement.point_name || "точки"}`}
    className={`image-placement-marker ${geometry.kind}${selected ? " selected" : ""}${draft ? " draft" : ""}`}
    style={geometryStyle(geometry, item)}
    type="button"
    onClick={(event) => { event.stopPropagation(); onSelect?.(); }}
  >{geometry.kind === "point" && <><MapPin size={22} weight="fill" /><span>{placement.point_name}</span></>}</button>;
}

function ImageCanvas({ item, assignment, preview, previewLoading, previewError, zoom, geometryKind, draft, setDraft, selectedPoint, onSelectPlacement, interactive = true }) {
  const dragStart = useRef(null);
  const coordinates = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(item.width_px - Number.EPSILON, ((event.clientX - bounds.left) / bounds.width) * item.width_px)),
      y: Math.max(0, Math.min(item.height_px - Number.EPSILON, ((event.clientY - bounds.top) / bounds.height) * item.height_px)),
    };
  };
  const pointDraft = (point, geometry) => point && setDraft({
    analytical_point_id: point.analytical_point_id,
    point_name: point.point_name,
    point_sample_name: point.sample_name,
    geometry,
  });
  const onPointerDown = (event) => {
    if (!selectedPoint || !preview) return;
    const start = coordinates(event);
    if (geometryKind === "point") pointDraft(selectedPoint, { kind: "point", x_px: start.x, y_px: start.y });
    else {
      dragStart.current = start;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
  };
  const onPointerUp = (event) => {
    if (!selectedPoint || !dragStart.current || geometryKind === "point") return;
    const start = dragStart.current;
    dragStart.current = null;
    const end = coordinates(event);
    let width = Math.abs(end.x - start.x);
    let height = Math.abs(end.y - start.y);
    if (geometryKind === "square") width = height = Math.min(width, height);
    if (width < 1 || height < 1) return;
    const x = end.x < start.x ? start.x - width : start.x;
    const y = end.y < start.y ? start.y - height : start.y;
    pointDraft(selectedPoint, { kind: geometryKind, x_px: x, y_px: y, width_px: width, height_px: height });
  };
  const onKeyDown = (event) => {
    if (!selectedPoint || !preview || !["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    if (geometryKind === "point") pointDraft(selectedPoint, { kind: "point", x_px: item.width_px / 2, y_px: item.height_px / 2 });
    else {
      const size = Math.min(item.width_px, item.height_px) * 0.12;
      pointDraft(selectedPoint, { kind: geometryKind, x_px: (item.width_px - size) / 2, y_px: (item.height_px - size) / 2, width_px: size, height_px: geometryKind === "square" ? size : size * 0.7 });
    }
  };
  return <div className="image-canvas-scroll">
    {previewLoading && <div className="image-preview-state">Готовлю безопасный preview…</div>}
    {previewError && <div className="image-preview-state error"><Warning size={20} />{previewError}</div>}
    {preview && <div
      className={`image-canvas-scale tool-${geometryKind}`}
      style={{ width: `${zoom}%` }}
      tabIndex={interactive ? 0 : undefined}
      role={interactive ? "application" : "img"}
      aria-label={interactive
        ? `Изображение ${item.display_name}. Выберите Analytical Point и разместите ${geometryKind === "point" ? "точку кликом" : "область протягиванием"}. Enter размещает геометрию в центре.`
        : `Предпросмотр ${item.display_name} с сохранёнными размещениями.`}
      onPointerDown={interactive ? onPointerDown : undefined}
      onPointerUp={interactive ? onPointerUp : undefined}
      onKeyDown={interactive ? onKeyDown : undefined}
    >
      <img src={preview.preview_data_url} alt={`${assignment.media_type || "Изображение"} ${assignment.sample_name || "без Sample"}`} draggable="false" />
      <div className="image-placement-layer">
        {(assignment.placements || []).map((placement) => <PlacementMarker key={placement.analytical_point_id} placement={placement} item={item} selected={selectedPoint?.analytical_point_id === placement.analytical_point_id} onSelect={() => onSelectPlacement(placement.analytical_point_id)} />)}
        {draft && <PlacementMarker placement={draft} item={item} selected draft />}
      </div>
    </div>}
  </div>;
}

function PlacementStep({ items, assignments, setAssignments, points, activeItem, activeAssignment, activePath, setActivePath, busy, previews, previewLoading, previewError, onInvalidatePlan, onBack, onPreview, onPlan }) {
  const [pointScope, setPointScope] = useState("same_sample");
  const [pointSearch, setPointSearch] = useState("");
  const [selectedPointId, setSelectedPointId] = useState("");
  const [geometryKind, setGeometryKind] = useState("point");
  const [draft, setDraft] = useState(null);
  const [reasonCode, setReasonCode] = useState("");
  const [reasonComment, setReasonComment] = useState("");
  const [zoom, setZoom] = useState(100);
  const pointItems = points?.items || [];
  const selectedPoint = pointItems.find((point) => point.analytical_point_id === selectedPointId) || null;
  const currentPlacements = activeAssignment?.placements || [];
  const crossSample = Boolean(selectedPoint && selectedPoint.sample_name !== activeAssignment?.sample_name);
  const visiblePoints = useMemo(() => pointItems
    .filter((point) => pointScope === "all_samples" || point.sample_name === activeAssignment?.sample_name)
    .filter((point) => `${point.point_name} ${point.sample_name} ${point.methods.join(" ")} ${point.analysis_ids.join(" ")}`.toLocaleLowerCase().includes(pointSearch.toLocaleLowerCase()))
    .sort((left, right) => {
      const leftPlaced = currentPlacements.some((placement) => placement.analytical_point_id === left.analytical_point_id);
      const rightPlaced = currentPlacements.some((placement) => placement.analytical_point_id === right.analytical_point_id);
      return Number(leftPlaced) - Number(rightPlaced) || left.point_name.localeCompare(right.point_name, "ru", { numeric: true });
    }), [activeAssignment?.sample_name, currentPlacements, pointItems, pointScope, pointSearch]);
  const totalPlacements = Object.values(assignments).reduce((count, assignment) => count + assignment.placements.length, 0);
  const crossSampleCount = Object.values(assignments).reduce((count, assignment) => count + assignment.placements.filter((placement) => placement.cross_sample_exception_reason).length, 0);

  useEffect(() => {
    setDraft(null); setReasonCode(""); setReasonComment(""); setZoom(100);
  }, [activePath]);
  useEffect(() => { onPreview(activeItem); }, [activeItem, onPreview]);

  const choosePoint = (point) => {
    setSelectedPointId(point.analytical_point_id);
    setDraft(null); setReasonCode(""); setReasonComment("");
  };
  const saveDraft = () => {
    if (!draft || (crossSample && !reasonCode)) return;
    const reason = crossSample
      ? `${CROSS_SAMPLE_REASONS[reasonCode]}${reasonComment.trim() ? ` — ${reasonComment.trim()}` : ""}`
      : null;
    const placement = { analytical_point_id: draft.analytical_point_id, geometry: draft.geometry, cross_sample_exception_reason: reason, point_name: draft.point_name, point_sample_name: draft.point_sample_name };
    onInvalidatePlan();
    setAssignments((current) => ({
      ...current,
      [activePath]: { ...current[activePath], placements: [...current[activePath].placements.filter((item) => item.analytical_point_id !== placement.analytical_point_id), placement] },
    }));
    setDraft(null); setReasonCode(""); setReasonComment("");
  };
  const removePlacement = (pointId) => {
    onInvalidatePlan();
    setAssignments((current) => ({ ...current, [activePath]: { ...current[activePath], placements: current[activePath].placements.filter((item) => item.analytical_point_id !== pointId) } }));
    setDraft(null);
  };
  const selectedPlacement = currentPlacements.find((placement) => placement.analytical_point_id === selectedPointId);

  return <>
    <nav className="image-placement-filebar" aria-label="Изображения для размещения точек">
      <span><Images size={17} /><b>Изображения</b></span>
      <div>
        {items.map((item, index) => {
          const assignment = assignments[item.source_path];
          const focused = item.source_path === activePath;
          return <button
            type="button"
            className={focused ? "active" : ""}
            aria-current={focused ? "true" : undefined}
            key={item.source_path}
            onClick={() => setActivePath(item.source_path)}
          >
            <b>{index + 1}. {item.display_name}</b>
            <small>{assignment.media_type} · {assignment.placements.length} размещено</small>
          </button>;
        })}
      </div>
      <strong>{items.findIndex((item) => item.source_path === activePath) + 1} / {items.length}</strong>
    </nav>
    <section className="image-point-workspace">
      <aside className="image-point-list">
        <header><b>Аналитические точки</b><span>{visiblePoints.length}</span></header>
        <div className="point-scope-toggle"><button type="button" className={pointScope === "same_sample" ? "active" : ""} onClick={() => setPointScope("same_sample")}>Этот Sample</button><button type="button" className={pointScope === "all_samples" ? "active" : ""} onClick={() => setPointScope("all_samples")}>Другой Sample…</button></div>
        <label className="point-search"><MagnifyingGlass size={16} /><input aria-label="Найти Analytical Point" placeholder="Точка, метод или Analysis ID" value={pointSearch} onChange={(event) => setPointSearch(event.target.value)} /></label>
        <div className="point-candidate-list">
          {visiblePoints.map((point) => {
            const placed = currentPlacements.some((placement) => placement.analytical_point_id === point.analytical_point_id);
            return <button type="button" className={selectedPointId === point.analytical_point_id ? "selected" : ""} key={point.analytical_point_id} onClick={() => choosePoint(point)}>
              <span className={`point-radio${selectedPointId === point.analytical_point_id ? " checked" : ""}`}></span>
              <span><b>{point.point_name}</b><small>{point.methods.length ? point.methods.join(", ") : `${point.analysis_ids.length} Analysis`}</small><em>{point.sample_name}</em></span>
              <strong className={placed ? "placed" : ""}>{placed ? "размещена" : "не размещена"}</strong>
            </button>;
          })}
          {visiblePoints.length === 0 && <div className="point-list-empty"><MapPin size={28} /><b>Точек в этой группе нет</b><span>Можно выбрать другой Sample или завершить импорт без точек.</span></div>}
        </div>
      </aside>

      <main className="image-point-canvas-pane">
        <header><div><b>Sample: {activeAssignment.sample_name}</b><span>Шлиф: {activeAssignment.thin_section_name}</span><span>{activeItem.display_name} ({activeAssignment.media_type})</span></div><div className="image-geometry-tools">{GEOMETRY_TYPES.map(([value, label]) => <button type="button" className={geometryKind === value ? "active" : ""} key={value} onClick={() => { setGeometryKind(value); setDraft(null); }}>{label}</button>)}</div><label className="image-zoom">Zoom <input type="range" min="100" max="300" step="25" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /><b>{zoom}%</b></label></header>
        <ImageCanvas item={activeItem} assignment={activeAssignment} preview={previews[activePath]} previewLoading={previewLoading === activePath} previewError={previewError[activePath]} zoom={zoom} geometryKind={geometryKind} draft={draft} setDraft={setDraft} selectedPoint={selectedPoint} onSelectPlacement={setSelectedPointId} />
        <div className="image-canvas-hint"><Info size={17} />{selectedPoint ? (geometryKind === "point" ? `Кликни на изображении, чтобы поставить ${selectedPoint.point_name}.` : `Протяни ${geometryKind === "square" ? "квадрат" : "прямоугольник"} на изображении.`) : "Сначала выбери Analytical Point слева."}</div>
      </main>

      <aside className="image-point-inspector">
        <header><span>Точка</span><h2>{selectedPoint?.point_name || "не выбрана"}</h2>{selectedPoint && <p>Sample {selectedPoint.sample_name}</p>}</header>
        {selectedPoint ? <>
          <section><h3>Связанные Analyses</h3><div className="point-analysis-list">{selectedPoint.analysis_ids.map((id, index) => <div key={id}><span>{selectedPoint.methods[index] || `Analysis ${index + 1}`}</span><b title={id}>{shortenId(id)}</b></div>)}</div></section>
          {crossSample && <section className="cross-sample-warning"><Warning size={19} weight="fill" /><div><b>Точка другого Sample</b><span>Изображение: {activeAssignment.sample_name}<br />Точка: {selectedPoint.sample_name}</span></div></section>}
          {draft && <section className="placement-draft"><h3>Предпросмотр размещения</h3><p>{geometryLabel(draft.geometry)}</p>{crossSample && <><label>Причина исключения<select aria-label="Причина межобразцового исключения" value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}><option value="">Выбери причину</option>{Object.entries(CROSS_SAMPLE_REASONS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Комментарий<textarea value={reasonComment} onChange={(event) => setReasonComment(event.target.value)} maxLength={500} placeholder="Дополнительное обоснование (необязательно)" /></label></>}<button className="primary-button inspector-action" type="button" onClick={saveDraft} disabled={busy || (crossSample && !reasonCode)}>Сохранить привязку</button></section>}
          {!draft && !selectedPlacement && <section className="point-instruction"><Info size={18} /><p>Выбери Point, Rectangle или Square и укажи место на изображении. Положение останется preview до сохранения.</p></section>}
          {selectedPlacement && !draft && <section className="saved-placement"><CheckCircle size={19} weight="fill" /><div><b>Размещение сохранено в черновике</b><span>{geometryLabel(selectedPlacement.geometry)}</span>{selectedPlacement.cross_sample_exception_reason && <em>{selectedPlacement.cross_sample_exception_reason}</em>}</div><button className="danger-outline" type="button" onClick={() => removePlacement(selectedPointId)}><Trash size={16} /> Снять только связь</button></section>}
        </> : <div className="point-inspector-empty"><MapPin size={34} /><p>Выбери точку слева. Фокус не меняет Selection и ничего не записывает.</p></div>}
      </aside>
    </section>
    <footer className="image-commit-bar">
      <button className="outline-button" type="button" onClick={onBack} disabled={busy}><ArrowLeft size={17} /> Назад</button>
      <div><b>{totalPlacements} размещено</b><span>{crossSampleCount ? ` · ${crossSampleCount} исключений` : " · без исключений"}</span></div>
      <small>Неразмещённые точки не блокируют импорт</small>
      <button className="primary-button" type="button" disabled={busy || Boolean(draft)} onClick={() => onPlan(items.map((item) => cleanAssignment(assignments[item.source_path])))}>Далее: проверка <ArrowRight size={18} /></button>
    </footer>
  </>;
}

function ReviewStep({ plan, assignments, activePath, setActivePath, previews, previewLoading, previewError, onPreview, busy, onBack, onApply }) {
  const items = plan?.items || [];
  const activeItem = items.find((item) => item.source_path === activePath) || items[0];
  const placementCount = items.reduce((count, item) => count + item.placements.length, 0);
  const exceptionCount = items.reduce((count, item) => count + item.placements.filter((placement) => placement.cross_sample_exception_reason).length, 0);
  const unplacedMediaCount = items.filter((item) => item.placements.length === 0).length;
  useEffect(() => { onPreview(activeItem); }, [activeItem, onPreview]);
  return <>
    <SourcePane items={items} assignments={assignments} activePath={activeItem?.source_path} setActivePath={setActivePath} phase="review" />
    <main className="image-review-pane">
      <header><div><h2>Проверка импорта изображений</h2><p>Проверь назначения, размещения и исключения до единой транзакции.</p></div></header>
      <div className="image-review-table" role="table" aria-label="Проверка импорта изображений">
        <div className="image-review-head" role="row"><span>Файл</span><span>Sample</span><span>Шлиф</span><span>Тип</span><span>Точки</span><span>Исключения</span><span>Статус</span></div>
        {items.map((item) => {
          const exceptions = item.placements.filter((placement) => placement.cross_sample_exception_reason).length;
          return <button type="button" role="row" className={item.source_path === activeItem.source_path ? "active" : ""} key={item.source_path} onClick={() => setActivePath(item.source_path)}><span>{item.display_name}</span><span>{item.sample_name}</span><span>{item.thin_section_name}</span><span className={`image-type type-${item.media_type}`}>{item.media_type}</span><span>{item.placements.length}</span><span className={exceptions ? "review-question" : ""}>{exceptions}</span><span className="image-ready"><CheckCircle size={15} weight="fill" /> Готово</span></button>;
        })}
      </div>
      <div className="image-review-legend"><span><i className="ready"></i>Готово</span><span><i className="question"></i>Подтверждённое исключение</span><span><i></i>Без пространственной точки</span></div>
    </main>
    <aside className="image-review-inspector">
      <header><span>Выбрано</span><h2>{activeItem?.display_name}</h2></header>
      {activeItem && <>
        <div className="review-preview"><ImageCanvas item={activeItem} assignment={activeItem} preview={previews[activeItem.source_path]} previewLoading={previewLoading === activeItem.source_path} previewError={previewError[activeItem.source_path]} zoom={100} geometryKind="point" draft={null} setDraft={() => {}} selectedPoint={null} onSelectPlacement={() => {}} interactive={false} /></div>
        <section><h3>Размещённые Analytical Points ({activeItem.placements.length})</h3>{activeItem.placements.length ? <div className="review-placement-list">{activeItem.placements.map((placement) => <div key={placement.analytical_point_id}><b>{placement.point_name || shortenId(placement.analytical_point_id)}</b><span>{geometryLabel(placement.geometry)}</span>{placement.cross_sample_exception_reason && <em>{placement.cross_sample_exception_reason}</em>}</div>)}</div> : <p className="review-empty-copy">На этом изображении нет пространственных точек. Импорт всё равно разрешён.</p>}</section>
      </>}
    </aside>
    <footer className="image-review-footer">
      <div className="review-safety"><Info size={20} /><span>Создаются Media Assets и подтверждённые пространственные связи. Исходные файлы, Samples и Analyses не изменяются.</span></div>
      <div><b>{items.length}</b><span>изображений</span></div><div><b>{placementCount}</b><span>точек/областей</span></div><div><b>{exceptionCount}</b><span>исключений</span></div><div><b>{unplacedMediaCount}</b><span>без точек</span></div>
      <button className="outline-button" type="button" onClick={onBack} disabled={busy}><ArrowLeft size={17} /> К размещению</button>
      <button className="primary-button" type="button" onClick={() => onApply(plan)} disabled={busy}>Завершить импорт изображений <ArrowRight size={18} /></button>
    </footer>
  </>;
}

export function ImagesWorkspace({ inspection, plan, points = { items: [] }, busy, onChooseFiles, onChooseFolder, onRemove, onPreview = async () => null, onPlan, onApply, onCancel, onInvalidatePlan = () => {} }) {
  const items = inspection?.items || [];
  const [phase, setPhase] = useState("assignment");
  const [assignments, setAssignments] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [activePath, setActivePath] = useState("");
  const [previews, setPreviews] = useState({});
  const [previewLoading, setPreviewLoading] = useState("");
  const [previewError, setPreviewError] = useState({});
  const requestedPreviews = useRef(new Set());
  const previewGeneration = useRef(0);
  const sourceFingerprints = useRef(new Map());
  const [changedSources, setChangedSources] = useState([]);

  useEffect(() => {
    setChangedSources(items.filter((item) => sourceFingerprints.current.has(item.source_path)
      && sourceFingerprints.current.get(item.source_path) !== item.source_fingerprint).map((item) => item.display_name));
    sourceFingerprints.current = new Map(items.map((item) => [item.source_path, item.source_fingerprint]));
    setAssignments((current) => Object.fromEntries(items.map((item) => {
      const retained = current[item.source_path];
      return [item.source_path, retained && retained._source_fingerprint === item.source_fingerprint ? retained : initialAssignment(item)];
    })));
    setSelected(new Set(items.map((item) => item.source_path)));
    setActivePath((current) => items.some((item) => item.source_path === current) ? current : (items[0]?.source_path || ""));
    requestedPreviews.current.clear();
    previewGeneration.current += 1;
    setPreviewLoading("");
    setPreviews({}); setPreviewError({}); setPhase("assignment");
  }, [inspection]);
  useEffect(() => { if (plan) setPhase("review"); }, [plan]);

  const activeItem = items.find((item) => item.source_path === activePath) || items[0];
  const activeAssignment = activeItem ? assignments[activeItem.source_path] : null;
  // A new inspection arrives before the reconciliation effect runs. Never
  // render placement controls against the previous batch's assignments.
  const visiblePhase = items.every((item) => assignments[item.source_path]?._source_fingerprint === item.source_fingerprint)
    ? phase : "assignment";
  const loadPreview = useCallback(async (item) => {
    if (!item || requestedPreviews.current.has(item.source_path)) return;
    requestedPreviews.current.add(item.source_path);
    const generation = previewGeneration.current;
    setPreviewLoading(item.source_path);
    setPreviewError((current) => ({ ...current, [item.source_path]: "" }));
    try {
      const preview = await onPreview(item.source_path);
      if (generation !== previewGeneration.current) return;
      if (!preview?.preview_data_url) throw new Error("Preview изображения недоступен.");
      if (preview.source_fingerprint && preview.source_fingerprint !== item.source_fingerprint) throw new Error("Файл изменился после проверки. Выбери его заново.");
      setPreviews((current) => ({ ...current, [item.source_path]: preview }));
    } catch (caught) {
      if (generation !== previewGeneration.current) return;
      setPreviewError((current) => ({ ...current, [item.source_path]: caught instanceof Error ? caught.message : String(caught) }));
    } finally {
      if (generation === previewGeneration.current) setPreviewLoading((current) => current === item.source_path ? "" : current);
    }
  }, [onPreview]);

  if (items.length === 0) {
    return <section className="images-empty"><Images size={52} weight="duotone" /><h1>Добавить изображения</h1><p>Выбери серию BSE, PPL, XPL, обычные фотографии или папку с вложенными папками. PetroLab проверит форматы и предложит назначения из имён файлов.</p><div className="images-empty-actions"><button className="primary-button large" type="button" onClick={onChooseFiles} disabled={busy}><Plus size={20} /> Выбрать файлы</button><button className="outline-button large" type="button" onClick={onChooseFolder} disabled={busy}><FolderOpen size={20} /> Выбрать папку</button></div><small>PNG, JPEG, TIFF и BMP. Исходные файлы не переименовываются и не изменяются.</small></section>;
  }
  if (visiblePhase === "review" && plan) return <section className="images-workspace image-review-workspace"><ReviewStep plan={plan} assignments={assignments} activePath={activePath} setActivePath={setActivePath} previews={previews} previewLoading={previewLoading} previewError={previewError} onPreview={loadPreview} busy={busy} onBack={() => { onInvalidatePlan(); setPhase("points"); }} onApply={onApply} /></section>;
  return <section className={`images-workspace${visiblePhase === "points" ? " image-placement-workspace" : ""}`}>
    {visiblePhase === "assignment" && <SourcePane items={items} assignments={assignments} activePath={activeItem?.source_path} setActivePath={setActivePath} phase="assignment" />}
    {visiblePhase === "assignment"
      ? <AssignmentStep items={items} inspection={inspection} changedSources={changedSources} assignments={assignments} setAssignments={setAssignments} selected={selected} setSelected={setSelected} activeItem={activeItem} activeAssignment={activeAssignment} setActivePath={setActivePath} busy={busy} onChooseFiles={onChooseFiles} onChooseFolder={onChooseFolder} onRemove={onRemove} onCancel={onCancel} onInvalidatePlan={onInvalidatePlan} onContinue={() => setPhase("points")} />
      : <PlacementStep items={items} assignments={assignments} setAssignments={setAssignments} points={points} activeItem={activeItem} activeAssignment={activeAssignment} activePath={activePath} setActivePath={setActivePath} busy={busy} previews={previews} previewLoading={previewLoading} previewError={previewError} onInvalidatePlan={onInvalidatePlan} onBack={() => setPhase("assignment")} onPreview={loadPreview} onPlan={onPlan} />}
  </section>;
}
