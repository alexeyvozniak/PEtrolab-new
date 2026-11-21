import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ThinSectionLinks } from "./ThinSectionLinks";
import { MediaAttachment } from "./MediaAttachment";
import "./mediaWorkspace.css";

export function MediaViewer({ image, annotations, onPlace, loadRegion, focus, shape = "point" }) {
  const [zoom, setZoom] = useState(100);
  const [start, setStart] = useState(null);
  const [preview, setPreview] = useState(null);
  const [tile, setTile] = useState(null);
  const [tileError, setTileError] = useState("");
  const viewer = useRef(null);
  const scene = useRef(null);
  const anchor = useRef(null);
  const regionLoader = useRef(loadRegion);
  regionLoader.current = loadRegion;
  const precision = zoom > 400 && Boolean(loadRegion);
  const changeZoom = (value) => {
    const viewport = viewer.current;
    const bounds = scene.current.getBoundingClientRect();
    if (bounds.width && bounds.height) {
      anchor.current = { zoom: value, x: (viewport.scrollLeft + viewport.clientWidth / 2) / bounds.width,
        y: (viewport.scrollTop + viewport.clientHeight / 2) / bounds.height };
    }
    setZoom(value);
  };
  useLayoutEffect(() => {
    if (!focus) return;
    anchor.current = { zoom: 2000, x: (focus.x_px + (focus.width_px ?? 0) / 2) / image.width_px,
      y: (focus.y_px + (focus.height_px ?? 0) / 2) / image.height_px };
    setZoom(2000);
  }, [focus, image]);
  useLayoutEffect(() => {
    if (anchor.current?.zoom !== zoom) return;
    const viewport = viewer.current;
    const bounds = scene.current.getBoundingClientRect();
    viewport.scrollLeft = anchor.current.x * bounds.width - viewport.clientWidth / 2;
    viewport.scrollTop = anchor.current.y * bounds.height - viewport.clientHeight / 2;
    anchor.current = null;
  }, [zoom, focus]);
  useEffect(() => {
    setTile(null);
    setTileError("");
    if (!precision) return;
    const viewport = viewer.current;
    let sequence = 0;
    let timer;
    const update = () => {
      const current = ++sequence;
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const { width: displayedWidth, height: displayedHeight } = scene.current.getBoundingClientRect();
        if (!displayedWidth || !displayedHeight) return;
        const px = image.width_px / displayedWidth;
        const py = image.height_px / displayedHeight;
        const width = Math.min(1400, image.width_px, Math.ceil(viewport.clientWidth * px) + 2);
        const height = Math.min(1400, image.height_px, Math.ceil(viewport.clientHeight * py) + 2);
        const left = Math.max(0, Math.min(image.width_px - width,
          Math.floor((viewport.scrollLeft + viewport.clientWidth / 2) * px - width / 2)));
        const top = Math.max(0, Math.min(image.height_px - height,
          Math.floor((viewport.scrollTop + viewport.clientHeight / 2) * py - height / 2)));
        try {
          const result = await regionLoader.current({ left, top, width, height });
          if (current === sequence) { setTile(result); setTileError(""); }
        } catch (caught) {
          if (current === sequence) { setTile(null); setTileError(caught.message); }
        }
      }, 120);
    };
    update();
    viewport.addEventListener("scroll", update);
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resize?.observe(viewport);
    return () => {
      sequence += 1;
      clearTimeout(timer);
      resize?.disconnect();
      viewport.removeEventListener("scroll", update);
    };
  }, [zoom, precision, image, focus]);
  const position = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x_px: Math.max(0, Math.min(image.width_px - 0.01, (event.clientX - bounds.left) * image.width_px / bounds.width)),
      y_px: Math.max(0, Math.min(image.height_px - 0.01, (event.clientY - bounds.top) * image.height_px / bounds.height)),
    };
  };
  const region = (a, b) => {
    const width = Math.abs(a.x_px - b.x_px);
    const height = Math.abs(a.y_px - b.y_px);
    const edge = Math.min(width, height);
    const width_px = shape === "square" ? edge : width;
    const height_px = shape === "square" ? edge : height;
    return { kind: shape, x_px: b.x_px < a.x_px ? a.x_px - width_px : a.x_px,
      y_px: b.y_px < a.y_px ? a.y_px - height_px : a.y_px, width_px, height_px };
  };
  const reset = () => { setStart(null); setPreview(null); };
  const length = Math.max(image.width_px, image.height_px) * 100 / zoom;
  return <>
    <label className="media-zoom">Масштаб {zoom}% <input aria-label="Масштаб изображения" type="range" min="50" max={loadRegion ? 2000 : 400} step="25" value={zoom}
      onChange={(event) => changeZoom(Number(event.target.value))} /></label>
    {precision && tileError && <p role="alert">{tileError}</p>}
    <div className="media-viewer" ref={viewer}>
      <div className="media-scene" ref={scene} style={{ width: `${zoom}%`, aspectRatio: `${image.width_px} / ${image.height_px}` }}>
        <img src={image.preview_url} alt="Изображение шлифа" draggable={false} />
        {precision && tile && <img className="media-precision-region" src={tile.preview_url} alt="" draggable={false} style={{
          left: `${tile.region.left * 100 / image.width_px}%`, top: `${tile.region.top * 100 / image.height_px}%`,
          width: `${tile.region.width * 100 / image.width_px}%`, height: `${tile.region.height * 100 / image.height_px}%`,
        }} />}
        <svg viewBox={`0 0 ${image.width_px} ${image.height_px}`} preserveAspectRatio="none" aria-label="Аннотации изображения"
          className={onPlace ? "editable" : undefined}
          onPointerDown={onPlace ? (event) => {
            if (event.button !== 0) return;
            const location = position(event);
            if (precision && (!tile || location.x_px < tile.region.left || location.y_px < tile.region.top
                || location.x_px >= tile.region.left + tile.region.width || location.y_px >= tile.region.top + tile.region.height)) return;
            if (shape === "point") { onPlace({ kind: "point", ...location }); return; }
            setStart(location);
            event.currentTarget.setPointerCapture(event.pointerId);
          } : undefined}
          onPointerMove={start ? (event) => setPreview(region(start, position(event))) : undefined}
          onPointerUp={start ? (event) => {
            const geometry = region(start, position(event));
            if (geometry.width_px > 0 && geometry.height_px > 0) onPlace(geometry);
            reset();
          } : undefined}
          onPointerCancel={reset} onLostPointerCapture={reset}>
          {[...annotations, ...(preview ? [{ ...preview, id: "draft" }] : [])].map((item) =>
            <g key={item.id}>
              {item.kind === "point"
                ? <circle cx={item.x_px} cy={item.y_px} r={length / 95} />
                : <rect x={item.x_px} y={item.y_px} width={item.width_px} height={item.height_px} />}
              {item.label && <text x={item.x_px + length / 70} y={item.y_px} fontSize={length / 55}>{item.label}</text>}
            </g>)}
        </svg>
      </div>
    </div>
  </>;
}

