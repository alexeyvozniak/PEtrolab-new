import { invoke } from "@tauri-apps/api/core";

export const PROTOCOL_VERSION = "1.0";

export const createImportWorkspace = (sources, projectDatabasePath) => invokePetrolab("import.workspace.create", { sources, project_database_path: projectDatabasePath });
export const restoreImportWorkspace = (projectDatabasePath) =>
  invokePetrolab("import.workspace.restore", { project_database_path: projectDatabasePath });
export const listWorkGroups = (projectDatabasePath) =>
  invokePetrolab("work_group.list", { project_database_path: projectDatabasePath });
export const listGenerations = (projectDatabasePath) =>
  invokePetrolab("generation.list", { project_database_path: projectDatabasePath });
export const assignGeneration = (projectDatabasePath, assignment) =>
  invokePetrolab("generation.assign", { project_database_path: projectDatabasePath, ...assignment });
export const undoGeneration = (projectDatabasePath, operationId, actor) =>
  invokePetrolab("generation.undo", { project_database_path: projectDatabasePath, operation_id: operationId, actor });
export const listTableViews = (projectDatabasePath) =>
  invokePetrolab("table_view.list", { project_database_path: projectDatabasePath });
export const saveTableView = (projectDatabasePath, view) =>
  invokePetrolab("table_view.save", { project_database_path: projectDatabasePath, ...view });
export const listEditDrafts = (projectDatabasePath, analysisId) =>
  invokePetrolab("edit_draft.list", { project_database_path: projectDatabasePath, analysis_id: analysisId });
export const saveEditDraft = (projectDatabasePath, measurementId, newValue) =>
  invokePetrolab("edit_draft.save", { project_database_path: projectDatabasePath, measurement_id: measurementId, new_value: newValue });
export const checkEditDraft = (projectDatabasePath, draftId) =>
  invokePetrolab("edit_draft.check", { project_database_path: projectDatabasePath, draft_id: draftId });
export const commitEditDraft = (projectDatabasePath, draftId, actor, reason) =>
  invokePetrolab("edit_draft.commit", { project_database_path: projectDatabasePath, draft_id: draftId, actor, reason });
export const createWorkGroup = (projectDatabasePath, metadata) =>
  invokePetrolab("work_group.create", { project_database_path: projectDatabasePath, ...metadata });
export const previewSemanticExtension = (workspaceId, sourceId, decision) => invokePetrolab("import.workspace.preview_window", { workspace_id: workspaceId, source_id: sourceId, semantic_extension: decision });
export const addWorkspaceSources = (workspaceId, revision, sources) =>
  invokePetrolab("import.workspace.add_sources", { workspace_id: workspaceId, expected_revision: revision, sources });
export const getImportWorkspace = (workspaceId) => invokePetrolab("import.workspace.get", { workspace_id: workspaceId });
export const listFormulaMethods = () => invokePetrolab("formula.methods.list", {});
export const previewImportFormula = (workspace, selection, methodId) =>
  invokePetrolab("import.workspace.preview_formula", { workspace_id: workspace.workspace_id,
    expected_revision: workspace.draft_revision, source_id: workspace.active_source_id,
    ...(Array.isArray(selection) ? { preview_ids: selection } : { preview_id: selection }), method_id: methodId });
export const applyWorkspaceDecision = async (workspaceId, revision, sourceId, decision, bulk = false, knownPlan = null) => {
  const response = await invokePetrolab(bulk ? "import.workspace.apply_bulk_decision" : "import.workspace.apply_decision", {
    workspace_id: workspaceId, expected_revision: revision, source_id: sourceId, decision,
    ...(knownPlan ? { known_active_plan: knownPlan.reference } : {}),
  });
  const projection = response?.result;
  const reference = projection?.active?.plan_reference;
  if (!reference) return response;
  if (knownPlan?.plan && projection.session.workspace_id === workspaceId
      && projection.session.active_source_id === sourceId
      && reference.source_id === sourceId
      && reference.source_id === knownPlan.reference.source_id
      && reference.plan_fingerprint === knownPlan.reference.plan_fingerprint
      && projection.session.plans.some(item => item.source_id === sourceId && item.plan_fingerprint === reference.plan_fingerprint)) {
    const { plan_reference, ...active } = projection.active;
    return { ...response, result: { ...projection, active: { ...active, plan: knownPlan.plan } } };
  }
  // The revision was already accepted by Python. Retrieve its full projection
  // rather than attempting another mutation with the previous revision.
  return getImportWorkspace(workspaceId);
};
export const discardImportWorkspace = (workspaceId, revision) =>
  invokePetrolab("import.workspace.discard", { workspace_id: workspaceId, expected_revision: revision });
