import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle,
  Columns,
  Database,
  File,
  FileArrowUp,
  GearSix,
  Info,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
  Warning,
} from "@phosphor-icons/react";
import {
  applyImportPlan,
  classifyCleanTable,
  clearImportStaging,
  createImportPlan,
  getProjectDatabasePath,
  inspectImportSource,
  isPetrolabDesktop,
  listProjectAnalyses,
  pickImportFile,
  previewImportWindow,
  retractLastImport,
  reviewImportDuplicates,
  reviseImportMappings,
  reviseImportSections,
  stageImportFile,
  suggestImportRecipe,
} from "./desktopApi";
import { ImportBlockReview } from "./ImportBlockReview";
import { ImportDuplicateReview } from "./ImportDuplicateReview";
import { ImportMappingEditor } from "./ImportMappingEditor";
import { ImportWorkspace } from "./ImportWorkspace";
import "./styles.css";

const navigation = [
  [MagnifyingGlass, "Поиск", false],
  [FileArrowUp, "Импорт", true],
  [Database, "Анализы", true],
  [Columns, "Образцы", false],
  [Columns, "Минералы", false],
  [Columns, "Связи", false],
  [File, "Изображения", false],
  [Columns, "Построение", false],
  [Columns, "Статистика", false],
  [Columns, "Публикации", false],
];

function unwrap(response) {
  if (!response) throw new Error("PetroLab не получил ответ от научного сервиса.");
  if (response.error) {
    const details = response.error.details ? Object.values(response.error.details).filter(Boolean).join(", ") : "";
    throw new Error(`${response.error.message}${details ? ` (${details})` : ""}`);
  }
  return response.result;
}

function fileName(path) {
  if (!path) return "";
  return path.split(/[\\/]/).pop();
}

function warningText(warning) {
  const names = {
    HEADER_NOT_DETECTED: "Табличный заголовок не распознан",
    UNIT_REQUIRES_REVIEW: "Колонка похожа на измерение, но единица не указана явно",
    MERGED_HEADERS: "В заголовке есть объединённые ячейки",
    HIDDEN_ROWS: "В файле есть скрытые строки",
    FORMULA_WITHOUT_CACHED_VALUE: "Есть формулы без сохранённого значения",
    DUPLICATE_CANDIDATES: "Найдены возможные совпадения идентичности",
    TRANSPOSED_TABLE_LIKELY: "Похоже, анализы расположены по столбцам — проверь ориентацию блока",
    LEGACY_XLS_REQUIRES_CONVERSION: "Старый XLS пока требует сохранения копии как XLSX",
  };
  return names[warning.code] || warning.code || "Предупреждение импорта";
}

function cleanReasonText(reason) {
  const names = {
    CLEAN_TABLE_NO_DATA_ROWS: "На листе нет строк данных после заголовка",
    CLEAN_TABLE_BLANK_HEADER: "Есть колонка с данными, но без заголовка",
    CLEAN_TABLE_DUPLICATE_HEADER: "Есть повторяющиеся заголовки колонок",
    CLEAN_TABLE_INTERNAL_BLANK_ROW: "Внутри таблицы есть пустая строка",
    CLEAN_TABLE_REPEATED_HEADER: "Строка заголовков повторяется внутри данных",
    CLEAN_TABLE_ANALYSIS_REQUIRED: "Нет явной колонки Analysis",
    CLEAN_TABLE_MEASUREMENT_REQUIRED: "Нет ни одного Measurement с явной единицей",
    CLEAN_TABLE_NO_VALID_DATA_SHEETS: "Не найден ни один лист, полностью соответствующий Clean Table",
    CLEAN_TABLE_DUPLICATE_IDENTITIES: "Есть повторяющиеся идентичности Analysis — нужна проверка совпадений",
    UNRECOGNIZED_CLEAN_FIELD: "Есть поле без однозначной роли или явной единицы",
    MERGED_HEADERS: "В исходнике есть объединённые ячейки",
    HIDDEN_ROWS: "В исходнике есть скрытые строки",
    FORMULA_WITHOUT_CACHED_VALUE: "Есть формулы без сохранённого значения",
  };
  const base = names[reason.code] || reason.code || "Нужна проверка структуры";
  const location = reason.sheet_name ? ` · ${reason.sheet_name}` : "";
  const field = reason.source_header ? ` · ${reason.source_header}` : "";
  const row = reason.row_number ? ` · строка ${reason.row_number}` : "";
  const column = Number.isInteger(reason.source_column_index) ? ` · колонка ${reason.source_column_index + 1}` : "";
  return `${base}${location}${field}${row}${column}`;
}

