import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle,
  Columns,
  Database,
  File,
  FileArrowUp,
  GearSix,
  House,
  Info,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
  Warning,
} from "@phosphor-icons/react";
import {
  createImportWorkspace, restoreImportWorkspace, addWorkspaceSources, applyWorkspaceDecision, discardImportWorkspace, previewWorkspaceWindow,
  commitImportWorkspace, listFormulaMethods, previewImportFormula,
  createWorkGroup, listWorkGroups, listGenerations, assignGeneration, undoGeneration,
  listTableViews, saveTableView,
  listEditDrafts, saveEditDraft, checkEditDraft, commitEditDraft,
  pickAnalysisExportPath, exportAnalysisSelection,
  clearImportStaging,
  getProjectDatabasePath,
  getProjectOverview, getProjectAnalysis, queryProjectAnalyses, queryProjectAnalysisIds, saveProjectWorkPlanTask,
  listProjectSamples, getProjectSample, saveSampleContext, addSampleNote,
  createSamplePoint, listPointAnalyses, setPointAnalysisLink, undoPointAnalysisLink, createManualPointAnalysis,
  pickMediaFiles, pickMediaExportPath, inspectMediaFiles, previewMediaFile, draftMediaImport, commitMediaImport,
  pickMediaFolder, inspectMediaFolder, loadMediaImportDraft, saveMediaImportDraft,
  createMediaRegion, listMediaLinks, setMediaLink, importLinkedPhoto,
  previewProjectMedia, exportMediaOriginal, exportMediaRendered, exportMediaBatch,
  reviewStatistics, runClustering, listCalculationRuns, openCalculationRun, saveCalculatedCluster,
  getPublicationCatalog, pickPublicationFigure, pickPublicationExportPath, preparePublication, exportPublication, capturePublicationPlot,
  capturePublicationTable, capturePublicationMedia,
  getPlotCatalog, getPlotData, recordPlotVisibility, undoPlotVisibility,
  listPlotSpecifications, openPlotSpecification, savePlotSpecification, pickPlotExportPath, exportPlot,
  isPetrolabDesktop,
  listProjectAnalyses,
  listProjectMineralIdentifications,
  pickImportFile,
  retractLastImport,
  stageImportFile,
} from "./desktopApi";
import { ImportWorkspace } from "./ImportWorkspace";
import { AnalysesWorkspace } from "./AnalysesWorkspace";
import { ProjectOverview, ProjectSearch } from "./ProjectNavigation";
import { PlotWorkspace } from "./PlotWorkspace";
import { SampleWorkspace } from "./SampleWorkspace";
import { MediaImport } from "./MediaWorkspace";
import { StatisticsWorkspace } from "./StatisticsWorkspace";
import { PublicationWorkspace } from "./PublicationWorkspace";
import "./styles.css";

const ANALYSES_PAGE_SIZE = 500;