export const commitImportWorkspace = (workspaceId, revision) =>
  invokePetrolab("import.workspace.commit", { workspace_id: workspaceId, expected_revision: revision });
export const previewWorkspaceWindow = (workspaceId, sourceId, sheetName, startRow, rowCount = 30, startColumn = 0, columnCount = 24) =>
  invokePetrolab("import.workspace.preview_window", { workspace_id: workspaceId, source_id: sourceId,
    sheet_name: sheetName, start_row: startRow, row_count: rowCount, start_column: startColumn, column_count: columnCount });

function desktopInvoke(command, args) {
  const internals = typeof window === "undefined" ? null : window.__TAURI_INTERNALS__;
  if (!internals || typeof internals.invoke !== "function") {
    throw new Error("Полный импорт доступен в установленном PetroLab Desktop. Этот preview предназначен только для проверки интерфейса.");
  }
  return invoke(command, args);
}

export function isPetrolabDesktop() {
  return typeof window !== "undefined" && typeof window.__TAURI_INTERNALS__?.invoke === "function";
}

const WORKSPACE_REVIEW_COMMANDS = new Set([
  "import.workspace.create", "import.workspace.restore", "import.workspace.add_sources",
  "import.workspace.get", "import.workspace.apply_decision", "import.workspace.apply_bulk_decision",
  "import.workspace.replan",
]);

export function expandWorkspaceReview(result) {
  const projection = result?.workspace ?? result;
  const plan = projection?.active?.plan;
  if (!plan || !Object.hasOwn(plan, "measurement_columns_v1")) return result;
  const { measurement_columns_v1: columns, planned_records: records, ...rest } = plan;
  if (!Array.isArray(columns) || !columns.length || columns.some(key => typeof key !== "string")
      || new Set(columns).size !== columns.length || !Array.isArray(records)) {
    throw new Error("PetroLab получил несовместимое представление измерений.");
  }
  const expanded = records.map(record => ({
    ...record,
    measurements: record.measurements.map(values => {
      if (!Array.isArray(values) || values.length !== columns.length) {
        throw new Error("PetroLab получил неполное представление измерения.");
      }
      return Object.fromEntries(columns.map((key, index) => [key, values[index]]));
    }),
  }));
  const restored = { ...projection, active: { ...projection.active, plan: { ...rest, planned_records: expanded } } };
  return result?.workspace ? { ...result, workspace: restored } : restored;
}

export async function invokePetrolab(command, payload) {
  const compact = WORKSPACE_REVIEW_COMMANDS.has(command);
  const envelope = {
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    command,
    payload: compact ? { ...payload, measurement_wire_format: "columns_v1" } : payload,
  };
  const response = await desktopInvoke("petrolab_command", { envelope });
  return compact && response?.result
    ? { ...response, result: expandWorkspaceReview(response.result) }
    : response;
}

export const pickImportFile = () => desktopInvoke("pick_import_file");
export const openExternalUrl = (url) => desktopInvoke("open_external_url", { url });
export const pickAnalysisExportPath = (format = "xlsx") => desktopInvoke("pick_analysis_export_path", { format });
export const pickPlotExportPath = (name) => desktopInvoke("pick_plot_export_path", { name });
export const exportPlot = (svg, { format, width, dpi }, outputPath) => invokePetrolab("plot.export", {
  svg, format, width_mm: width, dpi, output_path: outputPath,
});
export const exportAnalysisSelection = (projectDatabasePath, analysisIds, outputPath, format = "xlsx") =>
  invokePetrolab(format === "csv" ? "analysis.selection.export_csv" : "analysis.selection.export_xlsx", {
    project_database_path: projectDatabasePath, analysis_ids: analysisIds, output_path: outputPath,
  });
