import { useEffect, useState } from "react";
import { PointLinks } from "./PointLinks";
import { MediaGallery } from "./MediaWorkspace";
import "./sampleWorkspace.css";

const TABS = ["Обзор", "Полевые данные", "Источники", "Точки", "Шлифы", "Изображения", "Заметки"];
const FIELDS = {
  locality: "Местонахождение или обнажение",
  storage: "Хранение",
  collection_position: "Положение отбора",
  collector: "Собрал",
  collection_date: "Дата отбора",
};

export function SampleWorkspace({ loadSamples, loadSample, saveContext, addNote, onOpenAnalyses, busy, pointLinks,
  initialTab = "Обзор", onImportMedia, previewMedia, exportOriginal, exportRendered }) {
  const [samples, setSamples] = useState(null);
  const [sampleId, setSampleId] = useState("");
  const [sample, setSample] = useState(null);
  const [tab, setTab] = useState(initialTab);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState(null);
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    loadSamples().then((items) => {
      if (!active) return;
      setSamples(items);
      setSampleId(items[0]?.sample_id || "");
    }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [loadSamples]);
  useEffect(() => {
    if (!sampleId) return;
    let active = true;
    loadSample(sampleId).then((item) => { if (active) setSample(item); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [loadSample, sampleId]);
  const current = sample?.sample_id === sampleId ? sample : null;
  const choose = (event) => {
    setDraft(null);
    setName("");
    setBody("");
    setSampleId(event.target.value);
    setTab(initialTab);
    setError("");
  };
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const context = await saveContext(current.sample_id, draft, current.context.revision);
      setSample((item) => ({ ...item, context }));
      setDraft(null);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving(false);
    }
  };
  const saveNote = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const note = await addNote(current.sample_id, name, body);
      setSample((item) => ({ ...item, notes: [note, ...item.notes] }));
      setBody("");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving(false);
    }
  };
  const passport = current && <section className="sample-card">
    <header><h3>Паспорт образца</h3>
      {!draft && saveContext && <button className="outline-button" type="button" disabled={saving || busy}
        onClick={() => setDraft(Object.fromEntries(Object.keys(FIELDS).map((field) => [field, current.context[field]])))}>Редактировать паспорт</button>}
    </header>
    {draft ? <form className="sample-form" onSubmit={save}>
      {Object.entries(FIELDS).map(([field, label]) => <label key={field}>{label}
        <input type={field === "collection_date" ? "date" : "text"} maxLength={2000} value={draft[field]} disabled={saving}
          onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} />
      </label>)}
      <div><button className="primary-button" type="submit" disabled={saving}>Сохранить паспорт</button>
        <button className="outline-button" type="button" disabled={saving} onClick={() => setDraft(null)}>Отмена</button></div>
    </form> : <dl>
      {Object.entries(FIELDS).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>{current.context[field] || "—"}</dd></div>)}
      <div><dt>Sample ID</dt><dd>{current.sample_id}</dd></div>
    </dl>}
  </section>;
  const notes = current && <section className="sample-card">
    <h3>Заметки</h3>
    {current.notes.length ? <ul className="sample-notes">{current.notes.map((note) =>
      <li key={note.note_id}><p>{note.body}</p><small>{note.author} · <time dateTime={note.created_at}>{new Date(note.created_at).toLocaleString("ru-RU")}</time></small></li>)}
    </ul> : <p>У образца нет заметок.</p>}
    {addNote && <form className="sample-form" onSubmit={saveNote}>
      <label>Автор заметки<input value={name} maxLength={120} disabled={saving} onChange={(event) => setName(event.target.value)} /></label>
      <label>Текст заметки<textarea value={body} maxLength={10000} disabled={saving} onChange={(event) => setBody(event.target.value)} /></label>
      <div><button className="outline-button" disabled={saving || busy || !name.trim() || !body.trim()}>Добавить заметку</button></div>
    </form>}
  </section>;
  const sources = current && <ul className="sample-items">{current.sources.map((source) => <li key={source.source_id}>
    <span>{source.source_name} · {source.analysis_count}</span>
    <button className="outline-button" type="button" disabled={busy} onClick={() => onOpenAnalyses(current, source)}>Открыть анализы источника</button>
  </li>)}</ul>;
  const gallery = current && <MediaGallery key={sampleId} images={current.images} previewMedia={previewMedia}
    exportOriginal={exportOriginal} exportRendered={exportRendered} />;
  return <section className="sample-workspace">
    <div className="sample-header">
      <div>
        <h2>{current ? `Образец ${current.sample_name}` : "Образцы"}</h2>
        {current && <p>Минералы: {current.minerals.length ? current.minerals.join(", ") : "не указаны"}</p>}
      </div>
      {samples?.length > 0 && <label>Образец <select value={sampleId} disabled={saving} onChange={choose}>
        {samples.map((item) => <option key={item.sample_id} value={item.sample_id}>{item.sample_name} · {item.analysis_count}</option>)}
      </select></label>}
      {initialTab === "Изображения" && onImportMedia && <button className="primary-button" type="button" disabled={busy}
        onClick={onImportMedia}>Импорт изображений</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    {!error && (!samples || (sampleId && !current)) && <p role="status">Загружаю образцы…</p>}
    {samples?.length === 0 && <p>В проекте ещё нет физических образцов. Назначьте образец выбранным анализам при подготовке импорта.</p>}
    {current && <>
      <nav aria-label="Разделы образца" className="sample-tabs">
        {TABS.map((item) => <button type="button" key={item} aria-current={tab === item ? "page" : undefined} onClick={() => setTab(item)}>{item}</button>)}
        <button type="button" disabled={busy || !current.analysis_count} onClick={() => onOpenAnalyses(current)}>Анализы · {current.analysis_count}</button>
      </nav>
      {tab === "Обзор" && <div className="sample-overview">
        <div>
          {passport}
          <section className="sample-card">
            <h3>Связанные данные</h3>
            <ul className="sample-items">
              <li><span>Анализы · {current.analysis_count}</span><button type="button" className="outline-button"
                disabled={busy || !current.analysis_count} onClick={() => onOpenAnalyses(current)}>Открыть анализы</button></li>
              {[["Точки", current.points.length], ["Шлифы", current.thin_sections.length], ["Источники", current.sources.length]].map(([label, count]) =>
                <li key={label}><span>{label} · {count}</span><button type="button" className="outline-button" onClick={() => setTab(label)}>Открыть {label.toLowerCase()}</button></li>)}
            </ul>
          </section>
          {notes}
        </div>
        <section className="sample-card"><h3>Изображения</h3>{gallery}</section>
      </div>}
      {tab === "Полевые данные" && passport}
      {tab === "Заметки" && notes}
      {tab === "Источники" && <section className="sample-card"><h3>Источники</h3>{current.sources.length ? sources : <p>У образца нет связанных источников анализов.</p>}</section>}
      {tab === "Точки" && pointLinks && <PointLinks key={sampleId} sample={current} busy={busy} {...pointLinks}
        reloadSample={async () => {
          const refreshed = await loadSample(sampleId);
          setSample((item) => item.sample_id === refreshed.sample_id ? refreshed : item);
        }} />}
      {tab === "Шлифы" && <section className="sample-card"><h3>Шлифы</h3>{current.thin_sections.length ?
        current.thin_sections.map((item) => <details key={item.thin_section_id}>
          <summary>{item.thin_section_name}</summary>
          <MediaGallery images={current.images.filter((image) => image.thin_section_id === item.thin_section_id)}
            previewMedia={previewMedia} showPoints />
        </details>) : <p>У образца нет связанных шлифов.</p>}</section>}
      {tab === "Изображения" && <section className="sample-card"><h3>Изображения</h3>{gallery}</section>}
    </>}
  </section>;
}
