import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle, Eye, Warning } from "@phosphor-icons/react";
import { previewImportWindow } from "./desktopApi";
import "./importBlockReview.css";

const PREVIEW_ROW_COUNT = 30;
const PREVIEW_COLUMN_COUNT = 24;
const STRUCTURE_DEBOUNCE_MS = 420;

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

function invalidState(value) {
  if (!value.enabled) return false;
  const transposed = value.orientation === "columns_are_analyses";
  return !Number.isInteger(Number(value.header_row))
    || Number(value.header_row) < 1
    || Number(value.data_start_row) < 1
    || Number(value.data_end_row) < Number(value.data_start_row)
    || (transposed && (
      Number(value.header_column) < 1
      || Number(value.data_start_column) < 1
      || (value.data_end_column != null && Number(value.data_end_column) < Number(value.data_start_column))
    ));
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

function decisionFor(section, next, previous) {
  const orientationChanged = next.orientation !== previous.orientation;
  const headerChanged = Number(next.header_row) !== Number(previous.header_row);
  const transposedBounds = next.orientation === "columns_are_analyses" ? {
    header_column: Number(next.header_column),
    data_start_column: Number(next.data_start_column),
    ...(next.data_end_column != null ? { data_end_column: Number(next.data_end_column) } : {}),
    analysis_axis_role: "Analysis",
    analysis_axis_field: "Analysis",
  } : {};
  return {
    block_id: section.block_id,
    enabled: next.enabled,
    orientation: next.orientation,
    header_row: Number(next.header_row),
    data_start_row: Number(next.data_start_row),
    data_end_row: Number(next.data_end_row),
    ...transposedBounds,
    rebuild_mappings: orientationChanged || headerChanged,
  };
}

function previewResult(response) {
  if (!response) throw new Error("PetroLab не получил окно предпросмотра.");
  if (response.error) throw new Error(response.error.message || "Не удалось прочитать строки Excel.");
  return response.result;
}

function issueCoordinates(issue) {
  if (!issue) return { row: null, column: null };
  const axis = issue.source_axis || "column";
  const row = Number.isInteger(issue.row_number)
    ? Number(issue.row_number)
    : axis === "row" && Number.isInteger(issue.source_row_index)
      ? Number(issue.source_row_index) + 1
      : null;
  const column = axis === "column" && Number.isInteger(issue.source_column_index)
    ? Number(issue.source_column_index)
    : null;
  return { row, column };
}

function RawPreview({ preview, state, loading, error, onNavigate, focusIssue }) {
  const [jumpRow, setJumpRow] = useState(preview?.start_row || 1);
  const [jumpColumn, setJumpColumn] = useState(Number(preview?.start_column || 0) + 1);

  useEffect(() => {
    if (preview?.start_row) setJumpRow(preview.start_row);
  }, [preview?.start_row]);

  useEffect(() => {
    if (Number.isInteger(preview?.start_column)) setJumpColumn(Number(preview.start_column) + 1);
  }, [preview?.start_column]);

  if (!preview || preview.preview_error || !Array.isArray(preview.rows)) {
    const message = error || preview?.preview_error || "PetroLab не получил строки этого листа.";
    return (
      <div className="raw-preview-unavailable" role="status">
        <Warning size={24} weight="fill" />
        <div>
          <b>Таблица не отображается</b>
          <span>{message}</span>
          <small>Импорт нельзя продолжать вслепую: сначала должен быть виден исходный лист.</small>
        </div>
        <button
          type="button"
          onClick={() => onNavigate(Number(state.header_row) || 1, true, 0)}
          disabled={loading || !preview?.source_path}
        >
          Перечитать лист
        </button>
      </div>
    );
  }

  const totalRows = Number(preview.used_range?.rows || 0);
  const totalColumns = Number(preview.used_range?.columns || 0);
  const currentRowCount = Math.max(1, Number(preview.end_row || 1) - Number(preview.start_row || 1) + 1);
  const previousStart = Math.max(1, Number(preview.start_row || 1) - currentRowCount);
  const nextStart = Math.min(Math.max(1, totalRows), Number(preview.end_row || 0) + 1);
  const canGoBack = Number(preview.start_row || 1) > 1;
  const canGoForward = Number(preview.end_row || 0) < totalRows;

  const currentColumnCount = Math.max(1, Number(preview.end_column || 1) - Number(preview.start_column || 0));
  const previousColumnStart = Math.max(0, Number(preview.start_column || 0) - currentColumnCount);
  const nextColumnStart = Math.min(Math.max(0, totalColumns - 1), Number(preview.end_column || 0));
  const canGoLeft = Number(preview.start_column || 0) > 0;
  const canGoRight = Number(preview.end_column || 0) < totalColumns;
  const firstColumnLabel = preview.column_labels?.[0] || "?";
  const lastColumnLabel = preview.column_labels?.[preview.column_labels.length - 1] || "?";
  const focused = issueCoordinates(focusIssue);

  const jumpToRow = () => {
    const row = Number(jumpRow);
    if (Number.isInteger(row) && row >= 1 && (!totalRows || row <= totalRows)) onNavigate(row, true);
  };

  const jumpToColumn = () => {
    const column = Number(jumpColumn);
    if (Number.isInteger(column) && column >= 1 && (!totalColumns || column <= totalColumns)) {
      onNavigate(Number(preview.start_row || 1), false, column - 1);
    }
  };

  return (
    <div className="raw-preview-shell">
      <div className="raw-preview-nav">
        <div>
          <b>{preview.sheet_name || "Лист"} · строки {preview.start_row}–{preview.end_row} · колонки {firstColumnLabel}–{lastColumnLabel}</b>
          <span>из {totalRows || "?"} строк · {totalColumns || "?"} колонок · это исходная таблица, а не результат импорта</span>
        </div>
        <div className="raw-preview-nav-actions">
          <button type="button" onClick={() => onNavigate(previousStart, false)} disabled={!canGoBack || loading}>← Выше</button>
          <button type="button" onClick={() => onNavigate(Number(state.header_row), true)} disabled={loading || Number(state.header_row) < 1}>К заголовку</button>
          <label>
            <span>К строке</span>
            <input
              type="number"
              min="1"
              max={totalRows || undefined}
              value={jumpRow}
              onChange={(event) => setJumpRow(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") jumpToRow(); }}
              disabled={loading}
            />
          </label>
          <button type="button" onClick={jumpToRow} disabled={loading}>Перейти</button>
          <button type="button" onClick={() => onNavigate(nextStart, false)} disabled={!canGoForward || loading}>Ниже →</button>
          <button type="button" onClick={() => onNavigate(Number(preview.start_row || 1), false, previousColumnStart)} disabled={!canGoLeft || loading}>← Левее</button>
          <label>
            <span>К колонке №</span>
            <input
              type="number"
              min="1"
              max={totalColumns || undefined}
              value={jumpColumn}
              onChange={(event) => setJumpColumn(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") jumpToColumn(); }}
              disabled={loading}
            />
          </label>
          <button type="button" onClick={jumpToColumn} disabled={loading}>Показать</button>
          <button type="button" onClick={() => onNavigate(Number(preview.start_row || 1), false, nextColumnStart)} disabled={!canGoRight || loading}>Правее →</button>
        </div>
      </div>
      {error && <div className="raw-preview-error"><Warning size={16} weight="fill" /> {error}</div>}
      {loading && <div className="raw-preview-loading-line">Читаю другой участок листа…</div>}
      <div className="raw-preview-wrap" aria-label={`Исходная таблица ${preview.sheet_name || "Excel"}`}>
        <table className="raw-preview-table">
          <thead>
            <tr>
              <th className="raw-row-number">#</th>
              {(preview.column_labels || []).map((label, index) => {
                const physicalColumn = Number(preview.start_column || 0) + index;
                return <th className={focused.column === physicalColumn ? "raw-focused-column" : ""} key={`${label}-${physicalColumn}`}>{label}</th>;
              })}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row) => {
              const isHeader = row.row_number === Number(state.header_row);
              const isData = row.row_number >= Number(state.data_start_row) && row.row_number <= Number(state.data_end_row);
              const isFocusedRow = focused.row === row.row_number;
              const rowClass = [isHeader ? "raw-header-row" : isData ? "raw-data-row" : "", isFocusedRow ? "raw-focused-row" : ""].filter(Boolean).join(" ");
              return (
                <tr key={row.row_number} className={rowClass}>
                  <th className="raw-row-number">{row.row_number}</th>
                  {(row.values || []).map((value, index) => {
                    const physicalColumn = Number(preview.start_column || 0) + index;
                    const focusedCell = focused.column === physicalColumn && (!focused.row || focused.row === row.row_number);
                    return <td className={focusedCell ? "raw-focused-cell" : focused.column === physicalColumn ? "raw-focused-column" : ""} key={`${row.row_number}-${physicalColumn}`}>{value ?? ""}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BlockCard({ section, index, preview, value, busy, onChange, focusIssue }) {
  const transposed = value.orientation === "columns_are_analyses";
  const context = section.unit_context;
  const invalid = invalidState(value);
  const [livePreview, setLivePreview] = useState(preview);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(preview?.preview_error || "");
  const [previewTarget, setPreviewTarget] = useState(null);
  const lastFocusKey = useRef("");

  useEffect(() => {
    setLivePreview(preview);
    setPreviewError(preview?.preview_error || "");
  }, [preview]);

  const fetchPreview = useCallback(async (row, center = true, requestedColumnStart = null) => {
    const sourcePath = livePreview?.source_path || preview?.source_path;
    if (!sourcePath || !section.sheet_name) {
      setPreviewError("Не найден путь к временной копии источника. Выбери файл заново.");
      return;
    }
    const totalRows = Number(livePreview?.used_range?.rows || preview?.used_range?.rows || 0);
    const totalColumns = Number(livePreview?.used_range?.columns || preview?.used_range?.columns || 0);
    const requested = Math.max(1, Math.min(Number(row) || 1, totalRows || Number(row) || 1));
    const startRow = center ? Math.max(1, requested - 4) : requested;
    const currentColumnStart = Number(livePreview?.start_column ?? preview?.start_column ?? 0);
    const rawColumnStart = requestedColumnStart == null ? currentColumnStart : Number(requestedColumnStart);
    const startColumn = Math.max(0, Math.min(Number.isFinite(rawColumnStart) ? rawColumnStart : 0, Math.max(0, totalColumns - 1)));
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const response = await previewImportWindow(
        sourcePath,
        section.sheet_name,
        startRow,
        PREVIEW_ROW_COUNT,
        startColumn,
        PREVIEW_COLUMN_COUNT,
      );
      setLivePreview(previewResult(response));
    } catch (caught) {
      setPreviewError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPreviewLoading(false);
    }
  }, [livePreview, preview, section.sheet_name]);

  useEffect(() => {
    if (!previewTarget) return undefined;
    const target = previewTarget;
    const timer = window.setTimeout(() => {
      setPreviewTarget(null);
      fetchPreview(target, true);
    }, 280);
    return () => window.clearTimeout(timer);
  }, [previewTarget, fetchPreview]);

  useEffect(() => {
    if (!focusIssue) return;
    const coordinates = issueCoordinates(focusIssue);
    const focusKey = [focusIssue.code, coordinates.row, coordinates.column].join("::");
    if (!focusKey || lastFocusKey.current === focusKey) return;
    lastFocusKey.current = focusKey;

    const currentStartRow = Number(livePreview?.start_row || 0);
    const currentEndRow = Number(livePreview?.end_row || 0);
    const currentStartColumn = Number(livePreview?.start_column || 0);
    const currentEndColumn = Number(livePreview?.end_column || 0) - 1;
    const rowVisible = !coordinates.row || (coordinates.row >= currentStartRow && coordinates.row <= currentEndRow);
    const columnVisible = coordinates.column == null || (coordinates.column >= currentStartColumn && coordinates.column <= currentEndColumn);
    if (rowVisible && columnVisible) return;

    const row = coordinates.row || Number(value.header_row) || 1;
    const columnStart = coordinates.column == null ? null : Math.max(0, coordinates.column - 2);
    fetchPreview(row, true, columnStart);
  }, [focusIssue]);

  const set = (field, next) => {
    const nextState = { ...value, [field]: next };
    onChange(nextState, field);
    if (["header_row", "data_start_row", "data_end_row"].includes(field) && Number(next) >= 1) {
      setPreviewTarget(Number(next));
    }
  };

  return (
    <article className={`import-block-card${value.enabled ? "" : " block-disabled"}${invalid ? " block-invalid" : ""}`}>
      <div className="block-card-head">
        <div className="block-title">
          <label className="block-toggle">
            <input type="checkbox" checked={value.enabled} onChange={(event) => set("enabled", event.target.checked)} disabled={busy} />
            <span />
          </label>
          <div>
            <b>{section.sheet_name} · таблица {index + 1}</b>
            <small>{transposed ? "анализы по столбцам" : "анализы по строкам"} · заголовок {value.header_row}</small>
          </div>
        </div>
        <div className="block-confidence">
          {value.enabled ? <><CheckCircle size={17} weight="fill" /> импортируется</> : "пропущена"}
        </div>
      </div>

      <RawPreview
        preview={livePreview}
        state={value}
        loading={previewLoading}
        error={previewError}
        onNavigate={fetchPreview}
        focusIssue={focusIssue}
      />

      <details className="block-structure-settings" open={invalid || undefined}>
        <summary>
          <span>Структура: {transposed ? "анализы по столбцам" : "анализы по строкам"} · заголовок {value.header_row} · данные {value.data_start_row}–{value.data_end_row}</span>
          <b>Изменить структуру</b>
        </summary>
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
              <label><span>Последняя колонка Analysis</span><input type="number" min="1" value={value.data_end_column || ""} onChange={(event) => set("data_end_column", event.target.value ? Number(event.target.value) : null)} disabled={busy || !value.enabled} placeholder="до конца" /></label>
            </>
          )}
        </div>
      </details>

      {context && (
        <div className="unit-evidence"><Eye size={17} /><span>Единица из источника: <b>{context.unit}</b> · строка {context.row_number}: «{context.text}»</span></div>
      )}
      {invalid && <div className="block-error"><Warning size={17} weight="fill" /> Проверь границы блока.</div>}
    </article>
  );
}

export function ImportBlockReview({ recipe, previews = {}, activeBlockId = null, busy, onApply, onDirtyChange, focusedIssue = null }) {
  const [draft, setDraft] = useState(() => Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])));
  const timers = useRef(new Map());

  useEffect(() => {
    for (const timer of timers.current.values()) window.clearTimeout(timer);
    timers.current.clear();
    setDraft(Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])));
  }, [recipe]);

  useEffect(() => () => {
    for (const timer of timers.current.values()) window.clearTimeout(timer);
  }, []);

  const applied = useMemo(() => Object.fromEntries(recipe.sections.map((section) => [section.block_id, stateFor(section)])), [recipe]);
  const dirtyBlocks = useMemo(
    () => recipe.sections.filter((section) => !sameState(draft[section.block_id] || stateFor(section), applied[section.block_id])),
    [recipe, draft, applied],
  );
  const enabledCount = useMemo(() => Object.values(draft).filter((value) => value.enabled).length, [draft]);
  const invalidCount = useMemo(() => Object.values(draft).filter(invalidState).length, [draft]);

  useEffect(() => { onDirtyChange?.(dirtyBlocks.length > 0); }, [dirtyBlocks.length, onDirtyChange]);

  const scheduleApply = (section, nextState, field, nextDraft) => {
    const existing = timers.current.get(section.block_id);
    if (existing) window.clearTimeout(existing);
    if (invalidState(nextState) || Object.values(nextDraft).filter((item) => item.enabled).length === 0) return;
    const previous = applied[section.block_id];
    if (!previous || sameState(nextState, previous)) return;
    const run = () => {
      timers.current.delete(section.block_id);
      onApply([decisionFor(section, nextState, previous)]);
    };
    if (["enabled", "orientation"].includes(field)) run();
    else timers.current.set(section.block_id, window.setTimeout(run, STRUCTURE_DEBOUNCE_MS));
  };

  const changeBlock = (section, nextState, field) => {
    const nextDraft = { ...draft, [section.block_id]: nextState };
    setDraft(nextDraft);
    scheduleApply(section, nextState, field, nextDraft);
  };

  const requestedSection = activeBlockId
    ? recipe.sections.find((section) => section.block_id === activeBlockId)
    : null;
  const activeSection = requestedSection
    || recipe.sections.find((section) => section.enabled !== false)
    || recipe.sections[0]
    || null;
  const visibleSections = activeSection ? [activeSection] : [];

  return (
    <div className="block-review">
      <div className="block-review-intro">
        <div>
          <b>Исходная таблица</b>
          <span>Сначала смотри на Excel. Настройки структуры спрятаны ниже таблицы и нужны только если автоматическое распознавание ошиблось.</span>
        </div>
        <span>Включено: <b>{enabledCount}</b> из {recipe.sections.length}</span>
      </div>
      <div className="block-card-list">
        {visibleSections.map((section) => (
          <BlockCard
            key={section.block_id}
            section={section}
            index={recipe.sections.findIndex((item) => item.block_id === section.block_id)}
            preview={previews[section.block_id]}
            value={draft[section.block_id] || stateFor(section)}
            busy={busy}
            focusIssue={focusedIssue && (
              (focusedIssue.block_id && focusedIssue.block_id === section.block_id)
              || (!focusedIssue.block_id && focusedIssue.sheet_name === section.sheet_name)
            ) ? focusedIssue : null}
            onChange={(nextState, field) => changeBlock(section, nextState, field)}
          />
        ))}
        {!activeSection && (
          <div className="block-review-empty">
            <Warning size={24} weight="fill" />
            <div><b>PetroLab не нашёл таблицу для отображения</b><span>Этот файл нельзя импортировать до явного выбора структуры.</span></div>
          </div>
        )}
      </div>
      <div className="block-review-actions">
        <span>{invalidCount > 0
          ? `Проверь границы: некорректных блоков ${invalidCount}`
          : dirtyBlocks.length
            ? `Изменения структуры применяются автоматически… (${dirtyBlocks.length})`
            : "Таблица отображается · структура синхронизирована"}</span>
      </div>
    </div>
  );
}