export const stageImportFile = (sourcePath) => desktopInvoke("stage_import_file", { sourcePath });
export const clearImportStaging = (stagedPath) => desktopInvoke("clear_import_staging", { stagedPath });
export const getProjectDatabasePath = () => desktopInvoke("project_database_path");
export const getProjectOverview = (projectDatabasePath) =>
  invokePetrolab("project.overview", { project_database_path: projectDatabasePath });
export const saveProjectWorkPlanTask = (projectDatabasePath, { id, title, completed, revision }) =>
  invokePetrolab("project.work_plan.save", { project_database_path: projectDatabasePath,
    task_id: id ?? null, title, completed, expected_revision: revision });
export const listProjectSamples = (projectDatabasePath) =>
  invokePetrolab("project.samples.list", { project_database_path: projectDatabasePath });
export const reviewStatistics = (projectDatabasePath, input, features) => invokePetrolab("statistics.review", {
  project_database_path: projectDatabasePath, input, features,
});
export const runClustering = (projectDatabasePath, review, parameters) => invokePetrolab("statistics.cluster.run", {
  project_database_path: projectDatabasePath, input: review.input, features: review.features,
  review_fingerprint: review.input_fingerprint, parameters,
});
export const listCalculationRuns = (projectDatabasePath) => invokePetrolab("statistics.runs.list", { project_database_path: projectDatabasePath });
export const openCalculationRun = (projectDatabasePath, runId) =>
  invokePetrolab("statistics.run.open", { project_database_path: projectDatabasePath, run_id: runId });
export const saveCalculatedCluster = (projectDatabasePath, runId, cluster, name, actor) =>
  invokePetrolab("statistics.cluster.save_group", { project_database_path: projectDatabasePath, run_id: runId, cluster, name, actor });
export const getProjectSample = (projectDatabasePath, sampleId) =>
  invokePetrolab("project.sample.get", { project_database_path: projectDatabasePath, sample_id: sampleId });
export const saveSampleContext = (projectDatabasePath, sampleId, context, expectedRevision) =>
  invokePetrolab("project.sample.context.save", { project_database_path: projectDatabasePath, sample_id: sampleId,
    context, expected_revision: expectedRevision });
export const addSampleNote = (projectDatabasePath, sampleId, author, body) =>
  invokePetrolab("project.sample.note.add", { project_database_path: projectDatabasePath, sample_id: sampleId, author, body });
