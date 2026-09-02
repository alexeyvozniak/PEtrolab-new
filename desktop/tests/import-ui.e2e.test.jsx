// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const uiState = vi.hoisted(() => ({ imported: false }));

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
  const emptyProject = { total: 0, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] };
  const importedProject = {
    total: 2,
    source_count: 1,
    import_batch_count: 1,
    latest_import: null,
    analyses: [{
      analysis_id: "analysis-ui-1",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      row_number: 2,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-1", Sample: "KIV-2" },
      source_metadata: {},
      measurements: { SiO2: { raw_token: "40.1", unit: "wt.%" } },
    }],
  };
  return {
    isPetrolabDesktop: () => true,
    getProjectDatabasePath: vi.fn().mockResolvedValue("C:/PetroLab/project.sqlite"),
    listProjectAnalyses: vi.fn().mockImplementation(async () => ({ result: uiState.imported ? importedProject : emptyProject })),
    pickImportFile: vi.fn().mockResolvedValue("C:/fixtures/ui-clean-table.csv"),
    stageImportFile: vi.fn().mockResolvedValue({ local_path: "C:/PetroLab/staging/ui-clean-table.csv", original_path: "C:/fixtures/ui-clean-table.csv" }),
    clearImportStaging: vi.fn().mockResolvedValue(undefined),
    inspectImportSource: vi.fn().mockResolvedValue({ result: { source_format: "csv", source_fingerprint: "0123456789abcdef", sheets: [{ name: "Data" }] } }),
    classifyCleanTable: vi.fn().mockResolvedValue({ result: { mode: "clean_table_fast", clean_table_version: "1", recipe, sections: [{ sheet_name: "Data", analysis_fields: ["Analysis"], measurements: [{ field: "SiO2", unit: "wt.%" }] }], ignored_helper_sheets: [] } }),
    createImportPlan: vi.fn().mockResolvedValue({ result: plan }),
    applyImportPlan: vi.fn().mockImplementation(async () => {
      uiState.imported = true;
      return { result: { analysis_count: 2, measurement_count: 6, source_metadata_count: 0 } };
    }),
    previewImportWindow: vi.fn(),
    suggestImportRecipe: vi.fn(),
    reviseImportMappings: vi.fn(),
    reviseImportSections: vi.fn(),
    reviewImportDuplicates: vi.fn(),
    retractLastImport: vi.fn(),
  };
});

import { applyImportPlan, pickImportFile } from "../src/desktopApi";
import { App } from "../src/App";

afterEach(() => {
  uiState.imported = false;
  cleanup();
});

test("user clicks through Clean Table import and sees the saved Analysis", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  const importButton = await screen.findByRole("button", { name: "Импортировать таблицу" });
  expect(pickImportFile).toHaveBeenCalledOnce();

  await user.click(importButton);
  await screen.findByRole("heading", { name: "Анализы" });
  await screen.findByText("Windows UI smoke");
  expect(screen.getByText("UI-1")).toBeTruthy();
  expect(applyImportPlan).toHaveBeenCalledWith(
    "C:/PetroLab/project.sqlite",
    "C:/PetroLab/staging/ui-clean-table.csv",
    expect.any(Object),
  );
  await waitFor(() => expect(uiState.imported).toBe(true));
});
