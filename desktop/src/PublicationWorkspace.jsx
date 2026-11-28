import { useEffect, useMemo, useState } from "react";
import { plotSvgPreview } from "./plotSvg";
import "./publicationWorkspace.css";

const KINDS = { work_group: "Рабочие группы", calculation_run: "Кластеризация", formula_run: "Формулы минералов", plot_specification: "Раскладки" };
const FORMATS = { svg: "SVG", pdf: "PDF", tiff: "TIFF", png: "PNG" };

export function PublicationWorkspace({ load, pickFigure, check, exportZip, items, setItems, name, setName, settings, setSettings }) {
  const [catalog, setCatalog] = useState(null);
  const [prepared, setPrepared] = useState(null);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState(null);
  const [linkLayoutId, setLinkLayoutId] = useState("");
  const [figureFormat, setFigureFormat] = useState("pdf");
  const [previewTarget, setPreviewTarget] = useState({ id: "", panel: -1 });
  const capturedFigures = items.filter((item) => item.kind === "plot_capture");
  const previewFigure = capturedFigures.find((item) => item.draft_id === previewTarget.id) || capturedFigures[0];
  const previewPanel = previewFigure?.draft_id === previewTarget.id ? previewTarget.panel : -1;
  const previewSvg = previewFigure?.capture?.svg;
  const preview = useMemo(() => previewSvg ? plotSvgPreview(previewSvg, previewPanel) : null, [previewSvg, previewPanel]);
  const lithos = settings.profile === "lithos";
  const selectedFormat = lithos ? figureFormat : "svg";
  useEffect(() => {
    let active = true;
    load().then((value) => { if (active) setCatalog(value); })
      .catch((caught) => { if (active) setStatus({ error: caught.message }); });
    return () => { active = false; };
  }, [load]);
  const update = (next) => {
    setItems(next);
    setPrepared(null);
    setStatus(null);
  };
  const add = (kind, id, label, fields = {}) => update([...items, { draft_id: crypto.randomUUID(), kind, id, label, caption: "", ...fields }]);
  const changeSettings = (next) => {
    setSettings({ ...settings, ...next });
    setPrepared(null);
    setStatus(null);
  };
  const perform = async (task) => {
    setPending(true);
    setStatus(null);
    try { await task(); }
    catch (caught) { setStatus({ error: caught.message }); }
    finally { setPending(false); }
  };
  const payload = () => items.map(({ draft_id, label, format, ...item }) => item);
  const available = {
    work_group: catalog?.groups.map(({ group, unavailable_analysis_ids }) => ({
      id: group.id, label: group.name, note: `${group.analysis_ids.length} анализов`, disabled: unavailable_analysis_ids.length > 0,
    })),
    calculation_run: catalog?.runs.map((run) => ({ id: run.id, label: `K-means · ${run.transform}`, note: run.created_at.slice(0, 10) })),
    formula_run: (catalog?.formula_runs || []).map((run) => ({ id: run.id,
      label: `${run.method_name} · ${run.analysis_label}`, note: `Версия ${run.method_version} · ${run.created_at.slice(0, 10)}` })),
    plot_specification: catalog?.layouts.map((item) => ({ id: item.id, label: item.name })),
  };
  const selectFigure = () => perform(async () => {
    const path = await pickFigure(selectedFormat);
    if (!path) return;
    const kind = selectedFormat === "svg" ? "svg_figure" : "publication_figure";
    add(kind, linkLayoutId, path.split(/[\\/]/).pop(), { source_path: path, format: selectedFormat });
  });
  const move = (index, delta) => {
    const ordered = items.slice();
    [ordered[index], ordered[index + delta]] = [ordered[index + delta], ordered[index]];
    update(ordered);
  };
  return <section className="publication-workspace">
    <h2>Публикации</h2>
    {status && <p role={status.error ? "alert" : "status"}>{status.error || status.notice}</p>}
    <div className="publication-grid">
      <aside className="publication-card">
        <h3>Библиотека материалов</h3>
        {!catalog && !status?.error && <p role="status">Загружаю материалы…</p>}
        {catalog && Object.entries(KINDS).map(([kind, label]) => <section key={kind}>
          <h4>{label}</h4>
          {!available[kind].length && <p>Пока пусто.</p>}
          <ul>{available[kind].map((item) => <li key={item.id}>
            <button className="outline-button" type="button" disabled={pending || item.disabled || items.length >= 24}
              onClick={() => add(kind, item.id, item.label)}>Добавить «{item.label}»</button>
            {item.note && <small>{item.note}</small>}
          </li>)}</ul>
        </section>)}
        {catalog?.layouts.length > 0 && <section>
          <h4>Фигура</h4>
          <label>Раскладка фигуры<select value={linkLayoutId} disabled={pending} onChange={(event) => setLinkLayoutId(event.target.value)}>
            <option value="">Выберите сохранённую раскладку</option>
            {catalog.layouts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></label>
          {lithos && <label>Формат фигуры<select value={selectedFormat} disabled={pending}
            onChange={(event) => setFigureFormat(event.target.value)}>
            {Object.entries(FORMATS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>}
          <button className="outline-button" type="button" disabled={pending || !linkLayoutId || items.length >= 24}
            onClick={selectFigure}>Добавить файл {FORMATS[selectedFormat]}</button>
        </section>}
      </aside>
      <main className="publication-card">
        <h3>Состав пакета</h3>
        <label>Название пакета<input value={name} maxLength={120} disabled={pending} onChange={(event) => {
          setName(event.target.value); setPrepared(null); setStatus(null);
        }} /></label>
        <label>Профиль журнала<select value={settings.profile} disabled={pending}
          onChange={(event) => changeSettings({ profile: event.target.value })}>
          <option value="neutral" disabled={items.some(({ kind }) => kind === "publication_figure")}>Без профиля</option>
          <option value="lithos">Lithos</option>
        </select></label>
        {lithos && <label>Ширина фигур<select value={settings.width} disabled={pending}
          onChange={(event) => changeSettings({ width: Number(event.target.value) })}>
          <option value={90}>90 мм</option><option value={180}>180 мм</option>
        </select></label>}
        <ol className="publication-items">{items.map((item, index) => <li key={item.draft_id}>
          <b>{item.label}</b>
          {lithos && ["tiff", "png"].includes(item.format) && <label>Тип изображения<select value={item.artwork || "line_art"} disabled={pending}
            onChange={(event) => update(items.map((entry) => entry.draft_id === item.draft_id
              ? { ...entry, artwork: event.target.value } : entry))}>
            <option value="line_art">Линейная графика</option>
            <option value="combination">Смешанная графика</option>
            <option value="halftone">Полутоновое изображение</option>
          </select></label>}
          <label>Подпись материала {index + 1}<textarea value={item.caption} maxLength={2000} disabled={pending}
            onChange={(event) => update(items.map((entry) => entry.draft_id === item.draft_id
              ? { ...entry, caption: event.target.value } : entry))} /></label>
          <div className="publication-actions">
            <button className="outline-button" type="button" disabled={pending || index === 0} onClick={() => move(index, -1)}>Выше</button>
            <button className="outline-button" type="button" disabled={pending || index === items.length - 1} onClick={() => move(index, 1)}>Ниже</button>
            <button className="outline-button" type="button" disabled={pending} onClick={() => update(items.filter((entry) => entry.draft_id !== item.draft_id))}>Убрать</button>
          </div>
        </li>)}</ol>
        {items.length === 0 && <p>Добавьте рабочую группу, расчёт или раскладку из библиотеки.</p>}
        <button className="primary-button" type="button" disabled={pending || !items.length || !name.trim()}
          onClick={() => perform(async () => { setPrepared(null); setPrepared(await check(name, payload(), settings)); })}>Проверить пакет</button>
      </main>
      <aside className="publication-card">
        <h3>Проверка и экспорт</h3>
        {preview && <section aria-label="Предпросмотр фигуры">
          <h4>Предпросмотр фигуры</h4>
          {capturedFigures.length > 1 && <label>Фигура<select value={previewFigure.draft_id}
            onChange={(event) => setPreviewTarget({ id: event.target.value, panel: -1 })}>
            {capturedFigures.map((figure) => <option key={figure.draft_id} value={figure.draft_id}>{figure.label}</option>)}
          </select></label>}
          {preview.labels.length > 1 && <label>Панель<select value={previewPanel}
            onChange={(event) => setPreviewTarget({ id: previewFigure.draft_id, panel: Number(event.target.value) })}>
            <option value={-1}>Вся фигура</option>
            {preview.labels.map((label, index) => <option key={label} value={index}>Панель {label}</option>)}
          </select></label>}
          <img className="publication-figure-preview" src={preview.url}
            alt={previewPanel < 0 ? previewFigure.label : `${previewFigure.label}, панель ${preview.labels[previewPanel]}`} />
        </section>}
        {lithos && <p>PDF со встроенными шрифтами или TIFF. SVG для редактирования, PNG для просмотра.</p>}
        {prepared ? <>
          <p>Материалов · {prepared.manifest.items.length}</p>
          <p>Анализов · {prepared.manifest.analysis_count}</p>
          {lithos && <ul>{prepared.manifest.items.filter((item) => item.figure).map(({ figure }) =>
            <li key={figure.number}>Figure {figure.number} · {figure.format} · {figure.target_width_mm} мм
              {figure.effective_dpi && ` · ${figure.effective_dpi} dpi`}</li>)}</ul>}
          <ul>{prepared.manifest.files.map((file) => <li key={file.path}>{file.path}</li>)}</ul>
          {prepared.manifest.warnings.length > 0 && <details open><summary>Предупреждения</summary>
            <ul>{prepared.manifest.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </details>}
          <button className="primary-button" type="button" disabled={pending} onClick={() => perform(async () => {
            const result = await exportZip(name, payload(), prepared.fingerprint, settings);
            if (result) setStatus({ notice: `Пакет сохранён: ${result.output_path}` });
          })}>Собрать ZIP</button>
        </> : <p>Проверьте состав перед сборкой ZIP.</p>}
      </aside>
    </div>
  </section>;
}