export const pickMediaFiles = () => desktopInvoke("pick_media_files");
export const pickPublicationFigure = (format) => desktopInvoke("pick_publication_figure", { format });
export const pickPublicationExportPath = () => desktopInvoke("pick_publication_export_path");
export const getPublicationCatalog = (projectDatabasePath) => invokePetrolab("publication.catalog", { project_database_path: projectDatabasePath });
export const capturePublicationPlot = (projectDatabasePath, capture, caption) => invokePetrolab("publication.capture_plot", {
  project_database_path: projectDatabasePath, capture, caption,
});
export const capturePublicationTable = (projectDatabasePath, analysisIds) => invokePetrolab("publication.capture_table", {
  project_database_path: projectDatabasePath, analysis_ids: analysisIds,
});
export const capturePublicationMedia = (projectDatabasePath, mediaId, options) => invokePetrolab("publication.capture_media", {
  project_database_path: projectDatabasePath, media_asset_id: mediaId, options,
});
export const preparePublication = (projectDatabasePath, name, items, { profile, width }) => invokePetrolab("publication.prepare", {
  project_database_path: projectDatabasePath, name, items, profile, width_mm: width,
});
export const exportPublication = (projectDatabasePath, name, items, fingerprint, outputPath, { profile, width }) => invokePetrolab("publication.export", {
  project_database_path: projectDatabasePath, name, items, expected_fingerprint: fingerprint, output_path: outputPath,
  profile, width_mm: width,
});
export const pickMediaExportPath = (name) => desktopInvoke("pick_media_export_path", { name });
export const inspectMediaFiles = (paths) => invokePetrolab("media.inspect_sources", { source_paths: paths });
export const previewMediaFile = (path, region, fingerprint) => invokePetrolab("media.preview_input", {
  source_path: path, region, expected_fingerprint: fingerprint,
});
export const draftMediaImport = (projectDatabasePath, assignments) => invokePetrolab("media.import.plan", {
  project_database_path: projectDatabasePath, assignments,
});
export const commitMediaImport = (projectDatabasePath, plan, draftFingerprint) => invokePetrolab("media.import.apply", {
  project_database_path: projectDatabasePath, plan, draft_fingerprint: draftFingerprint,
});
export const pickMediaFolder = () => desktopInvoke("pick_media_folder");
export const inspectMediaFolder = (folder) => invokePetrolab("media.inspect_folder", { folder });
export const loadMediaImportDraft = (projectDatabasePath) => invokePetrolab("media.import.draft.load", { project_database_path: projectDatabasePath });
export const saveMediaImportDraft = (projectDatabasePath, plan, expectedFingerprint) => invokePetrolab("media.import.draft.save", {
  project_database_path: projectDatabasePath, plan, expected_fingerprint: expectedFingerprint,
});
export const previewProjectMedia = (projectDatabasePath, mediaAssetId, region) => invokePetrolab("media.preview", {
  project_database_path: projectDatabasePath, media_asset_id: mediaAssetId, region,
});
export const createMediaRegion = (projectDatabasePath, id, geometry) => invokePetrolab("media.region.create", {
  project_database_path: projectDatabasePath, media_asset_id: id, geometry,
});
export const listMediaLinks = (projectDatabasePath, id) => invokePetrolab("media.links.list", {
  project_database_path: projectDatabasePath, spatial_annotation_id: id,
});
export const setMediaLink = (projectDatabasePath, id, assetId, attached) => invokePetrolab("media.link.set", {
  project_database_path: projectDatabasePath, spatial_annotation_id: id, media_asset_id: assetId, attached,
});
export const importLinkedPhoto = (projectDatabasePath, id, photo, type) => invokePetrolab("media.link.import_photo", {
  project_database_path: projectDatabasePath, spatial_annotation_id: id, source_path: photo.source_path,
  expected_fingerprint: photo.source_fingerprint, media_type: type,
});
export const exportMediaOriginal = (projectDatabasePath, mediaAssetId, outputPath) => invokePetrolab("media.export_original", {
  project_database_path: projectDatabasePath, media_asset_id: mediaAssetId, output_path: outputPath,
});
export const exportMediaRendered = (projectDatabasePath, mediaAssetId, outputPath, options) => invokePetrolab("media.export_rendered", {
  project_database_path: projectDatabasePath, media_asset_id: mediaAssetId, output_path: outputPath, options,
});
export const exportMediaBatch = (projectDatabasePath, mediaAssetIds, outputPath, options) => invokePetrolab("media.export_batch", {
  project_database_path: projectDatabasePath, media_asset_ids: mediaAssetIds, output_path: outputPath, options,
});
export const createSamplePoint = (projectDatabasePath, fields) =>
  invokePetrolab("analytical_point.create", { project_database_path: projectDatabasePath, ...fields });
export const listPointAnalyses = (projectDatabasePath, pointId) =>
  invokePetrolab("analytical_point.analyses", { project_database_path: projectDatabasePath, point_id: pointId });
export const createManualPointAnalysis = (projectDatabasePath, pointId, entry) =>
  invokePetrolab("analytical_point.analysis.create_manual", { project_database_path: projectDatabasePath, point_id: pointId, entry });
