import { useEffect, useMemo, useState } from "react";
import {
  CaretRight,
  CheckCircle,
  File,
  Info,
  Plus,
  Warning,
} from "@phosphor-icons/react";
import { ImportBlockReview } from "./ImportBlockReview";
import { ImportDuplicateReview } from "./ImportDuplicateReview";
import { ImportMappingEditor } from "./ImportMappingEditor";
import "./importWorkspace.css";

function warningLabel(item) {
  const labels = {
    CLEAN_TABLE_NO_DATA_ROWS: "На листе нет строк данных",
    CLEAN_TABLE_BLANK_HEADER: "Колонка с данными не имеет заголовка",
    CLEAN_TABLE_DUPLICATE_HEADER: "Повторяющийся заголовок",
    CLEAN_TABLE_INTERNAL_BLANK_ROW: "Пустая строка внутри таблицы",
    CLEAN_TABLE_REPEATED_HEADER: "Заголовок повторяется внутри данных",
    CLEAN_TABLE_ANALYSIS_REQUIRED: "Не определён Analysis",
    CLEAN_TABLE_MEASUREMENT_REQUIRED: "Не найдено измерение с единицей",
    CLEAN_TABLE_DUPLICATE_IDENTITIES: "Повторяются идентичности Analysis",
    CLEAN_TABLE_NO_VALID_DATA_SHEETS: "Нет однозначного листа данных",
    UNRECOGNIZED_CLEAN_FIELD: "Не определена роль поля",
    HEADER_NOT_DETECTED: "Не распознан заголовок",
    UNIT_REQUIRES_REVIEW: "Нужно указать единицу",
    MERGED_HEADERS: "Объединённые ячейки в заголовке",
    HIDDEN_ROWS: "В исходнике есть скрытые строки",
    FORMULA_WITHOUT_CACHED_VALUE: "Формула не имеет сохранённого значения",
    DUPLICATE_CANDIDATES: "Возможные совпадения Analysis",
    TRANSPOSED_TABLE_LIKELY: "Проверь ориентацию анализов",
    LEGACY_XLS_REQUIRES_CONVERSION: "Файл XLS требует рабочей XLSX-копии",
  };
  return labels[item.code] || item.code || "Нужна проверка";
}

function issueDetail(item) {
  return [
    item.sheet_name,
    item.source_header,
    item.row_number ? `строка ${item.row_number}` : null,
    Number.isInteger(item.source_column_index) ? `колонка ${item.source_column_index + 1}` : null,
  ].filter(Boolean).join(" · ");
}

function issueKey(item, index) {
  return [
    item.code,
    item.block_id || item.sheet_name,
    item.source_axis,
    item.source_column_index,
    item.source_row_index,
    item.row_number,
    index,
  ].filter((value) => value !== null && value !== undefined).join("::");
}

function sectionIssues(section, issues) {
  return issues.filter((item) => (
    (item.block_id && item.block_id === section.block_id)
    || (!item.block_id && item.sheet_name && item.sheet_name === section.sheet_name)
  ));
}

function sectionSubtitle(section) {
  const orientation = section.orientation === "columns_are_analyses"
    ? "анализы по столбцам"
    : "анализы по строкам";
  return `Заголовок: строка ${section.header_row} · ${orientation}`;
}

function origin(record) {
  return record.orientation === "columns_are_analyses"
    ? `${record.sheet_name} · колонка ${record.source_column_number}`
    : `${record.sheet_name} · строка ${record.row_number}`;
}

function measurementSummary(record) {
  return (record.measurements || []).slice(0, 5).map((item) => {
    const context = item.method || item.measurement_set;
    return `${item.field}${context ? ` (${context})` : ""}=${item.raw_token ?? "∅"} ${item.unit}`;
  }).join(" · ") || "Нет Measurement";
}

function CleanReadyPreview({ classification, plan, onDetailed, busy }) {
  return (
    <div className="workspace-ready">
      <div className="workspace-ready-head">
        <div>
          <span className="workspace-ready-state"><CheckCircle size={18} weight="fill" /> Таблица готова к импорту</span>
          <h3>PetroLab однозначно распознал структуру и единицы</h3>
          <p>Clean Table v{classification.clean_table_version}. Исходный файл не изменяется, а provenance каждой ячейки останется доступна.</p>
        </div>
        <button className="outline-button" type="button" onClick={onDetailed} disabled={busy}>Открыть подробную проверку</button>
      </div>
      <div className="workspace-plan-table">
        <div className="workspace-plan-head"><span>Источник</span><span>Analysis</span><span>Measurement</span></div>
        {(plan.planned_records || []).slice(0, 18).map((record) => (
          <div className="workspace-plan-row" key={record.preview_id}>
            <span>{origin(record)}</span>
            <b>{(record.identity || []).filter(Boolean).join(" · ") || "Analysis"}</b>
            <span>{measurementSummary(record)}</span>
          </div>
        ))}
      </div>
      {(plan.planned_records || []).length > 18 && <p className="workspace-more">Показано 18 из {plan.planned_records.length} Analysis.</p>}
    </div>
  );
}

