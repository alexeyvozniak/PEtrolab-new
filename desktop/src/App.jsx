import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle,
  Columns,
  Database,
  File,
  FileArrowUp,
  FolderOpen,
  GearSix,
  Info,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
  Warning,
} from "@phosphor-icons/react";
import {
  addAnalysisToAnalyticalPoint,
  createImportWorkspace, addWorkspaceSources, getImportWorkspace, applyWorkspaceDecision, discardImportWorkspace, previewWorkspaceWindow,
  createAnalyticalPoint,
  applyMediaImportPlan,
  applyImportPlan,
  clearImportStaging,
  decideProjectMineralAssignment,
  createMediaImportPlan,
  getMediaPreview,
  getProjectDatabasePath,
  inspectMediaSources,
  isPetrolabDesktop,
  listProjectAnalyses,
  listAnalyticalPoints,
  listOperationJournal,
  listProjectMineralIdentifications,
  pickImportFile,
  pickMediaFolder,
  pickMediaFiles,
  retractLastImport,
  removeAnalysisFromAnalyticalPoint,
  removeSpatialAnnotationFromAnalyticalPoint,
  retireAnalyticalPoint,
  stageImportFile,
  undoOperation,
} from "./desktopApi";
import { ImportWorkspace } from "./ImportWorkspace";
import { AnalysesWorkspace } from "./AnalysesWorkspace";
import { MineralsWorkspace } from "./MineralsWorkspace";
import { ImagesWorkspace } from "./ImagesWorkspace";
import "./styles.css";

const ANALYSES_PAGE_SIZE = 500;

