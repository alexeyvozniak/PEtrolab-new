// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const uiState = vi.hoisted(() => ({ imported: false, mode: "clean", detailsEnabled: true, unitApplied: false, duplicatesReviewed: false }));

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
  return {
    isPetrolabDesktop: () => true,
    getProjectDatabasePath: vi.fn().mockResolvedValue("C:/PetroLab/project.sqlite"),
    listProjectAnalyses: vi.fn().mockImplementation(async () => ({ result: uiState.imported ? importedProject : emptyProject })),
    pickImportFile: vi.fn().mockImplementation(async () => uiState.mode === "clean" ? "C:/fixtures/ui-clean-table.csv" : "C:/fixtures/complex-workbook.xlsx"),
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
      return { result: { recipe: currentComplexRecipe(), plan: complexPlan(), duplicate_review: { candidate_group_count: 1 } };
    }),
    applyImportPlan: vi.fn().mockImplementation(async () => {
      uiState.imported = true;
      return { result: { analysis_count: 2, measurement_count: 6, source_metadata_count: 0 } };
    }),
    reviseImportMappings: vi.fn(),
    retractLastImport: vi.fn(),
  };
});

import { applyImportPlan, pickImportFile } from "../src/desktopApi";
import { App } from "../src/App";

afterEach(() => {
  uiState.imported = false;
  uiState.mode = "clean";
  uiState.detailsEnabled = true;
  uiState.unitApplied = false;
  uiState.duplicatesReviewed = false;
  vi.clearAllMocks();
  cleanup();
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
  expect(within(sourceTable).getByText("Analysis")).toBeTruthy();
  expect(within(sourceTable).getByText("SiO2")).toBeTruthy();
  expect(within(sourceTable).getByText("Sigma")).toBeTruthy();
  expect(screen.getByText("Колонка с данными не имеет заголовка · 3 мест")).toBeTruthy();
});

test("user resolves a repeated complex workbook with sheet-level and grouped decisions", async () => {
  uiState.mode = "complex";
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  await screen.findByRole("heading", { name: "Импорт таблиц" });

  expect(screen.getByRole("button", { name: /Не импортировать лист Details/ })).toBeTruthy();
  expect(screen.getAllByText("Details").length).toBe(1);
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
