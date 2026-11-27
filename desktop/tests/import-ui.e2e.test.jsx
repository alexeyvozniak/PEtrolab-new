// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalysesWorkspace } from "../src/AnalysesWorkspace";
import { ImportMappingEditor } from "../src/ImportMappingEditor";
import { MediaViewer } from "../src/MediaWorkspace";
import { SampleWorkspace } from "../src/SampleWorkspace";
import { ThinSectionLinks } from "../src/ThinSectionLinks";
import { useState } from "react";

test("thin section precision zoom loads original pixels and places in original coordinates", async () => {
  const loadRegion = vi.fn(async (region) => ({ region, preview_url: "/region.png" }));
  const onPlace = vi.fn();
  const { container } = render(<MediaViewer image={{ width_px: 1000, height_px: 500, preview_url: "/overview.jpg" }}
    annotations={[]} loadRegion={loadRegion} onPlace={onPlace} />);
  const viewport = container.querySelector(".media-viewer");
  const scene = container.querySelector(".media-scene");
  const svg = screen.getByLabelText("Аннотации изображения");
  const rect = () => ({ left: 0, top: 0, width: parseInt(scene.style.width) * 4, height: parseInt(scene.style.width) * 2 });
  Object.defineProperties(viewport, { clientWidth: { value: 400 }, clientHeight: { value: 200 } });
  scene.getBoundingClientRect = rect;
  svg.getBoundingClientRect = () => ({ ...rect(), left: -viewport.scrollLeft, top: -viewport.scrollTop });
  fireEvent.change(screen.getByRole("slider", { name: "Масштаб изображения" }), { target: { value: "2000" } });
  expect(screen.getByText("Масштаб 2000%")).toBeTruthy();
  await waitFor(() => expect(container.querySelector(".media-precision-region")).toBeTruthy());
  expect(loadRegion).toHaveBeenLastCalledWith({ left: 474, top: 236, width: 52, height: 27 });
  fireEvent(svg, new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 200, clientY: 100 }));
  expect(onPlace).toHaveBeenCalledExactlyOnceWith({ kind: "point", x_px: 500, y_px: 250 });
});

test("reopening a thin section and choosing a saved point centres on its original pixels", async () => {
  const sample = { sample_id: "sample", sample_name: "KIV-2", minerals: [], analysis_count: 0, context: {}, notes: [], sources: [],
    thin_sections: [{ thin_section_id: "section", thin_section_name: "TS1" }], images: [
      { thin_section_id: "section", media_asset_id: "view", display_name: "bse.png", media_type: "BSE", width_px: 1000, height_px: 500 },
      { thin_section_id: null, media_asset_id: "other", display_name: "field.png", media_type: "Другое" },
    ] };
  const annotation = { spatial_annotation_id: "saved-point", geometry_kind: "point", point_name: "P-07", x_px: 750, y_px: 125 };
  const area = { spatial_annotation_id: "saved-area", geometry_kind: "rectangle", label: "Z-01",
    x_px: 200, y_px: 100, width_px: 400, height_px: 200 };
  const previewMedia = vi.fn(async (_id, region) => region ? { region, preview_url: "/region.png" }
    : { width_px: 1000, height_px: 500, preview_url: "/overview.jpg", annotations: [annotation, area] });
  const props = { initialTab: "Шлифы", loadSamples: async () => [sample], loadSample: async () => sample, previewMedia };
  const user = userEvent.setup();
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const { container, unmount } = render(<SampleWorkspace {...props} />);
    await user.click(await screen.findByText("TS1"));
    expect(screen.queryByText("field.png")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Открыть" }));
    const point = await screen.findByRole("button", { name: "P-07" });
    const viewport = container.querySelector(".media-viewer");
    const scene = container.querySelector(".media-scene");
    Object.defineProperties(viewport, { clientWidth: { value: 400 }, clientHeight: { value: 200 } });
    scene.getBoundingClientRect = () => ({ width: parseInt(scene.style.width) * 4, height: parseInt(scene.style.width) * 2 });
    await user.click(point);
    expect(point.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("slider", { name: "Масштаб изображения" }).value).toBe("2000");
    expect(screen.getByLabelText("Аннотации изображения").querySelector("circle").getAttribute("cx")).toBe("750");
    await waitFor(() => expect(previewMedia).toHaveBeenLastCalledWith("view", { left: 724, top: 111, width: 52, height: 27 }));
    await user.click(screen.getByRole("button", { name: "Z-01" }));
    expect(screen.getByRole("slider", { name: "Масштаб изображения" }).value).toBe("200");
    expect({ left: viewport.scrollLeft, top: viewport.scrollTop }).toEqual({ left: 120, top: 60 });
    expect(screen.getByLabelText("Аннотации изображения").querySelector("rect").getAttribute("width")).toBe("400");
    unmount();
    previewMedia.mockClear();
  }
});

