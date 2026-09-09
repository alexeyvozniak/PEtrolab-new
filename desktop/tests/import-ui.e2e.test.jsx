// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const uiState = vi.hoisted(() => ({ imported: false, mediaImported: false, mediaPlacementCount: 0, mode: "clean", detailsEnabled: true, unitApplied: false, duplicatesReviewed: false }));

vi.mock("../src/desktopApi", () => {
  const recipe = {
    sections: [{
      block_id: "clean-data",
      sheet_name: "Data",
      header_row: 1,
      orientation: "rows_are_analyses",
      enabled: true,
      mappings: [],
    }],
    global_decisions: {},
  };
  const plan = {
    summary: {
      planned_analysis_count: 2,
      planned_measurement_count: 6,
      enabled_block_count: 1,
      duplicate_candidate_groups: 0,
    },
    warnings: [],
    planned_records: [
      { preview_id: "UI-1", sheet_name: "Data", row_number: 2, orientation: "rows_are_analyses", identity: ["UI-1"], measurements: [{ field: "SiO2", raw_token: "40.1", unit: "wt.%" }] },
      { preview_id: "UI-2", sheet_name: "Data", row_number: 3, orientation: "rows_are_analyses", identity: ["UI-2"], measurements: [{ field: "SiO2", raw_token: "39.8", unit: "wt.%" }] },
    ],
  };
  const complexRecords = [
    { preview_id: "C-1", sheet_name: "Summary", row_number: 3, orientation: "rows_are_analyses", identity: ["Spectrum 1"], measurements: [{ field: "SiO2", raw_token: "40.1", unit: "wt.%" }] },
    { preview_id: "C-2", sheet_name: "Summary", row_number: 4, orientation: "rows_are_analyses", identity: ["Spectrum 1"], measurements: [{ field: "SiO2", raw_token: "39.8", unit: "wt.%" }] },
  ];
  const complexWarnings = [
    { code: "UNIT_REQUIRES_REVIEW", sheet_name: "Summary", block_id: "summary-main", source_axis: "column", source_column_index: 1, source_header: "SiO2", canonical_field: "SiO2" },
    { code: "UNMAPPED_FIELD_REQUIRES_REVIEW", sheet_name: "Details", block_id: "details-1", source_axis: "column", source_column_index: 1, source_header: "Sigma" },
    { code: "UNMAPPED_FIELD_REQUIRES_REVIEW", sheet_name: "Details", block_id: "details-2", source_axis: "column", source_column_index: 1, source_header: "Sigma" },
  ];
  const complexCleanReasons = [
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 4 },
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 5 },
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 6 },
  ];
  const currentComplexRecipe = () => ({
    sections: [{
      block_id: "summary-main",
      sheet_name: "Summary",
      header_row: 2,
      data_start_row: 3,
      data_end_row: 4,
      orientation: "rows_are_analyses",
      enabled: true,
      mappings: [
        { source_axis: "column", source_column_index: 0, source_header: "Analysis", target_role: "identity", canonical_field: "Analysis", review_decision: "recognized" },
        uiState.unitApplied
          ? { source_axis: "column", source_column_index: 1, source_header: "SiO2", target_role: "measurement", canonical_field: "SiO2", unit: "wt.%", review_decision: "assigned" }
          : { source_axis: "column", source_column_index: 1, source_header: "SiO2", target_role: "ignore", canonical_field: "SiO2", suggested_target: "measurement", suggested_canonical_field: "SiO2", review_decision: "unresolved" },
      ],
    }, ...[1, 2].map((index) => ({
      block_id: `details-${index}`,
      sheet_name: "Details",
      header_row: index === 1 ? 2 : 10,
      data_start_row: index === 1 ? 3 : 11,
      data_end_row: index === 1 ? 8 : 16,
      orientation: "rows_are_analyses",
      enabled: uiState.detailsEnabled,
      mappings: [
        { source_axis: "column", source_column_index: 0, source_header: `Spectrum ${index}`, target_role: "identity", canonical_field: "Analysis", review_decision: "recognized" },
        { source_axis: "column", source_column_index: 1, source_header: "Sigma", target_role: "ignore", canonical_field: "Sigma", review_decision: "unresolved" },
      ],
    }))],
    global_decisions: uiState.duplicatesReviewed ? {
      duplicate_policy: "keep_all",
      duplicate_review: { decision: "keep_all", candidate_group_count: 1 },
    } : {},
  });
  const complexPlan = () => ({
    summary: {
      planned_analysis_count: 2,
      planned_measurement_count: uiState.unitApplied ? 2 : 0,
      enabled_block_count: uiState.detailsEnabled ? 3 : 1,
      duplicate_candidate_groups: uiState.unitApplied ? 1 : 0,
    },
    warnings: uiState.unitApplied ? [{ code: "DUPLICATE_CANDIDATES", preview_ids: [["C-1", "C-2"]] }] : [],
    planned_records: uiState.unitApplied ? complexRecords : [],
  });
  const emptyProject = { total: 0, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] };
  const measurementList = Array.from({ length: 16 }, (_, index) => ({
    field: index === 0 ? "SiO2" : `Trace-${index}`,
    raw_token: index === 0 ? "40.1" : String(index / 10),
    unit: index === 0 ? "wt.%" : "ppm",
    source_header: index === 0 ? "SiO2 wt.%" : `Trace-${index} ppm`,
    source_cell: `${String.fromCharCode(67 + index)}2`,
    method: index === 0 ? "EPMA" : "LA-ICP-MS",
  }));
  const importedProject = {
    total: 2,
    returned: 2,
    offset: 0,
    has_more: false,
    source_count: 1,
    import_batch_count: 1,
    latest_import: null,
    analyses: [{
      analysis_id: "analysis-ui-1",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      source_row_number: 2,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-1", Sample: "KIV-2" },
      source_metadata: {},
      measurements: Object.fromEntries(measurementList.map((item) => [item.field, item])),
      measurement_list: measurementList,
    }, {
      analysis_id: "analysis-ui-2",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      source_row_number: 3,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-2", Sample: "KIV-3" },
      source_metadata: { Comment: "control" },
      measurements: { SiO2: { raw_token: "39.8", unit: "wt.%", source_cell: "C3" } },
    }],
  };
  const mediaInspection = {
    items: ["BSE", "PPL", "XPL"].map((type) => ({
      source_path: `C:/fixtures/KIV-2_A_${type}_01.tif`,
      display_name: `KIV-2_A_${type}_01.tif`,
      source_fingerprint: `fingerprint-${type}`,
      mime_type: "image/tiff",
      format: "tiff",
      width_px: 640,
      height_px: 480,
      suggested_media_type: type,
      suggested_sample_name: "KIV-2",
      suggested_thin_section_name: "KIV-2-A",
      suggestion_basis: ["filename_modality_token", "filename_prefix", "filename_section_prefix"],
    })),
    duplicate_groups: [],
  };
  const analyticalPoints = {
    total: 2,
    sample_names: ["KIV-2", "OTHER"],
    items: [{
      analytical_point_id: "point-kiv-2-p07",
      point_name: "P-07",
      sample_id: "sample-kiv-2",
      sample_name: "KIV-2",
      analysis_ids: ["analysis-ui-1", "analysis-la-87"],
      methods: ["EPMA", "LA-ICP-MS"],
      placement_count: 0,
    }, {
      analytical_point_id: "point-other-p03",
      point_name: "P-03",
      sample_id: "sample-other",
      sample_name: "OTHER",
      analysis_ids: ["analysis-other-3"],
      methods: ["EPMA"],
      placement_count: 0,
    }],
  };
  const api = {
    isPetrolabDesktop: () => true,
    getProjectDatabasePath: vi.fn().mockResolvedValue("C:/PetroLab/project.sqlite"),
    listProjectAnalyses: vi.fn().mockImplementation(async () => ({ result: uiState.imported ? importedProject : emptyProject })),
    listProjectMineralIdentifications: vi.fn().mockImplementation(async () => {
      const analyses = uiState.imported ? importedProject.analyses : [];
      return { result: {
        total: analyses.length,
        returned: analyses.length,
        offset: 0,
        has_more: false,
        identifications: analyses.map((analysis) => ({
          analysis_id: analysis.analysis_id,
          source_id: "source-ui",
          source_name: analysis.source_name,
          sheet_name: analysis.sheet_name,
          source_row_number: analysis.source_row_number,
          status: "not_checked",
          prediction: null,
          confidence: "insufficient_input",
          accepted: null,
          candidates: [],
          reasons: [],
          ruleset_version: "test-ruleset",
        })),
        status_counts: analyses.length ? { not_checked: analyses.length } : {},
      } };
    }),
    pickImportFile: vi.fn().mockImplementation(async () => uiState.mode === "clean" ? "C:/fixtures/ui-clean-table.csv" : "C:/fixtures/complex-workbook.xlsx"),
    pickMediaFiles: vi.fn().mockResolvedValue(mediaInspection.items.map((item) => item.source_path)),
    pickMediaFolder: vi.fn().mockResolvedValue(mediaInspection.items.map((item) => item.source_path)),
    inspectMediaSources: vi.fn().mockResolvedValue({ result: mediaInspection }),
    listAnalyticalPoints: vi.fn().mockResolvedValue({ result: analyticalPoints }),
    getMediaPreview: vi.fn().mockImplementation(async (sourcePath) => ({ result: {
      source_path: sourcePath,
      source_fingerprint: mediaInspection.items.find((item) => item.source_path === sourcePath).source_fingerprint,
      source_width_px: 640,
      source_height_px: 480,
      preview_width_px: 640,
      preview_height_px: 480,
      preview_data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
    } })),
    createMediaImportPlan: vi.fn().mockImplementation(async (_path, assignments) => {
      uiState.mediaPlacementCount = assignments.reduce((count, assignment) => count + assignment.placements.length, 0);
      return { result: {
        schema_version: 1,
        semantic_fingerprint: "media-plan",
        items: assignments.map((assignment, index) => ({
          ...mediaInspection.items[index],
          ...assignment,
          media_asset_id: `asset-${index}`,
          existing_media_asset_id: null,
          placements: assignment.placements.map((placement, placementIndex) => {
            const point = analyticalPoints.items.find((item) => item.analytical_point_id === placement.analytical_point_id);
            return { ...placement, spatial_annotation_id: `annotation-${index}-${placementIndex}`, point_name: point.point_name, point_sample_name: point.sample_name };
          }),
        })),
        warnings: assignments.filter((assignment) => assignment.placements.length === 0).map((assignment) => ({ code: "UNPLACED_MEDIA", message: `${assignment.source_path} has no placed Analytical Points.` })),
      } };
    }),
    applyMediaImportPlan: vi.fn().mockImplementation(async () => {
      uiState.mediaImported = true;
      return { result: { created_media_asset_count: 3, reused_media_asset_count: 0, spatial_annotation_count: uiState.mediaPlacementCount } };
    }),
    stageImportFile: vi.fn().mockImplementation(async (path) => ({ local_path: `C:/PetroLab/staging/${path.split("/").pop()}`, original_path: path })),
    clearImportStaging: vi.fn().mockResolvedValue(undefined),
    inspectImportSource: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean"
      ? { source_format: "csv", source_fingerprint: "0123456789abcdef", sheets: [{ name: "Data" }] }
      : { source_format: "xlsx", source_fingerprint: "fedcba9876543210", sheets: [{ name: "Summary" }, { name: "Details" }] } })),
    classifyCleanTable: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean"
      ? { mode: "clean_table_fast", clean_table_version: "1", recipe, sections: [{ sheet_name: "Data", analysis_fields: ["Analysis"], measurements: [{ field: "SiO2", unit: "wt.%" }] }], ignored_helper_sheets: [] }
      : { mode: "raw_review", reasons: complexCleanReasons } })),
    suggestImportRecipe: vi.fn().mockImplementation(async () => ({ result: { recipe: currentComplexRecipe(), warnings: complexWarnings } })),
    createImportPlan: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean" ? plan : complexPlan() })),
    getImportBulkUnitScopes: vi.fn().mockImplementation(async () => ({ result: { scopes: uiState.unitApplied ? [] : [{ bulk_scope_id: "summary-unit", block_count: 1, field_count: 1, fields: ["SiO2"], sheet_names: ["Summary"] }] } })),
    getImportBulkIgnoreScopes: vi.fn().mockImplementation(async () => ({ result: { scopes: uiState.detailsEnabled ? [{ bulk_scope_id: "details-ignore", block_count: 2, field_count: 2, fields: ["Sigma"], sheet_names: ["Details"] }] : [] } })),
    applyImportBulkIgnore: vi.fn(),
    applyImportBulkUnit: vi.fn().mockImplementation(async () => {
      uiState.unitApplied = true;
      return { result: { recipe: currentComplexRecipe(), applied_decision_count: 1 } };
    }),
    reviseImportSections: vi.fn().mockImplementation(async (_path, _recipe, decisions) => {
      if (decisions.some((decision) => decision.block_id.startsWith("details-") && decision.enabled === false)) uiState.detailsEnabled = false;
      return { result: { recipe: currentComplexRecipe() } };
    }),
    previewImportWindow: vi.fn().mockImplementation(async (_path, sheetName, startRow = 1) => ({ result: {
      source_path: "C:/PetroLab/staging/complex-workbook.xlsx",
      sheet_name: sheetName,
      start_row: startRow,
      end_row: startRow + 2,
      start_column: 0,
      end_column: 3,
      column_labels: ["A", "B", "C"],
      used_range: { rows: 20, columns: 3 },
      rows: [0, 1, 2].map((offset) => ({ row_number: startRow + offset, values: offset === 0 ? ["Analysis", "SiO2", "Sigma"] : [`Spectrum ${offset}`, "40.1", "0.2"] })),
    } })),
    reviewImportDuplicates: vi.fn().mockImplementation(async () => {
      uiState.duplicatesReviewed = true;
      return { result: { recipe: currentComplexRecipe(), plan: complexPlan(), duplicate_review: { candidate_group_count: 1 } } };
    }),
    applyImportPlan: vi.fn().mockImplementation(async () => {
      uiState.imported = true;
      return { result: { analysis_count: 2, measurement_count: 6, source_metadata_count: 0 } };
    }),
    reviseImportMappings: vi.fn(),
    retractLastImport: vi.fn(),
  };
  let sourceDescriptor;
  let revision = 0;
  let selectedBlock = "";
  const projectWorkspace = async () => {
    const classification = (await api.classifyCleanTable()).result;
    const currentRecipe = uiState.mode === "clean" ? recipe : currentComplexRecipe();
    const currentPlan = (await api.createImportPlan()).result;
    const source = { source_id: "source-1", ...sourceDescriptor, included: true, sheets: [] };
    const problems = [...(currentPlan.issues || []), ...(currentPlan.warnings || []),
      ...(uiState.mode === "clean" ? [] : complexCleanReasons),
      ...(uiState.mode === "clean" ? [] : complexWarnings.filter(w => w.code === "UNIT_REQUIRES_REVIEW" ? !uiState.unitApplied : uiState.detailsEnabled))];
    return { result: {
      session: { workspace_id: "workspace-1", draft_revision: revision, active_source_id: "source-1",
        active_block_id: selectedBlock || currentRecipe.sections[0].block_id, sources: [source],
        issues: problems.map((item, index) => ({ issue_id: String(index), code: item.code, source_id: "source-1", message_params: item, blocking: item.blocking || false })),
        readiness: { ready_to_commit: currentPlan.ready_to_commit !== false && (uiState.mode === "clean" || (uiState.unitApplied && !uiState.detailsEnabled && uiState.duplicatesReviewed)) },
      },
      active: { source_id: "source-1", inspection: (await api.inspectImportSource()).result, recipe: currentRecipe,
        plan: currentPlan, classification, issues: problems, decisions: [],
        bulk_unit_scopes: uiState.mode === "clean" ? [] : (await api.getImportBulkUnitScopes()).result.scopes,
        bulk_ignore_scopes: uiState.mode === "clean" ? [] : (await api.getImportBulkIgnoreScopes()).result.scopes,
      },
    } };
  };
  api.createImportWorkspace = vi.fn(async (sources) => {
    sourceDescriptor = sources[0]; revision = 0; selectedBlock = "";
    return projectWorkspace();
  });
  api.addWorkspaceSources = vi.fn();
  api.getImportWorkspace = vi.fn(projectWorkspace);
  api.discardImportWorkspace = vi.fn(async () => ({ result: { staged_paths: [sourceDescriptor.staged_path] } }));
  api.previewWorkspaceWindow = vi.fn(async (_workspace, _source, sheetName, startRow, rows, column, columns) =>
    api.previewImportWindow(sourceDescriptor.staged_path, sheetName, startRow, rows, column, columns));
  api.applyWorkspaceDecision = vi.fn(async (_workspace, _revision, _source, decision) => {
    if (decision.kind === "sections") await api.reviseImportSections(null, null, decision.decisions);
    if (decision.kind === "unit") await api.applyImportBulkUnit();
    if (decision.kind === "duplicates") await api.reviewImportDuplicates();
    if (decision.kind === "activate") selectedBlock = decision.block_id || selectedBlock;
    revision += 1;
    return projectWorkspace();
  });
  return api;

});

