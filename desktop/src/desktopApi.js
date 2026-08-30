import { invoke } from "@tauri-apps/api/core";

export const PROTOCOL_VERSION = "1.0";

export async function invokePetrolab(command, payload) {
  const envelope = {
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    command,
    payload,
  };
  return invoke("petrolab_command", { envelope });
}

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
