import { invoke } from "@tauri-apps/api/core";

export const PROTOCOL_VERSION = "1.0";

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

export async function invokePetrolab(command, payload) {
  const envelope = {
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    command,
    payload,
  };
  return desktopInvoke("petrolab_command", { envelope });
}

export const pickImportFile = () => desktopInvoke("pick_import_file");
export const stageImportFile = (sourcePath) => desktopInvoke("stage_import_file", { sourcePath });
export const clearImportStaging = (stagedPath) => desktopInvoke("clear_import_staging", { stagedPath });
export const getProjectDatabasePath = () => desktopInvoke("project_database_path");

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