function warningCoordinate(warning) {
  const axis = warning.source_axis || "column";
  const index = axis === "column" ? warning.source_column_index : warning.source_row_index;
  return `${warning.block_id || warning.sheet_name || ""}::${axis}::${index}`;
}

function decisionCoordinate(decision) {
  return `${decision.block_id || ""}::${decision.source_axis || "column"}::${decision.source_index}`;
}

function recordOrigin(record) {
  if (record.orientation === "columns_are_analyses") {
    return `${record.sheet_name} · колонка ${record.source_column_number}`;
  }
  return `${record.sheet_name} · строка ${record.row_number}`;
}

function savedAnalysisOrigin(analysis) {
  if (analysis.source_orientation === "columns_are_analyses") {
    return `колонка ${analysis.source_column_number ?? "?"}`;
  }
  return `строка ${analysis.source_row_number ?? "?"}`;
}

function measurementPreview(measurement) {
  const context = measurement.method || measurement.measurement_set;
  const label = context ? `${measurement.field} (${context})` : measurement.field;
  return `${label}=${measurement.raw_token ?? "∅"} ${measurement.unit} [${measurement.source_cell || ""}]`;
}

function CleanTableSummary({ classification, onDetailed, busy }) {
  return (
    <div className="live-card">
      <div className="section-title">
        <div>
          <h3><CheckCircle size={20} weight="fill" /> Clean Table распознан</h3>
          <p>Структура однозначна: PetroLab не требует ручного выбора блоков, ролей и единиц.</p>
        </div>
        <button className="outline-button" type="button" onClick={onDetailed} disabled={busy}>Открыть подробную проверку</button>
      </div>
      <div className="warning-list">
        {classification.sections.map((section) => (
          <div key={section.sheet_name}>
            <CheckCircle size={18} weight="fill" />
            <span>
              <b>{section.sheet_name}</b>
              {section.analysis_fields?.length ? ` · ${section.analysis_fields.join(", ")}` : ""}
              {section.metadata_fields?.length ? ` · metadata: ${section.metadata_fields.join(", ")}` : ""}
              {section.measurements?.length ? ` · ${section.measurements.map((item) => `${item.field} [${item.unit}]`).join(", ")}` : ""}
            </span>
          </div>
        ))}
      </div>
      {classification.ignored_helper_sheets?.length > 0 && (
        <p className="more-note">Служебные листы официального шаблона не импортируются: {classification.ignored_helper_sheets.join(", ")}.</p>
      )}
    </div>
  );
}