function SelectionTestWorkspace(props) {
  const [selectedIds, setSelectedIds] = useState([]);
  return <AnalysesWorkspace {...props} selectedIds={selectedIds} setSelectedIds={setSelectedIds} />;
}

test("thin section links EPMA and LA-ICP-MS together and only adds an explicitly chosen analysis to selection", async () => {
  const point = { analytical_point_id: "point", point_sample_id: "sample", point_name: "P-07" };
  const analyses = [{ analysis_id: "epma", identity: "A1", method: "EPMA", active: true },
    { analysis_id: "laser", identity: "A2", method: "LA-ICP-MS", active: true }];
  let links = [];
  const loadPoint = vi.fn(async () => links);
  const queryProject = vi.fn(async () => ({ analyses, has_more: false }));
  const changeLink = vi.fn(async (_, ids, type) => {
    links = type ? analyses.filter((row) => ids.includes(row.analysis_id)) : links.filter((row) => row.analysis_id !== ids);
  });
  const addToSelection = vi.fn();
  const user = userEvent.setup();
  render(<ThinSectionLinks point={point} actions={{ loadPoint, changeLink, queryProject, addToSelection, selectedIds: ["prior"] }} />);
  await screen.findByText("У этой точки нет связанных анализов.");
  expect(addToSelection).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Найти существующие анализы" }));
  await user.click(await screen.findByRole("checkbox", { name: "Отметить A1" }));
  await user.click(screen.getByRole("checkbox", { name: "Отметить A2" }));
  expect(queryProject).toHaveBeenCalledWith(expect.objectContaining({ sample_id: "sample" }));
  await user.click(screen.getByRole("button", { name: "Связать отмеченные анализы (2)" }));
  expect(changeLink).toHaveBeenCalledExactlyOnceWith("point", ["epma", "laser"], "same_point", "Локальный пользователь");
  await screen.findByText("A2");
  expect(addToSelection).not.toHaveBeenCalled();
  const row = screen.getByText("A1").closest("li");
  await user.click(within(row).getByRole("button", { name: "Добавить в отбор" }));
  expect(addToSelection).toHaveBeenCalledExactlyOnceWith("epma");
  await user.click(within(row).getByRole("button", { name: "Снять связь" }));
  await screen.findByText("Связь снята.");
  await waitFor(() => expect(screen.queryByText("A1")).toBeNull());
  expect(screen.getByText("A2")).toBeTruthy();
});

test("drag, Shift and Ctrl select stable analysis IDs without changing focus semantics", () => {
  const analyses = Array.from({ length: 34 }, (_, index) => ({
    analysis_id: `id-${index + 1}`, source_id: "source", source_name: "ranges.xlsx", sheet_name: "Sheet",
    source_row_number: index + 2, identity: { Analysis: `A-${index + 1}` }, measurements: {}, source_metadata: {},
  }));
  render(<SelectionTestWorkspace project={{ total: 34, source_count: 1, analyses }} busy={false} />);
  const table = within(screen.getByRole("table"));
  const cell = (index) => table.getByRole("cell", { name: `A-${index}`, exact: true });
  const checkbox = (index) => table.getByRole("checkbox", { name: `Выбрать A-${index}`, exact: true });
  const names = () => table.getAllByRole("checkbox").filter((item) => item.checked).map((item) => item.getAttribute("aria-label"));
  fireEvent.click(cell(3));
  expect(names()).toEqual([]);
  fireEvent(checkbox(8), new MouseEvent("pointerdown", { bubbles: true, button: 0, buttons: 1 }));
  fireEvent(cell(17), new MouseEvent("pointerover", { bubbles: true, buttons: 1 }));
  fireEvent(window, new MouseEvent("pointerup", { bubbles: true, button: 0 }));
  expect(names()).toEqual(Array.from({ length: 10 }, (_, index) => `Выбрать A-${index + 8}`));
  fireEvent.click(cell(19), { shiftKey: true });
  expect(names()).toEqual(Array.from({ length: 12 }, (_, index) => `Выбрать A-${index + 8}`));
  fireEvent.click(cell(27), { ctrlKey: true });
  expect(names()).toEqual([...Array.from({ length: 12 }, (_, index) => `Выбрать A-${index + 8}`), "Выбрать A-27"]);
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "A-27" } });
  expect(screen.getByText("Скрыто фильтром: 12")).toBeTruthy();
});

