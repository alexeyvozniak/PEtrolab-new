import { useState } from "react";

const conflictLabels = {
  source_changed: "Исходный файл изменился",
  value_changed: "Значение в исходной ячейке изменилось",
  missing_source: "Исходный файл недоступен",
  mixed_ownership: "Несовместимые режимы источников",
};

export function EditDraftPanel({ analysisId, measurements, actions }) {
  const [rows, setRows] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const available = measurements.filter((measurement) => measurement.measurement_id);
  if (!available.length) return null;

  const run = async (operation) => {
    setPending(true);
    setError("");
    setNotice("");
    try {
      await operation();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setPending(false);
    }
  };
  const refresh = async () => setRows((await actions.list(analysisId)).drafts);
  const save = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    run(async () => {
      const measurementId = fields.get("measurement_id");
      const draft = await actions.save(measurementId, fields.get("new_value") || null);
      const measurement = available.find((item) => item.measurement_id === measurementId);
      setRows((current) => [{ draft, source_cell: measurement?.source_cell, measurement_id: measurementId }, ...current]);
      form.reset();
      setNotice("Черновик сохранён.");
      if (actions.commit) await refresh();
    });
  };
  const check = (id) => run(async () => {
    const result = await actions.check(id);
    setRows((current) => current.map((row) => row.draft.id === id ? { ...row, draft: result } : row));
    if (result.conflict.kind === "none") setNotice("Исходный файл совпадает с импортированной версией.");
  });
  const commit = (event, row) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    if (!window.confirm(`Записать правку в ячейку ${row.source_cell} исходного файла?\n${row.external_path}\n\nПеред записью PetroLab создаст резервную копию.`)) return;
    run(async () => {
      const result = await actions.commit(row.draft.id, fields.get("actor"), fields.get("reason"));
      setRows((current) => current.map((item) => item.draft.id === row.draft.id
        ? { ...item, draft: result.maintenance_error ? item.draft : result.draft, operation: result.operation || item.operation }
        : item));
      if (result.applied) setNotice("Правка записана в XLSX. Импортированное измерение сохранено в проекте.");
      if (result.maintenance_error) setError(result.maintenance_error);
    });
  };

  return <details className="analysis-edit-drafts" onToggle={(event) => {
    if (event.currentTarget.open) run(refresh);
  }}>
    <summary>Черновики правок</summary>
    <form onSubmit={save} aria-label="Новый черновик правки">
      <label>Измерение<select name="measurement_id" disabled={pending}>
        {available.map((measurement) => <option key={measurement.measurement_id} value={measurement.measurement_id}>
          {[measurement.field, measurement.source_cell, measurement.raw_token, measurement.unit].filter(Boolean).join(" · ")}
        </option>)}
      </select></label>
      <label>Новое значение<input name="new_value" maxLength={32767} disabled={pending} /></label>
      <small>Пустое поле означает очистку ячейки в черновике.</small>
      <button className="outline-button" type="submit" disabled={pending}>Сохранить черновик</button>
    </form>
    {error && <small role="alert">{error}</small>}
    {notice && <small role="status">{notice}</small>}
    {rows.map((row) => {
      const { draft, source_cell, operation, external_path } = row;
      const change = draft.changes[0];
      const conflict = draft.conflict;
      return <div key={draft.id} className="analysis-edit-draft">
        <b>{change.field} · {source_cell}</b>
        <span>Было {change.old_value ?? "—"} → предлагается {change.new_value ?? "—"} {change.unit}</span>
        {draft.status === "committed" ? <strong>Записано в XLSX</strong> :
          <button className="outline-button" type="button" onClick={() => check(draft.id)} disabled={pending}>Проверить исходный файл</button>}
        {actions.commit && draft.status !== "committed" && /\.xlsx$/i.test(external_path || "") && <form onSubmit={(event) => commit(event, row)} aria-label={`Запись ячейки ${source_cell}`}>
          <label>Автор правки<input name="actor" required disabled={pending} /></label>
          <label>Причина правки<input name="reason" required disabled={pending} /></label>
          <button type="submit" className="outline-button" disabled={pending || (draft.status === "conflict" && !operation)}>Записать в исходный XLSX</button>
        </form>}
        {operation?.parameters?.backup_path && <span>Резервная копия: {operation.parameters.backup_path}</span>}
        {conflict.kind !== "none" && <strong role="status">{conflictLabels[conflict.kind]}</strong>}
        {conflict.current_values.map((value) => <span key={value.field}>Сейчас в файле: {value.current_value ?? "—"}</span>)}
        {conflict.detected_at && <details>
          <summary>Контрольные суммы</summary>
          <span>При импорте: {draft.source_fingerprint_at_start}</span>
          <span>При проверке: {conflict.current_source_fingerprint ?? "—"}</span>
        </details>}
      </div>;
    })}
  </details>;
}