export function App() {
  const desktopRuntimeAvailable = isPetrolabDesktop();
  const [screen, setScreen] = useState("Импорт");
  const [databasePath, setDatabasePath] = useState("");
  const [project, setProject] = useState({ total: 0, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] });
  const [sourcePath, setSourcePath] = useState("");
  const [sourceDisplayPath, setSourceDisplayPath] = useState("");
  const [inspection, setInspection] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [recipeWarnings, setRecipeWarnings] = useState([]);
  const [plan, setPlan] = useState(null);
  const [blockPreviews, setBlockPreviews] = useState({});
  const [cleanClassification, setCleanClassification] = useState(null);
  const [detailedReview, setDetailedReview] = useState(false);
  const [blockDraftDirty, setBlockDraftDirty] = useState(false);
  const [mappingDraftDirty, setMappingDraftDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [query, setQuery] = useState("");

  const refreshAnalyses = useCallback(async (path = databasePath) => {
    if (!path) return;
    setProject(unwrap(await listProjectAnalyses(path)));
  }, [databasePath]);

  useEffect(() => {
    if (!desktopRuntimeAvailable) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const path = await getProjectDatabasePath();
        if (cancelled) return;
        setDatabasePath(path);
        const result = unwrap(await listProjectAnalyses(path));
        if (!cancelled) setProject(result);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
    return () => { cancelled = true; };
  }, [desktopRuntimeAvailable]);

  const identityColumns = useMemo(() => {
    const fields = new Set();
    project.analyses.forEach((analysis) => Object.keys(analysis.identity || {}).forEach((field) => fields.add(field)));
    return [...fields];
  }, [project.analyses]);

  const metadataColumns = useMemo(() => {
    const fields = new Set();
    project.analyses.forEach((analysis) => Object.keys(analysis.source_metadata || {}).forEach((field) => fields.add(field)));
    return [...fields];
  }, [project.analyses]);

  const measurementColumns = useMemo(() => {
    const fields = new Set();
    project.analyses.forEach((analysis) => Object.keys(analysis.measurements || {}).forEach((field) => fields.add(field)));
    return [...fields].slice(0, 14);
  }, [project.analyses]);

  const filteredAnalyses = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return project.analyses;
    return project.analyses.filter((analysis) => JSON.stringify(analysis).toLowerCase().includes(needle));
  }, [project.analyses, query]);

  const plannedMeasurementCount = plan?.summary?.planned_measurement_count
    ?? plan?.planned_records?.reduce((total, record) => total + record.measurements.length, 0)
    ?? 0;
  const enabledBlockCount = plan?.summary?.enabled_block_count
    ?? recipe?.sections?.filter((section) => section.enabled !== false).length
    ?? 0;
  const duplicateCandidateGroups = plan?.summary?.duplicate_candidate_groups ?? 0;
  const duplicateReview = recipe?.global_decisions?.duplicate_review;
  const duplicateReviewRequired = duplicateCandidateGroups > 0 && !(
    recipe?.global_decisions?.duplicate_policy === "keep_all"
    && duplicateReview?.decision === "keep_all"
    && duplicateReview?.candidate_group_count === duplicateCandidateGroups
  );
  const isCleanFast = cleanClassification?.mode === "clean_table_fast" && !detailedReview;

  const visibleRecipeWarnings = useMemo(() => {
    if (!recipe) return recipeWarnings;
    return recipeWarnings.filter((warning) => {
      const section = recipe.sections.find((item) => item.block_id === warning.block_id)
        || recipe.sections.find((item) => item.sheet_name === warning.sheet_name);
      if (warning.code === "TRANSPOSED_TABLE_LIKELY") {
        return Boolean(section && section.enabled !== false && section.orientation === "columns_are_analyses");
      }
      if (warning.code !== "UNIT_REQUIRES_REVIEW") return true;
      if (!section || section.enabled === false) return false;
      const axis = warning.source_axis || "column";
      const index = axis === "column" ? warning.source_column_index : warning.source_row_index;
      const mapping = section.mappings.find((item) => {
        const itemAxis = item.source_axis || (Number.isInteger(item.source_column_index) ? "column" : "row");
        const itemIndex = itemAxis === "column" ? item.source_column_index : item.source_row_index;
        return itemAxis === axis && itemIndex === index;
      });
      return !mapping || mapping.target_role === "ignore";
    });
  }, [recipe, recipeWarnings]);

  const canSaveImport = Boolean(
    plan
    && plan.summary.planned_analysis_count > 0
    && plannedMeasurementCount > 0
    && enabledBlockCount > 0
    && !blockDraftDirty
    && !mappingDraftDirty
    && !duplicateReviewRequired,
  );

  const loadBlockPreviews = useCallback(async (path, nextRecipe) => {
    if (!path || !nextRecipe?.sections?.length) return {};
    const pairs = await Promise.all(nextRecipe.sections.map(async (section) => {
      const startRow = Math.max(1, Number(section.header_row || 1) - 2);
      const preview = unwrap(await previewImportWindow(path, section.sheet_name, startRow, 12, 0, 18));
      return [section.block_id, preview];
    }));
    return Object.fromEntries(pairs);
  }, []);

  const resetImportState = () => {
    setSourcePath("");
    setSourceDisplayPath("");
    setInspection(null);
    setRecipe(null);
    setRecipeWarnings([]);
    setPlan(null);
    setBlockPreviews({});
    setCleanClassification(null);
    setDetailedReview(false);
    setBlockDraftDirty(false);
    setMappingDraftDirty(false);
  };

  const chooseFile = async () => {
    if (busy) return;
    setBusy(true);
    setActivity("Выберите файл…");
    setError("");
    setSuccess("");
    const previousStaged = sourcePath;
    let newlyStaged = "";
    try {
      const selectedPath = await pickImportFile();
      if (!selectedPath) return;
      setActivity("Копирую файл в рабочую область PetroLab…");
      const selected = await stageImportFile(selectedPath);
      newlyStaged = selected.local_path;
      setActivity("Проверяю, соответствует ли файл PetroLab Clean Table…");
      const [inspected, classification] = await Promise.all([
        inspectImportSource(newlyStaged).then(unwrap),
        classifyCleanTable(newlyStaged).then(unwrap),
      ]);

      let nextRecipe;
      let nextWarnings = [];
      let previews = {};
      if (classification.mode === "clean_table_fast") {
        nextRecipe = classification.recipe;
        setActivity("Clean Table распознан. Строю итоговый план…");
      } else {
        setActivity("Файл требует подготовки. Ищу логические таблицы…");
        const suggestion = unwrap(await suggestImportRecipe(newlyStaged));
        nextRecipe = suggestion.recipe;
        nextWarnings = suggestion.warnings || [];
        setActivity("Строю предпросмотр исходных строк…");
        previews = await loadBlockPreviews(newlyStaged, nextRecipe);
      }
      const planned = unwrap(await createImportPlan(newlyStaged, nextRecipe));

      setSourcePath(newlyStaged);
      setSourceDisplayPath(selected.original_path || selectedPath);
      setInspection(inspected);
      setRecipe(nextRecipe);
      setRecipeWarnings(nextWarnings);
      setPlan(planned);
      setBlockPreviews(previews);
      setCleanClassification(classification);
      setDetailedReview(false);
      setBlockDraftDirty(false);
      setMappingDraftDirty(false);
      setScreen("Импорт");

      if (previousStaged && previousStaged !== newlyStaged) clearImportStaging(previousStaged).catch(() => {});
    } catch (caught) {
      if (newlyStaged) clearImportStaging(newlyStaged).catch(() => {});
      setScreen("Импорт");
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const openDetailedReview = async () => {
    if (busy || !sourcePath || !recipe) return;
    setBusy(true);
    setActivity("Открываю подробную проверку исходника…");
    try {
      const previews = await loadBlockPreviews(sourcePath, recipe);
      setBlockPreviews(previews);
      setDetailedReview(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const applySections = async (decisions) => {
    if (busy || !sourcePath || !recipe || !decisions?.length) return;
    setBusy(true);
    setActivity(`Проверяю структуру ${decisions.length} блоков…`);
    setError("");
    setSuccess("");
    try {
      const revised = unwrap(await reviseImportSections(sourcePath, recipe, decisions));
      const [planned, previews] = await Promise.all([
        createImportPlan(sourcePath, revised.recipe).then(unwrap),
        loadBlockPreviews(sourcePath, revised.recipe),
      ]);
      setRecipe(revised.recipe);
      setPlan(planned);
      setBlockPreviews(previews);
      setDetailedReview(true);
      setBlockDraftDirty(false);
      setMappingDraftDirty(false);
      setSuccess(`Структура применена: ${decisions.length} блоков. Теперь проверь роли полей.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const applyMappings = async (decisions) => {
    if (busy || !sourcePath || !recipe || !decisions?.length) return;
    setBusy(true);
    setActivity(`Применяю сопоставление ${decisions.length} полей…`);
    setError("");
    setSuccess("");
    try {
      const revised = unwrap(await reviseImportMappings(sourcePath, recipe, decisions));
      const planned = unwrap(await createImportPlan(sourcePath, revised.recipe));
      const resolved = new Set(decisions.map(decisionCoordinate));
      setRecipeWarnings((current) => current.filter((warning) => warning.code !== "UNIT_REQUIRES_REVIEW" || !resolved.has(warningCoordinate(warning))));
      setRecipe(revised.recipe);
      setPlan(planned);
      setDetailedReview(true);
      setMappingDraftDirty(false);
      setSuccess(`Сопоставление применено: ${decisions.length} полей. Проверь итоговый план.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const keepAllDuplicateCandidates = async () => {
    if (busy || !sourcePath || !recipe || !duplicateCandidateGroups) return;
    setBusy(true);
    setActivity(`Фиксирую решение по ${duplicateCandidateGroups} группам совпадений…`);
    setError("");
    setSuccess("");
    try {
      const reviewed = unwrap(await reviewImportDuplicates(sourcePath, recipe, "keep_all"));
      setRecipe(reviewed.recipe);
      setPlan(reviewed.plan);
      setSuccess(`Совпадения проверены: ${reviewed.duplicate_review.candidate_group_count} групп. Все записи останутся отдельными.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const commitImport = async () => {
    if (busy || !canSaveImport || !databasePath || !sourcePath || !recipe || !plan) return;
    const stagedPath = sourcePath;
    setBusy(true);
    setActivity("Сохраняю проверенный импорт в проект…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await applyImportPlan(databasePath, stagedPath, recipe));
      await refreshAnalyses(databasePath);
      resetImportState();
      clearImportStaging(stagedPath).catch(() => {});
      const metadataNote = result.source_metadata_count ? `, ${result.source_metadata_count} исходных метаданных` : "";
      setSuccess(`Импорт сохранён: ${result.analysis_count} Analysis, ${result.measurement_count} Measurement${metadataNote}.`);
      setScreen("Анализы");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const retractLatest = async () => {
    if (busy || !databasePath || !project.latest_import) return;
    const latest = project.latest_import;
    const confirmed = window.confirm(
      `Отменить последний импорт «${latest.source_name}» (${latest.analysis_count} Analysis)?\n\nДанные исчезнут из активного проекта, но история импорта сохранится для воспроизводимости.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setActivity("Отменяю последний импорт…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await retractLastImport(databasePath, "user_retracted_from_analyses"));
      await refreshAnalyses(databasePath);
      setSuccess(`Импорт «${result.source_name}» отменён: ${result.analysis_count} Analysis убраны из активного проекта.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const startNewImport = () => {
    if (busy) return;
    const stagedPath = sourcePath;
    resetImportState();
    if (stagedPath) clearImportStaging(stagedPath).catch(() => {});
    setError("");
    setSuccess("");
    setScreen("Импорт");
  };

  const goTo = (label, enabled) => {
    if (!enabled || busy) return;
    setError("");
    setScreen(label);
    if (label === "Анализы") refreshAnalyses().catch((caught) => setError(caught.message));
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Database size={30} weight="duotone" /></div>
          <div><strong>PetroLab</strong><span>Desktop v2 alpha</span></div>
        </div>
        <nav>
          {navigation.map(([Icon, label, enabled]) => (
            <button
              className={`${screen === label ? "nav-item active" : "nav-item"}${enabled ? "" : " disabled"}`}
              key={label}
              disabled={!enabled || busy}
              onClick={() => goTo(label, enabled)}
              title={enabled ? label : "Экран ещё не подключён в этой alpha-сборке"}
            >
              <Icon size={19} /><span>{label}</span>{!enabled && <small>скоро</small>}
            </button>
          ))}
        </nav>
        <div className="side-footer"><Info size={18} /><span>Сейчас оживлены: импорт и анализы</span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{screen}</h2>
            <p>Источников: <b>{project.source_count}</b> · импортов: <b>{project.import_batch_count}</b> · анализов: <b>{project.total}</b></p>
          </div>
          <div className="top-actions">
            <button className="outline-button" onClick={startNewImport} disabled={busy || !desktopRuntimeAvailable} title={desktopRuntimeAvailable ? undefined : "Полный импорт доступен в установленном PetroLab Desktop"}><Plus size={18} /> Добавить данные</button>
            <button className="icon-button" disabled title="Настройки будут подключены позже"><GearSix size={21} /></button>
          </div>
        </header>

        {activity && <div className="global-message activity"><SpinnerGap className="spin" size={20} /><span>{activity}</span></div>}
        {!desktopRuntimeAvailable && <div className="global-message activity"><Info size={20} /><span>Предпросмотр проверяет компоновку. Выбор и импорт файлов доступны в установленном PetroLab Desktop.</span></div>}
        {error && <div className="global-message error"><Warning size={20} weight="fill" /><span>{error}</span></div>}
        {success && <div className="global-message success"><CheckCircle size={20} weight="fill" /><span>{success}</span></div>}

        {screen === "Импорт" && (
          <section className={`live-page${sourcePath ? " import-live-page" : ""}`}>
            {!sourcePath && (
              <div className="file-start-card">
                <div className="file-start-icon"><FileArrowUp size={46} weight="duotone" /></div>
                <h1>Добавить файл</h1>
                <p>Если это PetroLab Clean Table, импорт будет коротким. Сырые и неоднозначные Excel откроются в отдельной подготовке.</p>
                <button className="primary-button large" onClick={chooseFile} disabled={busy || !desktopRuntimeAvailable} title={desktopRuntimeAvailable ? undefined : "Полный импорт доступен в установленном PetroLab Desktop"}>
                  {busy ? <SpinnerGap className="spin" size={20} /> : <FileArrowUp size={20} />}
                  {busy ? "Открываю файл…" : "Выбрать файл"}
                </button>
                <small>Исходный файл не изменяется. Перед чтением PetroLab создаёт локальную временную копию.</small>
              </div>
            )}

            {sourcePath && inspection && recipe && plan && (
              <ImportWorkspace
                sourceName={fileName(sourceDisplayPath || sourcePath)}
                sourceDisplayPath={sourceDisplayPath}
                inspection={inspection}
                recipe={recipe}
                recipeWarnings={visibleRecipeWarnings}
                plan={plan}
                blockPreviews={blockPreviews}
                cleanClassification={cleanClassification}
                detailedReview={detailedReview}
                blockDraftDirty={blockDraftDirty}
                mappingDraftDirty={mappingDraftDirty}
                duplicateReviewRequired={duplicateReviewRequired}
                canSaveImport={canSaveImport}
                plannedMeasurementCount={plannedMeasurementCount}
                busy={busy}
                onOpenDetailed={openDetailedReview}
                onApplySections={applySections}
                onApplyMappings={applyMappings}
                onBlockDirtyChange={setBlockDraftDirty}
                onMappingDirtyChange={setMappingDraftDirty}
                onKeepAllDuplicates={keepAllDuplicateCandidates}
                onCommit={commitImport}
                onCancel={startNewImport}
                onChooseOther={chooseFile}
              />
            )}
          </section>
        )}

        {screen === "Анализы" && (
          <section className="live-page analyses-page">
            <div className="analysis-toolbar">
              <div className="search-box"><MagnifyingGlass size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти по Sample, Mineral, Generation, Source, значению…" /></div>
              <span>Показано {filteredAnalyses.length} из {project.total}</span>
              {project.latest_import && <button className="outline-button danger-outline" onClick={retractLatest} disabled={busy} title={`Последний импорт: ${project.latest_import.source_name}`}>Отменить последний импорт</button>}
              <button className="outline-button" onClick={() => refreshAnalyses().catch((caught) => setError(caught.message))} disabled={busy}>Обновить</button>
            </div>

            {project.total === 0 ? (
              <div className="empty-analyses"><Database size={48} weight="duotone" /><h2>В проекте пока нет анализов</h2><p>После проверенного импорта строки появятся здесь и сохранятся после перезапуска PetroLab.</p><button className="primary-button" onClick={startNewImport} disabled={busy}>Добавить данные</button></div>
            ) : (
              <div className="analysis-table-wrap">
                <table className="analysis-table">
                  <thead><tr><th>Source</th><th>Лист</th><th>Источник в файле</th>{identityColumns.map((field) => <th key={`identity-${field}`}>{field}</th>)}{metadataColumns.map((field) => <th key={`metadata-${field}`} title="Исходное значение из файла">{field} · исходное</th>)}{measurementColumns.map((field) => <th key={`measurement-${field}`}>{field}</th>)}</tr></thead>
                  <tbody>
                    {filteredAnalyses.map((analysis) => (
                      <tr key={analysis.analysis_id} title={analysis.analysis_id}>
                        <td><b>{analysis.source_name}</b></td><td>{analysis.sheet_name}</td><td>{savedAnalysisOrigin(analysis)}</td>
                        {identityColumns.map((field) => <td key={`identity-${field}`}>{analysis.identity?.[field] || ""}</td>)}
                        {metadataColumns.map((field) => <td key={`metadata-${field}`} title="Сохранено без интерпретации как исходный текст">{analysis.source_metadata?.[field] || ""}</td>)}
                        {measurementColumns.map((field) => {
                          const measurement = analysis.measurements?.[field];
                          const context = measurement?.method || measurement?.measurement_set;
                          return <td key={`measurement-${field}`}>{measurement ? <><span>{measurement.raw_token ?? "∅"}</span><small>{measurement.unit}{context ? ` · ${context}` : ""}</small></> : ""}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