test("large table virtualizes rows while selection, search and keyboard cover the full loaded result", () => {
  const analyses = Array.from({ length: 1000 }, (_, index) => ({
    analysis_id: "row-" + index, source_id: "source", source_name: "large.xlsx", sheet_name: "Sheet",
    source_row_number: index + 2, identity: { Analysis: "V-" + String(index + 1).padStart(4, "0") },
    measurements: { SiO2: { raw_token: "40", numeric_value: 40, unit: "wt.%",source_cell:"B"+(index+2) } }, source_metadata: {},
  }));
  render(<SelectionTestWorkspace project={{ total: 1000, source_count: 1, analyses }} busy={false} />);
  const table = screen.getByRole("table");
  const scroll = screen.getByLabelText(/Таблица анализов: Ctrl\+A/);
  Object.defineProperty(scroll, "clientHeight", { value: 420, configurable: true });
  expect(table.getAttribute("aria-rowcount")).toBe("1002");
  expect(table.querySelectorAll("tbody tr:not(.analysis-row-spacer)").length).toBeLessThan(60);
  expect(within(table).queryByRole("checkbox", { name: "Выбрать V-1000" })).toBeNull();
  fireEvent.click(screen.getByText("Колонки",{exact:false}).closest("summary"));
  const pin = screen.getByLabelText("Закреплённая колонка");
  fireEvent.change(pin,{target:{value:"identity:Analysis"}});
  expect(table.querySelector("thead tr:first-child th:nth-child(2)").classList.contains("analysis-pinned-column")).toBe(true);
  expect(table.querySelector("tbody tr:not(.analysis-row-spacer) td:nth-child(2)").textContent).toBe("V-0001");
  const secondPin=screen.getByLabelText("Закреплённая колонка 2");
  fireEvent.change(secondPin,{target:{value:"source"}});
  expect(table.querySelectorAll("thead tr:first-child th.analysis-pinned-column")).toHaveLength(2);
  expect(table.querySelector("thead tr:first-child th:nth-child(3)").style.left).toBe("192px");
  fireEvent.change(secondPin,{target:{value:""}});
  expect(table.querySelectorAll("thead tr:first-child th.analysis-pinned-column")).toHaveLength(1);
  fireEvent.keyDown(scroll, { key: "a", ctrlKey: true });
  expect(screen.getByText("1000 выбрано")).toBeTruthy();
  fireEvent.keyDown(scroll, { key: "End" });
  expect(within(table).getByRole("checkbox", { name: "Выбрать V-1000" }).checked).toBe(true);
  expect(table.querySelectorAll("tbody tr:not(.analysis-row-spacer)").length).toBeLessThan(60);
  fireEvent.change(screen.getByRole("textbox", { name: "Поиск анализов" }), { target: { value: "V-1000" } });
  expect(within(table).getByRole("checkbox", { name: "Выбрать V-1000" }).checked).toBe(true);
  expect(screen.getByText("Скрыто фильтром: 999")).toBeTruthy();
  expect(screen.getByText("1000 выбрано")).toBeTruthy();
  expect(table.querySelector("tbody tr:not(.analysis-row-spacer) td.analysis-pinned-column").textContent).toBe("V-1000");
  fireEvent.contextMenu(table.querySelector('td[data-source-cell="B1001"]'),{clientX:100,clientY:100});
  fireEvent.click(screen.getByRole("menuitem",{name:"Показать исходную ячейку B1001"}));
  expect(document.activeElement.dataset.sourceCell).toBe("B1001");
  expect(document.activeElement.classList.contains("provenance-focused")).toBe(true);
  expect(screen.getByText("1000 выбрано")).toBeTruthy();
  fireEvent.change(pin,{target:{value:""}});
  expect(table.querySelector(".analysis-pinned-column")).toBeNull();
});