export const setPointAnalysisLink = (projectDatabasePath, pointId, analysisId, linkType, actor) =>
  invokePetrolab("analytical_point.link.set", { project_database_path: projectDatabasePath, point_id: pointId,
    ...(Array.isArray(analysisId) ? { analysis_ids: analysisId } : { analysis_id: analysisId }), link_type: linkType, actor });
export const undoPointAnalysisLink = (projectDatabasePath, operationId, actor) =>
  invokePetrolab("analytical_point.link.undo", { project_database_path: projectDatabasePath, operation_id: operationId, actor });
export const queryProjectAnalyses = (projectDatabasePath, query) =>
  invokePetrolab("analysis.query", { project_database_path: projectDatabasePath, ...query });
export const queryProjectAnalysisIds = (projectDatabasePath, query) =>
  invokePetrolab("analysis.query.ids", { project_database_path: projectDatabasePath, ...query });
export const getProjectAnalysis = (projectDatabasePath, analysisId) =>
  invokePetrolab("project.analysis.get", { project_database_path: projectDatabasePath, analysis_id: analysisId });
export const getSelectionSummary = (path,analysisIds) => invokePetrolab("project.selection.summary",{project_database_path:path,analysis_ids:analysisIds});
export const getProjectPlotColors = path => invokePetrolab("project.plot_colors.get", {project_database_path:path});
export const saveProjectPlotColors = (path,scheme,revision) => invokePetrolab("project.plot_colors.save", {project_database_path:path,scheme,expected_revision:revision});
export const getPlotCatalog = (projectDatabasePath, analysisIds, includeCategories = false) =>
  invokePetrolab("plot_data.catalog", { project_database_path: projectDatabasePath, analysis_ids: analysisIds,
    ...(includeCategories ? { include_categories: true } : {}) });
export const listPlotSpecifications = (projectDatabasePath) =>
  invokePetrolab("plot_spec.list", { project_database_path: projectDatabasePath });
export const savePlotSpecification = (projectDatabasePath, layout) =>
  invokePetrolab("plot_spec.save", { project_database_path: projectDatabasePath, ...layout });
export const openPlotSpecification = (projectDatabasePath, id) =>
  invokePetrolab("plot_spec.open", { project_database_path: projectDatabasePath, id });
export const getPlotData = (projectDatabasePath, analysisIds, kind, axes, hiddenAnalysisIds, hiddenSourceIds, layers, normalization) =>
  invokePetrolab("plot_data.query", { project_database_path: projectDatabasePath, analysis_ids: analysisIds, kind, axes,
    hidden_analysis_ids: hiddenAnalysisIds, hidden_source_ids: hiddenSourceIds, layers, normalization });
export const recordPlotVisibility = (projectDatabasePath, analysisIds, hidden, sessionId) =>
  invokePetrolab(hidden ? "plot_visibility.hide" : "plot_visibility.restore", {
    project_database_path: projectDatabasePath, analysis_ids: analysisIds, session_id: sessionId,
  });
export const undoPlotVisibility = (projectDatabasePath, operationId, sessionId, hiddenAnalysisIds) =>
  invokePetrolab("plot_visibility.undo", {
    project_database_path: projectDatabasePath, operation_id: operationId, session_id: sessionId,
    hidden_analysis_ids: hiddenAnalysisIds,
  });

export const inspectImportSource = (sourcePath) =>
  invokePetrolab("import.inspect_source", { source_path: sourcePath });

export const classifyCleanTable = (sourcePath) =>
  invokePetrolab("import.clean_table.classify", { source_path: sourcePath });

export const previewImportWindow = async (sourcePath, sheetName, startRow, rowCount = 12, startColumn = 0, columnCount = 24) => {
  const response = await invokePetrolab("import.preview.window", {
    source_path: sourcePath,
    sheet_name: sheetName,
    start_row: startRow,
    row_count: rowCount,
    start_column: startColumn,
    column_count: columnCount,
  });
  if (response?.result) {
    return { ...response, result: { ...response.result, source_path: sourcePath } };
  }
  return response;
};