const navigation = [
  [MagnifyingGlass, "Поиск", false],
  [FileArrowUp, "Импорт", true],
  [Database, "Анализы", true],
  [Columns, "Образцы", false],
  [Columns, "Минералы", true],
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

function mergeAnalysesById(current, additions) {
  const byId = new Map((current || []).map((analysis) => [analysis.analysis_id, analysis]));
  (additions || []).forEach((analysis) => byId.set(analysis.analysis_id, analysis));
  return [...byId.values()];
}

async function attachMineralIdentifications(path, project) {
  const review = unwrap(await listProjectMineralIdentifications(path, project.returned || project.analyses.length, project.offset || 0));
  const byId = new Map((review.identifications || []).map((item) => [item.analysis_id, item]));
  return {
    ...project,
    mineral_status_counts: review.status_counts || {},
    mineral_options: review.mineral_options || [],
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
  const [bulkUnitOverrideScopes, setBulkUnitOverrideScopes] = useState([]);
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
  const [mediaPoints, setMediaPoints] = useState({ total: 0, sample_names: [], items: [] });
  const [operationJournal, setOperationJournal] = useState({ total: 0, items: [] });
  const [pointOperationNotice, setPointOperationNotice] = useState(null);

  const loadMediaPreview = useCallback(async (sourcePathValue) => (
    unwrap(await getMediaPreview(sourcePathValue))
  ), []);

  const refreshAnalyses = useCallback(async (path = databasePath) => {
    if (!path) return;
    const listed = unwrap(await listProjectAnalyses(path, ANALYSES_PAGE_SIZE, 0));
    setProject(await attachMineralIdentifications(path, listed));
  }, [databasePath]);

  const refreshAnalyticalPoints = useCallback(async (path = databasePath) => {
    if (!path) return;
    try {
      const [pointProjection, journal] = await Promise.all([
        listAnalyticalPoints(path).then(unwrap),
        listOperationJournal(path).then(unwrap),
      ]);
      setMediaPoints(pointProjection);
      setOperationJournal(journal);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [databasePath]);

  const loadMoreAnalyses = useCallback(async () => {
    if (!databasePath || busy || !project.has_more) return;
    setBusy(true);
    setActivity("Загружаю следующую страницу анализов…");
    try {
      const next = unwrap(await listProjectAnalyses(databasePath, ANALYSES_PAGE_SIZE, project.returned));
      const enriched = await attachMineralIdentifications(databasePath, next);
      setProject((current) => ({
        ...current,
        ...enriched,
        returned: current.returned + enriched.returned,
        mineral_status_counts: mergeStatusCounts(current.mineral_status_counts, enriched.mineral_status_counts),
        analyses: [...current.analyses, ...enriched.analyses],
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  }, [busy, databasePath, project.returned, project.has_more]);

  const loadSourceAnalyses = useCallback(async (analysisIds) => {
    if (busy || !databasePath || !Array.isArray(analysisIds) || !analysisIds.length) return [];
    setBusy(true);
    setActivity("Загружаю выбранные исходные Analyses…");
    setError("");
    try {
      const exact = unwrap(await listProjectAnalyses(databasePath, analysisIds.length, 0, analysisIds));
      setProject((current) => ({ ...current, analyses: mergeAnalysesById(current.analyses, exact.analyses) }));
      return exact.analyses;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setActivity("");
      setBusy(false);
    }
  }, [busy, databasePath]);

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
        try {
          const [pointProjection, journal] = await Promise.all([
            listAnalyticalPoints(path).then(unwrap),
            listOperationJournal(path).then(unwrap),
          ]);
          if (!cancelled) {
            setMediaPoints(pointProjection);
            setOperationJournal(journal);
          }
        } catch (caught) {
          if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
        }
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
    setBulkUnitOverrideScopes(active.bulk_unit_override_scopes || []);
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
    setBulkUnitOverrideScopes([]);
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
      if (decision.kind !== "activate") setSuccess("Решение сохранено.");
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return false;
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const applySections = (decisions) => decide({ kind: "sections", decisions });
  const applyMappings = (decisions) => decide({ kind: "mappings", decisions });
  const applyBulkUnit = (bulkScopeId, unit) => decide({ kind: "unit", bulk_scope_id: bulkScopeId, unit }, undefined, true);
  const applyBulkUnitOverride = (bulkScopeId, unit) => decide({ kind: "unit_override", bulk_scope_id: bulkScopeId, unit }, undefined, true);
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

  const decideMineral = async (analysis, target, reason) => {
    if (busy || !databasePath || !analysis?.mineral_verification) return;
    setBusy(true);
    setActivity(target ? "Сохраняю решение по минералу…" : "Возвращаю анализ в очередь проверки…");
    setError("");
    setSuccess("");
    try {
      await decideProjectMineralAssignment(
        databasePath,
        analysis.analysis_id,
        analysis.mineral_verification,
        target,
        reason,
      ).then(unwrap);
      await refreshAnalyses(databasePath);
      setSuccess(target
        ? `Решение сохранено отдельно от исходных данных: ${target}.`
        : "Решение сброшено. Анализ снова требует проверки.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const inspectImageBatch = async (newPaths) => {
    const existingPaths = (mediaInspection?.items || []).map((item) => item.source_path);
    const paths = [...new Set([...existingPaths, ...newPaths])];
    setActivity("Проверяю форматы, размеры и отпечатки изображений…");
    const [result, pointProjection] = await Promise.all([
      inspectMediaSources(paths).then(unwrap),
      listAnalyticalPoints(databasePath).then(unwrap),
    ]);
    setMediaInspection(result);
    setMediaPoints(pointProjection);
    setMediaPlan(null);
    setScreen("Изображения");
  };

  const createPointFromAnalyses = async ({ sampleName, pointName, analysisIds, linkType }) => {
    if (busy || !databasePath) return null;
    setBusy(true);
    setActivity("Создаю Analytical Point и сохраняю явные связи…");
    setError("");
    setSuccess("");
    try {
      const created = unwrap(await createAnalyticalPoint(databasePath, sampleName, pointName, analysisIds, linkType));
      let projectionRefreshed = true;
      try {
        const [pointProjection, journal] = await Promise.all([
          listAnalyticalPoints(databasePath).then(unwrap),
          listOperationJournal(databasePath).then(unwrap),
        ]);
        setMediaPoints(pointProjection);
        setOperationJournal(journal);
      } catch (caught) {
        projectionRefreshed = false;
        const detail = caught instanceof Error ? caught.message : String(caught);
        setError(`Analytical Point создана, но обновить список точек не удалось: ${detail}`);
      }
      if (created.operation) {
        setPointOperationNotice({
          operation: created.operation,
          message: `Analytical Point «${created.point_name}» создана из ${created.analysis_ids.length} Analyses.`,
        });
      }
      setSuccess(`Analytical Point «${created.point_name}» создана из ${created.analysis_ids.length} Analyses. Исходные измерения не изменены.`);
      if (mediaInspection && projectionRefreshed) setScreen("Изображения");
      return { ...created, projection_refreshed: projectionRefreshed };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const retirePoint = async (point, reason) => {
    if (busy || !databasePath) return null;
    setBusy(true);
    setActivity("Снимаю связь Analytical Point и записываю операцию…");
    setError("");
    setSuccess("");
    try {
      const retired = unwrap(await retireAnalyticalPoint(databasePath, point, reason));
      setPointOperationNotice({
        operation: retired.operation,
        message: `Связь Analytical Point «${retired.point_name}» снята.`,
      });
      setMediaPoints((current) => {
        const items = (current.items || []).filter((item) => item.analytical_point_id !== retired.analytical_point_id);
        return { ...current, total: items.length, sample_names: [...new Set(items.map((item) => item.sample_name))].sort((left, right) => left.localeCompare(right, "ru")), items };
      });
      setSuccess(`Связь «${retired.point_name}» снята обратимо. Analyses, Measurements, Source и Media Asset сохранены.`);
      let projectionRefreshed = true;
      try {
        const [pointProjection, journal] = await Promise.all([
          listAnalyticalPoints(databasePath).then(unwrap),
          listOperationJournal(databasePath).then(unwrap),
        ]);
        setMediaPoints(pointProjection);
        setOperationJournal(journal);
      } catch (caught) {
        projectionRefreshed = false;
        const detail = caught instanceof Error ? caught.message : String(caught);
        setError(`Связь снята, но обновить реестр не удалось: ${detail}`);
      }
      return { ...retired, projection_refreshed: projectionRefreshed };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const changePointMembership = async ({ point, action, analysisId, linkType, reason }) => {
    if (busy || !databasePath) return null;
    setBusy(true);
    setActivity(action === "add" ? "Добавляю Analysis и записываю обратимую операцию…" : "Снимаю Analysis и записываю обратимую операцию…");
    setError("");
    setSuccess("");
    try {
      const changed = unwrap(await (action === "add"
        ? addAnalysisToAnalyticalPoint(databasePath, point, analysisId, linkType, reason)
        : removeAnalysisFromAnalyticalPoint(databasePath, point, analysisId, reason)));
      const verb = action === "add" ? "добавлена в" : "снята с";
      setPointOperationNotice({
        operation: changed.operation,
        message: `Analysis ${verb} Analytical Point «${point.point_name}».`,
      });
      setMediaPoints((current) => ({
        ...current,
        items: (current.items || []).map((item) => item.analytical_point_id === point.analytical_point_id
          ? { ...item, analysis_ids: changed.analysis_ids }
          : item),
      }));
      setSuccess(`Состав «${point.point_name}» изменён обратимо: теперь ${changed.analysis_ids.length} Analyses. Analysis, Measurements и Source сохранены.`);
      let projectionRefreshed = true;
      try {
        const [pointProjection, journal] = await Promise.all([
          listAnalyticalPoints(databasePath).then(unwrap),
          listOperationJournal(databasePath).then(unwrap),
        ]);
        setMediaPoints(pointProjection);
        setOperationJournal(journal);
      } catch (caught) {
        projectionRefreshed = false;
        const detail = caught instanceof Error ? caught.message : String(caught);
        setError(`Состав изменён, но обновить реестр не удалось: ${detail}`);
      }
      return { ...changed, projection_refreshed: projectionRefreshed };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const removePointPlacement = async (point, placement, reason) => {
    if (busy || !databasePath) return null;
    setBusy(true);
    setActivity("Снимаю пространственную связь и записываю обратимую операцию…");
    setError("");
    setSuccess("");
    try {
      const removed = unwrap(await removeSpatialAnnotationFromAnalyticalPoint(
        databasePath, point, placement.spatial_annotation_id, reason,
      ));
      setPointOperationNotice({
        operation: removed.operation,
        message: `Размещение ${placement.media_display_name} снято с Analytical Point «${point.point_name}».`,
      });
      setMediaPoints((current) => ({
        ...current,
        items: (current.items || []).map((item) => {
          if (item.analytical_point_id !== point.analytical_point_id) return item;
          const placements = (item.placements || []).filter((candidate) => candidate.spatial_annotation_id !== placement.spatial_annotation_id);
          return { ...item, placements, placement_count: placements.length };
        }),
      }));
      setSuccess(`Размещение «${placement.media_display_name}» снято обратимо. Spatial Annotation, Media Asset и научные данные сохранены.`);
      let projectionRefreshed = true;
      try {
        const [pointProjection, journal] = await Promise.all([
          listAnalyticalPoints(databasePath).then(unwrap),
          listOperationJournal(databasePath).then(unwrap),
        ]);
        setMediaPoints(pointProjection);
        setOperationJournal(journal);
      } catch (caught) {
        projectionRefreshed = false;
        const detail = caught instanceof Error ? caught.message : String(caught);
        setError(`Размещение снято, но обновить реестр не удалось: ${detail}`);
      }
      return { ...removed, projection_refreshed: projectionRefreshed };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const undoPointOperation = async (operationId) => {
    if (busy || !databasePath || !operationId) return null;
    setBusy(true);
    setActivity("Проверяю точный scope и отменяю операцию…");
    setError("");
    setSuccess("");
    try {
      const undone = unwrap(await undoOperation(databasePath, operationId));
      setPointOperationNotice(null);
      if (undone.effect === "retracted") {
        setMediaPoints((current) => {
          const items = (current.items || []).filter((item) => item.analytical_point_id !== undone.analytical_point_id);
          return { ...current, total: items.length, sample_names: [...new Set(items.map((item) => item.sample_name))].sort((left, right) => left.localeCompare(right, "ru")), items };
        });
      }
      setSuccess({
        restored: "Связь Analytical Point восстановлена по устойчивым ID.",
        retracted: "Создание Analytical Point отменено обратимо; исходные Analyses сохранены.",
        analysis_added: "Analysis возвращена в состав Analytical Point по устойчивому ID.",
        analysis_removed: "Добавление Analysis отменено; исходная Analysis сохранена.",
        annotation_link_restored: "Пространственная связь восстановлена по устойчивым ID.",
      }[undone.effect] || "Операция отменена по устойчивым ID.");
      let projectionRefreshed = true;
      try {
        const [pointProjection, journal] = await Promise.all([
          listAnalyticalPoints(databasePath).then(unwrap),
          listOperationJournal(databasePath).then(unwrap),
        ]);
        setMediaPoints(pointProjection);
        setOperationJournal(journal);
      } catch (caught) {
        projectionRefreshed = false;
        const detail = caught instanceof Error ? caught.message : String(caught);
        setError(`Операция отменена, но обновить реестр не удалось: ${detail}`);
      }
      return { ...undone, projection_refreshed: projectionRefreshed };
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
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
      await inspectImageBatch(paths);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const chooseImageFolder = async () => {
    if (busy || !desktopRuntimeAvailable) return;
    setBusy(true);
    setActivity("Выберите папку с изображениями…");
    setError("");
    setSuccess("");
    try {
      const paths = await pickMediaFolder();
      if (!paths) return;
      if (!paths.length) {
        throw new Error("В выбранной папке и её вложенных папках нет PNG, JPEG, TIFF или BMP.");
      }
      await inspectImageBatch(paths);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const removeImagesFromBatch = async (sourcePaths) => {
    if (busy || !sourcePaths?.length) return;
    const removed = new Set(sourcePaths);
    const remaining = (mediaInspection?.items || [])
      .map((item) => item.source_path)
      .filter((path) => !removed.has(path));
    setMediaPlan(null);
    if (!remaining.length) {
      setMediaInspection(null);
      return;
    }
    setBusy(true);
    setActivity("Обновляю очередь изображений…");
    setError("");
    try {
      const result = unwrap(await inspectMediaSources(remaining));
      setMediaInspection(result);
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
      const placementCount = result.items.reduce((count, item) => count + item.placements.length, 0);
      setSuccess(`План проверен: ${result.items.length} изображений, ${placementCount} пространственных связей.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const importImages = async (reviewedPlan) => {
    if (busy || !databasePath || !reviewedPlan) return;
    setBusy(true);
    setActivity("Повторно проверяю файлы и сохраняю изображения…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await applyMediaImportPlan(databasePath, reviewedPlan));
      setMediaInspection(null);
      setMediaPlan(null);
      await refreshAnalyticalPoints(databasePath);
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
    if (["Анализы", "Минералы"].includes(label)) refreshAnalyses().catch((caught) => setError(caught.message));
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
        <div className="side-footer"><Info size={18} /><span>Оживлены: импорт, анализы, минералы и изображения</span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{screen}</h2>
            <p>Источников: <b>{project.source_count}</b> · импортов: <b>{project.import_batch_count}</b> · анализов: <b>{project.total}</b></p>
          </div>
          <div className="top-actions">
            {screen === "Изображения" && <button className="outline-button" onClick={chooseImageFolder} disabled={busy || !desktopRuntimeAvailable} title="Добавить изображения из папки и вложенных папок"><FolderOpen size={18} /> Папка</button>}
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
                <p>Excel или CSV · исходный файл останется без изменений</p>
                <button className="primary-button large" onClick={chooseFile} disabled={busy || !desktopRuntimeAvailable} title={desktopRuntimeAvailable ? undefined : "Полный импорт доступен в установленном PetroLab Desktop"}>
                  {busy ? <SpinnerGap className="spin" size={20} /> : <FileArrowUp size={20} />}
                  {busy ? "Открываю файл…" : "Выбрать файл"}
                </button>
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
                bulkUnitOverrideScopes={bulkUnitOverrideScopes}
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
                onApplyBulkUnitOverride={applyBulkUnitOverride}
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
            analyticalPoints={mediaPoints}
            operationJournal={operationJournal}
            pointOperationNotice={pointOperationNotice}
            busy={busy}
            onRefresh={() => refreshAnalyses().catch((caught) => setError(caught.message))}
            onRefreshAnalyticalPoints={() => refreshAnalyticalPoints()}
            onRetract={retractLatest}
            onAddData={startNewImport}
            onLoadMore={loadMoreAnalyses}
            onLoadSourceAnalyses={loadSourceAnalyses}
            onCreateAnalyticalPoint={createPointFromAnalyses}
            onChangeAnalyticalPointMembership={changePointMembership}
            onRemoveAnalyticalPointPlacement={removePointPlacement}
            onRetireAnalyticalPoint={retirePoint}
            onUndoOperation={undoPointOperation}
          />
        )}

        {screen === "Минералы" && (
          <MineralsWorkspace
            databasePath={databasePath}
            project={project}
            busy={busy}
            onRefresh={() => refreshAnalyses().catch((caught) => setError(caught.message))}
            onDecide={decideMineral}
            onLoadMore={loadMoreAnalyses}
            onAddData={startNewImport}
          />
        )}

        {(screen === "Изображения" || mediaInspection) && <div hidden={screen !== "Изображения"} className="image-workspace-container">
          <ImagesWorkspace
            inspection={mediaInspection}
            plan={mediaPlan}
            points={mediaPoints}
            busy={busy}
            onChoose={chooseImages}
            onChooseFolder={chooseImageFolder}
            onRemove={removeImagesFromBatch}
            onPreview={loadMediaPreview}
            onPlan={planImages}
            onApply={importImages}
            onCancel={cancelImageImport}
            onInvalidatePlan={() => setMediaPlan(null)}
            onOpenAnalyses={() => setScreen("Анализы")}
          />
        </div>}
      </section>
    </main>
  );
}
