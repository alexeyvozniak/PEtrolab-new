// Explicit browser-only fixture. Not imported by the production entrypoint.
// Picker and service responses are simulated; no project files are written.
import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "../src/App.jsx";

const items = ["BSE", "PPL", "XPL"].map((type, index) => ({
  source_path: `C:/synthetic/KIV-2_A_${type}_01.tif`,
  display_name: `KIV-2_A_${type}_01.tif`,
  source_fingerprint: `synthetic-${index}`,
  mime_type: "image/tiff", format: "tiff", width_px: 640, height_px: 480,
  suggested_media_type: type, suggested_sample_name: "KIV-2",
  suggested_thin_section_name: "KIV-2-A",
}));
const points = [
  { analytical_point_id: "point-1", point_name: "P-07", sample_name: "KIV-2", analysis_ids: ["synthetic-epma", "synthetic-la"], analysis_members: [{ analysis_id: "synthetic-epma", method: "EPMA", source_name: "KIV-2_EPMA.xlsx", sheet_name: "Data", source_row_number: 9, source_orientation: "rows_are_analyses" }, { analysis_id: "synthetic-la", method: "LA-ICP-MS", source_name: "KIV-2_LA-ICP-MS.xlsx", sheet_name: "Trace", source_row_number: 11, source_orientation: "rows_are_analyses" }], methods: ["EPMA", "LA-ICP-MS"], link_types: ["same_point"], placement_count: 1, created_at: "2026-09-15T10:24:00Z", placements: [{ spatial_annotation_id: "annotation-p07-bse", media_asset_id: "media-kiv-2-bse", media_display_name: "KIV-2_A_BSE_01.tif", media_type: "BSE", thin_section_id: "section-kiv-2-a", thin_section_name: "KIV-2-A", geometry: { kind: "point", x_px: 5710, y_px: 4876 }, image_width_px: 8192, image_height_px: 6144, cross_sample_exception: false, exception_reason: null, linked_at: "2026-09-15T10:30:00Z" }] },
  { analytical_point_id: "point-2", point_name: "P-03", sample_name: "OTHER", analysis_ids: ["synthetic-other"], methods: ["EPMA"], link_types: ["same_zone"], placement_count: 0, created_at: "2026-09-15T10:25:00Z" },
];
const analyses = [
  { analysis_id: "synthetic-epma", source_name: "KIV-2_EPMA.xlsx", sheet_name: "Data", source_row_number: 9, source_orientation: "rows_are_analyses", identity: { Analysis: "P-07-EPMA", Sample: "KIV-2", Point: "P-07" }, source_metadata: {}, measurements: { SiO2: { raw_token: "48.2", unit: "wt.%", method: "EPMA" } }, measurement_list: [{ field: "SiO2", raw_token: "48.2", unit: "wt.%", method: "EPMA" }] },
  { analysis_id: "synthetic-la", source_name: "KIV-2_LA-ICP-MS.xlsx", sheet_name: "Trace", source_row_number: 11, source_orientation: "rows_are_analyses", identity: { Analysis: "P-07-LA", Sample: "KIV-2", Point: "P-07" }, source_metadata: {}, measurements: { Rb: { raw_token: "12.4", unit: "ppm", method: "LA-ICP-MS" } }, measurement_list: [{ field: "Rb", raw_token: "12.4", unit: "ppm", method: "LA-ICP-MS" }] },
  { analysis_id: "synthetic-candidate", source_name: "KIV-3_EPMA.xlsx", sheet_name: "Data", source_row_number: 6, source_orientation: "rows_are_analyses", identity: { Analysis: "P-11-EPMA", Sample: "KIV-3", Point: "P-11" }, source_metadata: {}, measurements: { SiO2: { raw_token: "47.6", unit: "wt.%", method: "EPMA" } }, measurement_list: [{ field: "SiO2", raw_token: "47.6", unit: "wt.%", method: "EPMA" }] },
];
const canvas = document.createElement("canvas");
canvas.width = 640; canvas.height = 480;
const context = canvas.getContext("2d");
context.fillStyle = "#78847a"; context.fillRect(0, 0, 640, 480);
context.fillStyle = "#fff"; context.font = "20px sans-serif";
context.fillText("SYNTHETIC QA IMAGE — 640 × 480", 120, 230);
const preview = canvas.toDataURL("image/png");
let requestIndex = 0;
let activePoints = [...points];
let journal = [];
// The internal QA origin uses HTTP; production Tauri provides randomUUID.
if (!window.crypto.randomUUID) window.crypto.randomUUID = () => `synthetic-request-${++requestIndex}`;

