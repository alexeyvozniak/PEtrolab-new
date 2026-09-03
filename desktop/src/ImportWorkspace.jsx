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
  if (["UNIT_REQUIRES_REVIEW", "UNMAPPED_FIELD_REQUIRES_REVIEW"].includes(item.code)) {
    return `${item.code}::${item.block_id || item.sheet_name || ""}`;
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
  const [activeBlockId, setActiveBlockId] = useState(sections.find((item) => item.enabled !== false)?.block_id || sections[0]?.block_id || "");
  const [selectedIssueKey, setSelectedIssueKey] = useState("");
  const [bulkUnits, setBulkUnits] = useState({});
  const [showResultPreview, setShowResultPreview] = useState(false);

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

  const issueGroups = useMemo(() => groupIssues(issues), [issues]);
  const selectedGroup = issueGroups.find((entry) => entry.key === selectedIssueKey) || issueGroups[0] || null;
  const selectedIssue = selectedGroup?.item || null;
  const activeSection = sections.find((item) => item.block_id === activeBlockId) || sections[0];
  const cleanFast = cleanClassification?.mode === "clean_table_fast" && !detailedReview;
  const blockingCount = (blockDraftDirty ? 1 : 0)
    + (mappingDraftDirty ? 1 : 0)
    + (duplicateReviewRequired ? 1 : 0)
    + (unresolvedReviewCount > 0 ? 1 : 0)
    + (plannedMeasurementCount === 0 ? 1 : 0);

  const selectIssue = (entry) => {
    setSelectedIssueKey(entry.key);
    const matching = sections.find((section) => (
      (entry.item.block_id && section.block_id === entry.item.block_id)
      || (!entry.item.block_id && entry.item.sheet_name && section.sheet_name === entry.item.sheet_name)
    ));
    if (matching) setActiveBlockId(matching.block_id);
  };

  const selectSheet = (group) => {
    const current = group.sections.find((section) => section.block_id === activeBlockId);
    const next = current || group.sections.find((section) => section.enabled !== false) || group.sections[0];
    if (next) setActiveBlockId(next.block_id);
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
            <p>{cleanFast ? "Таблица готова к импорту" : issueGroups.length ? `Файл требует внимания: ${issueGroups.length} ${issueGroups.length === 1 ? "группа вопросов" : "группы вопросов"}` : "Подробная проверка"}</p>
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
            {sheetGroups.map((group) => {
              const count = group.sections.reduce((total, section) => total + sectionIssues(section, issues).length, 0);
              const active = group.sections.some((section) => section.block_id === activeBlockId);
              const enabledCount = group.sections.filter((section) => section.enabled !== false).length;
              const disabled = enabledCount === 0;
              const otherEnabled = sections.some((section) => section.sheet_name !== group.sheet_name && section.enabled !== false);
              return (
                <div className={`import-sheet-group${active ? " active" : ""}${disabled ? " excluded" : ""}`} key={group.sheet_name}>
                  <div className="import-sheet-group-main">
                    <button className="import-sheet-row" type="button" onClick={() => selectSheet(group)}>
                      <span className="import-sheet-check">{disabled ? "—" : count ? <Warning size={15} weight="fill" /> : <CheckCircle size={15} weight="fill" />}</span>
                      <span className="import-sheet-copy">
                        <b>{group.sheet_name}</b>
                        <small>{group.sections.length === 1 ? sectionSubtitle(group.sections[0]) : `${group.sections.length} таблиц · включено ${enabledCount}`}</small>
                      </span>
                      <span className={`import-sheet-status${count ? " warning" : ""}`}>
                        {disabled ? "Пропущен" : count ? `${count} вопр.` : "Готов"}
                      </span>
                      <CaretRight size={14} />
                    </button>
                    <button
                      className={`import-sheet-toggle${disabled ? " disabled-sheet" : ""}`}
                      type="button"
                      onClick={() => toggleSheet(group)}
                      disabled={busy || (!disabled && !otherEnabled)}
                      aria-label={disabled ? `Импортировать лист ${group.sheet_name}` : `Не импортировать лист ${group.sheet_name}`}
                      title={disabled ? "Включить все таблицы листа" : !otherEnabled ? "Нельзя исключить последний импортируемый лист" : "Не импортировать все таблицы листа"}
                    >
                      <span />
                    </button>
                  </div>
                  {active && group.sections.length > 1 && (
                    <div className="import-block-list" aria-label={`Таблицы листа ${group.sheet_name}`}>
                      {group.sections.map((section, index) => {
                        const blockIssues = sectionIssues(section, issues).length;
                        return (
                          <button
                            className={`import-block-row${section.block_id === activeBlockId ? " active" : ""}${section.enabled === false ? " excluded" : ""}`}
                            type="button"
                            key={section.block_id}
                            onClick={() => setActiveBlockId(section.block_id)}
                          >
                            <span>Таблица {index + 1}</span>
                            <small>{section.enabled === false ? "пропущена" : blockIssues ? `${blockIssues} вопр.` : "готова"}</small>
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
          <div className="import-pane-label">Нерешённые вопросы · {issueGroups.length}</div>
          {issueGroups.length > 0 ? (
            <div className="import-issue-list">
              {issueGroups.map((entry) => (
                <button
                  className={`import-issue-row${selectedGroup === entry ? " active" : ""}`}
                  type="button"
                  key={entry.key}
                  onClick={() => selectIssue(entry)}
                >
                  <Warning size={16} weight="fill" />
                  <span><b>{warningLabel(entry.item)}{entry.items.length > 1 ? ` · ${entry.items.length} полей` : ""}</b><small>{issueDetail(entry.item) || "Требуется явное решение"}</small></span>
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
      </footer>
      {showResultPreview && <ResultPreview plan={plan} sourceName={sourceName} onClose={() => setShowResultPreview(false)} />}
    </div>
  );
}