export function ImportWorkspace({
  sourceName,
  sourceDisplayPath,
  inspection,
  recipe,
  recipeWarnings,
  plan,
  blockPreviews,
  cleanClassification,
  detailedReview,
  blockDraftDirty,
  mappingDraftDirty,
  duplicateReviewRequired,
  canSaveImport,
  plannedMeasurementCount,
  busy,
  onOpenDetailed,
  onApplySections,
  onApplyMappings,
  onBlockDirtyChange,
  onMappingDirtyChange,
  onKeepAllDuplicates,
  onCommit,
  onCancel,
  onChooseOther,
}) {
  const sections = recipe.sections || [];
  const [activeBlockId, setActiveBlockId] = useState(sections.find((item) => item.enabled !== false)?.block_id || sections[0]?.block_id || "");
  const [selectedIssueKey, setSelectedIssueKey] = useState("");

  useEffect(() => {
    if (!sections.some((item) => item.block_id === activeBlockId)) {
      setActiveBlockId(sections.find((item) => item.enabled !== false)?.block_id || sections[0]?.block_id || "");
    }
  }, [activeBlockId, sections]);

  const issues = useMemo(() => {
    const raw = [
      ...(cleanClassification?.mode === "raw_review" ? cleanClassification.reasons || [] : []),
      ...(recipeWarnings || []),
      ...(plan.warnings || []),
    ];
    const seen = new Set();
    return raw.filter((item) => {
      const key = [item.code, item.block_id, item.sheet_name, item.source_axis, item.source_column_index, item.source_row_index, item.row_number].join("::");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [cleanClassification, plan.warnings, recipeWarnings]);

  const keyedIssues = issues.map((item, index) => ({ item, key: issueKey(item, index) }));
  const selectedIssue = keyedIssues.find((entry) => entry.key === selectedIssueKey)?.item || keyedIssues[0]?.item || null;
  const activeSection = sections.find((item) => item.block_id === activeBlockId) || sections[0];
  const cleanFast = cleanClassification?.mode === "clean_table_fast" && !detailedReview;
  const blockingCount = (blockDraftDirty ? 1 : 0)
    + (mappingDraftDirty ? 1 : 0)
    + (duplicateReviewRequired ? 1 : 0)
    + (plannedMeasurementCount === 0 ? 1 : 0);

  const selectIssue = (entry) => {
    setSelectedIssueKey(entry.key);
    const matching = sections.find((section) => (
      (entry.item.block_id && section.block_id === entry.item.block_id)
      || (!entry.item.block_id && entry.item.sheet_name && section.sheet_name === entry.item.sheet_name)
    ));
    if (matching) setActiveBlockId(matching.block_id);
  };

  return (
    <div className="import-workspace">
      <header className="import-workspace-head">
        <div className="import-workspace-title">
          <File size={25} weight="duotone" />
          <div>
            <h1>Импорт таблиц</h1>
            <p>{cleanFast ? "Таблица готова к импорту" : issues.length ? `Файл требует внимания: ${issues.length} ${issues.length === 1 ? "вопрос" : "вопроса"}` : "Подробная проверка"}</p>
          </div>
        </div>
        <div className="import-workspace-head-actions">
          <span title={sourceDisplayPath}>{sourceName} · {inspection.source_format.toUpperCase()} · SHA-256 {inspection.source_fingerprint.slice(0, 12)}…</span>
          <button className="outline-button" type="button" onClick={onChooseOther} disabled={busy}><Plus size={17} /> Другой файл</button>
          <button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отменить</button>
        </div>
      </header>

      <div className="import-workspace-body">
        <aside className="import-source-pane">
          <div className="import-pane-label">Файл и листы</div>
          <div className="import-source-file">
            <File size={19} weight="duotone" />
            <div><b>{sourceName}</b><span>{inspection.sheets.length} листов</span></div>
          </div>
          <div className="import-sheet-list">
            {sections.map((section, index) => {
              const count = sectionIssues(section, issues).length;
              const active = section.block_id === activeBlockId;
              const disabled = section.enabled === false;
              return (
                <button
                  className={`import-sheet-row${active ? " active" : ""}${disabled ? " excluded" : ""}`}
                  type="button"
                  key={section.block_id}
                  onClick={() => setActiveBlockId(section.block_id)}
                >
                  <span className="import-sheet-check">{disabled ? "—" : count ? <Warning size={15} weight="fill" /> : <CheckCircle size={15} weight="fill" />}</span>
                  <span className="import-sheet-copy">
                    <b>{section.sheet_name}{sections.filter((item) => item.sheet_name === section.sheet_name).length > 1 ? ` · блок ${index + 1}` : ""}</b>
                    <small>{sectionSubtitle(section)}</small>
                  </span>
                  <span className={`import-sheet-status${count ? " warning" : ""}`}>
                    {disabled ? "Не импортируется" : count ? `${count} вопр.` : "Готов"}
                  </span>
                  <CaretRight size={14} />
                </button>
              );
            })}
            {(cleanClassification?.ignored_helper_sheets || []).map((sheet) => (
              <div className="import-sheet-row excluded" key={sheet}>
                <span className="import-sheet-check">—</span>
                <span className="import-sheet-copy"><b>{sheet}</b><small>Служебный или пустой лист</small></span>
                <span className="import-sheet-status">Не импортируется</span>
              </div>
            ))}
          </div>
          <div className="import-source-note"><Info size={15} /><span>Каждый лист сохраняет собственную строку заголовка, ориентацию и сопоставление.</span></div>
        </aside>

        <main className="import-table-pane">
          {cleanFast ? (
            <CleanReadyPreview classification={cleanClassification} plan={plan} onDetailed={onOpenDetailed} busy={busy} />
          ) : (
            <ImportBlockReview
              recipe={recipe}
              previews={blockPreviews}
              activeBlockId={activeBlockId}
              busy={busy}
              onApply={onApplySections}
              onDirtyChange={onBlockDirtyChange}
            />
          )}
        </main>

        <aside className="import-inspector-pane">
          <div className="import-pane-label">Нерешённые вопросы · {issues.length}</div>
          {keyedIssues.length > 0 ? (
            <div className="import-issue-list">
              {keyedIssues.map((entry) => (
                <button
                  className={`import-issue-row${selectedIssue === entry.item ? " active" : ""}`}
                  type="button"
                  key={entry.key}
                  onClick={() => selectIssue(entry)}
                >
                  <Warning size={16} weight="fill" />
                  <span><b>{warningLabel(entry.item)}</b><small>{issueDetail(entry.item) || "Требуется явное решение"}</small></span>
                </button>
              ))}
            </div>
          ) : (
            <div className="import-no-issues"><CheckCircle size={20} weight="fill" /><span>Обязательных вопросов нет</span></div>
          )}

          {!cleanFast && activeSection && (
            <div className="import-field-inspector">
              <div className="import-inspector-title">
                <span>Поля листа</span>
                <b>{activeSection.sheet_name}</b>
                {selectedIssue && <small>{warningLabel(selectedIssue)}</small>}
              </div>
              <ImportMappingEditor
                recipe={recipe}
                warnings={recipeWarnings}
                activeBlockId={activeBlockId}
                busy={busy || blockDraftDirty}
                onApplyAll={onApplyMappings}
                onDirtyChange={onMappingDirtyChange}
              />
            </div>
          )}

          {plan.summary.duplicate_candidate_groups > 0 && (
            <ImportDuplicateReview
              plan={plan}
              recipe={recipe}
              busy={busy || blockDraftDirty || mappingDraftDirty}
              onKeepAll={onKeepAllDuplicates}
            />
          )}
        </aside>
      </div>

      <footer className={`import-workspace-footer${canSaveImport ? "" : " blocked"}`}>
        <div className="import-footer-metrics">
          <span><b>{inspection.sheets.length}</b> листов</span>
          <span><b>{plan.summary.planned_analysis_count}</b> Analysis</span>
          <span><b>{plannedMeasurementCount}</b> Measurement</span>
          <span className={blockingCount ? "footer-warning" : ""}><b>{blockingCount}</b> обязательных решений</span>
        </div>
        <div className="import-footer-safety"><Info size={15} /><span>Исходный файл не изменится</span></div>
        <div className="import-footer-actions">
          <button className="outline-button" type="button" disabled={busy || !plan.planned_records?.length}>Предпросмотр результата</button>
          <button className="primary-button large" type="button" onClick={onCommit} disabled={busy || !canSaveImport}>
            <CheckCircle size={19} />
            {cleanFast ? "Импортировать таблицу" : canSaveImport ? "Сохранить импорт в проект" : "Импортировать после проверки"}
          </button>
        </div>
      </footer>
    </div>
  );
}