export const suggestImportRecipe = (sourcePath) =>
  invokePetrolab("import.recipe.suggest", { source_path: sourcePath });

export const getImportBulkUnitScopes = (sourcePath, recipe) =>
  invokePetrolab("import.recipe.bulk_scopes", { source_path: sourcePath, recipe });

export const applyImportBulkUnit = (sourcePath, recipe, bulkScopeId, unit) =>
  invokePetrolab("import.recipe.apply_bulk_unit", {
    source_path: sourcePath,
    recipe,
    bulk_scope_id: bulkScopeId,
    unit,
  });

export const getImportBulkIgnoreScopes = (sourcePath, recipe) =>
  invokePetrolab("import.recipe.bulk_ignore_scopes", { source_path: sourcePath, recipe });

export const applyImportBulkIgnore = (sourcePath, recipe, bulkScopeId) =>
  invokePetrolab("import.recipe.apply_bulk_ignore", {
    source_path: sourcePath,
    recipe,
    bulk_scope_id: bulkScopeId,
  });

export const reviseImportMapping = (sourcePath, recipe, sheetName, sourceColumnIndex, target, canonicalField, unit) =>
  invokePetrolab("import.recipe.revise_mapping", {
    source_path: sourcePath,
    recipe,
    sheet_name: sheetName,
    source_column_index: sourceColumnIndex,
    target,
    canonical_field: canonicalField ?? null,
    unit: unit ?? null,
  });

export const reviseImportMappings = (sourcePath, recipe, decisions) =>
  invokePetrolab("import.recipe.revise_mappings", {
    source_path: sourcePath,
    recipe,
    decisions,
  });

export const reviseImportSections = (sourcePath, recipe, decisions) =>
  invokePetrolab("import.recipe.revise_sections", {
    source_path: sourcePath,
    recipe,
    decisions,
  });

export const reviewImportDuplicates = (sourcePath, recipe, decision = "keep_all") =>
  invokePetrolab("import.recipe.review_duplicates", {
    source_path: sourcePath,
    recipe,
    decision,
  });

export const createImportPlan = (sourcePath, recipe) =>
  invokePetrolab("import.plan.create", { source_path: sourcePath, recipe });

export const applyImportPlan = (projectDatabasePath, sourcePath, recipe) =>
  invokePetrolab("import.plan.apply", {
    project_database_path: projectDatabasePath,
    source_path: sourcePath,
    recipe,
  });

export const listProjectAnalyses = (projectDatabasePath, limit = 500, offset = 0) =>
  invokePetrolab("project.analyses.list", {
    project_database_path: projectDatabasePath,
    limit,
    offset,
  });

export const listProjectMineralIdentifications = (projectDatabasePath, limit = 500, offset = 0) =>
  invokePetrolab("project.mineral_identification.list", {
    project_database_path: projectDatabasePath,
    limit,
    offset,
  });

export const retractLastImport = (projectDatabasePath, reason = "user_retracted") =>
  invokePetrolab("project.last_import.retract", {
    project_database_path: projectDatabasePath,
    reason,
  });

export const inspectMediaSources = (sourcePaths) =>
  invokePetrolab("media.inspect_sources", { source_paths: sourcePaths });

export const createMediaImportPlan = (projectDatabasePath, assignments) =>
  invokePetrolab("media.import.plan", {
    project_database_path: projectDatabasePath,
    assignments,
  });

export const applyMediaImportPlan = (projectDatabasePath, plan) =>
  invokePetrolab("media.import.apply", {
    project_database_path: projectDatabasePath,
    plan,
  });

export const createAnalyticalPoint = (projectDatabasePath, sampleName, pointName, analysisIds, linkType) =>
  invokePetrolab("analytical_point.create", {
    project_database_path: projectDatabasePath,
    sample_name: sampleName,
    point_name: pointName,
    analysis_ids: analysisIds,
    link_type: linkType,
  });
