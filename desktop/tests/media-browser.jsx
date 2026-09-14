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
  { analytical_point_id: "point-1", point_name: "P-07", sample_name: "KIV-2", analysis_ids: ["synthetic-epma", "synthetic-la"], methods: ["EPMA", "LA-ICP-MS"], placement_count: 0 },
  { analytical_point_id: "point-2", point_name: "P-03", sample_name: "OTHER", analysis_ids: ["synthetic-other"], methods: ["EPMA"], placement_count: 0 },
];
const canvas = document.createElement("canvas");
canvas.width = 640; canvas.height = 480;
const context = canvas.getContext("2d");
context.fillStyle = "#78847a"; context.fillRect(0, 0, 640, 480);
context.fillStyle = "#fff"; context.font = "20px sans-serif";
context.fillText("SYNTHETIC QA IMAGE — 640 × 480", 120, 230);
const preview = canvas.toDataURL("image/png");
let requestIndex = 0;
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
      case "project.analyses.list": return response({ total: 0, returned: 0, offset: 0, has_more: false, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] });
      case "project.mineral_identification.list": return response({ total: 0, identifications: [], status_counts: {} });
      case "media.inspect_sources": return response({ items: items.filter((item) => payload.source_paths.includes(item.source_path)), duplicate_groups: [] });
      case "analytical_point.list": return response({ total: 2, sample_names: ["KIV-2", "OTHER"], items: points });
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