import { applyImportPlan, pickImportFile, pickMediaFolder, createImportPlan } from "../src/desktopApi";
import { App } from "../src/App";

afterEach(() => {
  uiState.imported = false;
  uiState.mediaImported = false;
  uiState.mediaPlacementCount = 0;
  uiState.mode = "clean";
  uiState.detailsEnabled = true;
  uiState.unitApplied = false;
  uiState.duplicatesReviewed = false;
  vi.clearAllMocks();
  cleanup();
});

test("user confirms an image batch, places same- and cross-sample points, reviews and imports", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  expect(screen.getAllByText("KIV-2_A_BSE_01.tif").length).toBeGreaterThan(1);
  expect(screen.getByText("0 готово")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  expect(await screen.findByText("3 готово")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));

  await user.click(await screen.findByRole("button", { name: /^2\. KIV-2_A_PPL_01\.tif/ }));
  expect(await screen.findByText("2 / 3")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Другой Sample…" }));
  await user.click(screen.getByRole("button", { name: /P-03 EPMA OTHER/ }));
  fireEvent.keyDown(screen.getByRole("application"), { key: "Enter" });
  const crossSampleSave = await screen.findByRole("button", { name: "Сохранить привязку" });
  expect(crossSampleSave.disabled).toBe(true);
  await user.selectOptions(screen.getByRole("combobox", { name: "Причина межобразцового исключения" }), "image_covers_other_sample");
  await user.click(crossSampleSave);

  await user.click(screen.getByRole("button", { name: /^1\. KIV-2_A_BSE_01\.tif/ }));
  expect(await screen.findByText("1 / 3")).toBeTruthy();
  await user.click(await screen.findByRole("button", { name: /P-07/ }));
  fireEvent.keyDown(await screen.findByRole("application"), { key: "Enter" });
  expect(await screen.findByText("Point · 320, 240 px")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Сохранить привязку" }));
  expect(await screen.findByText("Размещение сохранено в черновике")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Далее: проверка" }));
  expect(await screen.findByRole("heading", { name: "Проверка импорта изображений" })).toBeTruthy();
  expect(screen.getByRole("img", { name: /Предпросмотр KIV-2_A_BSE_01\.tif/ })).toBeTruthy();
  expect(screen.queryByRole("application")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Завершить импорт изображений" }));

  await waitFor(() => expect(uiState.mediaImported).toBe(true));
  expect(await screen.findByRole("heading", { name: "Добавить изображения" })).toBeTruthy();
  expect(screen.getByText(/Импортировано изображений: 3/)).toBeTruthy();
  expect(screen.getByText(/Пространственных точек: 2/)).toBeTruthy();
});

test("user opens a recursively collected image folder as one batch", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать папку" }));

  expect(pickMediaFolder).toHaveBeenCalledOnce();
  expect(await screen.findByRole("heading", { name: "Назначь Sample и шлиф" })).toBeTruthy();
  expect(screen.getAllByText("KIV-2_A_BSE_01.tif").length).toBeGreaterThan(1);
  expect(screen.getByText("Выбрано: 3 из 3")).toBeTruthy();
});

test("an image folder without supported files explains why no batch opened", async () => {
  pickMediaFolder.mockResolvedValueOnce([]);
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать папку" }));

  expect(await screen.findByText("В выбранной папке и её вложенных папках нет PNG, JPEG, TIFF или BMP.")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Добавить изображения" })).toBeTruthy();
});

test("user clicks through Clean Table import and sees the saved Analysis", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  const importButton = await screen.findByRole("button", { name: "Импортировать таблицу" });
  expect(pickImportFile).toHaveBeenCalledOnce();

  await user.click(screen.getByRole("button", { name: "Предпросмотр результата" }));
  const preview = screen.getByRole("dialog", { name: "Что попадёт в проект" });
  await user.type(within(preview).getByRole("textbox", { name: "Поиск в результате импорта" }), "UI-2");
  expect(within(preview).getByText("UI-2")).toBeTruthy();
  expect(within(preview).queryByText("UI-1")).toBeNull();
  await user.click(within(preview).getByRole("button", { name: "Закрыть предпросмотр" }));

  await user.click(importButton);
  await screen.findByRole("heading", { name: "Анализы" });
  expect((await screen.findAllByText("Windows UI smoke")).length).toBeGreaterThan(1);
  expect(screen.getAllByText("UI-1").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Trace-15").length).toBeGreaterThan(0);

  await user.click(screen.getByRole("checkbox", { name: "Выбрать UI-1" }));
  expect(screen.getByText("1 выбрано")).toBeTruthy();

  const search = screen.getByRole("textbox", { name: "Поиск анализов" });
  await user.type(search, "KIV-3");
  const table = screen.getByRole("table");
  expect(within(table).getByText("UI-2")).toBeTruthy();
  expect(within(table).queryByText("UI-1")).toBeNull();
  await user.clear(search);
  expect(applyImportPlan).toHaveBeenCalledWith(
    "C:/PetroLab/project.sqlite",
    "C:/PetroLab/staging/ui-clean-table.csv",
    expect.any(Object),
  );
  await waitFor(() => expect(uiState.imported).toBe(true));
});

test("complex import always shows the source table and groups repeated structural issues", async () => {
  uiState.mode = "complex";
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  await screen.findByRole("heading", { name: "Импорт таблиц" });

  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  const sourceTable = screen.getByRole("table");
  expect(within(sourceTable).getByLabelText("Ячейка 1:1").textContent).toBe("Analysis");
  expect(within(sourceTable).getByLabelText("Ячейка 1:2").textContent).toBe("SiO2");
  expect(within(sourceTable).getByText("Sigma")).toBeTruthy();
  expect(screen.getByText("Колонка с данными не имеет заголовка · 3 мест")).toBeTruthy();
});

test("Python identity blocker is visible, navigable and prevents saving", async () => {
  uiState.mode = "complex";
  createImportPlan.mockResolvedValueOnce({ result: {
    ready_to_commit: false,
    summary: { planned_analysis_count: 1, planned_measurement_count: 1, enabled_block_count: 1, duplicate_candidate_groups: 0 },
    planned_records: [], warnings: [],
    issues: [{ code: "ANALYSIS_IDENTITY_REQUIRED", blocking: true, sheet_name: "Summary", block_id: "summary-main", row_number: 3, source_column_index: 0 }],
  } });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  const issue = await screen.findByRole("button", { name: /Нет идентичности Analysis/ });
  await user.click(issue);
  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Импортировать после проверки" }).disabled).toBe(true);
  expect(applyImportPlan).not.toHaveBeenCalled();
});

test("user resolves a repeated complex workbook with sheet-level and grouped decisions", async () => {
  uiState.mode = "complex";
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  await screen.findByRole("heading", { name: "Импорт таблиц" });

  expect(screen.getByRole("button", { name: /Не импортировать лист Details/ })).toBeTruthy();
  expect(screen.getAllByText("Details").length).toBe(1);
  await waitFor(() => expect(screen.getByRole("button", { name: "Не импортировать лист Details" }).disabled).toBe(false));
  await user.click(screen.getByRole("button", { name: "Не импортировать лист Details" }));
  await waitFor(() => expect(uiState.detailsEnabled).toBe(false));

  const groupedUnit = screen.getByRole("combobox", { name: "Единица для группы SiO2" });
  await waitFor(() => expect(groupedUnit.disabled).toBe(false));
  await user.selectOptions(groupedUnit, "wt.%");
  const applyUnit = screen.getByRole("button", { name: "Применить" });
  await waitFor(() => expect(applyUnit.disabled).toBe(false));
  await user.click(applyUnit);
  await waitFor(() => expect(uiState.unitApplied).toBe(true));

  await user.click(await screen.findByRole("button", { name: "Проверено: оставить все записи" }));
  await waitFor(() => expect(uiState.duplicatesReviewed).toBe(true));

  const save = await screen.findByRole("button", { name: "Сохранить импорт в проект" });
  await user.click(screen.getByRole("button", { name: "Предпросмотр результата" }));
  expect(screen.getByRole("dialog", { name: "Что попадёт в проект" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Закрыть предпросмотр" }));
  await user.click(save);

  await screen.findByRole("heading", { name: "Анализы" });
  expect(applyImportPlan).toHaveBeenCalled();
});