const navigation = [
  [House, "Обзор", true],
  [MagnifyingGlass, "Поиск", true],
  [FileArrowUp, "Импорт", true],
  [Database, "Анализы", true],
  [Columns, "Образцы", true],
  [Columns, "Минералы", false],
  [Columns, "Связи", true],
  [File, "Изображения", true],
  [Columns, "Построение", true],
  [Columns, "Статистика", true],
  [Columns, "Публикации", true],
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
  if (!project.analyses.length) return { ...project, mineral_status_counts: {} };
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

const previewMediaSource = async (path, region, fingerprint) => unwrap(await previewMediaFile(path, region, fingerprint));

export function App() {
  const desktopRuntimeAvailable = isPetrolabDesktop();
  const [screen, setScreen] = useState("Обзор");
  const [databasePath, setDatabasePath] = useState("");
  const [project, setProject] = useState({ total: 0, returned: 0, offset: 0, has_more: false, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] });
  const [selectedAnalysisIds, setSelectedAnalysisIds] = useState([]);
  const [navigationAnalysis, setNavigationAnalysis] = useState(null);
  const [navigationDraftId, setNavigationDraftId] = useState("");
  const [navigationSampleId, setNavigationSampleId] = useState("");
  const [searchSeed, setSearchSeed] = useState(null);
  const [pointLinkScope, setPointLinkScope] = useState(null);
  const [publicationItems, setPublicationItems] = useState([]);
  const [publicationName, setPublicationName] = useState("");
  const [publicationSettings, setPublicationSettings] = useState({ profile: "neutral", width: 90 });
  const [plotInputIds, setPlotInputIds] = useState(null);
  const [hiddenSourceIds, setHiddenSourceIds] = useState([]);
  const [hiddenAnalysisIds, setHiddenAnalysisIds] = useState([]);
  const [visibilitySessionId, setVisibilitySessionId] = useState(() => crypto.randomUUID());
  const [visibilityOperation, setVisibilityOperation] = useState(null);
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

  const refreshAnalyses = useCallback(async (path = databasePath) => {
    if (!path) return;
    const listed = unwrap(await listProjectAnalyses(path, ANALYSES_PAGE_SIZE, 0));
    setProject(await attachMineralIdentifications(path, listed));
    setNavigationAnalysis(null);
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


  const receiveWorkspace = useCallback(async (result, detailed = false) => {
    const { session, active } = result;
    // Publish the accepted revision before preview I/O: a failed preview must
    // not leave the client using a stale revision after a successful decision.
    setWorkspace({ ...session, duplicate_comparison: result.duplicate_comparison });
    setBlockPreviews({});
    const source = session.sources.find((item) => item.source_id === session.active_source_id);
    setSourcePath(source.staged_path);
    setSourceDisplayPath(source.original_display_path);
    setInspection(active.inspection);
    setRecipe(active.recipe);
    setSourceIssues(active.issues);
    setSemanticTools({ actions: active.semantic_actions || [], analytes: active.canonical_analytes || [], mineralScopes: active.mineral_acceptance_scopes || [], records: active.plan.planned_records || [], samples: active.project_samples });
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
  }, []);

  useEffect(() => {
    if (!desktopRuntimeAvailable) return undefined;
    let cancelled = false;
    setBusy(true);
    (async () => {
      try {
        const path = await getProjectDatabasePath();
        if (cancelled) return;
        setDatabasePath(path);
        const result = unwrap(await listProjectAnalyses(path, ANALYSES_PAGE_SIZE, 0));
        if (cancelled) return;
        const enriched = await attachMineralIdentifications(path, result);
        if (cancelled) return;
        setProject(enriched);
        const restored = unwrap(await restoreImportWorkspace(path));
        if (!cancelled && restored.workspace) {
          setScreen("Импорт");
          await receiveWorkspace(restored.workspace);
          if (!cancelled) setSuccess("Черновик импорта восстановлен.");
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => { cancelled = true; };
  }, [desktopRuntimeAvailable, receiveWorkspace]);

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
      const result = unwrap(await commitImportWorkspace(workspace.workspace_id, workspace.draft_revision));
      // Commit has succeeded. Never offer a second apply if refresh/cleanup fails.
      resetImportState();
      setSuccess(`Импорт сохранён: ${result.analysis_count} Analysis, ${result.measurement_count} Measurement.`);
      await Promise.all(result.staged_paths.map((path) => clearImportStaging(path).catch(() => {})));
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
    if (label === "Построение") {
      openPlots();
      return;
    }
    if (label === "Поиск") setSearchSeed(null);
    if (label === "Образцы") setNavigationSampleId("");
    setScreen(label);
  };
  const openPlots = (ids = selectedAnalysisIds) => {
    if (busy || !databasePath) return;
    setPlotInputIds(ids.length ? [...ids] : null);
    setScreen("Построение");
  };
  const togglePlotSource = (id) => {
    setHiddenSourceIds((current) => current.includes(id)
      ? current.filter((value) => value !== id)
      : [...current, id]);
  };
  const loadPlotCatalog = useCallback(async () => unwrap(await getPlotCatalog(databasePath, plotInputIds)), [databasePath, plotInputIds]);
  const loadPlotSelection = useCallback(async (analysisIds, offset, limit) =>
    unwrap(await queryProjectAnalyses(databasePath, { analysis_ids: analysisIds, offset, limit })), [databasePath]);
  const loadPlotLayouts = useCallback(async () => unwrap(await listPlotSpecifications(databasePath)), [databasePath]);
  const restorePlotLayout = async (id) => {
    const layout = unwrap(await openPlotSpecification(databasePath, id));
    setPlotInputIds(layout.input.analysis_ids);
    const scope = new Set(layout.input.analysis_ids);
    const sources = new Set(layout.legend.entries.map(({ value }) => value));
    setHiddenAnalysisIds((current) => [...current.filter((analysisId) => !scope.has(analysisId)), ...layout.hidden_analysis_ids]);
    setVisibilityOperation(null);
    setVisibilitySessionId(crypto.randomUUID());
    setHiddenSourceIds((current) => [...current.filter((sourceId) => !sources.has(sourceId)), ...layout.hidden_source_ids]);
    return layout;
  };
  const loadPlotData = useCallback(async (kind, axes, layers, normalization) =>
    unwrap(await getPlotData(databasePath, plotInputIds, kind, axes, hiddenAnalysisIds, hiddenSourceIds, layers, normalization)),
  [databasePath, plotInputIds, hiddenAnalysisIds, hiddenSourceIds]);
  const applyVisibilityEntry = ({ parameters: { analysis_ids: ids, hidden } }) => {
    const scope = new Set(ids);
    setHiddenAnalysisIds((current) => hidden ? [...new Set([...current, ...ids])] : current.filter((id) => !scope.has(id)));
  };
  const setPlotVisibility = async (ids, hidden) => {
    if (busy || !databasePath) return;
    const changed = ids.filter((id) => hidden !== hiddenAnalysisIds.includes(id));
    if (!changed.length) return;
    setBusy(true);
    setError("");
    try {
      const entry = unwrap(await recordPlotVisibility(databasePath, changed, hidden, visibilitySessionId));
      applyVisibilityEntry(entry);
      setVisibilityOperation(entry);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  };
  const undoVisibility = async () => {
    if (busy || !databasePath || !visibilityOperation) return;
    setBusy(true);
    setError("");
    try {
      const entry = unwrap(await undoPlotVisibility(databasePath, visibilityOperation.id, visibilitySessionId, hiddenAnalysisIds));
      applyVisibilityEntry(entry);
      setVisibilityOperation(null);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  };

  const loadOverview = useCallback(async () => databasePath ? unwrap(await getProjectOverview(databasePath)) : null, [databasePath]);
  const loadStatisticsGroups = useCallback(async () => databasePath ? unwrap(await listWorkGroups(databasePath)) : { groups: [] }, [databasePath]);
  const loadStatisticsRuns = useCallback(async () => databasePath ? unwrap(await listCalculationRuns(databasePath)) : [], [databasePath]);
  const loadPublication = useCallback(async () => databasePath ? unwrap(await getPublicationCatalog(databasePath))
    : { groups: [], layouts: [], runs: [] }, [databasePath]);
  const loadSamples = useCallback(async () => databasePath ? unwrap(await listProjectSamples(databasePath)) : [], [databasePath]);
  const loadSample = useCallback(async (id) => unwrap(await getProjectSample(databasePath, id)), [databasePath]);
  const loadPointAnalyses = useCallback(async (id) => unwrap(await listPointAnalyses(databasePath, id)), [databasePath]);
  const loadMediaLinks = useCallback(async (id) => unwrap(await listMediaLinks(databasePath, id)), [databasePath]);
  const loadMediaDraft = useCallback(async () => unwrap(await loadMediaImportDraft(databasePath)), [databasePath]);
  const queryProject = useCallback(async (query) => databasePath
    ? unwrap(await queryProjectAnalyses(databasePath, query)) : { analyses: [], total: 0, has_more: false }, [databasePath]);
  const saveWorkGroup = async (metadata) => unwrap(await createWorkGroup(databasePath, metadata));
  const generationActions = {
    list: async () => unwrap(await listGenerations(databasePath)),
    assign: async (value) => {
      const entry = unwrap(await assignGeneration(databasePath, value));
      await refreshAnalyses().catch((caught) => setError(caught.message));
      return entry;
    },
    undo: async (id, actor) => {
      unwrap(await undoGeneration(databasePath, id, actor));
      await refreshAnalyses().catch((caught) => setError(caught.message));
    },
  };
  const openSearchSource = (source) => {
    setSearchSeed({ source: source.source_name, source_id: source.source_id });
    setScreen("Поиск");
  };
  const openSampleAnalyses = (sample, source) => {
    setSearchSeed({ sample_id: sample.sample_id, sample_label: sample.sample_name,
      ...(source ? { source: source.source_name, source_id: source.source_id } : {}) });
    setScreen("Поиск");
  };
  const openSearchSample = (sampleId) => {
    setError("");
    setNavigationSampleId(sampleId);
    setScreen("Образцы");
  };
  const openSearchAnalysis = async (id, editDraft = false) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const analysis = unwrap(await getProjectAnalysis(databasePath, id));
      setNavigationAnalysis(analysis);
      setNavigationDraftId(editDraft ? id : "");
      setScreen("Анализы");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (screen !== "Связи") setPointLinkScope(null);
    if (screen !== "Анализы") setNavigationDraftId("");
  }, [screen]);

  const beginSearchPointLink = async (analysisIds) => {
    setBusy(true);
    setError("");
    try {
      const first = unwrap(await getProjectAnalysis(databasePath, analysisIds[0]));
      const sampleId = first.sample_association?.sample_id;
      if (!sampleId) throw new Error("Для массовой привязки отметьте анализы одного физического образца.");
      const sampleScope = unwrap(await queryProjectAnalysisIds(databasePath, { sample_id: sampleId }));
      const activeIds = new Set(sampleScope.analysis_ids);
      if (!analysisIds.every((id) => activeIds.has(id))) {
        throw new Error("Отмеченные анализы должны быть доступны и относиться к одному физическому образцу.");
      }
      setPointLinkScope({ sampleId, analysisIds: [...analysisIds] });
      setScreen("Связи");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  };
  const openOverviewGroup = async (id) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const { groups } = unwrap(await listWorkGroups(databasePath));
      const entry = groups.find(({ group }) => group.id === id);
      if (!entry) throw new Error("Рабочая группа недоступна.");
      const unavailable = new Set(entry.unavailable_analysis_ids);
      setSelectedAnalysisIds(entry.group.analysis_ids.filter((analysisId) => !unavailable.has(analysisId)));
      setNavigationAnalysis(null);
      setSuccess(`Открыта группа «${entry.group.name}»${unavailable.size ? ` · недоступно: ${unavailable.size}` : ""}.`);
      setScreen("Анализы");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  };

  const exportSelection = async (format) => {
    if (busy || !databasePath || !selectedAnalysisIds.length) return;
    const ids = [...selectedAnalysisIds];
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const destination = await pickAnalysisExportPath(format);
      if (!destination) return;
      setActivity(`Выгружаю отбор в ${format.toUpperCase()}…`);
      const result = unwrap(await exportAnalysisSelection(databasePath, ids, destination, format));
      setSuccess(`Экспортировано анализов: ${result.analysis_count}. ${result.output_path}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const addPublicationItem = async (capture, label, format) => {
    if (publicationItems.length >= 24) throw new Error("В пакете уже 24 материала.");
    const item = unwrap(await capture());
    setPublicationItems((current) => current.some(({ id }) => id === item.id) ? current : [...current, {
      ...item, draft_id: crypto.randomUUID(), label, format,
    }]);
    setScreen("Публикации");
  };

  const publishSelection = async () => {
    if (busy || !databasePath || !selectedAnalysisIds.length) return;
    setBusy(true);
    setError("");
    try {
      await addPublicationItem(() => capturePublicationTable(databasePath, selectedAnalysisIds), "Таблица отбора · XLSX");
    } catch (caught) {
      setError(caught.message || String(caught));
    } finally {
      setBusy(false);
    }
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
        <div className="side-footer"><Info size={18} /><span>Локальный проект</span></div>
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

        {screen === "Обзор" && <ProjectOverview load={loadOverview} project={project} workspace={workspace}
          onSaveTask={async (task) => unwrap(await saveProjectWorkPlanTask(databasePath, task))}
          selectionCount={selectedAnalysisIds.length} busy={busy} canImport={desktopRuntimeAvailable} onImport={startNewImport}
          onResume={() => setScreen("Импорт")} onSource={openSearchSource} onGroup={openOverviewGroup} />}
        {screen === "Поиск" && <ProjectSearch seed={searchSeed} queryProject={queryProject} onOpenAnalysis={openSearchAnalysis}
          onEditAnalysis={(id) => openSearchAnalysis(id, true)}
          onOpenSample={openSearchSample}
          queryAnalysisIds={async (query) => unwrap(await queryProjectAnalysisIds(databasePath, query))}
          selectionCount={selectedAnalysisIds.length} busy={busy}
          hiddenAnalysisIds={hiddenAnalysisIds} onSetVisibility={setPlotVisibility}
          hiddenSourceIds={hiddenSourceIds} onToggleSource={togglePlotSource}
          onUndoVisibility={visibilityOperation ? undoVisibility : null}
          onCreateWorkGroup={saveWorkGroup} generationActions={generationActions}
          onBeginPointLink={beginSearchPointLink}
          onPlot={openPlots}
          onAddSelection={(ids) => setSelectedAnalysisIds((current) => [...new Set([...current, ...ids])])} />}
        {["Образцы", "Связи", "Изображения"].includes(screen) && <SampleWorkspace key={screen} loadSamples={loadSamples} loadSample={loadSample}
          initialTab={screen === "Связи" ? "Точки" : screen === "Изображения" ? "Изображения" : "Обзор"}
          initialSampleId={screen === "Образцы" ? navigationSampleId : pointLinkScope?.sampleId}
          pointLinkScope={pointLinkScope} onClearPointLinkScope={() => setPointLinkScope(null)}
          saveContext={async (id, context, revision) => unwrap(await saveSampleContext(databasePath, id, context, revision))}
          addNote={async (id, author, body) => unwrap(await addSampleNote(databasePath, id, author, body))}
          onImportMedia={databasePath && desktopRuntimeAvailable ? () => setScreen("Импорт изображений") : undefined}
          previewMedia={async (id, region) => unwrap(await previewProjectMedia(databasePath, id, region))}
          mediaLinks={{
            createRegion: async (id, geometry) => unwrap(await createMediaRegion(databasePath, id, geometry)),
            list: loadMediaLinks,
            change: async (id, asset, attached) => unwrap(await setMediaLink(databasePath, id, asset, attached)),
            importPhoto: async (id, photo, type) => unwrap(await importLinkedPhoto(databasePath, id, photo, type)),
            pick: desktopRuntimeAvailable ? pickMediaFiles : undefined,
            previewInput: async (path) => unwrap(await previewMediaFile(path)),
          }}
          exportOriginal={async (image) => {
            const destination = await pickMediaExportPath(image.display_name);
            return destination ? unwrap(await exportMediaOriginal(databasePath, image.media_asset_id, destination)) : null;
          }}
          exportRendered={async (image, options) => {
            const base = image.display_name.replace(/\.[^.]+$/, "");
            const destination = await pickMediaExportPath(`${base}-annotated.png`);
            return destination ? unwrap(await exportMediaRendered(databasePath, image.media_asset_id, destination, options)) : null;
          }}
          exportBatch={async (ids, options) => {
            const destination = await pickMediaExportPath("PetroLab-images.zip");
            return destination ? unwrap(await exportMediaBatch(databasePath, ids, destination, options)) : null;
          }}
          addPublication={(image, options) => addPublicationItem(
            () => capturePublicationMedia(databasePath, image.media_asset_id, options),
            options ? `${image.display_name} · с разметкой` : image.display_name,
          )}
          pointLinks={{
            loadPoint: loadPointAnalyses,
            queryProject,
            createManualAnalysis: async (id, entry) => unwrap(await createManualPointAnalysis(databasePath, id, entry)),
            createPoint: async (fields) => unwrap(await createSamplePoint(databasePath, fields)),
            changeLink: async (pointId, analysisId, type, actor) => unwrap(await setPointAnalysisLink(databasePath, pointId, analysisId, type, actor)),
            undoLink: async (operationId, actor) => unwrap(await undoPointAnalysisLink(databasePath, operationId, actor)),
            selectedIds: selectedAnalysisIds,
            addToSelection: (id) => setSelectedAnalysisIds((current) => current.includes(id) ? current : [...current, id]),
            openAnalysis: openSearchAnalysis,
          }}
          onOpenAnalyses={openSampleAnalyses} busy={busy} />}
        {screen === "Импорт изображений" && <MediaImport actions={{
          pick: pickMediaFiles, samples: loadSamples, sample: loadSample,
          pickFolder: pickMediaFolder, inspectFolder: async (path) => unwrap(await inspectMediaFolder(path)),
          loadDraft: loadMediaDraft, saveDraft: async (plan, prior) => unwrap(await saveMediaImportDraft(databasePath, plan, prior)),
          inspect: async (paths) => unwrap(await inspectMediaFiles(paths)),
          preview: previewMediaSource,
          plan: async (assignments) => unwrap(await draftMediaImport(databasePath, assignments)),
          commit: async (plan, draftFingerprint) => unwrap(await commitMediaImport(databasePath, plan, draftFingerprint)),
        }} onCancel={() => setScreen("Изображения")} onDone={(result) => {
          const photoLinks = result.media_link_ids?.length || 0;
          setSuccess(`Изображений импортировано: ${result.created_media_asset_count}. Привязок: ${result.spatial_annotation_count}.`
            + (photoLinks ? ` Связей фото: ${photoLinks}.` : ""));
          setScreen("Изображения");
        }} />}
        {screen === "Статистика" && <StatisticsWorkspace selectedIds={selectedAnalysisIds}
          loadGroups={loadStatisticsGroups} loadRuns={loadStatisticsRuns}
          loadCatalog={async (ids) => unwrap(await getPlotCatalog(databasePath, ids))}
          reviewInput={async (input, features) => unwrap(await reviewStatistics(databasePath, input, features))}
          runClustering={async (review, parameters) => unwrap(await runClustering(databasePath, review, parameters))}
          openRun={async (id) => unwrap(await openCalculationRun(databasePath, id))}
          onPublishRun={(run) => {
            setPublicationItems((current) => {
              if (current.length >= 24 || current.some((item) => item.kind === "calculation_run" && item.id === run.id)) return current;
              return [...current, { draft_id: crypto.randomUUID(), kind: "calculation_run", id: run.id, label: "K-means", caption: "" }];
            });
            setScreen("Публикации");
          }}
          saveGroup={async (runId, cluster, name, actor) => unwrap(await saveCalculatedCluster(databasePath, runId, cluster, name, actor))} />}
        {screen === "Публикации" && <PublicationWorkspace load={loadPublication} items={publicationItems} setItems={setPublicationItems}
          name={publicationName} setName={setPublicationName} pickFigure={pickPublicationFigure}
          settings={publicationSettings} setSettings={setPublicationSettings}
          check={async (name, items, settings) => unwrap(await preparePublication(databasePath, name, items, settings))}
          exportZip={async (name, items, fingerprint, settings) => {
            const destination = await pickPublicationExportPath();
            return destination ? unwrap(await exportPublication(databasePath, name, items, fingerprint, destination, settings)) : null;
          }} />}
        {screen === "Построение" && <PlotWorkspace loadCatalog={loadPlotCatalog} loadData={loadPlotData} inputIds={plotInputIds}
          loadSelection={loadPlotSelection}
          loadLayouts={loadPlotLayouts} saveLayout={async (layout) => unwrap(await savePlotSpecification(databasePath, layout))}
          openLayout={restorePlotLayout} onExport={async (svg, options) => {
            const destination = await pickPlotExportPath(options.name);
            return destination ? unwrap(await exportPlot(svg, options, destination)).output_path : null;
          }}
          onAddPublication={(capture, caption) => addPublicationItem(
            () => capturePublicationPlot(databasePath, capture, caption), `${capture.name}.${capture.format}`, capture.format,
          )}
          selectedIds={selectedAnalysisIds} setSelectedIds={setSelectedAnalysisIds} onBack={() => setScreen("Анализы")}
          hiddenAnalysisIds={hiddenAnalysisIds} hiddenSourceIds={hiddenSourceIds} busy={busy}
          onSetVisibility={setPlotVisibility}
          onUndoVisibility={visibilityOperation ? undoVisibility : null}
          onToggleSource={togglePlotSource} />}
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
                semanticTools={{ ...semanticTools, onAssignSample: (decision) => decide({ ...decision, kind: "sample_assignment" }) }}
                onSemanticDecision={(decision) => decide({ ...decision, kind: 'semantic' })}
                onVerifyMinerals={() => decide({ kind: 'verify_minerals' })}
                onAcceptMineral={(decision) => decide({ ...decision, kind: 'accept_mineral' })}
                onListFormulaMethods={async () => unwrap(await listFormulaMethods())}
                onPreviewFormula={async (previewId, methodId) => unwrap(await previewImportFormula(workspace, previewId, methodId))}
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
                onKeepAllWorkspaceDuplicates={() => decide({
                  kind: "workspace_duplicates", fingerprint: workspace.duplicate_comparison.fingerprint,
                })}
                onCommit={commitImport}
                onCancel={cancelImport}
                onChooseOther={chooseFile}
              />
            )}
          </section>
        )}

        {screen === "Анализы" && (
          <AnalysesWorkspace
            project={navigationAnalysis && !project.analyses.some((item) => item.analysis_id === navigationAnalysis.analysis_id)
              ? { ...project, analyses: [...project.analyses, navigationAnalysis] } : project}
            initialFocusedId={navigationAnalysis?.analysis_id}
            initialDraftId={navigationDraftId}
            selectedIds={selectedAnalysisIds}
            setSelectedIds={setSelectedAnalysisIds}
            onListWorkGroups={async () => unwrap(await listWorkGroups(databasePath))}
            onCreateWorkGroup={saveWorkGroup}
            generationActions={generationActions}
            onExportSelection={exportSelection}
            onPublishSelection={publishSelection}
            onOpenPlots={() => openPlots()}
            hiddenPlotAnalysisIds={hiddenAnalysisIds}
            onSetPlotVisibility={setPlotVisibility}
            onUndoPlotVisibility={visibilityOperation ? undoVisibility : null}
            onListTableViews={async () => unwrap(await listTableViews(databasePath))}
            onSaveTableView={async (view) => unwrap(await saveTableView(databasePath, view))}
            editDraftActions={{
              list: async (id) => unwrap(await listEditDrafts(databasePath, id)),
              save: async (id, value) => unwrap(await saveEditDraft(databasePath, id, value)),
              check: async (id) => unwrap(await checkEditDraft(databasePath, id)),
              commit: async (id, actor, reason) => unwrap(await commitEditDraft(databasePath, id, actor, reason)),
            }}
            busy={busy}
            onRefresh={() => refreshAnalyses().catch((caught) => setError(caught.message))}
            onRetract={retractLatest}
            onAddData={startNewImport}
            onLoadMore={loadMoreAnalyses}
          />
        )}
      </section>
    </main>
  );
}