export function MediaGallery({ images, previewMedia, exportOriginal, exportRendered, showPoints = false, pointLinks, mediaLinks, reloadSample }) {
  const [openId, setOpenId] = useState("");
  const [image, setImage] = useState(null);
  const [status, setStatus] = useState(null);
  const [pending, setPending] = useState(false);
  const [focus, setFocus] = useState(null);
  const [attachment, setAttachment] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [shape, setShape] = useState("rectangle");
  const inspectPoint = Boolean(pointLinks && focus?.analytical_point_id);
  const [renderOptions, setRenderOptions] = useState({ points: true, regions: true, labels: true });
  const open = async (id) => {
    setOpenId(id);
    setImage(null);
    setFocus(null);
    setDrawing(false);
    setAttachment(false);
    setStatus(null);
    setPending(true);
    try { setImage(await previewMedia(id)); }
    catch (error) { setStatus({ error: error.message }); }
    finally { setPending(false); }
  };
  const saveRegion = async (geometry) => {
    setPending(true);
    setStatus(null);
    try {
      const region = await mediaLinks.createRegion(openId, geometry);
      setImage((current) => ({ ...current, annotations: [...current.annotations, region] }));
      setFocus(region);
      setDrawing(false);
      setAttachment(true);
    } catch (error) { setStatus({ error: error.message }); }
    finally { setPending(false); }
  };
  const save = async (exporter, item, options) => {
    setStatus(null);
    setPending(true);
    try {
      const result = await exporter(item, options);
      if (result) setStatus({ notice: `Сохранено: ${result.output_path}` });
    } catch (error) { setStatus({ error: error.message }); }
    finally { setPending(false); }
  };
  if (!images.length) return <p>У образца нет связанных изображений.</p>;
  return <>
    <ul className="sample-items media-items">
      {images.map((item) => <li key={item.media_asset_id}>
        <div><b>{item.display_name}</b><p>{item.media_type} · {item.width_px} × {item.height_px}</p></div>
        <div className="point-row-actions">
          {previewMedia && <button className="outline-button" type="button" disabled={pending}
            onClick={() => open(item.media_asset_id)}>Открыть</button>}
          {exportOriginal && <button className="outline-button" type="button" disabled={pending}
            onClick={() => save(exportOriginal, item)}>Выгрузить оригинал</button>}
        </div>
      </li>)}
    </ul>
    {status && <p role={status.error ? "alert" : "status"}>{status.error || status.notice}</p>}
    {image && <>
      {mediaLinks && <div className="point-row-actions media-attachment-tools">
        <button type="button" className="outline-button" aria-pressed={attachment} disabled={pending || drawing}
          onClick={() => setAttachment(!attachment)}>Медиа и привязка</button>
        <button type="button" className="outline-button" disabled={pending} onClick={() => { setDrawing(!drawing); setAttachment(true); }}>
          {drawing ? "Отменить выделение" : "Выделить область"}
        </button>
        {drawing && <label>Форма области <select value={shape} disabled={pending} onChange={(event) => setShape(event.target.value)}>
          <option value="rectangle">Прямоугольник</option><option value="square">Квадрат</option>
        </select></label>}
      </div>}
      {drawing && <p role="status">Протяните область на изображении.</p>}
      <div className={showPoints ? `media-with-points${inspectPoint || attachment ? " media-with-inspector" : ""}` : undefined}>
        {showPoints && <section aria-label="Точки снимка">
          {image.annotations.length > 0 ? <ul className="sample-items">{image.annotations.map((item) => <li key={item.spatial_annotation_id}>
            <button className="outline-button" type="button" aria-pressed={focus?.spatial_annotation_id === item.spatial_annotation_id}
              disabled={pending} onClick={() => { setDrawing(false); setFocus({ ...item }); }}>{item.point_name || item.label || (item.geometry_kind === "point" ? "Точка" : "Область")}</button>
          </li>)}</ul> : <p>На снимке нет сохранённых точек или областей.</p>}
        </section>}
        <div>
          <MediaViewer key={openId} image={image} loadRegion={(region) => previewMedia(openId, region)} focus={focus}
            onPlace={drawing && !pending ? saveRegion : undefined} shape={shape} annotations={image.annotations.map((item) => ({
            ...item, id: item.spatial_annotation_id, kind: item.geometry_kind, label: item.point_name || item.label,
          }))} />
        </div>
        {attachment && focus && !drawing && <MediaAttachment key={focus.spatial_annotation_id} target={focus}
          images={images.filter((item) => item.media_asset_id !== openId)} actions={mediaLinks} previewMedia={previewMedia} reloadSample={reloadSample} />}
        {attachment && (!focus || drawing) && <p className="media-attachment">Выберите точку или выделите область на снимке.</p>}
        {!attachment && inspectPoint && <ThinSectionLinks key={focus.analytical_point_id} point={focus} actions={pointLinks} />}
      </div>
      {exportRendered && <fieldset className="media-export-options">
        <legend>PNG с метками и подписями</legend>
        {Object.entries({ points: "Точки", regions: "Области", labels: "Подписи" }).map(([key, label]) =>
          <label key={key}><input type="checkbox" checked={renderOptions[key]} disabled={pending}
            onChange={(event) => setRenderOptions({ ...renderOptions, [key]: event.target.checked })} /> {label}</label>)}
        <button className="outline-button" type="button" disabled={pending}
          onClick={() => save(exportRendered, images.find(({ media_asset_id }) => media_asset_id === openId), renderOptions)}>
          Выгрузить с разметкой
        </button>
      </fieldset>}
    </>}
  </>;
}

