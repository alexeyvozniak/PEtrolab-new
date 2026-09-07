import { useCallback, useEffect, useState } from "react";
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
  createImportWorkspace, addWorkspaceSources, getImportWorkspace, applyWorkspaceDecision, discardImportWorkspace, previewWorkspaceWindow,
  applyMediaImportPlan,
  applyImportPlan,
  clearImportStaging,
  createMediaImportPlan,
  getProjectDatabasePath,
  inspectMediaSources,
  isPetrolabDesktop,
  listProjectAnalyses,
  listProjectMineralIdentifications,
  pickImportFile,
  pickMediaFiles,
  retractLastImport,
  stageImportFile,
} from "./desktopApi";
import { ImportWorkspace } from "./ImportWorkspace";
import { AnalysesWorkspace } from "./AnalysesWorkspace";
import { ImagesWorkspace } from "./ImagesWorkspace";
import "./styles.css";

const ANALYSES_PAGE_SIZE = 500;

const navigation = [
  [MagnifyingGlass, "Поиск", false],
  [FileArrowUp, "Импорт", true],
  [Database, "Анализы", true],
  [Columns, "Образцы", false],
  [Columns, "Минералы", false],
  [Columns, "Связи", false],
  [File, "Изображения", true],
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

function mergeStatusCounts(...counts) {
  return counts.reduce((merged, current) => {
    Object.entries(current || {}).forEach(([status, count]) => {
      merged[status] = (merged[status] || 0) + Number(count || 0);
    });
    return merged;
  }, {});
}

async function attachMineralIdentifications(path, project) {
  const review = unwrap(await listProjectMineralIdentifications(path, project.returned || project.analyses.length, project.offset || 0));
  const byId = new Map((review.identifications || []).map((item) => [item.analysis_id, item]));
  return {
    ...project,
    mineral_status_counts: review.status_counts || {},
    analyses: project.analyses.map((analysis) => ({
      ...analysis,
      mineral_verification: byId.get(analysis.analysis_id) || analysis.mineral_verification,
    })),
  };
}

export function App() {
  const desktopRuntimeAvailable = isPetrolabDesktop();
  const [screen, setScreen] = useState("Импорт");
  const [databasePath, setDatabasePath] = useState("");
  const [project, setProject] = useState({ total: 0, returned: 0, offset: 0, has_more: false, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] });
  const [workspace, setWorkspace] = useState(null);
  const [sourceIssues, setSourceIssues] = useState([]);
  const [focusedIssueKey, setFocusedIssueKey] = useState("");
  const [semanticTools, setSemanticTools] = useState({ actions: [], analytes: [] });
  const [sourcePath, setSourcePath] = useState("");
  const [sourceDisplayPath, setSourceDisplayPath] = useState("");
  const [inspection, setInspection] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [bulkUnitScopes, setBulkUnitScopes] = useState([]);
  const [bulkIgnoreScopes, setBulkIgnoreScopes] = useState([]);
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
  const [mediaInspection, setMediaInspection] = useState(null);
  const [mediaPlan, setMediaPlan] = useState(null);

  const refreshAnalyses = useCallback(async (path = databasePath) => {
    if (!path) return;
    const listed = unwrap(await listProjectAnalyses(path, ANALYSES_PAGE_SIZE, 0));
    setProject(await attachMineralIdentifications(path, listed));
  }, [databasePath]);

  const loadMoreAnalyses = useCallback(async () => {
    if (!databasePath || busy || !project.has_more) return;
    setBusy(true);
    setActivity("Загружаю следующую страницу анализов…");
    try {
      const next = unwrap(await listProjectAnalyses(databasePath, ANALYSES_PAGE_SIZE, project.analyses.length));
      const enriched = await attachMineralIdentifications(databasePath, next);
      setProject((current) => ({
        ...current,
        ...enriched,
        returned: current.analyses.length + enriched.analyses.length,
        mineral_status_counts: mergeStatusCounts(current.mineral_status_counts, enriched.mineral_status_counts),
        analyses: [...current.analyses, ...enriched.analyses],
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  }, [busy, databasePath, project.analyses.length, project.has_more]);

  useEffect(() => {
    if (!desktopRuntimeAvailable) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const path = await getProjectDatabasePath();
        if (cancelled) return;
        setDatabasePath(path);
        const result = unwrap(await listProjectAnalyses(path, ANALYSES_PAGE_SIZE, 0));
        const enriched = await attachMineralIdentifications(path, result);
        if (!cancelled) setProject(enriched);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
    return () => { cancelled = true; };
  }, [desktopRuntimeAvailable]);

  const plannedMeasurementCount = plan?.summary?.planned_measurement_count
    ?? plan?.planned_records?.reduce((total, record) => total + record.measurements.length, 0)
    ?? 0;
  // Readiness and scientific review requirements are service-owned projections.
  const duplicateReviewRequired = sourceIssues.some((issue) => issue.code === "DUPLICATE_REVIEW_REQUIRED" && issue.blocking);
  const visibleRecipeWarnings = sourceIssues;
  const unresolvedReviewCount = sourceIssues.filter((issue) => issue.blocking && ["UNIT_REQUIRES_REVIEW", "UNMAPPED_FIELD_REQUIRES_REVIEW"].includes(issue.code)).length;

  const canSaveImport = Boolean(
    plan
    && workspace?.readiness.ready_to_commit
    && !blockDraftDirty
    && !mappingDraftDirty
    && !duplicateReviewRequired,
  );


  const receiveWorkspace = async (result, detailed = false) => {
    const { session, active } = result;
    // Publish the accepted revision before preview I/O: a failed preview must
    // not leave the client using a stale revision after a successful decision.
    setWorkspace(session);
    setBlockPreviews({});
    const source = session.sources.find((item) => item.source_id === session.active_source_id);
    setSourcePath(source.staged_path);
    setSourceDisplayPath(source.original_display_path);
    setInspection(active.inspection);
    setRecipe(active.recipe);
    setSourceIssues(active.issues);
    setSemanticTools({ actions: active.semantic_actions || [], analytes: active.canonical_analytes || [], mineralScopes: active.mineral_acceptance_scopes || [], records: active.plan.planned_records || [] });
    setBulkUnitScopes(active.bulk_unit_scopes);
    setBulkIgnoreScopes(active.bulk_ignore_scopes);
    setPlan(active.plan);
    setCleanClassification(active.classification);
    setDetailedReview(detailed || session.sources.length > 1 || active.classification.mode !== "clean_table_fast");
    setBlockDraftDirty(false);
    setMappingDraftDirty(false);
    const pairs = await Promise.all(active.recipe.sections.map(async (section) => {
      const preview = unwrap(await previewWorkspaceWindow(session.workspace_id, source.source_id,
        section.sheet_name, Math.max(1, section.header_row), 12, 0, 18));
      return [section.block_id, { ...preview, workspace_id: session.workspace_id, source_id: source.source_id, source_path: source.staged_path }];
    }));
    setBlockPreviews(Object.fromEntries(pairs));
  };

  const resetImportState = () => {
    setWorkspace(null);
    setSourceIssues([]);
    setSourcePath("");
    setSourceDisplayPath("");
    setInspection(null);
    setRecipe(null);
    setPlan(null);
    setBlockPreviews({});
    setBulkUnitScopes([]);
    setBulkIgnoreScopes([]);
    setCleanClassification(null);
    setDetailedReview(false);
    setBlockDraftDirty(false);
    setMappingDraftDirty(false);
  };

  const chooseFile = async () => {
    if (busy || blockDraftDirty || mappingDraftDirty) return;
    setBusy(true);
    setActivity("Выберите файл…");
    setError("");
    setSuccess("");
    let newlyStaged = "";
    let accepted = false;
    try {
      const selectedPath = await pickImportFile();
      if (!selectedPath) return;
      setActivity("Копирую файл в рабочую область PetroLab…");
      const selected = await stageImportFile(selectedPath);
      newlyStaged = selected.local_path;
      setActivity("Проверяю, соответствует ли файл PetroLab Clean Table…");
      const sources = [{ staged_path: newlyStaged, original_display_path: selected.original_path || selectedPath }];
      const result = unwrap(await (workspace
        ? addWorkspaceSources(workspace.workspace_id, workspace.draft_revision, sources)
        : createImportWorkspace(sources, databasePath)));
      accepted = true;
      await receiveWorkspace(result);
      setScreen("Импорт");
    } catch (caught) {
      if (newlyStaged && !accepted) clearImportStaging(newlyStaged).catch(() => {});
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const decide = async (decision, sourceId = workspace?.active_source_id, bulk = false) => {
    if (busy || !workspace) return;
    setBusy(true);
    setActivity(decision.kind === "activate" ? "Открываю исходную таблицу…" : "Проверяю и сохраняю решение…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await applyWorkspaceDecision(workspace.workspace_id, workspace.draft_revision, sourceId, decision, bulk));
      await receiveWorkspace(result, true);
      if (decision.kind !== "activate") setSuccess("Решение сохранено в этой очереди. Исходный файл не изменён.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const applySections = (decisions) => decide({ kind: "sections", decisions });
  const applyMappings = (decisions) => decide({ kind: "mappings", decisions });
  const applyBulkUnit = (bulkScopeId, unit) => decide({ kind: "unit", bulk_scope_id: bulkScopeId, unit }, undefined, true);
  const applyBulkIgnore = (bulkScopeId) => decide({ kind: "ignore", bulk_scope_id: bulkScopeId }, undefined, true);
  const keepAllDuplicateCandidates = () => decide({ kind: "duplicates" });
  const openDetailedReview = () => setDetailedReview(true);
  const selectWorkspaceSource = (sourceId, blockId, issueKey = "") => {
    if (blockDraftDirty || mappingDraftDirty) return;
    setFocusedIssueKey(issueKey);
    return decide({ kind: "activate", block_id: blockId }, sourceId);
  };
  const toggleWorkspaceSource = (source) => {
    if (blockDraftDirty || mappingDraftDirty) return;
    return decide({ kind: "source_inclusion", included: !source.included,
      reason: "Исключено пользователем из текущей очереди" }, source.source_id);
  };

  const commitImport = async () => {
    if (busy || !canSaveImport || !databasePath || !workspace) return;
    setBusy(true);
    setError("");
    setActivity("Проверяю очередь перед сохранением…");
    try {
      const current = unwrap(await getImportWorkspace(workspace.workspace_id));
      if (!current.session.readiness.ready_to_commit) {
        await receiveWorkspace(current, true);
        throw new Error("Сохранение недоступно: проверьте обязательные вопросы очереди.");
      }
      const source = current.session.sources[0];
      const result = unwrap(await applyImportPlan(databasePath, source.staged_path, current.active.recipe));
      // Commit has succeeded. Never offer a second apply if refresh/cleanup fails.
      resetImportState();
      setSuccess(`Импорт сохранён: ${result.analysis_count} Analysis, ${result.measurement_count} Measurement.`);
      await discardImportWorkspace(workspace.workspace_id, current.session.draft_revision).then(unwrap);
      clearImportStaging(source.staged_path).catch(() => {});
      await refreshAnalyses(databasePath);
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

  const chooseImages = async () => {
    if (busy || !desktopRuntimeAvailable) return;
    setBusy(true);
    setActivity("Выберите изображения…");
    setError("");
    setSuccess("");
    try {
      const paths = await pickMediaFiles();
      if (!paths?.length) return;
      setActivity("Проверяю форматы, размеры и отпечатки изображений…");
      const result = unwrap(await inspectMediaSources(paths));
      setMediaInspection(result);
      setMediaPlan(null);
      setScreen("Изображения");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const planImages = async (assignments) => {
    if (busy || !databasePath) return;
    setBusy(true);
    setActivity("Проверяю назначения изображений…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await createMediaImportPlan(databasePath, assignments));
      setMediaPlan(result);
      setSuccess(`План проверен: ${result.items.length} изображений. Точки можно разместить отдельным следующим шагом.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const importImagesWithoutPoints = async (reviewedPlan) => {
    if (busy || !databasePath || !reviewedPlan) return;
    setBusy(true);
    setActivity("Повторно проверяю файлы и сохраняю изображения…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await applyMediaImportPlan(databasePath, reviewedPlan));
      setMediaInspection(null);
      setMediaPlan(null);
      setSuccess(`Импортировано изображений: ${result.created_media_asset_count + result.reused_media_asset_count}. Пространственных точек: ${result.spatial_annotation_count}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const cancelImageImport = () => {
    if (busy) return;
    setMediaInspection(null);
    setMediaPlan(null);
    setError("");
    setSuccess("");
  };


  const startNewImport = () => {
    if (busy) return;
    setScreen("Импорт");
    if (!workspace) chooseFile();
  };

  const cancelImport = async () => {
    if (busy || !workspace) return;
    if (!window.confirm("Закрыть очередь и сбросить решения по файлам? Исходники и сохранённые анализы останутся.")) return;
    setBusy(true);
    try {
      const discarded = unwrap(await discardImportWorkspace(workspace.workspace_id, workspace.draft_revision));
      resetImportState();
      await Promise.all(discarded.staged_paths.map((path) => clearImportStaging(path).catch(() => {})));
      setError("");
      setSuccess("");
    } catch (caught) {
      setError(caught.message);
    } finally { setBusy(false); }
  };

  const goTo = (label, enabled) => {
    if (!enabled || busy || blockDraftDirty || mappingDraftDirty) return;
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
              disabled={!enabled || busy || blockDraftDirty || mappingDraftDirty}
              onClick={() => goTo(label, enabled)}
              title={enabled ? label : "Экран ещё не подключён в этой alpha-сборке"}
            >
              <Icon size={19} /><span>{label}</span>{!enabled && <small>скоро</small>}
            </button>
          ))}
        </nav>
        <div className="side-footer"><Info size={18} /><span>Оживлены: таблицы, анализы и изображения</span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{screen}</h2>
            <p>Источников: <b>{project.source_count}</b> · импортов: <b>{project.import_batch_count}</b> · анализов: <b>{project.total}</b></p>
          </div>
          <div className="top-actions">
            <button className="outline-button" onClick={screen === "Изображения" ? chooseImages : startNewImport} disabled={busy || !desktopRuntimeAvailable} title={desktopRuntimeAvailable ? undefined : "Полный импорт доступен в установленном PetroLab Desktop"}><Plus size={18} /> {screen === "Изображения" ? "Добавить изображения" : "Добавить данные"}</button>
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
                key={workspace?.active_source_id}
                workspace={workspace}
                focusedIssueKey={focusedIssueKey}
                semanticTools={semanticTools}
                onSemanticDecision={(decision) => decide({ ...decision, kind: 'semantic' })}
                onVerifyMinerals={() => decide({ kind: 'verify_minerals' })}
                onAcceptMineral={(decision) => decide({ ...decision, kind: 'accept_mineral' })}
                onSelectSource={selectWorkspaceSource}
                onToggleSource={toggleWorkspaceSource}
                sourceName={fileName(sourceDisplayPath || sourcePath)}
                sourceDisplayPath={sourceDisplayPath}
                inspection={inspection}
                recipe={recipe}
                recipeWarnings={visibleRecipeWarnings}
                bulkUnitScopes={bulkUnitScopes}
                bulkIgnoreScopes={bulkIgnoreScopes}
                plan={plan}
                blockPreviews={blockPreviews}
                cleanClassification={cleanClassification}
                detailedReview={detailedReview}
                blockDraftDirty={blockDraftDirty}
                mappingDraftDirty={mappingDraftDirty}
                duplicateReviewRequired={duplicateReviewRequired}
                canSaveImport={canSaveImport}
                plannedMeasurementCount={plannedMeasurementCount}
                unresolvedReviewCount={unresolvedReviewCount}
                busy={busy}
                onOpenDetailed={openDetailedReview}
                onApplySections={applySections}
                onApplyMappings={applyMappings}
                onApplyBulkUnit={applyBulkUnit}
                onApplyBulkIgnore={applyBulkIgnore}
                onBlockDirtyChange={setBlockDraftDirty}
                onMappingDirtyChange={setMappingDraftDirty}
                onKeepAllDuplicates={keepAllDuplicateCandidates}
                onCommit={commitImport}
                onCancel={cancelImport}
                onChooseOther={chooseFile}
              />
            )}
          </section>
        )}

        {screen === "Анализы" && (
          <AnalysesWorkspace
            project={project}
            busy={busy}
            onRefresh={() => refreshAnalyses().catch((caught) => setError(caught.message))}
            onRetract={retractLatest}
            onAddData={startNewImport}
            onLoadMore={loadMoreAnalyses}
          />
        )}

        {screen === "Изображения" && (
          <ImagesWorkspace
            inspection={mediaInspection}
            plan={mediaPlan}
            busy={busy}
            onChoose={chooseImages}
            onPlan={planImages}
            onApply={importImagesWithoutPoints}
            onCancel={cancelImageImport}
            onInvalidatePlan={() => setMediaPlan(null)}
          />
        )}
      </section>
    </main>
  );
}
