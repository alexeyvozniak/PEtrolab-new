import { useEffect, useMemo, useState } from "react";
import {
  CaretRight,
  CheckCircle,
  File,
  Info,
  Plus,
  Warning,
  X,
} from "@phosphor-icons/react";
import { ImportBlockReview } from "./ImportBlockReview";
import { ImportDuplicateReview } from "./ImportDuplicateReview";
import { ImportMappingEditor } from "./ImportMappingEditor";
import { MineralVerificationPanel } from './MineralVerificationPanel';
import "./importWorkspace.css";

const REPEATABLE_ISSUE_CODES = new Set([
  "CLEAN_TABLE_BLANK_HEADER",
  "CLEAN_TABLE_DUPLICATE_HEADER",
  "CLEAN_TABLE_INTERNAL_BLANK_ROW",
  "CLEAN_TABLE_REPEATED_HEADER",
  "UNRECOGNIZED_CLEAN_FIELD",
  "UNIT_REQUIRES_REVIEW",
  "UNMAPPED_FIELD_REQUIRES_REVIEW",
  "FORMULA_WITHOUT_CACHED_VALUE",
  "HIDDEN_ROWS",
  "MERGED_HEADERS",
]);

function warningLabel(item) {
  const labels = {
    ANALYSIS_IDENTITY_REQUIRED: "Нет идентичности Analysis — назначьте заполненное поле",
    DUPLICATE_REVIEW_REQUIRED: "Проверьте возможные совпадения Analysis",
    IMPORT_PLAN_EMPTY: "Нет записей для импорта — проверьте блок и сопоставления",
    SOURCE_FINGERPRINT_MISMATCH: "Рабочая копия файла изменилась — добавьте исходник заново",
    FE_STRICTLY_REPORTED: "Форма Fe не определена — только исходная запись, без пересчёта",
    EMBEDDED_DRAWINGS_NOT_PREVIEWED: "Изображения листа не показаны в табличном просмотре",
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
    UNMAPPED_FIELD_REQUIRES_REVIEW: "Нужно выбрать роль поля",
    MERGED_HEADERS: "Объединённые ячейки в заголовке",
    HIDDEN_ROWS: "В исходнике есть скрытые строки",
    FORMULA_WITHOUT_CACHED_VALUE: "Формула не имеет сохранённого значения",
    DUPLICATE_CANDIDATES: "Возможные совпадения Analysis",
    TRANSPOSED_TABLE_LIKELY: "Проверь ориентацию анализов",
    LEGACY_XLS_SUPPORT_UNAVAILABLE: "В этой сборке недоступен модуль чтения старых XLS",
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
    item.source_id,
    item.code,
    item.block_id || item.sheet_name,
    item.source_axis,
    item.source_column_index,
    item.source_row_index,
    item.row_number,
    index,
  ].filter((value) => value !== null && value !== undefined).join("::");
}

function issueGroupKey(item) {
  if (REPEATABLE_ISSUE_CODES.has(item.code)) {
    return `${item.source_id || ""}::${item.code}::${item.block_id || item.sheet_name || "source"}`;
  }
  return issueKey(item, 0);
}

function groupIssues(items) {
  const groups = new Map();
  items.forEach((item, index) => {
    const key = issueGroupKey(item);
    const group = groups.get(key) || { key, item, items: [], firstIndex: index };
    group.items.push(item);
    groups.set(key, group);
  });
  return [...groups.values()].sort((left, right) => left.firstIndex - right.firstIndex);
}

function sectionIssues(section, issues) {
  return issues.filter((item) => (
    (item.block_id && item.block_id === section.block_id)
    || (!item.block_id && item.sheet_name && item.sheet_name === section.sheet_name)
  ));
}

function sectionIssueCount(section, issues) {
  return groupIssues(sectionIssues(section, issues)).length;
}

function sectionSubtitle(section) {
  const orientation = section.orientation === "columns_are_analyses"
    ? "анализы по столбцам"
    : "анализы по строкам";
  return `Заголовок: строка ${section.header_row} · ${orientation}`;
}

