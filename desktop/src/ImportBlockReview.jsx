import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Eye, Warning } from "@phosphor-icons/react";
import "./importBlockReview.css";

function stateFor(section) {
  return {
    enabled: section.enabled !== false,
    orientation: section.orientation || "rows_are_analyses",
    header_row: section.header_row,
    data_start_row: section.data_start_row,
    data_end_row: section.data_end_row,
    header_column: section.header_column || 1,
    data_start_column: section.data_start_column || 2,
    data_end_column: section.data_end_column || null,
  };
}

function sameState(left, right) {
  return left.enabled === right.enabled
    && left.orientation === right.orientation
    && Number(left.header_row) === Number(right.header_row)
    && Number(left.data_start_row) === Number(right.data_start_row)
    && Number(left.data_end_row) === Number(right.data_end_row)
    && Number(left.header_column) === Number(right.header_column)
    && Number(left.data_start_column) === Number(right.data_start_column)
    && Number(left.data_end_column || 0) === Number(right.data_end_column || 0);
}

function RawPreview({ preview, state }) {
  if (!preview) return <div className="raw-preview-loading">Предпросмотр загружается…</div>;
  return (
    <div className="raw-preview-wrap">
      <table className="raw-preview-table">
        <thead>
          <tr><th className="raw-row-number">#</th>{preview.column_labels.map((label) => <th key={label}>{label}</th>)}</tr>
        </thead>
        <tbody>
          {preview.rows.map((row) => {
            const isHeader = row.row_number === Number(state.header_row);
            const isData = row.row_number >= Number(state.data_start_row) && row.row_number <= Number(state.data_end_row);
            return (
              <tr key={row.row_number} className={isHeader ? "raw-header-row" : isData ? "raw-data-row" : ""}>
                <th className="raw-row-number">{row.row_number}</th>
                {row.values.map((value, index) => <td key={`${row.row_number}-${index}`}>{value ?? ""}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function BlockCard({ section, index, preview, value, busy, onChange }) {
  const transposed = value.orientation === "columns_are_analyses";
  const context = section.unit_context;
  const invalid = value.enabled && (
    !Number.isInteger(Number(value.header_row))
    || Number(value.header_row) < 1
    || Number(value.data_start_row) < 1
    || Number(value.data_end_row) < Number(value.data_start_row)
    || (transposed && (
      Number(value.header_column) < 1
      || Number(value.data_start_column) < 1
      || (value.data_end_column && Number(value.data_end_column) < Number(value.data_start_column))
    ))
  );

  const set = (field, next) => onChange({ ...value, [field]: next });
  return (
    <article className={`import-block-card${value.enabled ? "" : " block-disabled"}${invalid ? " block-invalid" : ""}`}>
      <div className="block-card-head">
        <div className="block-title">
          <label className="block-toggle">
            <input type="checkbox" checked={value.enabled} onChange={(event) => set("enabled", event.target.checked)} disabled={busy} />
            <span />
          </label>
          <div>
            <b>{section.sheet_name} · блок {index + 1}</b>
            <small>{section.block_id}</small>
          </div>
        </div>
        <div className="block-confidence">
          {value.enabled ? <><CheckCircle size={17} weight="fill" /> включён</> : "пропущен"}
        </div>
      </div>

      <div className="block-controls">
        <label>
          <span>Как расположены анализы</span>
          <select value={value.orientation} onChange={(event) => set("orientation", event.target.value)} disabled={busy || !value.enabled}>
            <option value="rows_are_analyses">По строкам</option>
            <option value="columns_are_analyses">По столбцам (инвертировано)</option>
          </select>
        </label>
        <label><span>Строка заголовка</span><input type="number" min="1" value={value.header_row} onChange={(event) => set("header_row", Number(event.target.value))} disabled={busy || !value.enabled} /></label>
        <label><span>{transposed ? "Первая строка полей" : "Первая строка данных"}</span><input type="number" min="1" value={value.data_start_row} onChange={(event) => set("data_start_row", Number(event.target.value))} disabled={busy || !value.enabled} /></label>
        <label><span>{transposed ? "Последняя строка полей" : "Последняя строка данных"}</span><input type="number" min="1" value={value.data_end_row} onChange={(event) => set("data_end_row", Number(event.target.value))} disabled={busy || !value.enabled} /></label>
        {transposed && (
          <>
            <label><span>Колонка названий полей</span><input type="number" min="1" value={value.header_column} onChange={(event) => set("header_column", Number(event.target.value))} disabled={busy || !value.enabled} /></label>
            <label><span>Первая колонка Analysis</span><input type="number" min="1" value={value.data_start_column} onChange={(event) => set("data_start_column", Number(event.target.value))} disabled={busy || !value.enabled} /></label>
            <label><span>Последняя колонка Analysis</span><input type="number" min="1" value={value.data_end_column || ""} onChange={(event) => set("data_end_column", event.target.value ? Number(event.target.value) : null)} disabled={busy || !value.enabled} /></label>
          </>
        )}
      </div>

      {context && (
        <div className="unit-evidence"><Eye size={17} /><span>Единица из источника: <b>{context.unit}</b> · строка {context.row_number}: «{context.text}»</span></div>
      )}
      {invalid && <div className="block-error"><Warning size={17} weight="fill" /> Проверь границы блока.</div>}
      <RawPreview preview={preview} state={value} />
    </article>
  );
}

export function ImportBlockReview({ recipe, previews = {}, busy, onApply, onDirtyChange }) {
  const [draft, setDraft] = useState(() => Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])));

  useEffect(() => {
    setDraft(Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])));
  }, [recipe]);

  const applied = useMemo(() => Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])), [recipe]);
  const dirtyBlocks = useMemo(
    () => recipe.sections.filter((section) => !sameState(draft[section.block_id] || stateFor(section), applied[section.block_id])),
    [recipe, draft, applied],
  );
  const enabledCount = useMemo(() => Object.values(draft).filter((value) => value.enabled).length, [draft]);
  const invalidCount = useMemo(() => Object.values(draft).filter((value) => value.enabled && (
    Number(value.header_row) < 1
    || Number(value.data_start_row) < 1
    || Number(value.data_end_row) < Number(value.data_start_row)
  )).length, [draft]);

  useEffect(() => { onDirtyChange?.(dirtyBlocks.length > 0); }, [dirtyBlocks.length, onDirtyChange]);

  const submit = () => {
    const decisions = dirtyBlocks.map((section) => {
      const next = draft[section.block_id];
      const previous = applied[section.block_id];
      const orientationChanged = next.orientation !== previous.orientation;
      const headerChanged = Number(next.header_row) !== Number(previous.header_row);
      return {
        block_id: section.block_id,
        enabled: next.enabled,
        orientation: next.orientation,
        header_row: Number(next.header_row),
        data_start_row: Number(next.data_start_row),
        data_end_row: Number(next.data_end_row),
        ...(next.orientation === "columns_are_analyses" ? {
          header_column: Number(next.header_column),
          data_start_column: Number(next.data_start_column),
          data_end_column: Number(next.data_end_column),
          analysis_axis_role: "Analysis",
          analysis_axis_field: "Analysis",
        } : {}),
        rebuild_mappings: orientationChanged || headerChanged,
      };
    });
    onApply(decisions);
  };

  return (
    <div className="block-review">
      <div className="block-review-intro">
        <div>
          <b>Сначала проверь, где в Excel действительно находятся таблицы.</b>
          <span>Зелёным показаны строки, которые войдут в блок, более тёмным — строка заголовка. Блок можно отключить целиком.</span>
        </div>
        <span>Включено: <b>{enabledCount}</b> из {recipe.sections.length}</span>
      </div>
      <div className="block-card-list">
        {recipe.sections.map((section, index) => (
          <BlockCard
            key={section.block_id}
            section={section}
            index={index}
            preview={previews[section.block_id]}
            value={draft[section.block_id] || stateFor(section)}
            busy={busy}
            onChange={(next) => setDraft((current) => ({ ...current, [section.block_id]: next }))}
          />
        ))}
      </div>
      <div className="block-review-actions">
        <span>{dirtyBlocks.length ? `Изменено блоков: ${dirtyBlocks.length}` : "Границы блоков не изменены"}</span>
        <button className="primary-button" onClick={submit} disabled={busy || !dirtyBlocks.length || !enabledCount || invalidCount > 0}>
          Применить структуру ({dirtyBlocks.length})
        </button>
      </div>
    </div>
  );
}