test("same-named sources filter independently without changing selection", async () => {
  const user = userEvent.setup();
  const analyses = [
    { analysis_id: "a1", source_id: "source-1", source_name: "same.xlsx", sheet_name: "Sheet 1", source_row_number: 2, identity: { Analysis: "A1" }, measurements: {}, source_metadata: {} },
    { analysis_id: "a2", source_id: "source-2", source_name: "same.xlsx", sheet_name: "Sheet 2", source_row_number: 2, identity: { Analysis: "A2" }, measurements: {}, source_metadata: {} },
  ];
  render(<SelectionTestWorkspace project={{ total: 2, source_count: 2, analyses }} busy={false} />);
  await user.click(screen.getByRole("checkbox", { name: "Выбрать A1" }));
  await user.click(screen.getByRole("button", { name: /same\.xlsx · source-2/ }));
  expect(screen.queryByRole("checkbox", { name: "Выбрать A1" })).toBeNull();
  expect(screen.getByRole("checkbox", { name: "Выбрать A2" })).toBeTruthy();
  expect(screen.getByText("1 выбрано")).toBeTruthy();
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: /same\.xlsx · source-1/ }));
  expect(screen.getByRole("checkbox", { name: "Выбрать A1" }).checked).toBe(true);
  expect(screen.queryByText("Скрыто фильтром: 1")).toBeNull();
  expect(screen.queryByRole("checkbox", { name: "Выбрать A2" })).toBeNull();
});

const uiState = vi.hoisted(() => ({ imported: false, mode: "clean", detailsEnabled: true, unitApplied: false, duplicatesReviewed: false }));