function sectionDecision(section, enabled) {
  const transposed = section.orientation === "columns_are_analyses";
  return {
    block_id: section.block_id,
    enabled,
    orientation: section.orientation || "rows_are_analyses",
    header_row: Number(section.header_row),
    data_start_row: Number(section.data_start_row),
    data_end_row: Number(section.data_end_row),
    ...(transposed ? {
      header_column: Number(section.header_column || 1),
      data_start_column: Number(section.data_start_column || 2),
      ...(section.data_end_column != null ? { data_end_column: Number(section.data_end_column) } : {}),
      analysis_axis_role: section.analysis_axis_role || "Analysis",
      analysis_axis_field: section.analysis_axis_field || "Analysis",
    } : {}),
    rebuild_mappings: false,
  };
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

function ResultPreview({ plan, sourceName, onClose }) {
  const [query, setQuery] = useState("");
  const records = plan.planned_records || [];
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? records.filter((record) => JSON.stringify(record).toLowerCase().includes(needle))
    : records;
  const shown = filtered.slice(0, 120);
  return (
    <div className="import-result-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="import-result-dialog" role="dialog" aria-modal="true" aria-labelledby="import-result-title">
        <header>
          <div>
            <span>Проверка перед сохранением</span>
            <h2 id="import-result-title">Что попадёт в проект</h2>
            <p>{sourceName} · {plan.summary.planned_analysis_count} Analysis · {plan.summary.planned_measurement_count} Measurement</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть предпросмотр"><X size={20} /></button>
        </header>
        <div className="import-result-tools">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти Analysis, Sample, значение…" aria-label="Поиск в результате импорта" autoFocus />
          <span>{filtered.length} из {records.length}</span>
        </div>
        <div className="import-result-table-wrap">
          <table className="import-result-table">
            <thead><tr><th>Источник</th><th>Analysis</th><th>Измерения</th></tr></thead>
            <tbody>
              {shown.map((record) => (
                <tr key={record.preview_id}>
                  <td>{origin(record)}</td>
                  <td><b>{(record.identity || []).filter(Boolean).join(" · ") || "Analysis"}</b></td>
                  <td>{measurementSummary(record)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length === 0 && <div className="import-result-empty">По этому запросу записей нет.</div>}
        </div>
        {filtered.length > shown.length && <footer>Показаны первые {shown.length} записей из {filtered.length}. Поиск работает по всему плану.</footer>}
      </section>
    </div>
  );
}

export function ImportWorkspace({
  workspace,
  focusedIssueKey = "",
  semanticTools = { actions: [], analytes: [] },
  onSemanticDecision,
  onVerifyMinerals,
  onAcceptMineral,
  onSelectSource,
  onToggleSource,
  sourceName,
  sourceDisplayPath,
  inspection,
  recipe,
  recipeWarnings,
  bulkUnitScopes = [],
  bulkIgnoreScopes = [],
  plan,
  blockPreviews,
  cleanClassification,
  detailedReview,
  blockDraftDirty,
  mappingDraftDirty,
  duplicateReviewRequired,
  canSaveImport,
  plannedMeasurementCount,
  unresolvedReviewCount,
  busy,
  onOpenDetailed,
  onApplySections,
  onApplyMappings,
  onApplyBulkUnit,
  onApplyBulkIgnore,
  onBlockDirtyChange,
  onMappingDirtyChange,
  onKeepAllDuplicates,
  onCommit,
  onCancel,
  onChooseOther,
}) {
  const sections = recipe.sections || [];
  const [localBlockId, setActiveBlockId] = useState(sections.find((item) => item.enabled !== false)?.block_id || sections[0]?.block_id || "");
  const activeBlockId = workspace?.active_block_id || localBlockId;
  const selectBlock = (blockId) => workspace ? onSelectSource(workspace.active_source_id, blockId) : setActiveBlockId(blockId);
  const [selectedIssueKey, setSelectedIssueKey] = useState(focusedIssueKey);
  const [bulkUnits, setBulkUnits] = useState({});
  const [showResultPreview, setShowResultPreview] = useState(false);
  const [mineralReview, setMineralReview] = useState(Boolean(recipe.global_decisions.mineral_verification_enabled));
  const [mineralFocus, setMineralFocus] = useState(null);
  useEffect(() => { setMineralReview(Boolean(recipe.global_decisions.mineral_verification_enabled)); setMineralFocus(null); }, [recipe.global_decisions.mineral_verification_enabled, workspace?.active_source_id]);
  useEffect(() => { setSelectedIssueKey(focusedIssueKey); }, [focusedIssueKey, workspace?.active_source_id]);

  const sheetGroups = useMemo(() => {
    const groups = new Map();
    sections.forEach((section) => {
      const group = groups.get(section.sheet_name) || { sheet_name: section.sheet_name, sections: [] };
      group.sections.push(section);
      groups.set(section.sheet_name, group);
    });
    return [...groups.values()];
  }, [sections]);

  useEffect(() => {
    if (!sections.some((item) => item.block_id === activeBlockId)) {
      setActiveBlockId(sections.find((item) => item.enabled !== false)?.block_id || sections[0]?.block_id || "");
    }
  }, [activeBlockId, sections]);

  const issues = useMemo(() => {
    if (workspace) return workspace.issues.map((item) => ({ ...item.message_params, source_id: item.source_id, issue_id: item.issue_id, code: item.code, blocking: item.blocking }));
    const raw = [
      ...(cleanClassification?.mode === "raw_review" ? cleanClassification.reasons || [] : []),
      ...(recipeWarnings || []),
      ...(plan.warnings || []),
      ...(plan.issues || []),
    ];
    const seen = new Set();
    return raw.filter((item) => {
      const key = [item.code, item.block_id, item.sheet_name, item.source_axis, item.source_column_index, item.source_row_index, item.row_number].join("::");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [workspace, cleanClassification, plan.warnings, plan.issues, recipeWarnings]);

  const issueGroups = useMemo(() => groupIssues(issues).sort((left, right) => Number(right.item.source_id === workspace?.active_source_id) - Number(left.item.source_id === workspace?.active_source_id)), [issues, workspace?.active_source_id]);
  const selectedGroup = issueGroups.find((entry) => entry.key === selectedIssueKey && (!workspace || entry.item.source_id === workspace.active_source_id)) || issueGroups.find((entry) => !workspace || entry.item.source_id === workspace.active_source_id) || null;
  const selectedIssue = selectedGroup?.item || null;
  const activeSection = sections.find((item) => item.block_id === activeBlockId) || sections[0];
  const cleanFast = cleanClassification?.mode === "clean_table_fast" && !detailedReview;
  const blockingCount = workspace ? workspace.issues.filter((item) => item.blocking).length + Number(blockDraftDirty) + Number(mappingDraftDirty) : (blockDraftDirty ? 1 : 0)
    + (plan.issues || []).filter((item) => item.blocking).length
    + (mappingDraftDirty ? 1 : 0)
    + (duplicateReviewRequired ? 1 : 0)
    + (unresolvedReviewCount > 0 ? 1 : 0)
    + (plannedMeasurementCount === 0 ? 1 : 0);

  const selectIssue = (entry) => {
    setMineralFocus(null);
    setSelectedIssueKey(entry.key);
    if (workspace && entry.item.source_id !== workspace.active_source_id) {
      onSelectSource(entry.item.source_id, entry.item.block_id, entry.key);
      return;
    }
    const matching = sections.find((section) => (
      (entry.item.block_id && section.block_id === entry.item.block_id)
      || (!entry.item.block_id && entry.item.sheet_name && section.sheet_name === entry.item.sheet_name)
    ));
    if (matching) selectBlock(matching.block_id);
  };

  const selectSheet = (group) => {
    const current = group.sections.find((section) => section.block_id === activeBlockId);
    const next = current || group.sections.find((section) => section.enabled !== false) || group.sections[0];
    if (next) selectBlock(next.block_id);
  };

  const toggleSheet = (group) => {
    const enabled = group.sections.some((section) => section.enabled !== false);
    const nextEnabled = !enabled;
    const otherEnabled = sections.some((section) => section.sheet_name !== group.sheet_name && section.enabled !== false);
    if (!nextEnabled && !otherEnabled) return;
    onApplySections(group.sections.map((section) => sectionDecision(section, nextEnabled)));
  };

  return (
    <div className="import-workspace">
      <header className="import-workspace-head">
        <div className="import-workspace-title">
          <File size={25} weight="duotone" />
          <div>
            <h1>Импорт таблиц</h1>
            <p>{cleanFast ? "Таблица готова к импорту" : issueGroups.length ? `${workspace?.sources.length > 1 ? 'Очередь' : 'Файл'} требует внимания: ${issueGroups.length} ${issueGroups.length === 1 ? "тип вопроса" : "типов вопросов"}` : "Подробная проверка"}</p>
          </div>
        </div>
        <div className="import-workspace-head-actions">
          <span title={sourceDisplayPath}>{sourceName} · {inspection.source_format.toUpperCase()} · SHA-256 {inspection.source_fingerprint.slice(0, 12)}…</span>
          <button className="outline-button" type="button" onClick={onChooseOther} disabled={busy || blockDraftDirty || mappingDraftDirty}><Plus size={17} /> Добавить файл</button>
          <button className="outline-button" type="button" onClick={onCancel} disabled={busy}>Отменить</button>
        </div>
      </header>

      <div className="import-workspace-body">
        <aside className="import-source-pane">
          <div className="import-pane-label">Файл и листы</div>
          {workspace && <div className="workspace-source-queue" aria-label="Очередь источников">
            {workspace.sources.map((source) => {
              const count = workspace.issues.filter((issue) => issue.source_id === source.source_id && issue.blocking).length;
              const name = source.original_display_path.split(/[\\/]/).pop();
              return <div key={source.source_id} className={source.source_id === workspace.active_source_id ? "queue-source active" : "queue-source"}>
                <button type="button" aria-label={`Открыть источник ${name}`} aria-pressed={source.source_id === workspace.active_source_id} onClick={() => onSelectSource(source.source_id)} disabled={busy || blockDraftDirty || mappingDraftDirty}>
                  <File size={17} /><span><b>{name}</b><small>{!source.included ? source.exclusion_reason : count ? `${count} обязательных вопросов` : "Нет обязательных вопросов"}</small></span>
                </button>
                <button className="queue-source-inclusion" type="button" onClick={() => onToggleSource(source)} disabled={busy || blockDraftDirty || mappingDraftDirty} aria-label={`${source.included ? "Пропустить" : "Включить"} источник ${name}`}>{source.included ? "Пропустить" : "Включить"}</button>
                {source.source_id !== workspace.active_source_id && source.sheets.map((sheet) => <button className="queue-sheet" type="button" key={sheet.sheet_key} disabled={busy || blockDraftDirty || mappingDraftDirty || !sheet.blocks.length} onClick={() => onSelectSource(source.source_id, sheet.blocks[0]?.block_id)}>{sheet.physical_sheet_name} · {sheet.included ? `${sheet.blocks.length} табл.` : sheet.exclusion_reason}</button>)}
              </div>;
            })}
          </div>}
          <div className="import-source-file">
            <File size={19} weight="duotone" />
            <div><b>{workspace ? 'Листы выбранного файла' : sourceName}</b><span>{inspection.sheets.length} листов</span></div>
          </div>
          <div className="import-sheet-list">
            {sheetGroups.map((group) => {
              const sourceIssues = workspace ? issues.filter((item) => item.source_id === workspace.active_source_id) : issues;
              const count = group.sections.reduce((total, section) => total + sectionIssueCount(section, sourceIssues), 0);
              const active = group.sections.some((section) => section.block_id === activeBlockId);
              const enabledCount = group.sections.filter((section) => section.enabled !== false).length;
              const disabled = enabledCount === 0;
              const otherEnabled = sections.some((section) => section.sheet_name !== group.sheet_name && section.enabled !== false);
              return (
                <div className={`import-sheet-group${active ? " active" : ""}${disabled ? " excluded" : ""}`} key={group.sheet_name}>
                  <div className="import-sheet-group-main">
                    <button className="import-sheet-row" type="button" onClick={() => selectSheet(group)} disabled={busy || blockDraftDirty || mappingDraftDirty}>
                      <span className="import-sheet-check">{disabled ? "—" : count ? <Warning size={15} weight="fill" /> : <CheckCircle size={15} weight="fill" />}</span>
                      <span className="import-sheet-copy">
                        <b>{group.sheet_name}</b>
                        <small title={disabled ? group.sections[0].exclusion_reason : undefined}>{disabled ? group.sections[0].exclusion_reason || "Исключено пользователем" : group.sections.length === 1 ? sectionSubtitle(group.sections[0]) : `${group.sections.length} таблиц · включено ${enabledCount}`}</small>
                      </span>
                      <span className={`import-sheet-status${count ? " warning" : ""}`}>
                        {disabled ? "Пропущен" : count ? `${count} типов` : "Готов"}
                      </span>
                      <CaretRight size={14} />
                    </button>
                    <button
                      className={`import-sheet-toggle${disabled ? " disabled-sheet" : ""}`}
                      type="button"
                      onClick={() => toggleSheet(group)}
                      disabled={busy || blockDraftDirty || mappingDraftDirty || (!disabled && !otherEnabled)}
                      aria-label={disabled ? `Импортировать лист ${group.sheet_name}` : `Не импортировать лист ${group.sheet_name}`}
                      title={disabled ? "Включить все таблицы листа" : !otherEnabled ? "Нельзя исключить последний импортируемый лист" : "Не импортировать все таблицы листа"}
                    >
                      <span />
                    </button>
                  </div>
                  {active && group.sections.length > 1 && (
                    <div className="import-block-list" aria-label={`Таблицы листа ${group.sheet_name}`}>
                      {group.sections.map((section, index) => {
                        const blockIssues = sectionIssueCount(section, sourceIssues);
                        return (
                          <button
                            className={`import-block-row${section.block_id === activeBlockId ? " active" : ""}${section.enabled === false ? " excluded" : ""}`}
                            type="button"
                            key={section.block_id}
                            onClick={() => selectBlock(section.block_id)}
                            disabled={busy || blockDraftDirty || mappingDraftDirty}
                          >
                            <span>Таблица {index + 1}</span>
                            <small>{section.enabled === false ? "пропущена" : blockIssues ? `${blockIssues} типов` : "готова"}</small>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
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
          <div className="import-source-note"><Info size={15} /><span>Выбери лист слева. Его исходная таблица всегда должна быть видна в центре.</span></div>
        </aside>

        <main className="import-table-pane">
          {cleanFast ? (
            <CleanReadyPreview classification={cleanClassification} plan={plan} onDetailed={onOpenDetailed} busy={busy} />
          ) : (
            <ImportBlockReview
              semanticTools={semanticTools}
              onSemanticDecision={onSemanticDecision}
              recipe={recipe}
              previews={blockPreviews}
              activeBlockId={activeBlockId}
              focusedIssue={mineralFocus || selectedIssue}
              busy={busy || mappingDraftDirty}
              onApply={onApplySections}
              onDirtyChange={onBlockDirtyChange}
            />
          )}
        </main>

        <aside className="import-inspector-pane">
          {onVerifyMinerals && <div className="import-stage-tabs"><button type="button" onClick={() => setMineralReview(false)} disabled={busy}>1 · Структура</button><button type="button" disabled={busy || blockDraftDirty || mappingDraftDirty || plan.ready_to_commit === false} onClick={() => recipe.global_decisions.mineral_verification_enabled ? setMineralReview(true) : onVerifyMinerals()}>2 · Проверить минералы</button></div>}
          {mineralReview ? <MineralVerificationPanel records={plan.planned_records || []} scopes={semanticTools.mineralScopes || []} busy={busy} onAccept={onAcceptMineral} onReveal={(record) => { setMineralFocus({ ...record, source_column_index: (record.source_column_number || 1) - 1 }); selectBlock(record.block_id); }} /> : <>
          <div className="import-pane-label">Вопросы · {issueGroups.length} типов · {issues.length} мест</div>
          {issueGroups.length > 0 ? (
            <div className="import-issue-list">
              {issueGroups.map((entry) => (
                <button
                  className={`import-issue-row${selectedGroup === entry ? " active" : ""}`}
                  type="button"
                  key={entry.key}
                  onClick={() => selectIssue(entry)}
                  disabled={busy || blockDraftDirty || mappingDraftDirty}
                >
                  <Warning size={16} weight="fill" />
                  <span><b>{warningLabel(entry.item)}{entry.items.length > 1 ? ` · ${entry.items.length} мест` : ""}</b><small>{workspace?.sources.find((s) => s.source_id === entry.item.source_id)?.original_display_path.split(/[\\/]/).pop()} · {issueDetail(entry.item) || "Открыть контекст источника"}</small></span>
                </button>
              ))}
            </div>
          ) : (
            <div className="import-no-issues"><CheckCircle size={20} weight="fill" /><span>Обязательных вопросов нет</span></div>
          )}

          {!cleanFast && activeSection && (
            <div className="import-field-inspector">
              {(bulkUnitScopes.length > 0 || bulkIgnoreScopes.length > 0) && (
                <div className="import-bulk-scopes">
                  <div className="import-inspector-title"><span>Групповые решения</span><small>Только для полей с доказанно одинаковой физической структурой</small></div>
                  {bulkUnitScopes.map((scope) => (
                    <div className="import-bulk-scope" key={scope.bulk_scope_id}>
                      <b>{scope.block_count} {scope.block_count === 1 ? "блок" : "блока"} · {scope.field_count} полей</b>
                      <small>{scope.fields.slice(0, 6).join(", ")}{scope.fields.length > 6 ? "…" : ""}</small>
                      <div>
                        <select aria-label={`Единица для группы ${scope.fields.join(", ")}`} value={bulkUnits[scope.bulk_scope_id] || ""} onChange={(event) => setBulkUnits((current) => ({ ...current, [scope.bulk_scope_id]: event.target.value }))} disabled={busy || blockDraftDirty || mappingDraftDirty}>
                          <option value="">Единица…</option>
                          <option value="wt.%">wt.%</option><option value="at.%">at.%</option><option value="ppm">ppm</option><option value="ppb">ppb</option><option value="apfu">apfu</option><option value="mol%">mol%</option><option value="ratio">ratio</option><option value="epsilon">epsilon</option>
                        </select>
                        <button className="compact-button" type="button" onClick={() => onApplyBulkUnit(scope.bulk_scope_id, bulkUnits[scope.bulk_scope_id])} disabled={busy || blockDraftDirty || mappingDraftDirty || !bulkUnits[scope.bulk_scope_id]}>Применить</button>
                      </div>
                    </div>
                  ))}
                  {bulkIgnoreScopes.map((scope) => (
                    <div className="import-bulk-scope ignore-scope" key={scope.bulk_scope_id}>
                      <b>{scope.field_count} нераспознанных полей · {scope.sheet_names.length} {scope.sheet_names.length === 1 ? "лист" : "листов"}</b>
                      <small>{scope.fields.slice(0, 6).join(", ")}{scope.fields.length > 6 ? "…" : ""}</small>
                      <button className="compact-button" type="button" onClick={() => onApplyBulkIgnore(scope.bulk_scope_id)} disabled={busy || blockDraftDirty || mappingDraftDirty}>Не импортировать все нераспознанные поля</button>
                    </div>
                  ))}
                </div>
              )}
              <div className="import-inspector-title">
                <span>Поля выбранной таблицы</span>
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
          </>}
        </aside>
      </div>

      <footer className={`import-workspace-footer${canSaveImport ? "" : " blocked"}`}>
        <div className="import-footer-metrics">
          <span><b>{inspection.sheets.length}</b> листов</span>
          <span><b>{plan.summary.planned_analysis_count}</b> Analysis</span>
          <span><b>{plannedMeasurementCount}</b> Measurement</span>
          <span className={blockingCount ? "footer-warning" : ""}><b>{blockingCount}</b> обязательных решений{unresolvedReviewCount ? ` · ${unresolvedReviewCount} полей` : ""}</span>
        </div>
        <div className="import-footer-safety"><Info size={15} /><span>Исходный файл не изменится</span></div>
        <div className="import-footer-actions">
          <button className="outline-button" type="button" onClick={() => setShowResultPreview(true)} disabled={busy || !plan.planned_records?.length}>Предпросмотр результата</button>
          <button className="primary-button large" type="button" onClick={onCommit} disabled={busy || !canSaveImport}>
            <CheckCircle size={19} />
            {cleanFast ? "Импортировать таблицу" : canSaveImport ? "Сохранить импорт в проект" : "Импортировать после проверки"}
          </button>
        </div>
        {(blockDraftDirty || mappingDraftDirty || workspace?.sources.length > 1) && <div className="workspace-commit-note" role="status">
          {blockDraftDirty || mappingDraftDirty ? "Примените правки перед переключением источника или экрана." : "Очередь для проверки: сохранение нескольких файлов пока недоступно. Решения хранятся до закрытия приложения."}
        </div>}
      </footer>
      {showResultPreview && <ResultPreview plan={plan} sourceName={sourceName} onClose={() => setShowResultPreview(false)} />}
    </div>
  );
}