window.__TAURI_INTERNALS__ = {
  invoke: async (command, args = {}) => {
    if (command === "project_database_path") return "C:/synthetic/qa.sqlite";
    if (command === "pick_media_files") return [items[0].source_path];
    if (command === "pick_media_folder") return items.map((item) => item.source_path);
    if (command !== "petrolab_command") throw new Error(`Unsupported QA command: ${command}`);
    const request = args.envelope;
    const response = (result) => ({ protocol_version: "1.0", request_id: request.request_id, result });
    const payload = request.payload;
    switch (request.command) {
      case "project.analyses.list": return response({ total: analyses.length, returned: analyses.length, offset: 0, has_more: false, source_count: 2, import_batch_count: 1, latest_import: null, analyses });
      case "project.mineral_identification.list": return response({ total: analyses.length, identifications: [], status_counts: {} });
      case "media.inspect_sources": return response({ items: items.filter((item) => payload.source_paths.includes(item.source_path)), duplicate_groups: [] });
      case "analytical_point.list": return response({ total: activePoints.length, sample_names: [...new Set(activePoints.map((point) => point.sample_name))], items: activePoints });
      case "operation_journal.list": return response({ total: journal.length, items: journal });
      case "analytical_point.retire": {
        const point = points.find((item) => item.analytical_point_id === payload.analytical_point_id);
        const operation = {
          operation_id: "operation-retire-p07", action_kind: "analytical_point.retire", actor: "local-desktop-user",
          entity_type: "analytical_point", entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: point.analysis_ids, spatial_annotation_ids: (point.placements || []).map((placement) => placement.spatial_annotation_id), media_asset_ids: (point.placements || []).map((placement) => placement.media_asset_id) },
          parameters: { reason: payload.reason, sample_name: point.sample_name, point_name: point.point_name }, outcome: "applied", inverse_action_kind: "analytical_point.restore", created_at: "2026-09-15T10:40:00Z",
        };
        activePoints = activePoints.filter((item) => item.analytical_point_id !== point.analytical_point_id);
        journal = [operation, ...journal];
        return response({ analytical_point_id: point.analytical_point_id, sample_name: point.sample_name, point_name: point.point_name, operation });
      }
      case "analytical_point.analysis.add": {
        const point = activePoints.find((item) => item.analytical_point_id === payload.analytical_point_id);
        const analysisIds = [...point.analysis_ids, payload.analysis_id];
        const operation = {
          operation_id: "operation-add-analysis", action_kind: "analytical_point.analysis.add", actor: "local-desktop-user", entity_type: "analytical_point",
          entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: analysisIds, spatial_annotation_ids: (point.placements || []).map((placement) => placement.spatial_annotation_id), media_asset_ids: (point.placements || []).map((placement) => placement.media_asset_id) },
          parameters: { reason: payload.reason, analysis_id: payload.analysis_id, link_type: payload.link_type, sample_name: point.sample_name, point_name: point.point_name }, outcome: "applied", inverse_action_kind: "analytical_point.analysis.remove", created_at: "2026-09-15T10:39:00Z",
        };
        activePoints = activePoints.map((item) => item.analytical_point_id === point.analytical_point_id ? { ...item, analysis_ids: analysisIds, link_types: [...new Set([...item.link_types, payload.link_type])] } : item);
        journal = [operation, ...journal];
        return response({ analytical_point_id: point.analytical_point_id, analysis_id: payload.analysis_id, analysis_ids: analysisIds, link_type: payload.link_type, effect: "analysis_added", operation });
      }
      case "operation_journal.undo": {
        activePoints = [...points];
        journal = journal.map((item) => item.operation_id === payload.operation_id ? { ...item, outcome: "undone", undone_by_operation_id: "operation-undo-p07" } : item);
        return response({ target_operation_id: payload.operation_id, analytical_point_id: "point-1", effect: "restored", operation: { operation_id: "operation-undo-p07", action_kind: "operation.undo" } });
      }
      case "media.preview": {
        const item = items.find((entry) => entry.source_path === payload.source_path);
        return response({ ...item, preview_data_url: preview, preview_width_px: 640, preview_height_px: 480 });
      }
      case "media.import.plan": return response({
        schema_version: 1, semantic_fingerprint: "synthetic-plan",
        items: payload.assignments.map((assignment, index) => ({
          ...items.find((item) => item.source_path === assignment.source_path), ...assignment,
          media_asset_id: `synthetic-asset-${index}`, existing_media_asset_id: null,
          placements: assignment.placements.map((placement, position) => ({
            ...placement, spatial_annotation_id: `synthetic-annotation-${index}-${position}`,
            point_name: points.find((point) => point.analytical_point_id === placement.analytical_point_id).point_name,
          })),
        })), warnings: payload.assignments.filter((item) => item.placements.length === 0).map((item) => ({ code: "UNPLACED_MEDIA", source_path: item.source_path, message: `${item.source_path}: no points placed` })),
      });
      case "media.import.apply": return response({ created_media_asset_count: payload.plan.items.length, reused_media_asset_count: 0, spatial_annotation_count: payload.plan.items.reduce((total, item) => total + item.placements.length, 0) });
      default: throw new Error(`Unsupported QA service command: ${request.command}`);
    }
  },
};

createRoot(document.getElementById("root")).render(<App />);

// Deterministic screenshot routes for registry, import assignment and reversible unlink QA states.
const qaState = new URLSearchParams(window.location.search).get("qa");
if (["registry", "operation", "composition", "assignment"].includes(qaState)) {
  const clickWhenReady = (find, next) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      const target = find();
      if (target) {
        window.clearInterval(timer);
        target.click();
        if (next) window.setTimeout(next, 120);
      } else if (Date.now() - started > 4000) {
        window.clearInterval(timer);
      }
    }, 50);
  };
  if (qaState === "assignment") {
    clickWhenReady(
      () => [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "Изображения"),
      () => clickWhenReady(() => [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "Выбрать папку")),
    );
  } else {
    clickWhenReady(
      () => [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "Анализы"),
      () => clickWhenReady(
        () => [...document.querySelectorAll("button")].find((button) => button.textContent.includes("Analytical Points")),
        () => clickWhenReady(() => qaState === "operation"
          ? [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "Разорвать связь")
          : qaState === "composition"
            ? [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "Изменить состав")
            : document.querySelector('input[aria-label="Выбрать Analytical Point P-07"]')),
      ),
    );
  }
}
