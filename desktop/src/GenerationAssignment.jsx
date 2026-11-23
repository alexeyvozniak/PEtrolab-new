import { useState } from "react";

const ACTOR = "Локальный пользователь";

export function GenerationAssignment({ actions, selectedIds, busy }) {
  const [draft, setDraft] = useState(null);
  const [choice, setChoice] = useState("");
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [entry, setEntry] = useState(null);

  async function open() {
    setPending(true);
    setError("");
    try {
      const { generations } = await actions.list();
      setDraft({ generations, ids: [...selectedIds] });
      setChoice(generations.length ? "" : "new");
      setName("");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setPending(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      setEntry(await actions.assign({
        analysis_ids: draft.ids,
        actor: ACTOR,
        ...(choice === "new" ? { new_name: name.trim() } : { generation_id: choice }),
      }));
      setDraft(null);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setPending(false);
    }
  }

  async function undo() {
    setPending(true);
    setError("");
    try {
      await actions.undo(entry.id, ACTOR);
      setEntry(null);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setPending(false);
    }
  }

  return <>
    <button className="outline-button" type="button" onClick={open} disabled={busy || pending || Boolean(draft)}>
      Назначить Generation
    </button>
    {!draft && entry && <button className="outline-button" type="button" disabled={busy || pending} onClick={undo}>
      Отменить назначение Generation
    </button>}
    {draft && <form className="generation-assignment" aria-label="Назначение Generation" onSubmit={submit}>
      <b>Назначение Generation · {draft.ids.length}</b>
      <label>Generation
        <select value={choice} onChange={(event) => setChoice(event.target.value)} disabled={pending}>
          <option value="" disabled>Выберите Generation</option>
          {draft.generations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          <option value="new">Создать Generation</option>
        </select>
      </label>
      {choice === "new" && <label>Название
        <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required disabled={pending} />
      </label>}
      {error && <small role="alert">{error}</small>}
      <div className="analysis-selection-actions">
        <button className="primary-button" type="submit" disabled={busy || pending || !choice || (choice === "new" && !name.trim())}>Назначить</button>
        <button className="outline-button" type="button" disabled={pending} onClick={() => { setDraft(null); setError(""); }}>Отмена</button>
      </div>
    </form>}
    {!draft && error && <small role="alert">{error}</small>}
  </>;
}