test("categorical and logical filters compose with a unit-specific numeric condition", async () => {
  const user = userEvent.setup();
  const analyses = [["A1", "verified", "ppm", true], ["A2", "conflict", "wt.%", true], ["A3", "not_checked", "ppm", false]]
    .map(([id, status, unit, linked]) => ({
      analysis_id: id, source_id: "source", source_name: "mixed.xlsx", sheet_name: "Sheet", identity: { Analysis: id },
      mineral_verification: { status }, sample_association: { sample_id: linked ? "sample" : null },
      measurements: { F: { raw_token: "5", numeric_value: 5, unit } },
    }));
  render(<SelectionTestWorkspace project={{ total: 3, source_count: 1, analyses }} busy={false} />);
  await user.click(screen.getByText("Статус минерала", { exact: true }));
  await user.type(screen.getByRole("searchbox", { name: "Поиск статусов минерала" }), "конфликт");
  await user.click(screen.getByRole("checkbox", { name: "конфликт", exact: true }));
  await user.clear(screen.getByRole("searchbox", { name: "Поиск статусов минерала" }));
  await user.click(screen.getByRole("checkbox", { name: "принято", exact: true }));
  const table = within(screen.getByRole("table"));
  expect(table.queryByText("A3")).toBeNull();
  const numeric = table.getByRole("textbox", { name: "Фильтр F" });
  await user.type(numeric, "> 0");
  expect(numeric.getAttribute("aria-invalid")).toBe("true");
  await user.type(numeric, " ppm");
  expect(numeric.getAttribute("aria-invalid")).toBe("false");
  expect(table.getByText("A1")).toBeTruthy();
  expect(table.queryByText("A2")).toBeNull();
  await user.selectOptions(screen.getByRole("combobox", { name: "Связь с физическим образцом" }), "unlinked");
  expect(table.queryByText("A1")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
  expect(table.getByText("A3")).toBeTruthy();
});

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
      source_id: "source-ui",
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
      source_id: "source-ui",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      source_row_number: 3,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-2", Sample: "KIV-3" },
      source_metadata: { Comment: "control" },
      measurements: { SiO2: { raw_token: "39.8", unit: "wt.%", source_cell: "C3" } },
    }],
  };
  const api = {
    isPetrolabDesktop: () => true,
    getProjectDatabasePath: vi.fn().mockResolvedValue("C:/PetroLab/project.sqlite"),
    getProjectPlotPresets: vi.fn().mockResolvedValue({result:{preferences:{favorites:[],recent:[]},revision:0}}),
    saveProjectPlotPresets: vi.fn().mockImplementation(async (_path,preferences,revision)=>({result:{preferences,revision:revision+1}})),
    getProjectPlotColors: vi.fn().mockResolvedValue({result:{scheme:{mode:"source",colors:[]},revision:0}}),
    saveProjectPlotColors: vi.fn().mockImplementation(async (_path,scheme,revision)=>({result:{scheme,revision:revision+1}})),
    getSelectionSummary: vi.fn().mockResolvedValue({result:{analysis_count:0,pair:null,rows:[]}}),
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
    commitImportWorkspace: vi.fn().mockImplementation(async () => {
      uiState.imported = true;
      return { result: { analysis_count: 2, measurement_count: 6, staged_paths: [] } };
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
  api.restoreImportWorkspace = vi.fn(async () => ({ result: { workspace: null } }));
  api.getProjectOverview = vi.fn(async () => ({ result: { project_name: "QA", recent_imports: [], recent_groups: [] } }));
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

import { commitImportWorkspace, pickImportFile, createImportPlan } from "../src/desktopApi";
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
  const previewSearch = within(preview).getByRole("textbox", { name: "Поиск в результате импорта" });
  await user.clear(previewSearch);
  expect(within(preview).getByText("UI-1")).toBeTruthy();
  await user.type(previewSearch, "uI-1");
  expect(within(preview).getByText("UI-1")).toBeTruthy();
  expect(within(preview).queryByText("UI-2")).toBeNull();
  await user.type(previewSearch, "-not-found");
  expect(within(preview).getByText("По этому запросу записей нет.")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Что попадёт в проект" })).toBeNull();

  await user.click(importButton);
  await screen.findByRole("heading", { name: "Анализы" });
  expect((await screen.findAllByText("Windows UI smoke")).length).toBeGreaterThan(1);
  expect(screen.getAllByText("UI-1").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Trace-15").length).toBeGreaterThan(0);

  const analysisTable = screen.getByLabelText(/Таблица анализов: Ctrl\+A/);
  analysisTable.focus();
  await user.keyboard("{Control>}a{/Control}");
  expect(screen.getByText("2 выбрано")).toBeTruthy();
  const clipboard = { setData: vi.fn() };
  fireEvent.copy(analysisTable, { clipboardData: clipboard });
  expect(clipboard.setData).toHaveBeenCalledOnce();
  const copied = clipboard.setData.mock.calls[0][1];
  expect(copied).toContain("UI-1");
  expect(copied).toContain("UI-2");
  expect(copied).toContain("SiO2 · единица");
  await user.keyboard("{Escape}");
  expect(screen.queryByText("2 выбрано")).toBeNull();
  await user.keyboard("{Control>}z{/Control}");
  expect(screen.getByText("2 выбрано")).toBeTruthy();
  await user.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
  expect(screen.queryByText("2 выбрано")).toBeNull();
  await user.keyboard("{F1}");
  expect(screen.getByRole("dialog", { name: "Горячие клавиши PetroLab" })).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Горячие клавиши PetroLab" })).toBeNull();
  analysisTable.focus();
  await user.keyboard("{Control>}f{/Control}");
  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Поиск анализов" }));
  await user.type(document.activeElement, "UI-2");
  expect(screen.queryByRole("checkbox", { name: "Выбрать UI-1" })).toBeNull();
  await user.keyboard("{Escape}");
  fireEvent.contextMenu(screen.getByRole("checkbox", { name: "Выбрать UI-1" }).closest("tr"), { clientX: 100, clientY: 100 });
  const menu = screen.getByRole("menu", { name: "UI-1" });
  await user.click(within(menu).getByRole("menuitem", { name: "Добавить анализ в отбор" }));
  expect(screen.getByText("1 выбрано")).toBeTruthy();
  await user.keyboard("{Control>}k{/Control}");
  const palette = screen.getByRole("dialog", { name: "Быстрые команды PetroLab" });
  await user.type(within(palette).getByRole("textbox", { name: "Найти команду" }), "нет такой команды");
  expect(within(palette).getByText("Команды не найдены.")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Быстрые команды PetroLab" })).toBeNull();
  const nav = within(screen.getByRole("navigation"));
  await user.click(nav.getByRole("button", { name: "Импорт" }));
  await user.click(nav.getByRole("button", { name: "Анализы" }));
  expect(screen.getByRole("checkbox", { name: "Выбрать UI-1" }).checked).toBe(true);

  const search = screen.getByRole("textbox", { name: "Поиск анализов" });
  const resizer = screen.getByRole("separator", { name: "Ширина колонки SiO2" });
  resizer.focus();
  await user.keyboard("{ArrowRight}");
  expect(resizer.getAttribute("aria-valuenow")).toBe("120");
  await user.type(search, "KIV-3");
  await user.click(nav.getByRole("button", { name: "Импорт" }));
  await user.click(nav.getByRole("button", { name: "Анализы" }));
  expect(screen.getByRole("textbox", { name: "Поиск анализов" }).value).toBe("KIV-3");
  expect(screen.getByRole("separator", { name: "Ширина колонки SiO2" }).getAttribute("aria-valuenow")).toBe("120");
  const table = screen.getByRole("table");
  expect(within(table).getByText("UI-2")).toBeTruthy();
  expect(within(table).queryByText("UI-1")).toBeNull();
  await user.clear(screen.getByRole("textbox", { name: "Поиск анализов" }));
  expect(commitImportWorkspace).toHaveBeenCalledWith("workspace-1", expect.any(Number));
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
  expect(commitImportWorkspace).not.toHaveBeenCalled();
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
  expect(commitImportWorkspace).toHaveBeenCalled();
});


test("recognized bare element mappings use one confirmed unit even when the warning list is filtered",()=>{
  const onApplyAll=vi.fn();
  const symbols=["O","Si","Ti","Al","Fe","Mn","Mg","Ca","Na","K","Ba","Cr","Ni","P","V"];
  const recognized=symbols.map((field,index)=>({source_axis:"column",source_column_index:index,source_header:field,
    target_role:"ignore",canonical_field:null,suggested_target:"measurement",suggested_canonical_field:field,review_decision:"unresolved"}));
  const ignored={...recognized[0],source_column_index:15,source_header:"O",review_decision:"explicit_ignore"};
  const unknown={source_axis:"column",source_column_index:16,source_header:"Comment2",target_role:"ignore",review_decision:"unresolved"};
  const assigned={source_axis:"column",source_column_index:17,source_header:"La (ppm)",target_role:"measurement",canonical_field:"La",unit:"ppm",review_decision:"recognized"};
  const recipe={sections:[{block_id:"mica",sheet_name:"слюды",enabled:true,orientation:"rows_are_analyses",header_row:1,mappings:[...recognized,ignored,unknown,assigned]}]};
  render(<ImportMappingEditor recipe={recipe} warnings={[]} onApplyAll={onApplyAll}/>);
  expect(screen.getAllByRole("combobox",{name:"Что это"}).filter(node=>node.value==="Measurement")).toHaveLength(15);
  fireEvent.change(screen.getByLabelText("Общая единица распознанных компонентов: слюды"),{target:{value:"at.%"}});
  fireEvent.click(screen.getByRole("button",{name:"Назначить полям без единицы"}));
  fireEvent.click(screen.getByRole("button",{name:"Применить сопоставление (15)"}));
  expect(onApplyAll).toHaveBeenCalledOnce();
  expect(onApplyAll.mock.calls[0][0].map(({canonical_field,unit,source_index})=>[canonical_field,unit,source_index])).toEqual(symbols.map((field,index)=>[field,"at.%",index]));
});

test("workbook bulk units select matching enabled structures and preserve different sheets",()=>{
  const onApplyAll=vi.fn();
  const suggestion=(field,index)=>({source_axis:"column",source_column_index:index,source_header:field,target_role:"ignore",suggested_target:"measurement",suggested_canonical_field:field,review_decision:"unresolved"});
  const section=(id,name,fields,enabled=true)=>({block_id:id,sheet_name:name,enabled,orientation:"rows_are_analyses",header_row:1,mappings:fields.map(suggestion)});
  const recipe={sections:[section("a","Mica I",["Si","Mg","Fe"]),section("b","Mica II",["Si","Mg","Fe"]),section("c","Trace",["La","Yb"]),section("d","Excluded",["Si","Mg","Fe"],false)]};
  render(<ImportMappingEditor recipe={recipe} warnings={[]} activeBlockId="a" onApplyAll={onApplyAll}/>);
  fireEvent.click(screen.getByText(/Распознавание по всей книге/));
  fireEvent.click(screen.getByRole("button",{name:"Выбрать блоки такой же структуры"}));
  const blocks=within(screen.getByLabelText("Блоки книги для назначения единицы"));
  expect(blocks.getAllByRole("checkbox").map(node=>node.checked)).toEqual([true,true,false]);
  expect(blocks.queryByText(/Excluded/)).toBeNull();
  fireEvent.change(screen.getByLabelText("Общая единица выбранных блоков"),{target:{value:"at.%"}});
  fireEvent.click(screen.getByRole("button",{name:"Назначить единицу · 6 полей в 2 блоках"}));
  fireEvent.click(screen.getByRole("button",{name:"Применить сопоставление (6)"}));
  expect(onApplyAll).toHaveBeenCalledOnce();
  expect(onApplyAll.mock.calls[0][0].map(({block_id,canonical_field,unit})=>[block_id,canonical_field,unit])).toEqual(
    ["a","b"].flatMap(id=>["Si","Mg","Fe"].map(field=>[id,field,"at.%"])));
});