export function MediaImport({ actions, onCancel, onDone }) {
  const [files, setFiles] = useState([]);
  const [samples, setSamples] = useState([]);
  const [sampleId, setSampleId] = useState("");
  const [newSample, setNewSample] = useState("");
  const [section, setSection] = useState("");
  const [context, setContext] = useState(null);
  const [activePath, setActivePath] = useState("");
  const [image, setImage] = useState(null);
  const [pointId, setPointId] = useState("");
  const [pointSampleId, setPointSampleId] = useState("");
  const [pointContext, setPointContext] = useState(null);
  const [exceptionReason, setExceptionReason] = useState("");
  const [shape, setShape] = useState("point");
  const [plan, setPlan] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const pickedSample = samples.find(({ sample_id }) => sample_id === sampleId);
  const sampleName = pickedSample?.sample_name || newSample.trim();
  const active = files.find(({ source_path }) => source_path === activePath);
  const points = pointSampleId ? (pointContext?.sample_id === pointSampleId ? pointContext.points : [])
    : context?.sample_id === sampleId ? context.points : [];
  useEffect(() => {
    let alive = true;
    actions.samples().then((items) => { if (alive) setSamples(items); })
      .catch((caught) => { if (alive) setError(caught.message); });
    return () => { alive = false; };
  }, [actions.samples]);
  useEffect(() => {
    if (!sampleId || sampleId === "new") return;
    let alive = true;
    actions.sample(sampleId).then((item) => { if (alive) setContext(item); })
      .catch((caught) => { if (alive) setError(caught.message); });
    return () => { alive = false; };
  }, [actions.sample, sampleId]);
  useEffect(() => {
    if (!pointSampleId) return;
    let alive = true;
    actions.sample(pointSampleId).then((item) => { if (alive) setPointContext(item); })
      .catch((caught) => { if (alive) setError(caught.message); });
    return () => { alive = false; };
  }, [actions.sample, pointSampleId]);
  const perform = async (task) => {
    setPending(true);
    setError("");
    try { await task(); }
    catch (caught) { setError(caught.message); }
    finally { setPending(false); }
  };
  const pick = () => perform(async () => {
    const paths = await actions.pick();
    if (!paths.length) return;
    const inspection = await actions.inspect(paths);
    setFiles((current) => {
      const seen = new Set(current.map(({ source_fingerprint }) => source_fingerprint));
      const added = inspection.items.flatMap((item) => {
        if (seen.has(item.source_fingerprint)) return [];
        seen.add(item.source_fingerprint);
        return [{ ...item, media_type: "BSE", placements: [] }];
      });
      return [...current, ...added];
    });
  });
  const pickPreview = (item) => perform(async () => {
    setImage(null);
    setActivePath(item.source_path);
    const preview = await actions.preview(item.source_path);
    if (preview.source_fingerprint !== item.source_fingerprint) throw new Error("Изображение изменилось. Добавьте файл заново.");
    setImage(preview);
  });
  const changeFile = (path, changes) => setFiles((current) => current.map((item) => item.source_path === path ? { ...item, ...changes } : item));
  const changeSample = (value) => {
    setSampleId(value);
    setPointId("");
    setPointSampleId("");
    setExceptionReason("");
    setFiles((current) => current.map((item) => ({ ...item, placements: [] })));
  };
  const place = (geometry) => {
    const placements = active.placements.filter((item) => item.analytical_point_id !== pointId);
    changeFile(activePath, { placements: [...placements, { analytical_point_id: pointId, geometry,
      pointLabel: points.find(({ analytical_point_id }) => analytical_point_id === pointId)?.point_name,
      cross_sample_exception_reason: pointSampleId ? exceptionReason.trim() : null }] });
  };
  const review = () => perform(async () => {
    setPlan(await actions.plan(files.map((item) => ({
      source_path: item.source_path, expected_source_fingerprint: item.source_fingerprint, ownership_mode: "managed_copy",
      media_type: item.media_type, sample_name: sampleName, thin_section_name: section.trim(),
      placements: item.placements.map(({ analytical_point_id, geometry, cross_sample_exception_reason }) =>
        ({ analytical_point_id, geometry, cross_sample_exception_reason })),
      sample_target: { mode: sampleId === "new" ? "new" : "existing", sample_id: sampleId === "new" ? null : sampleId },
    }))));
  });
  return <section className="sample-workspace media-import">
    <div className="sample-header"><h2>Импорт изображений шлифов</h2>
      <button className="outline-button" type="button" disabled={pending} onClick={onCancel}>К изображениям</button></div>
    {error && <p role="alert">{error}</p>}
    {plan ? <>
      <h3>Проверка перед импортом</h3>
      <ul className="sample-items">{plan.items.map((item) => <li key={item.media_asset_id}>
        <span>{item.display_name} · {item.media_type} · {item.sample_name} · {item.thin_section_name}</span>
        <span>Привязок: {item.placements.length}</span>
      </li>)}</ul>
      {plan.items.some((item) => !item.placements.length) && <p>В пакете есть изображения без размещённых точек.</p>}
      {plan.items.flatMap((item) => item.placements.filter((placement) => placement.cross_sample_exception_reason)
        .map((placement) => <p key={placement.spatial_annotation_id}>
          {item.display_name} · точка другого образца · {placement.cross_sample_exception_reason}
        </p>))}
      <div className="point-row-actions">
        <button className="outline-button" type="button" disabled={pending} onClick={() => setPlan(null)}>Назад к назначению</button>
        <button className="primary-button" type="button" disabled={pending} onClick={() => perform(async () => onDone(await actions.commit(plan)))}>
          Импортировать изображения
        </button>
      </div>
    </> : <div className="sample-overview">
      <section className="sample-card">
        <h3>Файлы, образец и шлиф</h3>
        <button className="outline-button" type="button" disabled={pending} onClick={pick}>Выбрать изображения</button>
        <div className="sample-form">
          <label>Физический образец <select value={sampleId} disabled={pending} onChange={(event) => changeSample(event.target.value)}>
            <option value="">Выберите образец</option>
            {samples.map((item) => <option value={item.sample_id} key={item.sample_id}>{item.sample_name}</option>)}
            <option value="new">Новый образец</option>
          </select></label>
          {sampleId === "new" && <label>Имя нового образца<input value={newSample} disabled={pending} maxLength={200} onChange={(event) => setNewSample(event.target.value)} /></label>}
          <label>Имя шлифа<input list="sample-thin-sections" value={section} maxLength={200} disabled={pending}
            onChange={(event) => setSection(event.target.value)} /></label>
          <datalist id="sample-thin-sections">{(context?.sample_id === sampleId ? context.thin_sections : []).map((item) =>
            <option key={item.thin_section_id} value={item.thin_section_name} />)}</datalist>
        </div>
        <ul className="sample-items media-items">{files.map((item) => <li key={item.source_path}>
          <button className="outline-button" type="button" aria-pressed={activePath === item.source_path} disabled={pending}
            onClick={() => pickPreview(item)}>{item.display_name}</button>
          <label>Тип <select value={item.media_type} disabled={pending} onChange={(event) => changeFile(item.source_path, { media_type: event.target.value })}>
            {["BSE", "PPL", "XPL", "Аналитические точки", "Другое"].map((type) => <option key={type}>{type}</option>)}
          </select></label>
          <button className="outline-button" type="button" disabled={pending} onClick={() => {
            if (item.source_path === activePath) { setActivePath(""); setImage(null); }
            setFiles((current) => current.filter(({ source_path }) => source_path !== item.source_path));
          }}>Убрать</button>
        </li>)}</ul>
        <button className="primary-button" type="button" disabled={pending || !sampleId || !sampleName || !section.trim() || !files.length}
          onClick={review}>Проверить импорт изображений</button>
      </section>
      <section className="sample-card">
        <h3>Точки на изображении</h3>
        {!image && <p>Выберите файл для предпросмотра.</p>}
        {image && active && <>
          <div className="sample-form">
            <label>Образец аналитической точки<select value={pointSampleId} disabled={pending}
              onChange={(event) => { setPointSampleId(event.target.value); setPointId(""); setExceptionReason(""); }}>
              <option value="">Текущий образец</option>
              {samples.filter((item) => item.sample_id !== sampleId).map((item) =>
                <option value={item.sample_id} key={item.sample_id}>{item.sample_name}</option>)}
            </select></label>
            <label>Аналитическая точка<select value={pointId} disabled={pending} onChange={(event) => setPointId(event.target.value)}>
              <option value="">Без привязки</option>
              {points.map((point) => <option key={point.analytical_point_id} value={point.analytical_point_id}>{point.point_name}</option>)}
            </select></label>
            {pointSampleId && pointId && <label>Причина привязки к точке другого образца<input value={exceptionReason} maxLength={1000}
              onChange={(event) => setExceptionReason(event.target.value)} /></label>}
            <label>Геометрия<select value={shape} onChange={(event) => setShape(event.target.value)}>
              <option value="point">Точка</option><option value="rectangle">Прямоугольник</option><option value="square">Квадрат</option>
            </select></label>
          </div>
          {pointId && <p>Щёлкните на изображении для точки или протяните область.</p>}
          <MediaViewer key={activePath} image={image} shape={shape}
            loadRegion={(region) => actions.preview(activePath, region, image.source_fingerprint)}
            onPlace={pointId && !pending && (!pointSampleId || exceptionReason.trim()) ? place : undefined}
            annotations={active.placements.map((item) => ({ ...item.geometry, id: item.analytical_point_id,
              label: item.pointLabel }))} />
          <ul className="sample-items">{active.placements.map(({ analytical_point_id: id, pointLabel }) => <li key={id}>
            <span>{pointLabel}</span>
            <button className="outline-button" type="button" disabled={pending} onClick={() =>
              changeFile(activePath, { placements: active.placements.filter((item) => item.analytical_point_id !== id) })}>Снять предварительную привязку</button>
          </li>)}</ul>
        </>}
      </section>
    </div>}
  </section>;
}
