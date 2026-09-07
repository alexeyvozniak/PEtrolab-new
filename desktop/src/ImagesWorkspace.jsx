import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle,
  Copy,
  FileImage,
  Images,
  Info,
  Plus,
  Warning,
} from "@phosphor-icons/react";
import "./imagesWorkspace.css";

const MEDIA_TYPES = ["BSE", "PPL", "XPL", "Фото"];

function initialAssignment(item) {
  return {
    source_path: item.source_path,
    ownership_mode: "managed_copy",
    media_type: item.suggested_media_type || "",
    sample_name: item.suggested_sample_name || "",
    thin_section_name: item.suggested_thin_section_name || "",
    placements: [],
    confirmed: false,
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
  const { confirmed: _confirmed, ...payload } = assignment;
  return payload;
}

export function ImagesWorkspace({ inspection, plan, busy, onChoose, onPlan, onApply, onCancel, onInvalidatePlan = () => {} }) {
  const items = inspection?.items || [];
  const [assignments, setAssignments] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [activePath, setActivePath] = useState("");

  useEffect(() => {
    setAssignments(Object.fromEntries(items.map((item) => [item.source_path, initialAssignment(item)])));
    setSelected(new Set(items.map((item) => item.source_path)));
    setActivePath(items[0]?.source_path || "");
  }, [inspection]);

  const activeItem = items.find((item) => item.source_path === activePath) || items[0];
  const activeAssignment = activeItem ? assignments[activeItem.source_path] : null;
  const duplicatePaths = useMemo(
    () => new Set((inspection?.duplicate_groups || []).flat()),
    [inspection],
  );
  const readyCount = items.filter((item) => assignmentReady(assignments[item.source_path])).length;
  const selectedItems = items.filter((item) => selected.has(item.source_path));
  const selectedSuggestionsReady = selectedItems.length > 0 && selectedItems.every((item) => (
    item.suggested_media_type && item.suggested_sample_name && item.suggested_thin_section_name
  ));
  const canPlan = items.length > 0 && readyCount === items.length && duplicatePaths.size === 0;

  const patchAssignment = (path, values) => {
    onInvalidatePlan();
    setAssignments((current) => ({
      ...current,
      [path]: { ...current[path], ...values, confirmed: false },
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
          confirmed: true,
        };
      });
      return next;
    });
  };

  const applyActiveToSelection = () => {
    if (!activeAssignment) return;
    const shared = {
      media_type: activeAssignment.media_type.trim(),
      sample_name: activeAssignment.sample_name.trim(),
      thin_section_name: activeAssignment.thin_section_name.trim(),
      ownership_mode: activeAssignment.ownership_mode,
    };
    if (!shared.media_type || !shared.sample_name || !shared.thin_section_name) return;
    onInvalidatePlan();
    setAssignments((current) => {
      const next = { ...current };
      selectedItems.forEach((item) => {
        next[item.source_path] = { ...next[item.source_path], ...shared, confirmed: true };
      });
      return next;
    });
  };

  if (items.length === 0) {
    return <section className="images-empty">
      <Images size={52} weight="duotone" />
      <h1>Добавить изображения</h1>
      <p>Выбери сразу серию BSE, PPL, XPL или обычных фотографий. PetroLab проверит контейнеры и предложит назначения из имён файлов.</p>
      <button className="primary-button large" type="button" onClick={onChoose} disabled={busy}><Plus size={20} /> Выбрать изображения</button>
      <small>PNG, JPEG, TIFF и BMP. Исходные файлы не переименовываются и не изменяются.</small>
    </section>;
  }

  return <section className="images-workspace">
    <aside className="image-source-pane">
      <header><b>Загруженные изображения</b><span>{items.length}</span></header>
      <div className="image-source-list">
        {items.map((item, index) => {
          const assignment = assignments[item.source_path];
          const focused = item.source_path === activeItem?.source_path;
          return <button className={focused ? "focused" : ""} type="button" key={item.source_path} onClick={() => setActivePath(item.source_path)}>
            <span className="image-source-icon"><FileImage size={24} weight="duotone" /></span>
            <span><b>{index + 1}. {item.display_name}</b><small>{item.width_px} × {item.height_px} px · {item.format.toUpperCase()}</small><em>{assignmentReady(assignment) ? "назначено" : "нужно подтвердить"}</em></span>
          </button>;
        })}
      </div>
      <div className="image-source-safety"><Info size={17} /><span>Исходные файлы не изменяются</span></div>
    </aside>

    <main className="image-assignment-pane">
      <header>
        <div><h2>Назначь Sample и шлиф</h2><p>Предложения из имени файла не сохраняются без подтверждения.</p></div>
        <button className="outline-button" type="button" onClick={onChoose} disabled={busy}>Выбрать другие</button>
      </header>
      <div className="image-bulk-toolbar">
        <label><input type="checkbox" checked={selected.size === items.length} onChange={() => setSelected(selected.size === items.length ? new Set() : new Set(items.map((item) => item.source_path)))} /> Выбрано: {selected.size} из {items.length}</label>
        <button type="button" onClick={confirmSuggestions} disabled={busy || !selectedSuggestionsReady}><CheckCircle size={17} /> Подтвердить предложения</button>
      </div>
      {duplicatePaths.size > 0 && <div className="image-duplicate-warning"><Warning size={18} /><span>В очереди есть одинаковые физические изображения. Удали дубликаты перед продолжением.</span></div>}
      <div className="image-assignment-table" role="table" aria-label="Назначения импортируемых изображений">
        <div className="image-assignment-head" role="row"><span></span><span>Файл</span><span>Sample</span><span>Шлиф</span><span>Тип</span><span>Статус</span></div>
        {items.map((item) => {
          const assignment = assignments[item.source_path];
          return <div className={`${item.source_path === activeItem?.source_path ? "active " : ""}${duplicatePaths.has(item.source_path) ? "duplicate" : ""}`} role="row" key={item.source_path} onClick={() => setActivePath(item.source_path)}>
            <span><input aria-label={`Выбрать ${item.display_name}`} type="checkbox" checked={selected.has(item.source_path)} onChange={() => toggleSelected(item.source_path)} onClick={(event) => event.stopPropagation()} /></span>
            <button type="button" onClick={() => setActivePath(item.source_path)}>{item.display_name}</button>
            <span>{assignment?.sample_name || "—"}</span>
            <span>{assignment?.thin_section_name || "—"}</span>
            <span className={`image-type type-${assignment?.media_type || "unknown"}`}>{assignment?.media_type || "—"}</span>
            <span className={assignmentReady(assignment) ? "image-ready" : "image-pending"}>{duplicatePaths.has(item.source_path) ? "дубликат" : assignmentReady(assignment) ? "готово" : "проверь"}</span>
          </div>;
        })}
      </div>
      <div className="image-assignment-note"><Info size={18} /><p>Массовое назначение применяется только к отмеченным строкам. Пространственные точки создаются на следующем шаге.</p></div>
    </main>

    <aside className="image-inspector">
      <header><span>Выбрано изображение</span><h2>{activeItem?.display_name}</h2><p>{activeItem?.width_px} × {activeItem?.height_px} px · SHA-256 проверен</p></header>
      <section>
        <h3>Предложено из имени файла</h3>
        <dl><div><dt>Sample</dt><dd>{activeItem?.suggested_sample_name || "не определён"}</dd></div><div><dt>Шлиф</dt><dd>{activeItem?.suggested_thin_section_name || "не определён"}</dd></div><div><dt>Тип</dt><dd>{activeItem?.suggested_media_type || "не определён"}</dd></div></dl>
      </section>
      <section className="image-assignment-form">
        <h3>Назначение для выбранных</h3>
        <label>Sample<input value={activeAssignment?.sample_name || ""} onChange={(event) => patchAssignment(activeItem.source_path, { sample_name: event.target.value })} placeholder="Например, KIV-2" /></label>
        <label>Thin Section<input value={activeAssignment?.thin_section_name || ""} onChange={(event) => patchAssignment(activeItem.source_path, { thin_section_name: event.target.value })} placeholder="Например, KIV-2-A" /></label>
        <label>Тип изображения<select value={activeAssignment?.media_type || ""} onChange={(event) => patchAssignment(activeItem.source_path, { media_type: event.target.value })}><option value="">Выбери тип</option>{MEDIA_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>
        <label>Хранение<select value={activeAssignment?.ownership_mode || "managed_copy"} onChange={(event) => patchAssignment(activeItem.source_path, { ownership_mode: event.target.value })}><option value="managed_copy">Копия внутри проекта</option><option value="linked_external">Ссылка на исходный файл</option></select></label>
        <button className="outline-button image-bulk-apply" type="button" onClick={applyActiveToSelection} disabled={busy || selected.size === 0}><Copy size={17} /> Применить к выбранным ({selected.size})</button>
      </section>
      <div className="image-next-note"><Info size={18} /><p><b>Точки ещё не размещены.</b><br />Импорт без точек разрешён и явно отмечается в плане.</p></div>
    </aside>

    <footer className="image-commit-bar">
      <button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отмена</button>
      <div><b>{readyCount} готово</b><span>{items.length - readyCount > 0 ? ` · ${items.length - readyCount} требуют подтверждения` : " · назначения проверены"}</span></div>
      <small>Исходные файлы не изменяются</small>
      {!plan
        ? <button className="primary-button" type="button" disabled={busy || !canPlan} onClick={() => onPlan(items.map((item) => cleanAssignment(assignments[item.source_path])))}>Проверить план <ArrowRight size={18} /></button>
        : <button className="primary-button" type="button" disabled={busy} onClick={() => onApply(plan)}>Импортировать без точек <ArrowRight size={18} /></button>}
    </footer>
  </section>;
}
