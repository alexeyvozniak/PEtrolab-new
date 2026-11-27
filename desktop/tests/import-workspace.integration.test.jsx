// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { execFileSync, spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdir, mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const bridge = vi.hoisted(() => ({ invoke: null }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args) => bridge.invoke(...args) }));
import { App } from "../src/App";
import { invokePetrolab, expandWorkspaceReview } from "../src/desktopApi";

test("compact measurement transport restores every value and rejects incomplete rows", () => {
  const plan = { summary: { planned_analysis_count: 1 }, measurement_columns_v1: ["raw_token", "qualifier", "reported_fe_form"],
    planned_records: [{ preview_id: "A1", measurements: [["<DL", "below_detection_limit", null], ["0", null, "FeO"]] }] };
  const input = { workspace: { session: { draft_revision: 3 }, active: { plan } } };
  const restored = expandWorkspaceReview(input);
  expect(restored.workspace.active.plan.planned_records[0].measurements).toEqual([
    { raw_token: "<DL", qualifier: "below_detection_limit", reported_fe_form: null },
    { raw_token: "0", qualifier: null, reported_fe_form: "FeO" },
  ]);
  expect(restored.workspace.active.plan.measurement_columns_v1).toBeUndefined();
  expect(input.workspace.active.plan.measurement_columns_v1).toHaveLength(3);
  expect(expandWorkspaceReview(restored)).toBe(restored);
  expect(() => expandWorkspaceReview({ active: { plan: { ...plan, planned_records: [{ measurements: [["<DL"]] }] } } })).toThrow();
});

configure({ asyncUtilTimeout: 5000 });

let child, folder, first, second, queue, mediaQueue, mediaFolder, original, pending, requests, plotExports, externalUrls;
async function startService() {
  child = spawn("python", ["-m", "petrolab.ndjson_service"], {
    cwd: resolve(process.cwd(), ".."), windowsHide: true,
    env: { ...process.env, PYTHONPATH: resolve(process.cwd(), "../src"), PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8",
      OPENBLAS_NUM_THREADS: "1" },
  });
  const inFlight = new Map();
  pending = inFlight;
  const lines = createInterface({ input: child.stdout });
  lines.on("line", (line) => {
    const response = JSON.parse(line);
    const request = inFlight.get(response.request_id);
    if (request) { inFlight.delete(response.request_id); request.resolve(response); }
  });
  const rejectPending = (error) => {
    for (const request of inFlight.values()) request.reject(error);
    inFlight.clear();
  };
  child.on("error", rejectPending);
  child.stdin.on("error", rejectPending);
  child.once("close", (code, signal) => {
    lines.close();
    rejectPending(new Error(`Python workspace service closed (${code ?? signal})`));
  });
  const readiness = await invokePetrolab("import.inspect_source", { source_path: first });
  expect(readiness.result?.source_fingerprint, JSON.stringify(readiness.error)).toBeTruthy();
}

async function stopService() {
  const service = child;
  if (service.exitCode !== null || service.signalCode !== null) return;
  const closed = new Promise((resolve) => service.once("close", resolve));
  service.stdin.end();
  await closed;
}

beforeEach(async () => {
  folder = await mkdtemp(join(tmpdir(), "petrolab-workspace-ui-"));
  first = join(folder, "first.csv"); second = join(folder, "second.csv");
  original = "Analysis,Fe (wt.%),F (wt.%)\nA1,10,<DL\nA2,11,n.d.\n";
  await writeFile(first, original);
  await writeFile(second, "Analysis,SiO2 [wt.%]\nB1,40\nB2,41\n");
  queue = [first, second]; mediaQueue = []; mediaFolder = null; requests = []; plotExports = [];
  externalUrls = [];
  bridge.invoke = async (command, args) => {
    if (command === "open_external_url") { externalUrls.push(args.url); return; }
    if (command === "project_database_path") return join(folder, "project.sqlite");
    if (command === "pick_import_file") return queue.shift() || null;
    if (command === "pick_media_files") return mediaQueue.splice(0);
    if (command === "pick_media_folder") return mediaFolder;
    if (command === "pick_media_export_path") return join(folder, `copy-${args.name}`);
    if (command === "pick_publication_export_path") return join(folder, "petrolab-package.zip");
    if (command === "pick_analysis_export_path") return join(folder, `selection.${args?.format || "xlsx"}`);
    if (command === "pick_plot_export_path") {
      const destination = join(folder, `diagram-${plotExports.length + 1}-${args.name}`);
      plotExports.push(destination);
      return destination;
    }
    if (command === "stage_import_file") return { local_path: args.sourcePath, original_path: args.sourcePath };
    if (command === "clear_import_staging") return;
    if (command !== "petrolab_command") throw new Error(command);
    requests.push(args.envelope);
    if (!child.stdin.writable) throw new Error(`Python workspace service unavailable for ${args.envelope.command}`);
    return new Promise((resolve, reject) => {
      pending.set(args.envelope.request_id, { command: args.envelope.command, resolve, reject });
      child.stdin.write(JSON.stringify(args.envelope) + "\n");
    });
  };
  window.__TAURI_INTERNALS__ = { invoke: () => {} };
  await startService();
}, 30000);

afterEach(async () => {
  cleanup();
  await stopService();
  delete window.__TAURI_INTERNALS__;
  await rm(folder, { recursive: true, force: true });
});

async function enabledButton(name) {
  return waitFor(() => {
    const button = screen.getByRole("button", { name });
    const outstanding = [...pending.values()].map((request) => request.command);
    expect(button.disabled, `${name} (Python: ${outstanding.join(", ") || "idle"})`).toBe(false);
    return button;
  }, name === "Выбрать файл" ? { timeout: 20000 } : undefined);
}

async function savePlot(user, panelIndex, format = "SVG · Corel-safe") {
  const open = panelIndex === undefined ? await enabledButton("Выгрузить раскладку")
    : screen.getAllByRole("button", { name: "Выгрузить панель" })[panelIndex];
  await user.click(open);
  await user.click(screen.getByRole("radio", { name: format }));
  await user.click(await enabledButton("Сохранить графики"));
  await screen.findByText(/Сохранено: .*diagram-/);
  return plotExports.at(-1);
}

test("real Python workspace retains two sources and mapping, identity repair and raw tokens", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await enabledButton("Добавить файл");
  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  expect(within(await screen.findByRole("table")).getByText("<DL")).toBeTruthy();
  expect(screen.getAllByText(/Форма Fe не определена/).length).toBeGreaterThan(0);
  await user.click(await enabledButton("Добавить файл"));
  await user.click(await enabledButton("Открыть источник first.csv"));
  await user.click(await enabledButton("Все 3"));
  const mapping = screen.getAllByRole("combobox", { name: "Что это" })[0];
  await waitFor(() => expect(mapping.disabled).toBe(false));
  await user.selectOptions(mapping, "Ignore");
  expect(screen.getByRole("button", { name: "Открыть источник second.csv" }).disabled).toBe(true);
  await user.click(await enabledButton(/Применить сопоставление/));
  await screen.findAllByText(/Нет идентичности Analysis/);
  await user.click(await enabledButton("Открыть источник second.csv"));
  await user.click(await enabledButton("Открыть источник first.csv"));
  await user.click(await enabledButton("Все 3"));
  const restored = screen.getAllByRole("combobox", { name: "Что это" })[0];
  await waitFor(() => expect(restored.disabled).toBe(false));
  expect(restored.value).toBe("Ignore");
  await user.selectOptions(restored, "Analysis");
  await user.click(await enabledButton(/Применить сопоставление/));
  await waitFor(() => expect(screen.queryAllByText(/Нет идентичности Analysis/)).toHaveLength(0));
  expect(requests.filter(r => r.command === "import.workspace.commit")).toHaveLength(0);
  expect(await readFile(first, "utf8")).toBe(original);
  expect(within(screen.getByRole("table")).getByText("n.d.")).toBeTruthy();
}, 20000);

test("multisheet review requests only the currently visible physical table", async () => {
  const workbook = join(folder, "multiple.xlsx");
  execFileSync("python", ["-c", "from openpyxl import Workbook; import sys; w=Workbook(); a=w.active; a.title='FirstSheet'; b=w.create_sheet('SecondSheet'); a.append(['Analysis','SiO2 [wt.%]']); a.append(['A1',40]); b.append(['Analysis','SiO2 [wt.%]']); b.append(['B1',41]); w.save(sys.argv[1])", workbook]);
  queue = [workbook];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await enabledButton("Добавить файл");
  const previews = () => requests.filter(r => r.command === "import.workspace.preview_window");
  expect(previews()).toHaveLength(1);
  expect(previews()[0].payload.sheet_name).toBe("FirstSheet");
  await user.click(await enabledButton(/SecondSheet.*Готов/));
  await enabledButton("Добавить файл");
  expect(previews()).toHaveLength(2);
  expect(previews()[1].payload.sheet_name).toBe("SecondSheet");
  expect(requests.find(r => r.command === "import.workspace.apply_decision").payload.known_active_plan?.plan_fingerprint).toMatch(/^[a-f0-9]{64}$/);
  expect(within(await screen.findByRole("table")).getByText("B1")).toBeTruthy();
  await user.click(await enabledButton(/FirstSheet.*Готов/));
  await enabledButton("Добавить файл");
  expect(previews()).toHaveLength(3);
  expect(within(await screen.findByRole("table")).getByText("A1")).toBeTruthy();
  await user.click(await enabledButton("Предпросмотр результата"));
  const preview = screen.getByRole("dialog", { name: "Что попадёт в проект" });
  expect(within(preview).getByText("A1")).toBeTruthy();
  expect(within(preview).getByText("B1")).toBeTruthy();
}, 20000);

test("import stage indicator follows real awaited operations and clears after completion", async () => {
  queue = [second];
  const invoke = bridge.invoke;
  let release;
  bridge.invoke = async (command, args) => {
    if (command === "stage_import_file") await new Promise(resolve => { release = resolve; });
    return invoke(command, args);
  };
  try {
    render(<App />);
    fireEvent.click(await enabledButton("Выбрать файл"));
    const stage = await screen.findByText("2/4 · Копирую файл в рабочую область PetroLab…");
    expect(stage.closest('[role="status"]')).toBeTruthy();
    expect(screen.queryByText(/3\/4 · Распознаю/)).toBeNull();
    release();
    await enabledButton("Импортировать таблицу");
    expect(screen.queryByText(/4\/4 · Открываю предпросмотр/)).toBeNull();
  } finally {
    release?.();
    bridge.invoke = invoke;
  }
}, 20000);

test("real Python clean single-source still commits and displays persisted analyses", async () => {
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  expect((await screen.findAllByText("B1")).length).toBeGreaterThan(0);
  expect(screen.getAllByText("B2").length).toBeGreaterThan(0);
  expect(requests.filter(r => r.command === "import.workspace.commit")).toHaveLength(1);
}, 20000);

test("AT-26 marks search ranges, distinguishes a page from all results and journals exact visibility", async () => {
  const content = "Analysis,SiO2 [wt.%],Al2O3 [wt.%]\n"
    + Array.from({ length: 34 }, (_, index) => `P${String(index + 1).padStart(2, "0")},${index + 2},${index + 3}\n`).join("");
  await writeFile(first, content);
  const database = { project_database_path: join(folder, "project.sqlite") };
  const { result: { recipe } } = await invokePetrolab("import.recipe.suggest", { source_path: first });
  const imported = await invokePetrolab("import.plan.apply", { ...database, source_path: first, recipe });
  expect(imported.result.analysis_count).toBe(34);
  const outside = await invokePetrolab("import.recipe.suggest", { source_path: second });
  expect((await invokePetrolab("import.plan.apply", { ...database, source_path: second,
    recipe: outside.result.recipe })).result.analysis_count).toBe(2);
  const view = userEvent.setup();
  render(<App />);
  await view.click(await enabledButton("Поиск"));
  await screen.findByText(/Найдено анализов: 36/);
  await view.type(screen.getByLabelText("Источник", { exact: true }), "first.csv");
  await view.click(await enabledButton("Найти"));
  await screen.findByText(/Найдено анализов: 34/);
  const check = (number) => screen.getByRole("checkbox", { name: `Отметить P${String(number).padStart(2, "0")}` });
  const pointer = (node, type, buttons) => {
    const event = new MouseEvent(type, { bubbles: true, button: 0, buttons });
    Object.defineProperty(event, "pointerId", { value: 7 });
    fireEvent(node, event);
  };
  pointer(check(2), "pointerdown", 1);
  pointer(check(11).closest("tr"), "pointerover", 1);
  pointer(window, "pointerup", 0);
  await screen.findByText(/Отмечено: 10\. В отборе: 0/);
  fireEvent.click(check(13), { shiftKey: true });
  await screen.findByText(/Отмечено: 12\. В отборе: 0/);
  fireEvent.click(check(16), { ctrlKey: true });
  await screen.findByText(/Отмечено: 13\. В отборе: 0/);
  const markedRows = within(screen.getByRole("table")).getAllByRole("row").slice(1, 14);
  expect(markedRows.every((row) => row.classList.contains("marked"))).toBe(true);
  await view.click(await enabledButton("Скрыть отмеченные на графиках"));
  await screen.findByText(/Отмечено: 13\. В отборе: 0\. Скрыто на графиках из отмеченных: 13/);
  const hide = requests.find(({ command }) => command === "plot_visibility.hide");
  const snapshot = (await invokePetrolab("analysis.query.ids", { ...database, source: "first.csv" })).result.analysis_ids;
  const scope = [...snapshot.slice(1, 13), snapshot[15]];
  expect(hide.payload.analysis_ids).toEqual(scope);
  await view.click(await enabledButton("Вернуть отмеченные на графики"));
  expect(requests.find(({ command }) => command === "plot_visibility.restore").payload.analysis_ids).toEqual(scope);
  const journal = (await invokePetrolab("operation_journal.list", { ...database, category: "view_only" })).result.entries;
  expect(journal.map(({ action, scope_count }) => [action, scope_count]))
    .toEqual([["restore_plot_points", 13], ["hide_plot_points", 13]]);
  for (const { id } of journal) {
    const record = (await invokePetrolab("operation_journal.open", { ...database, operation_id: id })).result;
    expect(record.scope.map(({ entity_id }) => entity_id)).toEqual(scope);
  }
  await view.click(await enabledButton("Добавить отмеченные в отбор"));
  await screen.findByText(/Отмечено: 13\. В отборе: 13/);
  await view.click(screen.getByText("Отметки", { exact: true }));
  await view.click(await enabledButton("Снять отметки"));
  await view.selectOptions(screen.getByRole("combobox", { name: "Показывать по" }), "10");
  await view.click(await enabledButton("Выбрать видимые · 10"));
  await screen.findByText(/Отмечено: 10\. В отборе: 13/);
  await view.click(await enabledButton("Выбрать весь результат · 34"));
  await screen.findByText(/Отмечено: 34\. В отборе: 13/);
  await view.click(await enabledButton("Далее"));
  await waitFor(() => expect(check(11).checked).toBe(true));
  await view.click(screen.getByLabelText("Другие действия с отмеченными"));
  await view.click(await enabledButton("Сохранить как рабочую группу"));
  const groupForm = within(screen.getByRole("form", { name: "Новая рабочая группа" }));
  expect(groupForm.getByText("Новая рабочая группа · 34")).toBeTruthy();
  await view.type(groupForm.getByLabelText("Название"), "Все совпадения");
  await view.type(groupForm.getByLabelText("Автор"), "QA");
  await view.click(groupForm.getByRole("button", { name: "Сохранить группу" }));
  await screen.findByText("Сохранена группа «Все совпадения» · записей: 34.");
  const groups = (await invokePetrolab("work_group.list", database)).result.groups;
  expect(groups.find(({ group }) => group.name === "Все совпадения").group.analysis_ids).toEqual(snapshot);
  await view.click(await enabledButton("Назначить Generation"));
  const assignmentForm = within(await screen.findByRole("form", { name: "Назначение Generation" }));
  expect(assignmentForm.getByText("Назначение Generation · 34")).toBeTruthy();
  await view.type(assignmentForm.getByLabelText("Название"), "Rim");
  await view.click(assignmentForm.getByRole("button", { name: "Назначить", exact: true }));
  await view.click(await enabledButton("Отменить назначение Generation"));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Отменить назначение Generation" })).toBeNull());
  expect(requests.find(({ command }) => command === "generation.assign").payload.analysis_ids).toEqual(snapshot);
  await screen.findByText(/Найдено анализов: 34\. Отмечено: 34\. В отборе: 13/);
  await view.click(await enabledButton("Построить диаграммы"));
  await screen.findAllByRole("button", { name: "Выбрать точку P34" });
  expect(requests.findLast(({ command }) => command === "plot_data.query").payload.analysis_ids).toEqual(snapshot);
  expect(screen.getByText("Выбранные анализы · 13")).toBeTruthy();
  expect(await readFile(first, "utf8")).toBe(content);
}, 30000);

test("AT-01 overview keeps an edited and completed plan task after restarting", async () => {
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Добавить задачу"));
  await user.type(screen.getByLabelText("Задача", { exact: true }), "Проверить импорт");
  await user.click(await enabledButton("Сохранить задачу"));
  await screen.findByRole("checkbox", { name: "Проверить импорт" });
  await user.click(await enabledButton("Редактировать план работы"));
  await user.click(await enabledButton("Изменить задачу: Проверить импорт"));
  const title = screen.getByLabelText("Задача", { exact: true });
  await user.clear(title);
  await user.type(title, "Проверить EPMA");
  await user.click(await enabledButton("Сохранить задачу"));
  await user.click(await screen.findByRole("checkbox", { name: "Проверить EPMA" }));
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "Проверить EPMA" }).checked).toBe(true));
  const database = { project_database_path: join(folder, "project.sqlite") };
  const plan = (await invokePetrolab("project.overview", database)).result.work_plan;
  expect(plan).toEqual([{ id: expect.any(String), title: "Проверить EPMA", completed: true, revision: 3 }]);
  app.unmount();
  await stopService();
  await startService();
  render(<App />);
  expect((await screen.findByRole("checkbox", { name: "Проверить EPMA" })).checked).toBe(true);
  expect((await invokePetrolab("project.overview", database)).result.work_plan).toEqual(plan);
}, 20000);

test("overview opens a project source and global search opens an exact analysis without clearing selection", async () => {
  await writeFile(second, "Analysis,Sample,Mineral,SiO2 [wt.%],Publication authors,Publication year,Publication title,DOI\n"
    + "B1,Sample A,apatite,40,Иванов,2021,Северный массив,10.1234/apatite\nB2,Sample B,olivine,41,Петров,2022,Южный массив,10.1234/other\n");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("heading", { name: "Сегодня в проекте" });
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(screen.getByRole("checkbox", { name: "Выбрать B2" }));
  await user.click(await enabledButton("Обзор"));
  await user.click(await enabledButton("Открыть источник second.csv"));
  await screen.findByRole("heading", { name: "Поиск по проекту" });
  expect(screen.getByLabelText("Источник").value).toBe("second.csv");
  await user.clear(screen.getByLabelText("Источник"));
  await user.type(screen.getByLabelText("Источник"), "ИВАНОВ");
  await user.type(screen.getByLabelText("Минерал"), "APATITE");
  await user.click(await enabledButton("Найти"));
  await screen.findByText(/Найдено анализов: 1\. Отмечено: 0\. В отборе: 1/);
  const bibliography = within(await screen.findByRole("region", { name: "Библиография" }));
  expect(bibliography.getByText("Северный массив")).toBeTruthy();
  const citation = bibliography.getByRole("link", { name: "10.1234/apatite" });
  expect(citation.getAttribute("href")).toBe("https://doi.org/10.1234/apatite");
  await user.click(citation);
  expect(externalUrls).toEqual(["https://doi.org/10.1234/apatite"]);
  await user.click(screen.getByRole("checkbox", { name: "Отметить B1" }));
  await screen.findByText(/Отмечено: 1\. В отборе: 1/);
  await user.click(await enabledButton("Открыть анализ B1"));
  const analysis = within(await screen.findByRole("complementary", { name: "Подробности анализа" }));
  expect(analysis.getByRole("heading", { name: "B1" })).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
  expect(screen.getByRole("checkbox", { name: "Выбрать B1" }).checked).toBe(false);
  await user.click(await enabledButton("Обзор"));
  await user.click(await enabledButton("Открыть источник second.csv"));
  await user.type(screen.getByLabelText("Минерал"), "apatite");
  await user.click(await enabledButton("Найти"));
  await screen.findByText(/Найдено анализов: 1\. Отмечено: 0\. В отборе: 1/);
  await user.click(await enabledButton("Показать анализы источника"));
  await screen.findByText(/Найдено анализов: 2\. Отмечено: 0\. В отборе: 1/);
  expect(requests.findLast(({ command }) => command === "analysis.query").payload.source_id).toBeTruthy();
}, 20000);

test("histogram with one measurement field restores its layout and exports the visible bars", async () => {
  const content = "Analysis,SiO2 [wt.%]\nP1,10\nP2,20\nP3,<1\n";
  await writeFile(second, content);
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await user.click(await enabledButton("Построение"));
  const bars = await screen.findAllByRole("button", { name: /Выбрать интервал/ });
  expect(bars).toHaveLength(2);
  expect(screen.getByText("Анализов: 2 из 3 · пропущено: 1")).toBeTruthy();
  bars[0].focus();
  await user.keyboard("{Enter}");
  expect(bars[0].getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  await user.click(screen.getByText("Сохранённые раскладки", { exact: true }));
  await user.type(screen.getByLabelText("Название раскладки"), "Гистограмма SiO2");
  await user.click(await enabledButton("Сохранить раскладку"));
  await screen.findByText("Сохранена раскладка «Гистограмма SiO2».");
  await user.click(await enabledButton("Добавить диаграмму"));
  expect(screen.getAllByLabelText("Тип диаграммы")).toHaveLength(2);
  await user.click(await enabledButton("Открыть «Гистограмма SiO2»"));
  await screen.findByText("Открыта раскладка «Гистограмма SiO2».");
  expect((await screen.findByLabelText("Тип диаграммы")).value).toBe("histogram");
  await screen.findAllByRole("button", { name: /Выбрать интервал/ });
  const svg = await readFile(await savePlot(user, 0), "utf8");
  expect((svg.match(/<rect /g) || [])).toHaveLength(2);
  expect(await readFile(second, "utf8")).toBe(content);
}, 25000);

test("restoring a calculated layout retains sums, pinned APFU and exclusion reasons", async () => {
  const source = "Analysis,Na2O [wt.%],K2O [wt.%],FeOt [wt.%],MgO [wt.%],SiO2 [wt.%],CaO [wt.%],FeO [wt.%]\nP1,2,3,15,30,50,10,8\nP2,<DL,3,15,30,50,11,8\n";
  await writeFile(second, source);
  const database = { project_database_path: join(folder, "project.sqlite") };
  const { result: { recipe } } = await invokePetrolab("import.recipe.suggest", { source_path: second });
  expect((await invokePetrolab("import.plan.apply", { ...database, source_path: second, recipe })).error).toBeUndefined();
  const rows = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const analysis = rows.find((row) => row.identity.Analysis === "P1");
  const input = { ...database, method_id: "formula.pyroxene.6o", analysis_id: analysis.analysis_id,
    measurement_ids: analysis.measurement_list.filter(({ field }) => ["SiO2", "MgO", "FeO", "CaO"].includes(field)).map(({ measurement_id }) => measurement_id) };
  const reviewed = (await invokePetrolab("formula.review", input)).result;
  const run = (await invokePetrolab("formula.run", { ...input, input_fingerprint: reviewed.input_fingerprint,
    method_definition_fingerprint: reviewed.method_definition_fingerprint })).result;
  const { axes: catalog } = (await invokePetrolab("plot_data.catalog", database)).result;
  const measured = Object.fromEntries(catalog.map((axis) => [axis.field, axis]));
  const sum = { ...measured.Na2O, field: "Na2O + K2O", calculation: { operation: "sum", version: 1, operands: [measured.Na2O, measured.K2O] } };
  const formula = { version: 1, method_id: run.method_id, method_version: run.method_version,
    method_definition_fingerprint: run.method_definition_fingerprint, run_ids: [run.id] };
  const apfu = ["Mg", "Fe2+", "Ca"].map((element) => ({ field: `apfu.${element}`, unit: "APFU", measurement_set: null, method: null, formula }));
  const panels = [[sum, measured.FeOt, measured.MgO], apfu].map((axes) => ({ id: crypto.randomUUID(), kind: "ternary", axes }));
  const initial = await invokePetrolab("plot_spec.save", { ...database, name: "Расчётные оси", panels, colors: {} });
  expect(initial.result?.panels).toHaveLength(2);

  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Построение"));
  await user.click(await screen.findByText("Сохранённые раскладки", { exact: true }));
  await user.click(await enabledButton("Открыть «Расчётные оси»"));
  await screen.findByText("Открыта раскладка «Расчётные оси».");
  const panel = (title) => within(screen.getByText(title, { selector: ".plot-panel header b" }).closest("article"));
  await waitFor(() => {
    const afm = panel("Na2O + K2O / FeOt / MgO");
    const pyroxene = panel("apfu.Mg / apfu.Fe2+ / apfu.Ca");
    expect(afm.getByRole("button", { name: "Выбрать точку P1" })).toBeTruthy();
    expect(pyroxene.getByRole("button", { name: "Выбрать точку P1" })).toBeTruthy();
    expect(afm.getByText("ниже предела обнаружения (1)")).toBeTruthy();
    expect(pyroxene.getByText("нет выбранной формулы (1)")).toBeTruthy();
    expect(pyroxene.getByRole("option", { name: /apfu.Mg · APFU · версия/ })).toBeTruthy();
  });

  await user.type(screen.getByLabelText("Название раскладки"), "Копия расчётных осей");
  await user.click(await enabledButton("Сохранить раскладку"));
  await screen.findByText("Сохранена раскладка «Копия расчётных осей».");
  const stored = requests.findLast(({ command }) => command === "plot_spec.save");
  expect(stored.payload.panels.map(({ axes }) => axes)).toEqual(panels.map(({ axes }) => axes));
  const svg = await readFile(await savePlot(user), "utf8");
  expect(svg).toContain("Na2O + K2O");
  expect(svg).toContain("apfu.Fe2+");
  expect(await readFile(second, "utf8")).toBe(source);
}, 25000);

test("AT-08 excludes only the focused source from both plots and restores it from search", async () => {
  const alternate = join(folder, "alternate");
  await mkdir(alternate);
  const sameName = join(alternate, "first.csv");
  const header = "Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\n";
  const files = [[first, header + "P1,20,30,50\n"], [sameName, header + "P2,10,80,10\n"]];
  const database = { project_database_path: join(folder, "project.sqlite") };
  for (const [source_path, content] of files) {
    await writeFile(source_path, content);
    const { result: { recipe } } = await invokePetrolab("import.recipe.suggest", { source_path });
    expect((await invokePetrolab("import.plan.apply", { ...database, source_path, recipe })).error).toBeUndefined();
  }
  const before = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const excluded = before.find((row) => row.identity.Analysis === "P1");
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Поиск"));
  const focus = async (label) => user.click(await screen.findByRole("cell", { name: label, exact: true }));
  const point = (label) => screen.queryAllByRole("button", { name: `Выбрать точку ${label}` });
  const plotAll = async () => {
    await user.click(screen.getByText("Отметки", { exact: true }));
    await user.click(await enabledButton("Выбрать весь результат · 2"));
    await user.click(await enabledButton("Построить диаграммы"));
  };
  await user.click(await screen.findByRole("checkbox", { name: "Отметить P1" }));
  await user.click(await enabledButton("Добавить отмеченные в отбор"));
  await focus("P1");
  await user.click(await enabledButton("Исключить источник из графиков"));
  await screen.findByText(/Найдено анализов: 2\. Отмечено: 1\. В отборе: 1/);
  await plotAll();
  await waitFor(() => expect(point("P2")).toHaveLength(2));
  expect(point("P1")).toHaveLength(0);
  expect(requests.filter(({ command }) => command === "plot_data.query")
    .every(({ payload }) => payload.hidden_source_ids.length === 1 && payload.hidden_source_ids[0] === excluded.source_id)).toBe(true);
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  await user.click(await enabledButton("Развернуть таблицу"));
  const dock = await screen.findByRole("table", { name: "Таблица выбранных анализов" });
  expect(within(dock).getByRole("rowheader", { name: "P1" }).closest("tr").dataset.analysisId).toBe(excluded.analysis_id);
  expect(within(dock).getByText("Скрыт")).toBeTruthy();
  expect(within(dock).queryByRole("rowheader", { name: "P2" })).toBeNull();
  await user.click(await enabledButton("Поиск"));
  await focus("P1");
  await user.click(await enabledButton("Вернуть источник на графики"));
  await plotAll();
  await waitFor(() => expect(point("P1")).toHaveLength(2));
  expect(point("P2")).toHaveLength(2);
  expect(point("P1").every((node) => node.getAttribute("aria-pressed") === "true")).toBe(true);
  // The dock remains expanded when returning to the same plot workspace.
  expect(screen.getByRole("button", { name: "Свернуть таблицу" }).getAttribute("aria-expanded")).toBe("true");
  expect(within(await screen.findByRole("table", { name: "Таблица выбранных анализов" })).getByText("Не скрыт")).toBeTruthy();
  expect((await invokePetrolab("project.analyses.list", database)).result.analyses).toEqual(before);
  for (const [path, content] of files) expect(await readFile(path, "utf8")).toBe(content);
}, 20000);

test("categorical mineral colors use reported labels and preserve selection and vector export", async () => {
  await writeFile(second, "Analysis,Mineral,SiO2 [wt.%],MgO [wt.%]\nC1,olivine,40,50\nC2,pyroxene,50,20\n");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(await enabledButton("Построение"));
  await screen.findAllByRole("button", { name: /^Выбрать точку C1/ });
  const mode = screen.getByRole("combobox",{name:"Окрашивать по"});
  await waitFor(()=>expect(mode.disabled).toBe(false));
  await user.selectOptions(mode,"mineral");
  const legend = await screen.findByLabelText("Легенда категорий");
  expect(within(legend).getByText("olivine")).toBeTruthy();
  expect(within(legend).getByText("pyroxene")).toBeTruthy();
  fireEvent.change(within(legend).getByLabelText("Цвет: olivine"),{target:{value:"#112233"}});
  await user.click(await enabledButton("Сохранить цветовую схему проекта"));
  await screen.findByText("Цветовая схема сохранена в проекте.");
  const stored = (await invokePetrolab("project.plot_colors.get",{project_database_path:join(folder,"project.sqlite")})).result;
  expect(stored.scheme.mode).toBe("mineral");
  expect(stored.scheme.colors).toContainEqual({mode:"mineral",key:"olivine",color:"#112233"});
  const first = screen.getAllByRole("button", {name:/^Выбрать точку C1/})[0];
  const secondMarker = screen.getAllByRole("button", {name:/^Выбрать точку C2/})[0];
  expect(first.getAttribute("fill")).toBe("#112233");
  expect(first.getAttribute("fill")).not.toBe(secondMarker.getAttribute("fill"));
  const firstPanel = first.closest(".plot-panel");
  await user.click(within(firstPanel).getByText("Оформление точек · 100%"));
  const beforeStyle = requests.filter(request=>request.command==="plot_data.query").length;
  fireEvent.change(within(firstPanel).getByRole("slider",{name:"Непрозрачность точек панели"}),{target:{value:"0.35"}});
  fireEvent.change(within(firstPanel).getByRole("slider",{name:"Размер точек панели"}),{target:{value:"1.5"}});
  expect(first.getAttribute("opacity")).toBe("0.35");
  expect(Number(first.getAttribute("r"))).toBe(5.25);
  await user.click(within(firstPanel).getByRole("button",{name:"Применить оформление ко всем диаграммам"}));
  expect(screen.getAllByRole("button",{name:/^Выбрать точку C1/}).every(node=>node.getAttribute("opacity")==="0.35")).toBe(true);
  expect(requests.filter(request=>request.command==="plot_data.query").length).toBe(beforeStyle);
  fireEvent.keyDown(first,{key:"Enter"});
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  fireEvent.keyDown(secondMarker,{key:"Enter"});
  await user.click(await enabledButton("Сравнить составы"));
  const comparison = await screen.findByRole("table",{name:"Сравнение составов"});
  const mg = within(comparison).getByText("MgO").closest("tr");
  expect(within(mg).getByText("50")).toBeTruthy();
  expect(within(mg).getByText("20")).toBeTruthy();
  expect(within(mg).getByText("-30")).toBeTruthy();
  await user.click(await enabledButton("Показать статистику"));
  const summary=await screen.findByRole("table",{name:"Статистика полей"});
  expect(within(within(summary).getByText("MgO").closest("tr")).getAllByText("35").length).toBe(2);
  await user.click(await enabledButton("Закрыть статистику"));
  fireEvent.keyDown(secondMarker,{key:"Enter",ctrlKey:true});
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  const svg = await readFile(await savePlot(user),"utf8");
  expect(svg).toContain("category-legend");
  expect(svg).toContain("olivine");
  expect(svg).toContain("pyroxene");
  expect(svg).toContain(first.getAttribute("fill"));
  expect(svg).toContain('opacity="0.35"');
  expect(svg).toContain('r="5.25"');
  await user.selectOptions(within(legend).getByLabelText("Символ: olivine"),"diamond");
  const diamond=screen.getAllByRole("button",{name:/^Выбрать точку C1/})[0];
  expect(diamond.localName).toBe("polygon");
  expect(diamond.getAttribute("fill")).toBe("#112233");
  const shapedSvg=new DOMParser().parseFromString(await readFile(await savePlot(user),"utf8"),"image/svg+xml");
  expect([...shapedSvg.querySelectorAll("polygon")].some(node=>node.getAttribute("fill")==="#112233")).toBe(true);
  await user.click(await enabledButton("Сохранить цветовую схему проекта"));
  await screen.findByText("Цветовая схема сохранена в проекте.");
  const shaped=(await invokePetrolab("project.plot_colors.get",{project_database_path:join(folder,"project.sqlite")})).result;
  expect(shaped.scheme.colors).toContainEqual({mode:"mineral",key:"olivine",color:"#112233",symbol:"diamond"});
  await user.selectOptions(within(legend).getByLabelText("Символ: olivine"),"star_open");
  const star=screen.getAllByRole("button",{name:/^Выбрать точку C1/})[0];
  expect(star.localName).toBe("polygon");
  expect(star.getAttribute("fill")).toBe("none");
  expect(star.getAttribute("stroke")).toBe("#112233");
  const openSvg=new DOMParser().parseFromString(await readFile(await savePlot(user),"utf8"),"image/svg+xml");
  expect([...openSvg.querySelectorAll("polygon")].some(node=>node.getAttribute("fill")==="none"&&node.getAttribute("stroke")==="#112233")).toBe(true);
  await user.selectOptions(within(legend).getByLabelText("Символ: olivine"),"diamond");
  await user.selectOptions(mode,"generation");
  expect(within(await screen.findByLabelText("Легенда категорий")).getByText("Не указано")).toBeTruthy();
  await user.selectOptions(mode,"source");
  expect(screen.queryByLabelText("Легенда категорий")).toBeNull();
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  expect(requests.filter(request=>request.command==="plot_data.catalog" && request.payload.include_categories)).toHaveLength(1);
  await user.click(await enabledButton("Загрузить сохранённую схему"));
  await screen.findByText("Загружена сохранённая цветовая схема.");
  expect(mode.value).toBe("mineral");
  expect(screen.getAllByRole("button",{name:/^Выбрать точку C1/})[0].localName).toBe("polygon");
  expect(screen.getAllByRole("button",{name:/^Выбрать точку C1/})[0].getAttribute("fill")).toBe("#112233");
  await user.click(screen.getByText("Сохранённые раскладки", {exact:true}));
  await user.type(screen.getByLabelText("Название раскладки"), "Оливин и пироксен");
  await user.click(await enabledButton("Сохранить раскладку"));
  await screen.findByText("Сохранена раскладка «Оливин и пироксен».");
  const database = {project_database_path:join(folder,"project.sqlite")};
  const other = {mode:"mineral", key:"garnet", color:"#ab1245", symbol:"square"};
  const updated = (await invokePetrolab("project.plot_colors.save", {...database,
    scheme:{mode:"mineral",colors:[...shaped.scheme.colors, other]}, expected_revision:shaped.revision})).result;
  expect(updated.scheme.colors).toContainEqual(other);

  await user.click(await enabledButton("Рабочие состояния"));
  const dialog = within(await screen.findByRole("dialog", {name:"Рабочие состояния проекта"}));
  await user.selectOptions(await dialog.findByLabelText("Раскладка диаграмм"), dialog.getByRole("option", {name:"Оливин и пироксен"}));
  await user.selectOptions(dialog.getByLabelText("Открывать раздел"), "plotting");
  await user.type(dialog.getByLabelText("Название состояния"), "Сравнение минералов");
  await user.click(dialog.getByRole("button", {name:"Сохранить рабочее состояние"}));
  await user.click(await enabledButton("Открыть «Сравнение минералов»"));
  await screen.findByText("Рабочее состояние «Сравнение минералов» восстановлено.");
  expect((await invokePetrolab("project.plot_colors.get", database)).result).toEqual(updated);
  await user.click(await enabledButton("Сохранить цветовую схему проекта"));
  await screen.findByText("Цветовая схема сохранена в проекте.");
  const persisted = (await invokePetrolab("project.plot_colors.get", database)).result;
  expect(persisted.revision).toBe(updated.revision + 1);
  expect(persisted.scheme.colors).toContainEqual(other);
}, 35000);

test("axis catalog drops an exact catalog key and rejects an unknown key", async () => {
  await writeFile(second, "Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\nP1,20,30,50\nP2,10,80,10\n");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(await enabledButton("Построение"));
  await screen.findAllByRole("button", { name: "Выбрать точку P1" });
  const panel = document.querySelector(".plot-panel");
  const axis = within(panel).getByRole("combobox", { name: "Ось 1" });
  const original = axis.value;
  const target = [...axis.options].find(option => option.value !== original && option.value !== within(panel).getByRole("combobox", { name: "Ось 2" }).value);
  expect(target).toBeTruthy();
  await user.click(screen.getByText(/Каталог осей ·/));
  const search = await screen.findByRole("textbox", { name: "Поиск полей осей" });
  const catalog = search.closest("details");
  const field = [...catalog.querySelectorAll("[draggable=true]")].find(node => node.textContent === target.textContent);
  expect(field).toBeTruthy();
  const values = new Map();
  const dataTransfer = { types: ["application/x-petrolab-axis"], setData: (type, value) => values.set(type, value),
    getData: type => values.get(type) || "" };
  fireEvent.dragStart(field, { dataTransfer });
  expect(values.get("application/x-petrolab-axis")).toBe(target.value);
  fireEvent.dragOver(axis, { dataTransfer });
  fireEvent.drop(axis, { dataTransfer });
  await waitFor(() => expect(axis.value).toBe(target.value));
  await screen.findAllByRole("button", { name: "Выбрать точку P1" });
  values.set("application/x-petrolab-axis", JSON.stringify(["not_a_field", "wt.%", null, null]));
  fireEvent.drop(axis, { dataTransfer });
  expect(axis.value).toBe(target.value);
  expect(screen.getByText("Выбранные анализы · 0")).toBeTruthy();
  await user.click(await within(panel).findByRole("button", {name:"Добавить диаграмму в избранное"}));
  await user.click(screen.getByText("Избранное и недавние оси"));
  const presets = screen.getByText("Избранные комбинации").closest("details");
  await user.click(await enabledButton("Сохранить комбинации в проекте"));
  await screen.findByText("Избранное и недавние оси сохранены в проекте.");
  await user.click(within(presets).getByRole("button",{name:"Удалить избранную комбинацию"}));
  expect(within(presets).queryByRole("button",{name:"Удалить избранную комбинацию"})).toBeNull();
  await user.click(await enabledButton("Загрузить сохранённые комбинации"));
  await screen.findByText("Загружены сохранённые комбинации.");
  const favorite = within(presets).getByRole("button",{name:"Удалить избранную комбинацию"}).parentElement.firstElementChild;
  await user.click(favorite);
  await waitFor(() => expect(screen.getAllByRole("combobox", {name:"Тип диаграммы"})).toHaveLength(3));
  await user.click(screen.getByText("Минеральные шаблоны"));
  await user.click(await enabledButton("Добавить графики шаблона"));
  await waitFor(() => expect(screen.getAllByRole("combobox", {name:"Тип диаграммы"})).toHaveLength(4));
  expect(screen.getByText("Выбранные анализы · 0")).toBeTruthy();
}, 20000);

test("one common selection highlights the same analysis on binary and ternary plots and in the table", async () => {
  await writeFile(second, "Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\nP1,20,30,50\nP2,10,80,10\n");
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(await enabledButton("Построение"));
  await screen.findAllByRole("button", { name: "Выбрать точку P1" });
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Выбрать точку P1" })).toHaveLength(2));
  await user.selectOptions(screen.getByRole("combobox", { name: "Область" }), "lasso");
  const point = screen.getAllByRole("button", { name: "Выбрать точку P1" })[0];
  fireEvent.mouseEnter(point, { shiftKey: true });
  const tooltip = await screen.findByRole("tooltip");
  await within(tooltip).findByText("Исходные измерения (без пересчёта)");
  expect(within(tooltip).getAllByText(/MgO: 50 wt\.%/).some(node => node.closest(".plot-tooltip-measurements"))).toBe(true);
  expect(screen.getByText("Выбранные анализы · 0")).toBeTruthy();
  fireEvent.mouseLeave(point);
  expect(screen.queryByRole("tooltip")).toBeNull();
  const detailRequests = requests.filter(request => request.command === "project.analysis.get").length;
  fireEvent.mouseEnter(point, { shiftKey: true });
  await within(await screen.findByRole("tooltip")).findByText("Исходные измерения (без пересчёта)");
  expect(requests.filter(request => request.command === "project.analysis.get").length).toBe(detailRequests);
  fireEvent.mouseLeave(point);
  const canvas = point.closest("svg");
  canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 460, height: 280 });
  canvas.setPointerCapture = () => {};
  const x = Number(point.getAttribute("cx"));
  const y = Number(point.getAttribute("cy"));
  function pointer(type, clientX, clientY, button = 0) {
    const event = new MouseEvent(type, { bubbles: true, clientX, clientY, button });
    Object.defineProperty(event, "pointerId", { value: 1 });
    fireEvent(canvas, event);
  }
  pointer("pointerdown", x - 12, y - 12);
  pointer("pointermove", x + 12, y - 12);
  pointer("pointermove", x + 12, y + 12);
  pointer("pointermove", x - 12, y + 12);
  pointer("pointerup", x - 12, y - 12);
  expect(screen.getAllByRole("button", { name: "Выбрать точку P1" })
    .every((point) => point.getAttribute("aria-pressed") === "true")).toBe(true);
  const originalView = canvas.getAttribute("viewBox");
  fireEvent.wheel(canvas, { deltaY: -120, clientX: 230, clientY: 140 });
  expect(canvas.getAttribute("viewBox")).toBe(originalView);
  fireEvent.wheel(canvas, { deltaY: -120, clientX: 230, clientY: 140, ctrlKey: true });
  const zoomedView = canvas.getAttribute("viewBox");
  expect(Number(zoomedView.split(" ")[2])).toBeLessThan(460);
  expect(screen.getAllByLabelText("Диаграмма")[1].getAttribute("viewBox")).toBe(originalView);
  pointer("pointerdown", 230, 140, 1);
  pointer("pointermove", 250, 130, 1);
  pointer("pointerup", 250, 130, 1);
  expect(canvas.getAttribute("viewBox")).not.toBe(zoomedView);
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  await user.click(await enabledButton("Автомасштаб"));
  expect(canvas.getAttribute("viewBox")).toBe(originalView);
  // Blank click clears the common selection even in add mode.
  pointer("pointerdown", 15, 15);
  pointer("pointerup", 15, 15);
  expect(screen.getByText("Выбранные анализы · 0")).toBeTruthy();
  fireEvent.keyDown(point, { key: "Enter", shiftKey: true });
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  const secondPoint = screen.getAllByRole("button", { name: "Выбрать точку P2" })[0];
  fireEvent.keyDown(secondPoint, { key: "Enter", ctrlKey: true });
  expect(screen.getByText("Выбранные анализы · 2")).toBeTruthy();
  fireEvent.keyDown(secondPoint, { key: "Enter", altKey: true });
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  fireEvent.keyDown(canvas, { key: "Escape" });
  expect(screen.getByText("Выбранные анализы · 0")).toBeTruthy();
  fireEvent.keyDown(canvas, { key: "a", ctrlKey: true });
  expect(screen.getByText("Выбранные анализы · 2")).toBeTruthy();
  fireEvent.keyDown(secondPoint, { key: "Enter", ctrlKey: true });
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  for (let count = 0; count < 6; count += 1) {
    await user.click(screen.getByRole("button", { name: "Добавить диаграмму" }));
  }
  await waitFor(() => {
    const linked = screen.getAllByRole("button", { name: "Выбрать точку P1" });
    expect(linked).toHaveLength(8);
    expect(linked.every((point) => point.getAttribute("aria-pressed") === "true")).toBe(true);
  });
  await user.click(await enabledButton("Скрыть отбор на графиках"));
  await screen.findByRole("button", { name: "Вернуть скрытые точки · 1" });
  expect(screen.queryByRole("button", { name: "Выбрать точку P1" })).toBeNull();
  expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  await user.click(screen.getByRole("checkbox", { name: "second.csv" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Выбрать точку P2" })).toBeNull());
  await user.click(screen.getByRole("checkbox", { name: "second.csv" }));
  await screen.findAllByRole("button", { name: "Выбрать точку P2" });
  expect(screen.queryByRole("button", { name: "Выбрать точку P1" })).toBeNull();
  await user.click(await enabledButton("Отменить изменение видимости"));
  const hidden = requests.find(({ command }) => command === "plot_visibility.hide");
  const restoredView = requests.find(({ command }) => command === "plot_visibility.undo");
  expect(restoredView.payload.hidden_analysis_ids).toEqual(hidden.payload.analysis_ids);
  expect(restoredView.payload.session_id).toBe(hidden.payload.session_id);
  expect(restoredView.payload.operation_id).toBeTruthy();
  await waitFor(() => {
    const restored = screen.getAllByRole("button", { name: "Выбрать точку P1" });
    expect(restored).toHaveLength(8);
    expect(restored.every((point) => point.getAttribute("aria-pressed") === "true")).toBe(true);
  });
  await user.click(await enabledButton("Открыть в анализах"));
  const table = within(await screen.findByRole("table"));
  expect(table.getByRole("checkbox", { name: "Выбрать P1" }).checked).toBe(true);
  expect(table.getByRole("checkbox", { name: "Выбрать P2" }).checked).toBe(false);
  await user.click(await enabledButton("Построение"));
  await screen.findAllByRole("button", { name: "Выбрать точку P1" });
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Выбрать точку P1" })).toHaveLength(8));
  expect(screen.getByRole("combobox", { name: "Область" }).value).toBe("lasso");
  // Layout now persists, explicitly reduce it before saving the three-panel fixture.
  while (screen.getAllByRole("combobox", { name: "Тип диаграммы" }).length > 2) {
    const buttons = screen.getAllByRole("button", { name: "Убрать панель" });
    await user.click(buttons.at(-1));
  }
  const panelOrder = () => [...document.querySelectorAll(".plot-grid .plot-panel")].map(node => node.id);
  const beforeOrder = panelOrder();
  await user.click(await enabledButton("Переместить панель 1 ниже"));
  expect(panelOrder()).toEqual([beforeOrder[1], beforeOrder[0]]);
  await user.click(await enabledButton("Переместить панель 2 выше"));
  expect(panelOrder()).toEqual(beforeOrder);
  await user.click(await enabledButton("Добавить диаграмму"));
  await user.click(await enabledButton("Скрыть отбор на графиках"));
  await screen.findByRole("button", { name: "Вернуть скрытые точки · 1" });
  await user.click(screen.getByText("Сохранённые раскладки", { exact: true }));
  await user.type(screen.getByLabelText("Название раскладки"), "Три панели");
  await user.click(await enabledButton("Сохранить раскладку"));
  await screen.findByText("Сохранена раскладка «Три панели».");
  await user.click(await enabledButton("Вернуть скрытые точки · 1"));
  await user.click(await enabledButton("Открыть «Три панели»"));
  await screen.findByText("Открыта раскладка «Три панели».");
  expect(screen.queryByRole("button", { name: "Отменить изменение видимости" })).toBeNull();
  await waitFor(() => {
    expect(screen.getAllByRole("combobox", { name: "Тип диаграммы" })).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Выбрать точку P1" })).toBeNull();
    expect(screen.getByText("Выбранные анализы · 1")).toBeTruthy();
  });
  await waitFor(() => expect(screen.getAllByText(/скрыто: 1/)).toHaveLength(3));
  const readSvg = async (path) => new DOMParser().parseFromString(await readFile(path, "utf8"), "image/svg+xml");
  const single = await readSvg(await savePlot(user, 1));
  expect([...single.querySelectorAll("g")].map((group) => group.id)).toEqual(["panel-b"]);
  const layout = await readSvg(await savePlot(user));
  expect([...layout.querySelectorAll("g")].map((group) => group.id)).toEqual(["panel-a", "panel-b", "panel-c"]);
  expect(layout.querySelector("clipPath, mask, foreignObject, image")).toBeNull();
  // Returning to the layout preserves the original input P1/P2. P1 is
  // explicitly hidden, so exactly one visible P2 marker per panel remains.
  expect(layout.querySelectorAll("circle")).toHaveLength(3);
  expect(layout.querySelector("text")?.textContent).toBe("a");
  app.unmount();
  await stopService();
  await startService();
  render(<App />);
  await user.click(await enabledButton("Построение"));
  await user.click(screen.getByText("Сохранённые раскладки", { exact: true }));
  await user.click(await enabledButton("Открыть «Три панели»"));
  await waitFor(() => expect(screen.getAllByText(/скрыто: 1/)).toHaveLength(3));
}, 20000);

test("mineral patterns share selection and keep censored gaps through SVG export and layout restore", async () => {
  const content = "Analysis,Cs (ppm),La (ppm),Ce (ppb),Pr (ppm),Nd (ppm)\n"
    + "M1,0.079,2.37,<100,0.095,0.0467\nM2,0.0079,0.237,6120,0.19,0.467\n";
  await writeFile(second, content);
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(await enabledButton("Построение"));
  const [reeType, spiderType] = await screen.findAllByRole("combobox", { name: "Тип диаграммы" });
  await user.selectOptions(reeType, "ree_pattern");
  await user.selectOptions(spiderType, "spider");
  const ree = within(reeType.closest("article"));
  const spider = within(spiderType.closest("article"));
  expect(ree.getByRole("combobox", { name: "Эталон нормировки" }).selectedOptions[0].textContent).toBe("Хондрит C1");
  expect(spider.getByRole("combobox", { name: "Эталон нормировки" }).selectedOptions[0].textContent).toBe("Примитивная мантия");
  const m1 = await ree.findByRole("button", { name: "Выбрать точку M1 · La" });
  expect(ree.queryByRole("button", { name: "Выбрать точку M1 · Ce" })).toBeNull();
  const path = reeType.closest("article").querySelector(`path.plot-series[data-analysis-id="${m1.dataset.analysisId}"]`);
  const pathGeometry = path.getAttribute("d");
  expect(pathGeometry.match(/\bM\b/g)).toHaveLength(2);
  expect(pathGeometry.match(/\bL\b/g)).toHaveLength(1);
  const canvas = m1.ownerSVGElement;
  canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 460, height: 280 });
  canvas.setPointerCapture = () => {};
  const x = Number(m1.getAttribute("cx"));
  const y = Number(m1.getAttribute("cy"));
  for (const [type, offset] of [["pointerdown", -5], ["pointerup", 5]]) {
    const event = new MouseEvent(type, { bubbles: true, clientX: x + offset, clientY: y + offset });
    Object.defineProperty(event, "pointerId", { value: 1 });
    fireEvent(canvas, event);
  }
  expect((await spider.findByRole("button", { name: "Выбрать точку M1 · La" })).getAttribute("aria-pressed")).toBe("true");
  expect(spider.getByRole("button", { name: "Выбрать точку M2 · Ce" }).getAttribute("aria-pressed")).toBe("false");
  const exported = new DOMParser().parseFromString(await readFile(await savePlot(user, 0), "utf8"), "image/svg+xml");
  const exportedPath = exported.querySelector(`path[d="${pathGeometry}"]`);
  expect(exportedPath.getAttribute("stroke")).toBe(path.getAttribute("stroke"));
  expect(exportedPath.getAttribute("fill")).toBe("none");
  expect(exported.querySelector("clipPath, mask, foreignObject, image")).toBeNull();

  await user.selectOptions(ree.getByRole("combobox", { name: "Эталон нормировки" }), "sun_mcdonough_1989_mantle_diagram_v1");
  await ree.findByText("Примитивная мантия · Sun и McDonough, 1989");
  await user.click(screen.getByText("Сохранённые раскладки", { exact: true }));
  await user.type(screen.getByLabelText("Название раскладки"), "Спектры минералов");
  await user.click(await enabledButton("Сохранить раскладку"));
  await screen.findByText("Сохранена раскладка «Спектры минералов».");
  await user.click(await enabledButton("Открыть в анализах"));
  const table = within(await screen.findByRole("table"));
  expect(table.getByRole("checkbox", { name: "Выбрать M1" }).checked).toBe(true);
  expect(table.getByRole("checkbox", { name: "Выбрать M2" }).checked).toBe(false);
  app.unmount();
  render(<App />);
  await user.click(await enabledButton("Построение"));
  await user.click(screen.getByText("Сохранённые раскладки", { exact: true }));
  await user.click(await enabledButton("Открыть «Спектры минералов»"));
  await screen.findByText("Открыта раскладка «Спектры минералов».");
  await waitFor(() => expect(screen.getAllByRole("combobox", { name: "Тип диаграммы" }).map((select) => select.value))
    .toEqual(["ree_pattern", "spider"]));
  expect(screen.getAllByRole("combobox", { name: "Эталон нормировки" })[0].selectedOptions[0].textContent).toBe("Примитивная мантия");
  const restored = screen.getAllByRole("combobox", { name: "Тип диаграммы" })[0].closest("article");
  await waitFor(() => expect(within(restored).getByRole("button", { name: "Выгрузить панель" }).disabled).toBe(false));
  await user.click(within(restored).getByRole("button", { name: "Выгрузить панель" }));
  await user.click(screen.getByRole("checkbox", { name: "Добавить данные CSV" }));
  await user.click(await enabledButton("Добавить в пакет"));
  await screen.findByRole("heading", { name: "Состав пакета" });
  const request = requests.findLast(({ command }) => command === "publication.capture_plot");
  expect(request.payload.capture.panels[0].normalization).toBe("sun_mcdonough_1989_mantle_diagram_v1");
  expect(request.payload.capture.include_csv).toBe(true);
  expect(await readFile(second, "utf8")).toBe(content);
}, 35000);

test("visible plot fields survive marker hiding and SVG includes their geometry", async () => {
  await writeFile(second, "Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\nP1,20,30,50\nP2,10,80,10\nP3,55,35,10\n");
  queue = [second];
  const user = userEvent.setup();
  const { container } = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(await enabledButton("Построение"));
  await screen.findAllByRole("button", { name: "Выбрать точку P3" });
  for (const label of ["P1", "P2", "P3"]) {
    fireEvent.keyDown(screen.getAllByRole("button", { name: `Выбрать точку ${label}` })[0], { key: "Enter" });
  }
  await user.click(screen.getByText("Слои и поля", { exact: true }));
  await user.type(screen.getByLabelText("Название слоя"), "Серия");
  await user.click(await enabledButton("Только облако выделения · 3"));
  const layer = within(screen.getByRole("group", { name: "Серия · 3" }));
  expect(layer.getByLabelText("Метод поля").value).toBe("convex_hull");
  expect(layer.getByRole("checkbox", { name: "Точки" }).checked).toBe(false);
  await waitFor(() => expect(container.querySelectorAll(".plot-field")).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Выбрать точку P1" })).toBeNull();
  expect(screen.getByText("Выбранные анализы · 3")).toBeTruthy();
  await user.selectOptions(layer.getByLabelText("Оформление облака"),"outline");
  fireEvent.change(layer.getByLabelText("Цвет облака"),{target:{value:"#123456"}});
  fireEvent.change(layer.getByLabelText("Толщина контура"),{target:{value:"2"}});
  const svg = new DOMParser().parseFromString(await readFile(await savePlot(user), "utf8"), "image/svg+xml");
  expect(svg.querySelectorAll("polygon")).toHaveLength(2);
  expect([...svg.querySelectorAll("polygon")].every(p=>p.getAttribute("fill")==="none" && p.getAttribute("stroke")==="#123456" && p.getAttribute("stroke-width")==="2")).toBe(true);
  await user.selectOptions(layer.getByLabelText("Оформление облака"),"fill");
  expect([...container.querySelectorAll(".plot-field")].every(p=>p.getAttribute("stroke")==="none")).toBe(true);
  await user.selectOptions(layer.getByLabelText("Оформление облака"),"both");
  expect(svg.querySelector("circle, clipPath, mask")).toBeNull();
  const pdf = await readFile(await savePlot(user, 1, "PDF · векторный"));
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  await user.click(await enabledButton("Скрыть все поля"));
  await waitFor(() => expect(container.querySelectorAll(".plot-field")).toHaveLength(0));
  await user.click(await enabledButton("Показать все поля"));
  await waitFor(() => expect(container.querySelectorAll(".plot-field")).toHaveLength(2));
  const evidenceDirectory = process.env.PETROLAB_QA_SVG_DIRECTORY;
  if (evidenceDirectory) {
    await user.click(layer.getByRole("checkbox", { name: "Точки" }));
    await user.click(await enabledButton("Добавить диаграмму"));
    await user.click(await enabledButton("Добавить диаграмму"));
    await waitFor(() => expect(container.querySelectorAll(".plot-field")).toHaveLength(4));
    await writeFile(join(evidenceDirectory, "petrolab-panel-b.svg"), await readFile(await savePlot(user, 1)));
    await writeFile(join(evidenceDirectory, "petrolab-four-panels.svg"), await readFile(await savePlot(user)));
  }
  await user.click(screen.getAllByRole("button", { name: "Выгрузить панель" })[1]);
  await user.click(screen.getByRole("radio", { name: "PDF · векторный" }));
  await user.click(screen.getByRole("checkbox", { name: "Добавить данные CSV" }));
  await user.type(screen.getByRole("textbox", { name: "Подпись фигуры" }), "Рисунок b");
  await user.click(await enabledButton("Добавить в пакет"));
  await screen.findByRole("heading", { name: "Состав пакета" });
  expect(screen.getByRole("textbox", { name: "Подпись материала 1" }).value).toBe("Рисунок b");
  await user.type(screen.getByRole("textbox", { name: "Название пакета" }), "Lithos QA");
  await user.selectOptions(screen.getByLabelText("Профиль журнала"), "lithos");
  await user.click(await enabledButton("Проверить пакет"));
  await screen.findByText("data/01-plot_capture.csv");
  await screen.findByText("figures/Figure_01.pdf");
  await user.click(await enabledButton("Собрать ZIP"));
  await screen.findByText(/Пакет сохранён: .*petrolab-package.zip/);
  expect(requests.find(({ command }) => command === "publication.capture_plot").payload.capture.panels).toHaveLength(1);
  expect((await readFile(join(folder, "petrolab-package.zip"))).subarray(0, 2).toString()).toBe("PK");
}, 20000);

test("reviewing a cross-file match allows one save to import both included files", async () => {
  await writeFile(first, "Analysis,SiO2 [wt.%]\nB1,38\nA2,39\n");
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Добавить файл"));
  await screen.findByText("Совпадения между источниками");
  expect(screen.getByRole("button", { name: "Импортировать после проверки" }).disabled).toBe(true);
  await user.click(await enabledButton("Проверено: оставить записи из всех источников"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  for (const identity of ["A2", "B2"]) {
    expect(await table.findByText(identity)).toBeTruthy();
  }
  expect(await table.findAllByText("B1")).toHaveLength(2);
  expect(requests.filter(r => r.command === "import.workspace.commit")).toHaveLength(1);
}, 40000);

test("opening PetroLab again restores the queue and the saved skip decision", async () => {
  await writeFile(first, "Analysis,SiO2 [wt.%]\nA1,38\nA2,39\n");
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Добавить файл"));
  await user.click(await enabledButton("Пропустить источник second.csv"));
  await enabledButton("Включить источник second.csv");

  app.unmount();
  await stopService();
  await startService();
  render(<App />);
  await screen.findByText("Черновик импорта восстановлен.");
  await enabledButton("Включить источник second.csv");
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  expect(await table.findByText("A1")).toBeTruthy();
  expect(table.queryByText("B1")).toBeNull();
}, 20000);

test("Generation assignment includes the selected row hidden by a filter and can be undone", async () => {
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  await user.click(table.getByRole("checkbox", { name: "Выбрать B2" }));
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "B1" } });
  await user.click(await enabledButton("Назначить Generation"));
  const form = within(await screen.findByRole("form", { name: "Назначение Generation" }));
  await user.type(form.getByRole("textbox", { name: "Название" }), "Rim");
  await user.click(form.getByRole("button", { name: "Назначить", exact: true }));
  expect((await screen.findByRole("button", { name: "Отменить назначение Generation" }))).toBeTruthy();
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "" } });
  expect(await table.findByText("Rim")).toBeTruthy();
  const assignment = requests.find((item) => item.command === "generation.assign");
  expect(assignment.payload.analysis_ids).toHaveLength(1);
  await user.click(await enabledButton("Отменить назначение Generation"));
  await waitFor(() => expect(table.queryByText("Rim")).toBeNull());
  expect(table.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
}, 20000);

test("a saved work group restores the exact selection after reopening the application", async () => {
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  await user.click(table.getByRole("checkbox", { name: "Выбрать B2" }));
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "B1" } });
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  await user.click(screen.getByText("Представления таблицы", { exact: true }));
  const viewForm = within(screen.getByRole("form", { name: "Новое представление таблицы" }));
  await user.type(viewForm.getByLabelText("Название представления"), "Только B1");
  await user.click(await enabledButton("Сохранить представление"));
  await screen.findByText("Сохранено представление «Только B1».");
  await user.click(await enabledButton("Экспорт отбора XLSX"));
  await screen.findByText(/Экспортировано анализов: 1/);
  expect((await readFile(join(folder, "selection.xlsx"))).subarray(0, 2).toString()).toBe("PK");
  await user.click(await enabledButton("Экспорт отбора CSV"));
  await screen.findByText(/Экспортировано анализов: 1.*selection.csv/);
  const csv = await readFile(join(folder, "selection.csv"), "utf8");
  expect(csv).toContain('raw_token,unit,value_status');
  expect(csv).toContain('SiO2,41,wt.%');
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  await user.click(await enabledButton("Сохранить как рабочую группу"));
  const form = within(screen.getByRole("form", { name: "Новая рабочая группа" }));
  await user.type(form.getByLabelText("Название"), "Проверенные");
  await user.type(form.getByLabelText("Автор"), "QA");
  await user.click(form.getByRole("button", { name: "Сохранить группу", exact: true }));
  await screen.findByText(/Сохранена группа «Проверенные»/);
  const persisted = requests.find((item) => item.command === "work_group.create");
  expect(persisted.payload.analysis_ids).toHaveLength(1);
  expect(requests.find((item) => item.command === "analysis.selection.export_xlsx").payload.analysis_ids)
    .toEqual(persisted.payload.analysis_ids);
  expect(requests.find((item) => item.command === "analysis.selection.export_csv").payload.analysis_ids)
    .toEqual(persisted.payload.analysis_ids);

  app.unmount();
  await stopService();
  await startService();
  render(<App />);
  await user.click(await enabledButton("Анализы"));
  const reopened = within(await screen.findByRole("table"));
  expect(reopened.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(false);
  await user.click(await enabledButton("Рабочие группы"));
  await user.click(await enabledButton("Проверенные · 1"));
  await screen.findByText("Открыта группа «Проверенные».");
  expect(reopened.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
  expect(reopened.getByRole("checkbox", { name: "Выбрать B1" }).checked).toBe(false);
  await user.click(screen.getByText("Представления таблицы", { exact: true }));
  await user.click(await enabledButton("Только B1"));
  await screen.findByText("Открыто представление «Только B1».");
  expect(reopened.getByRole("textbox", { name: "Фильтр Analysis" }).value).toBe("B1");
  expect(reopened.queryByRole("checkbox", { name: "Выбрать B2" })).toBeNull();
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  await user.click(await enabledButton("Добавить таблицу в пакет"));
  await screen.findByRole("heading", { name: "Состав пакета" });
  expect(requests.find(({ command }) => command === "publication.capture_table").payload.analysis_ids)
    .toEqual(persisted.payload.analysis_ids);
  await user.type(screen.getByLabelText("Название пакета"), "Материалы отбора");
  await user.click(await enabledButton("Проверить пакет"));
  await screen.findByText("tables/01-selection_table.xlsx");
  expect(screen.getByText("Анализов · 1")).toBeTruthy();
}, 40000);

test("AT-33 loads later pages and restores a saved table and its exact hidden selection", async () => {
  const labels = ["B1", "B2", ...Array.from({ length: 499 }, (_, index) => `Other-${index}`), "B1-Late"];
  await writeFile(second, `Analysis,SiO2 [wt.%]\n${labels.map((label) => `${label},41`).join("\n")}\n`);
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  const database = { project_database_path: join(folder, "project.sqlite") };
  const original = (await invokePetrolab("project.analyses.list", database)).result;
  const selectedId = original.analyses.find(({ identity }) => identity.Analysis === "B2").analysis_id;
  const table = within(await screen.findByRole("table"));
  await user.click(table.getByRole("checkbox", { name: "Выбрать B2" }));
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "B1" } });
  await user.click(screen.getByText("Представления таблицы", { exact: true }));
  await user.type(screen.getByLabelText("Название представления"), "Строка B1");
  await user.click(await enabledButton("Сохранить представление"));
  await screen.findByText("Сохранено представление «Строка B1».");

  await user.click(await enabledButton("Рабочие состояния"));
  const dialog = within(await screen.findByRole("dialog", { name: "Рабочие состояния проекта" }));
  const view = await dialog.findByLabelText("Представление таблицы");
  await user.selectOptions(view, dialog.getByRole("option", { name: "Строка B1" }));
  await user.selectOptions(dialog.getByLabelText("Открывать раздел"), "analyses");
  await user.type(dialog.getByLabelText("Название состояния"), "Отбор для пересчёта");
  await user.click(dialog.getByRole("button", { name: "Сохранить рабочее состояние" }));
  await dialog.findByText("Рабочее состояние сохранено в проекте.");

  app.unmount();
  await stopService();
  await startService();
  render(<App />);
  await user.click(await enabledButton("Рабочие состояния"));
  await user.click(await enabledButton("Открыть «Отбор для пересчёта»"));
  await screen.findByText("Рабочее состояние «Отбор для пересчёта» восстановлено.");
  const restored = within(await screen.findByRole("table"));
  expect(restored.getByRole("textbox", { name: "Фильтр Analysis" }).value).toBe("B1");
  expect(restored.getByRole("checkbox", { name: "Выбрать B1-Late" }).checked).toBe(false);
  expect(restored.queryByRole("checkbox", { name: "Выбрать B2" })).toBeNull();
  expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  await user.click(await enabledButton("Экспорт отбора CSV"));
  await screen.findByText(/Экспортировано анализов: 1/);
  expect(requests.findLast(({ command }) => command === "analysis.selection.export_csv").payload.analysis_ids).toEqual([selectedId]);
  expect((await invokePetrolab("project.analyses.list", database)).result.analyses).toEqual(original.analyses);
}, 25000);

test("AT-36 exports exactly 17 selected analyses across loaded pages with unchanged state and provenance", async () => {
  const labels = Array.from({ length: 502 }, (_, index) => {
    if (index < 15) return `PICK-${String(index + 1).padStart(2, "0")}`;
    if (index >= 500) return `PICK-${index - 484}`;
    return `Other-${index}`;
  });
  const content = `Analysis,SiO2 [wt.%],F [wt.%]\n${labels.map((label, index) => `${label},${40 + index % 6},${index ? "0" : "<0.01"}`).join("\n")}\n`;
  await writeFile(second, content);
  const database = { project_database_path: join(folder, "project.sqlite") };
  const suggested = (await invokePetrolab("import.recipe.suggest", { source_path: second })).result;
  const seeded = await invokePetrolab("import.plan.apply", { ...database, source_path: second, recipe: suggested.recipe });
  expect(seeded.result.analysis_count).toBe(502);
  const pages = await Promise.all([0, 500].map((offset) => invokePetrolab("project.analyses.list", { ...database, limit: 500, offset })));
  const selected = pages.flatMap(({ result }) => result.analyses).filter(({ identity }) => identity.Analysis.startsWith("PICK-"));
  const group = await invokePetrolab("work_group.create", { ...database, name: "До экспорта",
    analysis_ids: [selected[0].analysis_id], created_by: "QA" });
  expect(group.result).toBeTruthy();
  const beforeGroups = (await invokePetrolab("work_group.list", database)).result;

  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Анализы"));
  const table = within(await screen.findByRole("table"));
  fireEvent.change(table.getByRole("textbox", { name: "Фильтр Analysis" }), { target: { value: "PICK-" } });
  await user.click(screen.getByText("Представления таблицы", { exact: true }));
  await user.type(within(screen.getByRole("form", { name: "Новое представление таблицы" })).getByLabelText("Название представления"), "Отбор по двум страницам");
  await user.click(await enabledButton("Сохранить представление"));
  await screen.findByText("Сохранено представление «Отбор по двум страницам».");
  const beforeViews = (await invokePetrolab("table_view.list", database)).result;
  expect(table.queryByRole("checkbox", { name: "Выбрать PICK-16", exact: true })).toBeNull();
  await user.click(table.getByRole("checkbox", { name: "Выбрать показанные анализы" }));
  expect(table.getByRole("checkbox", { name: "Выбрать PICK-15", exact: true }).checked).toBe(true);
  await user.click(await enabledButton("Загрузить ещё анализы"));
  await table.findByRole("checkbox", { name: "Выбрать PICK-17", exact: true });
  expect(table.getByRole("checkbox", { name: "Выбрать PICK-15", exact: true }).checked).toBe(true);
  await user.click(table.getByRole("checkbox", { name: "Выбрать PICK-16", exact: true }));
  await user.click(table.getByRole("checkbox", { name: "Выбрать PICK-17", exact: true }));
  await user.click(table.getByText("PICK-01", { exact: true }));
  await user.click(await enabledButton("Скрыть этот анализ на графиках"));
  await enabledButton("Вернуть этот анализ на графики");
  const requestStart = requests.length;
  await user.click(await enabledButton("Экспорт отбора XLSX"));
  await screen.findByText(/Экспортировано анализов: 17/);
  const exportRequest = requests.slice(requestStart).find(({ command }) => command === "analysis.selection.export_xlsx");
  expect(exportRequest.payload.analysis_ids).toEqual(selected.map(({ analysis_id }) => analysis_id));
  expect(table.getByRole("textbox", { name: "Фильтр Analysis" }).value).toBe("PICK-");
  expect(table.getAllByRole("checkbox", { name: /^Выбрать PICK-/ }).every((checkbox) => checkbox.checked)).toBe(true);
  await enabledButton("Вернуть этот анализ на графики");
  expect((await invokePetrolab("work_group.list", database)).result).toEqual(beforeGroups);
  expect((await invokePetrolab("table_view.list", database)).result).toEqual(beforeViews);

  const workbook = JSON.parse(execFileSync("python", ["-c", [
    "import json, sys",
    "from openpyxl import load_workbook",
    "book = load_workbook(sys.argv[1], read_only=True)",
    "print(json.dumps({sheet.title: list(sheet.values) for sheet in book}))",
    "book.close()",
  ].join("\n"), join(folder, "selection.xlsx")], { encoding: "utf8", windowsHide: true, timeout: 15000 }));
  const [headers, ...records] = workbook.Analyses;
  expect(records.map((row) => row[headers.indexOf("analysis_id")])).toEqual(exportRequest.payload.analysis_ids);
  expect(records.map((row) => row[headers.indexOf("source_row_number")])).toEqual(selected.map(({ source_row_number }) => source_row_number));
  expect(records.every((row) => /^[a-f0-9]{64}$/.test(row[headers.indexOf("source_sha256")]))).toBe(true);
  expect(workbook.Measurements.some((row) => row.includes("<0.01") && row.includes("below_detection_limit"))).toBe(true);
  expect(await readFile(second, "utf8")).toBe(content);
}, 45000);

test("an edit draft survives reopening and reports external source changes without changing the analysis", async () => {
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  const source = await readFile(second, "utf8");
  const openDraft = async () => {
    await user.click(await enabledButton("Поиск"));
    const actions = await screen.findByLabelText("Действия для анализа B1");
    await user.click(actions);
    await user.click(within(actions.closest("details")).getByRole("button", { name: "Исправить" }));
    const details = within(await screen.findByRole("complementary", { name: "Подробности анализа" }));
    expect(details.getByRole("heading", { name: "B1" })).toBeTruthy();
    return details.findByRole("form", { name: "Новый черновик правки" });
  };
  await user.click(screen.getByRole("checkbox", { name: "Выбрать B2" }));
  const form = within(await openDraft());
  expect(screen.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
  expect(screen.getByRole("checkbox", { name: "Выбрать B1" }).checked).toBe(false);
  expect(requests.some(({ command }) => ["edit_draft.save", "edit_draft.commit"].includes(command))).toBe(false);
  const newValue = form.getByLabelText("Новое значение");
  await waitFor(() => expect(newValue.disabled).toBe(false));
  await user.type(newValue, "42");
  expect(newValue.value).toBe("42");
  await user.click(await enabledButton("Сохранить черновик"));
  await screen.findByText("Черновик сохранён.");
  await screen.findByText("Было 40 → предлагается 42 wt.%");
  expect(await readFile(second, "utf8")).toBe(source);
  app.unmount();
  await stopService();
  await writeFile(second, "Analysis,SiO2 [wt.%]\nB1,99\nB2,41\n");
  await startService();
  render(<App />);
  await openDraft();
  await screen.findByText("Было 40 → предлагается 42 wt.%");
  await user.click(await enabledButton("Проверить исходный файл"));
  await screen.findByText("Исходный файл изменился");
  const table = within(screen.getByRole("table"));
  expect(table.getByText("40")).toBeTruthy();
  expect(table.queryByText("42")).toBeNull();
  expect(await readFile(second, "utf8")).toContain("B1,99");
}, 20000);

test("unit suggestions are not dirty edits and one valid mapping can be applied while others remain unresolved", async () => {
  await writeFile(second, 'Analysis,SiO2,MgO\nB1,40,50\nB2,41,49\n');
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton('Выбрать файл'));
  await enabledButton('Добавить файл');
  await enabledButton('Нужно решить 2');
  const unit = await screen.findByRole('combobox', { name: 'Единица SiO2' });
  await waitFor(() => expect(unit.disabled).toBe(false));
  await user.selectOptions(unit, 'wt.%');
  await user.click(await enabledButton(/Применить сопоставление/));
  await enabledButton('Нужно решить 1');
  expect(screen.getByRole('button', { name: 'Импортировать после проверки' }).disabled).toBe(true);
}, 20000);

test("real Python semantic range context action, extension confirmation and undo preserve the workbook", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  const firstCell = await screen.findByLabelText("Ячейка 2:1");
  fireEvent.contextMenu(firstCell);
  await user.click(screen.getByRole("menuitem", { name: "Назначить образец" }));
  await user.type(screen.getByLabelText("Значение назначения"), "K-17");
  await user.click(await enabledButton("Назначить диапазону"));
  await enabledButton("Отменить последнее назначение");
  await waitFor(() => expect(screen.getByLabelText("Ячейка 2:1").title).toContain("K-17"));
  const endRow = screen.getByLabelText("До строки");
  await user.clear(endRow);
  await user.type(endRow, "3");
  const before = requests.filter(r => r.command === "import.workspace.apply_decision").length;
  await user.click(await enabledButton("Проверить расширение до выделения"));
  await enabledButton("Подтвердить расширение");
  expect(requests.filter(r => r.command === "import.workspace.apply_decision")).toHaveLength(before);
  await user.click(await enabledButton("Подтвердить расширение"));
  await waitFor(() => expect(screen.getByLabelText("Ячейка 3:1").title).toContain("K-17"));
  await user.click(await enabledButton("Отменить последнее назначение"));
  await waitFor(() => expect(screen.getByLabelText("Ячейка 3:1").title).not.toContain("K-17"));
  expect(await readFile(first, "utf8")).toBe(original);
}, 20000);

test("selected analyses can be assigned to a new physical sample during import", async () => {
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Открыть подробную проверку"));
  fireEvent.contextMenu(await screen.findByLabelText("Ячейка 2:1"));
  await user.click(screen.getByRole("menuitem", { name: "Назначить образец" }));
  await user.selectOptions(await screen.findByLabelText("Физический образец"), "new");
  await user.type(screen.getByLabelText("Имя нового образца"), "K-17 B");
  await user.click(await enabledButton("Связать с физическим образцом"));
  await enabledButton("Снять связь");
  await user.click(await enabledButton("Сохранить импорт в проект"));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  await user.click(await table.findByText("B1"));
  const details = within(await screen.findByRole("complementary", { name: "Подробности анализа" }));
  expect(await details.findByText("K-17 B")).toBeTruthy();
  await user.click(await table.findByText("B2"));
  expect(details.queryByText("K-17 B")).toBeNull();
  await user.click(table.getByRole("checkbox", { name: "Выбрать B2" }));
  await user.click(await enabledButton("Образцы"));
  await screen.findByRole("heading", { name: "Образец K-17 B" });
  await user.click(await enabledButton("Редактировать паспорт"));
  await user.type(screen.getByLabelText("Местонахождение или обнажение"), "Северный массив");
  await user.click(await enabledButton("Сохранить паспорт"));
  await screen.findByText("Северный массив");
  await user.type(screen.getByLabelText("Автор заметки"), "А. Иванов");
  await user.type(screen.getByLabelText("Текст заметки"), "Полевое описание образца");
  await user.click(await enabledButton("Добавить заметку"));
  await screen.findByText("Полевое описание образца");
  await user.click(await enabledButton("Открыть источники"));
  await user.click(await enabledButton("Открыть анализы источника"));
  await screen.findByText("Найдено анализов: 1. Отмечено: 0. В отборе: 1.");
  expect(screen.queryByRole("button", { name: "Открыть анализ B2" })).toBeNull();
  await user.click(await enabledButton("Открыть анализ B1"));
  await screen.findByRole("heading", { name: "Анализы" });
  expect(within(await screen.findByRole("table")).getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
  await user.click(await enabledButton("Образцы"));
  const sampleTabs = within(await screen.findByRole("navigation", { name: "Разделы образца" }));
  expect(sampleTabs.getByRole("button", { name: "Источники" }).getAttribute("aria-current")).toBe("page");
  await user.click(sampleTabs.getByRole("button", { name: "Обзор" }));
  expect(await screen.findByText("Северный массив")).toBeTruthy();
  expect(await screen.findByText("Полевое описание образца")).toBeTruthy();
}, 20000);

test("numeric filters distinguish blanks, detection limits and zero without clearing selection", async () => {
  await writeFile(second, "Analysis,F (wt.%)\nA-ZERO,0\nA-CENSORED,<1\nA-MISSING,\nA-HIGH,10\n");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  const table = within(await screen.findByRole("table"));
  await user.click(await table.findByRole("checkbox", { name: "Выбрать A-HIGH" }));
  const filter = table.getByRole("textbox", { name: "Фильтр F" });
  for (const [expression, expected] of [["=0", "A-ZERO"], ["ниже предела", "A-CENSORED"], ["пусто", "A-MISSING"], ["9,5..10", "A-HIGH"]]) {
    fireEvent.change(filter, { target: { value: expression } });
    expect(table.getAllByRole("row")).toHaveLength(3);
    expect(table.getByText(expected)).toBeTruthy();
    if (expected !== "A-HIGH") expect(screen.getByText("Скрыто фильтром: 1")).toBeTruthy();
  }
  await user.click(screen.getByRole("button", { name: "Снять фильтр F" }));
  expect(table.getByRole("checkbox", { name: "Выбрать A-HIGH" }).checked).toBe(true);
}, 20000);

test("opens field context and exports a byte-for-byte photo original and a decorated copy without annotations", async () => {
  const source = join(folder, "ppl.png");
  const originalImage = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAAUElEQVR4nM3OMQEAIAzAsFJleEAI/j/+GaBRkLXvoURiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJMbfgekBmXUBQky7dlsAAAAASUVORK5CYII=", "base64");
  await writeFile(source, originalImage);
  mediaQueue = [source];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Изображения"));
  await user.click(await enabledButton("Импорт изображений"));
  await user.click(await enabledButton("Выбрать изображения"));
  await user.selectOptions(await screen.findByLabelText("Физический образец"), "new");
  await user.type(screen.getByLabelText("Имя нового образца"), "SM-01B");
  await user.click(await enabledButton("ppl.png"));
  await screen.findByRole("img", { name: "Изображение шлифа" });
  await user.selectOptions(screen.getByLabelText("Тип"), "Полевое фото");
  await user.click(screen.getByRole("checkbox", { name: "Без шлифа" }));
  expect(screen.queryByLabelText("Имя шлифа")).toBeNull();
  expect(screen.queryByLabelText("Аналитическая точка")).toBeNull();
  await user.click(await enabledButton("Проверить импорт изображений"));
  await within(await screen.findByRole("table")).findByText("Без шлифа");
  expect(screen.queryByText("В пакете есть изображения без размещённых точек.")).toBeNull();
  await user.click(await enabledButton("Импортировать изображения"));
  await screen.findByRole("heading", { name: "Образец SM-01B" });
  await user.click(within(screen.getByRole("navigation", { name: "Разделы образца" })).getByRole("button", { name: "Обзор" }));
  await user.click(await enabledButton("Редактировать паспорт"));
  await user.type(screen.getByLabelText("Местонахождение или обнажение"), "Северный массив · обнажение 12");
  await user.type(screen.getByLabelText("Хранение"), "ящик 4, кассета B");
  await user.click(await enabledButton("Сохранить паспорт"));
  await screen.findByText("Северный массив · обнажение 12");
  expect(screen.getByText("ящик 4, кассета B")).toBeTruthy();
  expect(screen.getByText("Шлифы · 0")).toBeTruthy();
  await user.type(screen.getByLabelText("Автор заметки"), "Иванов");
  await user.type(screen.getByLabelText("Текст заметки"), "Свежая поверхность отбора.");
  await user.click(await enabledButton("Добавить заметку"));
  await screen.findByText("Свежая поверхность отбора.");
  await user.click(await enabledButton("Открыть"));
  const preview = await screen.findByRole("img", { name: "Снимок образца" });
  expect(preview.src.startsWith("data:image/jpeg;base64,")).toBe(true);
  await user.click(await enabledButton("Выгрузить оригинал"));
  await screen.findByText(/Сохранено: .*copy-ppl.png/);
  expect(await readFile(join(folder, "copy-ppl.png"))).toEqual(originalImage);
  await user.click(screen.getByRole("checkbox", { name: "Масштабная линейка", exact: true }));
  await user.click(screen.getByRole("checkbox", { name: "Легенда", exact: true }));
  await user.selectOptions(screen.getByLabelText("Единица линейки"), "cm");
  expect(screen.getByRole("button", { name: "Выгрузить с разметкой" }).disabled).toBe(true);
  await user.type(screen.getByLabelText("Известная горизонтальная длина"), "4");
  await user.type(screen.getByLabelText("Длина этого отрезка в пикселях оригинала"), "24");
  await user.click(await enabledButton("Выгрузить с разметкой"));
  await screen.findByText(/Сохранено: .*copy-ppl-annotated.png/);
  const rendered = await readFile(join(folder, "copy-ppl-annotated.png"));
  expect(rendered.includes(Buffer.from('"rendered_scale": {"pixels": 12, "length": 2.0, "unit": "cm"}'))).toBe(true);
  expect(rendered.includes(Buffer.from('"rendered_legend": {"points": 0, "regions": 0}'))).toBe(true);
  expect(await readFile(source)).toEqual(originalImage);
  await user.click(await enabledButton("Добавить снимок с разметкой в пакет"));
  await screen.findByRole("heading", { name: "Состав пакета" });
  await user.type(screen.getByLabelText("Название пакета"), "Полевой материал");
  await user.click(await enabledButton("Проверить пакет"));
  await screen.findByText("images/01-media_capture.png");
  await user.click(await enabledButton("Собрать ZIP"));
  await screen.findByText(/Пакет сохранён:/);
  expect((await readFile(join(folder, "petrolab-package.zip"))).includes(Buffer.from("images/01-media_capture.png"))).toBe(true);
}, 20000);

test("AT-26 hands only marked analyses to an existing point and can undo the whole link", async () => {
  const content = "Analysis,Sample,Method,SiO2 [wt.%]\n"
    + "Epma,Z-2,EPMA,52\nTrace,Z-2,LA-ICP-MS,48\nPrior,Z-2,EPMA,50\nOther,Z-2,EPMA,54\nForeign,A-1,EPMA,51\n";
  await writeFile(first, content);
  const database = { project_database_path: join(folder, "project.sqlite") };
  let { result: workspace } = await invokePetrolab("import.workspace.create", { ...database, sources: [{ staged_path: first }] });
  for (const sampleName of ["Z-2", "A-1"]) {
    const previewIds = workspace.active.plan.planned_records
      .filter((row) => row.sample_association.reported.value === sampleName).map(({ preview_id }) => preview_id);
    const { workspace_id, draft_revision, active_source_id } = workspace.session;
    ({ result: workspace } = await invokePetrolab("import.workspace.apply_decision", {
      workspace_id, expected_revision: draft_revision, source_id: active_source_id,
      decision: { kind: "sample_assignment", mode: "new", sample_name: sampleName, preview_ids: previewIds },
    }));
  }
  expect((await invokePetrolab("import.workspace.commit", {
    workspace_id: workspace.session.workspace_id, expected_revision: workspace.session.draft_revision,
  })).error).toBeUndefined();
  const before = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const ids = Object.fromEntries(before.map(({ identity, analysis_id }) => [identity.Analysis, analysis_id]));
  const sampleId = before.find(({ analysis_id }) => analysis_id === ids.Epma).sample_association.sample_id;
  const original = [ids.Prior, ids.Other];
  const marked = [ids.Epma, ids.Trace];
  const { result: point } = await invokePetrolab("analytical_point.create", { ...database, sample_id: sampleId,
    point_name: "P-07", analysis_ids: original, link_type: "same_point", actor: "QA" });
  expect(point.analytical_point_id).toBeTruthy();
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Поиск"));
  const checkbox = (name) => screen.getByRole("checkbox", { name: `Отметить ${name}` });
  await user.click(await screen.findByRole("checkbox", { name: "Отметить Prior" }));
  await user.click(await enabledButton("Добавить отмеченные в отбор"));
  await user.click(checkbox("Prior"));
  for (const name of ["Epma", "Trace", "Foreign"]) await user.click(checkbox(name));
  await user.click(screen.getByLabelText("Другие действия с отмеченными"));
  await user.click(await enabledButton("Начать массовую привязку"));
  await screen.findByText("Отмеченные анализы должны быть доступны и относиться к одному физическому образцу.");
  expect(requests.filter(({ command }) => command === "analytical_point.link.set")).toHaveLength(0);
  await user.click(checkbox("Foreign"));
  await user.click(await enabledButton("Начать массовую привязку"));
  await screen.findByRole("heading", { name: "Образец Z-2" });
  await screen.findByText(/Отмечено в поиске: 2/);
  expect(requests.filter(({ command }) => command === "analytical_point.link.set")).toHaveLength(0);
  await user.selectOptions(screen.getByLabelText("Куда привязать"), point.analytical_point_id);
  await user.click(await enabledButton("Связать анализы"));
  await screen.findByText("К точке «P-07» привязано анализов: 2.");
  expect(requests.find(({ command }) => command === "analytical_point.link.set").payload.analysis_ids).toEqual(marked);
  const journal = (await invokePetrolab("operation_journal.list", database)).result.entries;
  const entry = (await invokePetrolab("operation_journal.open", { ...database, operation_id: journal[0].id })).result;
  expect(entry.scope.map(({ entity_type, entity_id }) => [entity_type, entity_id]))
    .toEqual([["analytical_point", point.analytical_point_id], ...marked.map((id) => ["analysis", id])]);
  expect((await invokePetrolab("analytical_point.analyses", { ...database, point_id: point.analytical_point_id })).result
    .map(({ analysis_id }) => analysis_id).sort()).toEqual([...original, ...marked].sort());
  await user.click(await enabledButton("Отменить пакетную привязку"));
  await screen.findByText("Пакетная привязка отменена.");
  expect((await invokePetrolab("analytical_point.analyses", { ...database, point_id: point.analytical_point_id })).result
    .map(({ analysis_id }) => analysis_id).sort()).toEqual([...original].sort());
  expect(screen.getByText(/В отборе: 1/)).toBeTruthy();
  await user.click(await enabledButton("Поиск"));
  const epmaActions = await screen.findByLabelText("Действия для анализа Epma");
  await user.click(epmaActions);
  await user.click(within(epmaActions.closest("details")).getByRole("button", { name: "Открыть образец" }));
  await screen.findByRole("heading", { name: "Образец Z-2" });
  await user.click(await enabledButton("Анализы · 4"));
  await screen.findByText(/Найдено анализов: 4\. Отмечено: 0\. В отборе: 1/);
  expect(screen.queryByRole("button", { name: "Открыть анализ Foreign" })).toBeNull();
  const epmaMenu = await screen.findByLabelText("Действия для анализа Epma");
  await user.click(epmaMenu);
  await user.click(within(epmaMenu.closest("details")).getByRole("button", { name: "Привязать к аналитической точке" }));
  await screen.findByText(/Отмечено в поиске: 1/);
  expect(screen.getByRole("button", { name: "Связать анализы" }).disabled).toBe(true);
  await user.selectOptions(screen.getByLabelText("Куда привязать"), point.analytical_point_id);
  expect(screen.getByRole("button", { name: "Связать анализы" }).disabled).toBe(false);
  await user.click(await enabledButton("Отмена"));
  expect(requests.filter(({ command }) => command === "analytical_point.link.set")).toHaveLength(1);
  expect((await invokePetrolab("project.analyses.list", database)).result.analyses).toEqual(before);
  expect(await readFile(first, "utf8")).toBe(content);
}, 30000);

test("point links restore the original removal through its journal entry", async () => {
  const content = "Analysis,Sample,SiO2 [wt.%]\nP1,KIV-2,52\nP2,KIV-2,48\n";
  await writeFile(first, content);
  const database = { project_database_path: join(folder, "project.sqlite") };
  const { result: { recipe } } = await invokePetrolab("import.recipe.suggest", { source_path: first });
  expect((await invokePetrolab("import.plan.apply", { ...database, source_path: first, recipe })).error).toBeUndefined();
  const before = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const point = (await invokePetrolab("analytical_point.create", { ...database, sample_name: "KIV-2", point_name: "P-07",
    analysis_ids: before.map(({ analysis_id }) => analysis_id), link_type: "same_point" })).result;
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Связи"));
  await user.click(await enabledButton("P-07"));
  const linked = await screen.findByText(/^P1(?: ·|$)/);
  await user.click(within(linked.closest("li")).getByRole("button", { name: "Снять связь" }));
  await screen.findByText("Связь снята.");
  expect(screen.queryByText(/^P1(?: ·|$)/)).toBeNull();
  expect(screen.getByText(/^P2(?: ·|$)/)).toBeTruthy();
  await user.click(await enabledButton("Восстановить снятую связь"));
  await screen.findByText("Связь восстановлена.");
  expect(await screen.findByText(/^P1(?: ·|$)/)).toBeTruthy();
  expect(requests.filter(({ command }) => command === "analytical_point.link.set")).toHaveLength(1);
  expect(requests.find(({ command }) => command === "analytical_point.link.undo").payload.operation_id).toBeTruthy();
  const after = await invokePetrolab("analytical_point.analyses", { ...database, point_id: point.analytical_point_id });
  expect(after.result).toHaveLength(2);
  expect((await invokePetrolab("project.analyses.list", database)).result.analyses).toEqual(before);
  expect(await readFile(first, "utf8")).toBe(content);
}, 20000);

test("AT-10 carries an explicitly selected thin-section analysis into the table and both plots", async () => {
  const image = join(folder, "at10-bse.png");
  const pixels = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAAGklEQVR4nO3BAQEAAACCIP+vbkhAAQAAAPBsEiAAAZJII8cAAAAASUVORK5CYII=", "base64");
  const epma = "Analysis,Sample,Method,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\nEPMA-07,KIV-2,EPMA,52,18,10\nPrior,KIV-2,EPMA,48,20,14\n";
  const trace = "Analysis,Sample,Method,La [ppm],Ce [ppm]\nLA-07,KIV-2,LA-ICP-MS,7,14\n";
  await Promise.all([writeFile(image, pixels), writeFile(first, epma), writeFile(second, trace)]);
  const database = { project_database_path: join(folder, "project.sqlite") };
  for (const source_path of [first, second]) {
    const { result: { recipe } } = await invokePetrolab("import.recipe.suggest", { source_path });
    expect((await invokePetrolab("import.plan.apply", { ...database, source_path, recipe })).error).toBeUndefined();
  }
  const before = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const ids = Object.fromEntries(before.map(({ identity, analysis_id }) => [identity.Analysis, analysis_id]));
  const point = (await invokePetrolab("analytical_point.create", { ...database, sample_name: "KIV-2", point_name: "P-07",
    analysis_ids: [ids["EPMA-07"], ids["LA-07"]], link_type: "same_point" })).result;
  const { result: plan } = await invokePetrolab("media.import.plan", { ...database, assignments: [{
    source_path: image, ownership_mode: "managed_copy", media_type: "BSE", sample_name: "KIV-2", thin_section_name: "TS1",
    placements: [{ analytical_point_id: point.analytical_point_id, geometry: { kind: "point", x_px: 36, y_px: 8 }, cross_sample_exception_reason: null }],
  }] });
  expect((await invokePetrolab("media.import.apply", { ...database, plan })).result.created_media_asset_count).toBe(1);
  const preview = await invokePetrolab("media.preview", { ...database, media_asset_id: plan.items[0].media_asset_id });
  expect(preview.result?.annotations, JSON.stringify(preview.error)).toMatchObject([{ point_name: "P-07" }]);

  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Анализы"));
  await user.click(await screen.findByRole("checkbox", { name: "Выбрать Prior" }));
  await user.click(await enabledButton("Образцы"));
  await user.click(await enabledButton("Шлифы"));
  await user.click(await screen.findByText("TS1", { exact: true }));
  await user.click(await enabledButton("Открыть"));
  await user.click(await enabledButton("P-07"));
  const links = within(await screen.findByRole("complementary", { name: "Анализы точки" }));
  const epmaLink = within((await links.findByText(/^EPMA-07\b/)).closest("li"));
  const traceLink = within((await links.findByText(/^LA-07\b/)).closest("li"));
  expect(epmaLink.getByRole("button", { name: "Добавить в отбор" }).disabled).toBe(false);
  expect(traceLink.getByRole("button", { name: "Добавить в отбор" }).disabled).toBe(false);
  await user.click(epmaLink.getByRole("button", { name: "Добавить в отбор" }));
  expect(epmaLink.getByRole("button", { name: "Добавить в отбор" }).disabled).toBe(true);
  expect(traceLink.getByRole("button", { name: "Добавить в отбор" }).disabled).toBe(false);
  await user.click(epmaLink.getByRole("button", { name: "Открыть анализ" }));

  const table = within(await screen.findByRole("table"));
  for (const [label, checked] of [["EPMA-07", true], ["Prior", true], ["LA-07", false]]) {
    expect(table.getByRole("checkbox", { name: `Выбрать ${label}` }).checked).toBe(checked);
  }
  const detail = within(screen.getByRole("complementary", { name: "Подробности анализа" }));
  expect(detail.getAllByText("EPMA-07", { exact: true }).length).toBeGreaterThan(0);
  await user.click(await enabledButton("Построить диаграммы"));
  await waitFor(() => {
    const markers = screen.getAllByRole("button", { name: /^Выбрать точку EPMA-07\b/, pressed: true });
    expect(markers).toHaveLength(2);
    expect(markers.map((marker) => marker.dataset.analysisId)).toEqual([ids["EPMA-07"], ids["EPMA-07"]]);
  });
  expect(screen.queryByRole("button", { name: /^Выбрать точку LA-07\b/ })).toBeNull();
  for (const kind of ["binary", "ternary"]) {
    expect(requests.findLast(({ command, payload }) => command === "plot_data.query" && payload.kind === kind).payload.analysis_ids)
      .toEqual([ids.Prior, ids["EPMA-07"]]);
  }
  const final = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  expect(final.map(({ measurement_list }) => measurement_list)).toEqual(before.map(({ measurement_list }) => measurement_list));
  expect(await Promise.all([readFile(first, "utf8"), readFile(second, "utf8"), readFile(image)])).toEqual([epma, trace, pixels]);
}, 30000);

test("saves a thin section point placed at 20× and reopens its original area after restarting Python", async () => {
  const source = join(folder, "bse.png");
  const originalImage = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAAUElEQVR4nM3OMQEAIAzAsFJleEAI/j/+GaBRkLXvoURiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJEZiJMbfgekBmXUBQky7dlsAAAAASUVORK5CYII=", "base64");
  await writeFile(source, originalImage);
  await writeFile(second, "Analysis,Sample,SiO2 [wt.%]\nB1,KIV-2,40\nB2,KIV-2,41\n");
  queue = [second]; mediaQueue = [source];
  const user = userEvent.setup();
  let app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  const database = { project_database_path: join(folder, "project.sqlite") };
  const input = await invokePetrolab("project.analyses.list", database);
  const pointFixture = await invokePetrolab("analytical_point.create", { ...database, sample_name: "KIV-2", point_name: "P-07",
    analysis_ids: input.result.analyses.map((row) => row.analysis_id), link_type: "same_point" });
  expect(pointFixture.result.point_name).toBe("P-07");
  await user.click(await enabledButton("Изображения"));
  await user.click(await enabledButton("Импорт изображений"));
  await user.click(await enabledButton("Выбрать изображения"));
  await user.selectOptions(await screen.findByLabelText("Физический образец"), await screen.findByRole("option", { name: "KIV-2" }));
  await user.type(screen.getByLabelText("Имя шлифа"), "TS1");
  await user.click(await enabledButton("bse.png"));
  await user.selectOptions(await screen.findByLabelText("Аналитическая точка"), await screen.findByRole("option", { name: "P-07" }));

  const mockGeometry = () => {
    const viewport = app.container.querySelector(".media-viewer");
    const scene = app.container.querySelector(".media-scene");
    const svg = screen.getByLabelText("Аннотации изображения");
    Object.defineProperties(viewport, { clientWidth: { value: 480 }, clientHeight: { value: 320 } });
    scene.getBoundingClientRect = () => ({ width: parseInt(scene.style.width) * 4.8, height: parseInt(scene.style.width) * 3.2 });
    svg.getBoundingClientRect = () => ({ ...scene.getBoundingClientRect(), left: -viewport.scrollLeft, top: -viewport.scrollTop });
    return { viewport, svg };
  };
  const { viewport, svg } = mockGeometry();
  fireEvent.change(screen.getByRole("slider", { name: "Масштаб изображения" }), { target: { value: "2000" } });
  viewport.scrollLeft = 6960;
  viewport.scrollTop = 1440;
  fireEvent.scroll(viewport);
  await waitFor(() => expect(app.container.querySelector(".media-precision-region")?.src).toContain("data:image/png;base64,"));
  fireEvent(svg, new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 240, clientY: 160 }));
  expect(svg.querySelector("circle").getAttribute("cx")).toBe("36");
  await user.click(await enabledButton("Проверить импорт изображений"));
  await user.click(await enabledButton("Импортировать изображения"));
  await screen.findByRole("heading", { name: "Образец KIV-2" });
  const apply = requests.find((request) => request.command === "media.import.apply");
  const placement = apply.payload.plan.items[0].placements[0];
  expect(placement.geometry).toMatchObject({ kind: "point", x_px: 36, y_px: 8 });

  app.unmount();
  await stopService();
  await startService();
  app = render(<App />);
  await user.click(await enabledButton("Образцы"));
  await user.click(await enabledButton("Шлифы"));
  await user.click(await screen.findByText("TS1", { exact: true }));
  await user.click(await enabledButton("Открыть"));
  const point = await enabledButton("P-07");
  mockGeometry();
  await user.click(point);
  expect(screen.getByRole("slider", { name: "Масштаб изображения" }).value).toBe("2000");
  const finalSvg = screen.getByLabelText("Аннотации изображения");
  expect([finalSvg.querySelector("circle").getAttribute("cx"), finalSvg.querySelector("circle").getAttribute("cy")]).toEqual(["36", "8"]);
  await waitFor(() => expect(app.container.querySelector(".media-precision-region")?.src).toContain("data:image/png;base64,"));
  const saved = await invokePetrolab("media.preview", { ...database, media_asset_id: apply.payload.plan.items[0].media_asset_id });
  expect(saved.result.annotations[0].spatial_annotation_id).toBe(placement.spatial_annotation_id);
  await user.click(await enabledButton("Создать ручную запись"));
  await user.type(screen.getByLabelText("ID / номер анализа"), "EPMA-007");
  fireEvent.change(screen.getByLabelText("Дата измерения"), { target: { value: "2026-08-28" } });
  await user.type(screen.getByLabelText("Оператор"), "Иванов");
  await user.type(screen.getByLabelText("FeO"), "<0.05");
  await user.click(await enabledButton("Создать и связать с P-07"));
  await screen.findByText("Анализ «EPMA-007» создан и связан с точкой.");
  const linked = await invokePetrolab("analytical_point.analyses", { ...database, point_id: pointFixture.result.analytical_point_id });
  const manual = linked.result.find(({ identity }) => identity === "EPMA-007");
  expect(manual).toMatchObject({ method: "EPMA", source_name: "Ручной ввод.csv", link_type: "same_point" });
  expect(screen.getByRole("slider", { name: "Масштаб изображения" }).value).toBe("2000");
  const photoPath = join(folder, "detail.png");
  const photoBytes = Buffer.concat([originalImage, Buffer.from("detail fixture")]);
  await writeFile(photoPath, photoBytes);
  mediaQueue = [photoPath];
  await user.click(await enabledButton("Медиа и привязка"));
  await user.click(await enabledButton("Выбрать файл фото"));
  await screen.findByRole("img", { name: "Выбранная фотография" });
  await user.click(await enabledButton("Прикрепить фото"));
  const inspector = within(screen.getByRole("complementary", { name: "Медиа и привязка" }));
  await inspector.findByText("detail.png");
  const pointLinks = await invokePetrolab("media.links.list", { ...database, spatial_annotation_id: placement.spatial_annotation_id });
  expect(pointLinks.result).toHaveLength(1);

  await user.click(await enabledButton("Выделить область"));
  await user.selectOptions(screen.getByLabelText("Форма области"), "square");
  const editable = screen.getByLabelText("Аннотации изображения");
  editable.setPointerCapture = () => {};
  await waitFor(() => expect(app.container.querySelector(".media-precision-region")?.src).toContain("data:image/png;base64,"));
  fireEvent(editable, new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 200, clientY: 120 }));
  fireEvent(editable, new MouseEvent("pointerup", { bubbles: true, button: 0, clientX: 300, clientY: 220 }));
  await enabledButton("Z-01");
  await user.selectOptions(await screen.findByLabelText("Фото из проекта"), await screen.findByRole("option", { name: "detail.png" }));
  await user.click(await enabledButton("Прикрепить из проекта"));
  await screen.findByText("Связанные фото (1)");
  await user.click(await enabledButton("Снять привязку"));
  await screen.findByText("Связанные фото (0)");
  const pointStillLinked = await invokePetrolab("media.links.list", { ...database, spatial_annotation_id: placement.spatial_annotation_id });
  expect(pointStillLinked.result).toEqual(pointLinks.result);
  expect(await readFile(photoPath)).toEqual(photoBytes);
  expect(await readFile(source)).toEqual(originalImage);
}, 30000);

test("media review names the unreadable image and lets the user finish with the remaining file", async () => {
  const image = join(folder, "BSE.png");
  const damaged = join(folder, "PPL.png");
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAAGklEQVR4nO3BAQEAAACCIP+vbkhAAQAAAPBsEiAAAZJII8cAAAAASUVORK5CYII=", "base64");
  const truncated = png.subarray(0, 24);
  await Promise.all([writeFile(image, png), writeFile(damaged, truncated)]);
  mediaQueue = [image, damaged];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Изображения"));
  await user.click(await enabledButton("Импорт изображений"));
  await user.click(await enabledButton("Выбрать изображения"));
  await user.selectOptions(await screen.findByLabelText("Физический образец"), "new");
  await user.type(screen.getByLabelText("Имя нового образца"), "KIV-2");
  await user.type(screen.getByLabelText("Имя шлифа"), "TS1");
  await user.click(await enabledButton("Проверить импорт изображений"));
  expect((await screen.findByRole("alert")).textContent).toContain("Не удалось прочитать пиксели изображения «PPL.png».");
  expect(screen.queryByRole("button", { name: "Импортировать изображения" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Сохранить черновик" })).toBeNull();
  expect(requests.some(({ command }) => command === "media.import.apply")).toBe(false);
  const row = (await enabledButton("PPL.png")).closest("li");
  await user.click(within(row).getByRole("button", { name: "Убрать" }));
  await user.click(await enabledButton("Проверить импорт изображений"));
  const review = within(await screen.findByRole("table"));
  expect(review.getByText("BSE.png", { exact: true })).toBeTruthy();
  expect(review.queryByText("PPL.png", { exact: true })).toBeNull();
  await user.click(await enabledButton("Импортировать изображения"));
  await screen.findByText("Изображений импортировано: 1. Привязок: 0.");
  expect(await Promise.all([readFile(image), readFile(damaged)])).toEqual([png, truncated]);
}, 25000);

test("reviews a BSE/PPL/XPL batch and saves only manually placed and confirmed points", async () => {
  await writeFile(second, "Analysis,SiO2 [wt.%]\nA1,40\nA2,41\nA3,42\nA4,43\nA5,44\nA6,45\n");
  const photos = Object.fromEntries(Object.entries({
    BSE: "iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAAGklEQVR4nO3BAQEAAACCIP+vbkhAAQAAAPBsEiAAAZJII8cAAAAASUVORK5CYII=",
    PPL: "iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAATUlEQVR4nM3OQQEAIACEMCTh9U/j3wKyBDvbKJEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYifF34HUBU10BMEN2uoMAAAAASUVORK5CYII=",
    XPL: "iVBORw0KGgoAAAANSUhEUgAAADAAAAAgCAIAAADbtmxLAAAATUlEQVR4nM3OQQEAIACEMKR/iIvq3wKyBDvbKJEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYiZEYifF34HUBUHwCIEdGWBYAAAAASUVORK5CYII=",
  }).map(([type, bytes]) => [join(folder, `${type}.png`), Buffer.from(bytes, "base64")]));
  await Promise.all(Object.entries(photos).map(([path, bytes]) => writeFile(path, bytes)));
  queue = [second]; mediaFolder = folder;
  const user = userEvent.setup();
  let app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  const database = { project_database_path: join(folder, "project.sqlite") };
  const analyses = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const points = await Promise.all([["KIV-2", "P-07"], ["KIV-2", "P-08"], ["KIV-5", "P-03"]].map(([sample, name], index) =>
    invokePetrolab("analytical_point.create", { ...database, sample_name: sample, point_name: name,
      analysis_ids: analyses.slice(2 * index, 2 * index + 2).map((row) => row.analysis_id), link_type: "same_point" })));
  expect(points.every((point) => point.result)).toBe(true);
  await user.click(await enabledButton("Изображения"));
  await user.click(await enabledButton("Импорт изображений"));
  await user.click(await enabledButton("Добавить папку"));
  await user.selectOptions(await screen.findByLabelText("Физический образец"), await screen.findByRole("option", { name: "KIV-2" }));
  await user.type(screen.getByLabelText("Имя шлифа"), "KIV-2-A");
  for (const type of ["PPL", "XPL"]) {
    const row = (await enabledButton(`${type}.png`)).closest("li");
    await user.selectOptions(within(row).getByLabelText("Тип"), type);
  }
  await user.click(await enabledButton("BSE.png"));
  const choosePoint = async (name) => user.selectOptions(await screen.findByLabelText("Аналитическая точка"),
    await screen.findByRole("option", { name }));
  await choosePoint("P-07");
  expect(screen.queryByRole("option", { name: "P-03" })).toBeNull();
  const svg = screen.getByLabelText("Аннотации изображения");
  expect(svg.querySelectorAll("circle")).toHaveLength(0);
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 480, height: 320 });
  const clickImage = (x, y) => fireEvent(svg, new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: x, clientY: y }));
  clickImage(150, 120);
  await user.selectOptions(screen.getByLabelText("Образец аналитической точки"), points[2].result.sample_id);
  await choosePoint("P-03");
  clickImage(250, 220);
  expect(svg.querySelector(".media-provisional")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Проверить импорт изображений" }).disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Подтвердить исключение и сохранить связь" }).disabled).toBe(true);
  await user.selectOptions(screen.getByLabelText("Причина исключения"), "Изображение охватывает другой образец");
  await user.click(await enabledButton("Подтвердить исключение и сохранить связь"));
  expect(svg.querySelector(".media-provisional")).toBeNull();
  await user.click(await enabledButton("PPL.png"));
  await user.click(await screen.findByRole("checkbox", { name: "BSE.png · P-07" }));
  await user.click(screen.getByRole("checkbox", { name: "BSE.png · P-03" }));
  await user.click(await enabledButton("BSE.png"));
  await user.click(await enabledButton("Проверить импорт изображений"));
  await screen.findByText("Неразмещённые точки (1)");
  expect(screen.getByText("KIV-2 · KIV-2-A · P-08")).toBeTruthy();
  expect(screen.getByText(/BSE.png · KIV-5 \/ P-03 · Изображение охватывает другой образец/)).toBeTruthy();
  const rows = within(screen.getByRole("table")).getAllByRole("row");
  expect(rows.map((row) => row.textContent)).toEqual(expect.arrayContaining([
    "BSE.pngKIV-2KIV-2-ABSE201", "PPL.pngKIV-2KIV-2-APPL020", "XPL.pngKIV-2KIV-2-AXPL000",
  ]));
  const inspector = within(screen.getByRole("complementary", { name: "Выбранный снимок" }));
  const packageFiles = within(screen.getByRole("complementary", { name: "Файлы пакета" }));
  expect(packageFiles.getByRole("heading", { name: "KIV-2 · KIV-2-A" })).toBeTruthy();
  expect((await inspector.findByLabelText("Аннотации изображения")).querySelectorAll("circle")).toHaveLength(2);
  await user.click(packageFiles.getByRole("button", { name: "Показать снимок PPL.png" }));
  await inspector.findByRole("heading", { name: "PPL.png" });
  expect(inspector.getByText("На снимке нет размещённых точек.")).toBeTruthy();
  expect(inspector.queryByText(/Изображение охватывает другой образец/)).toBeNull();
  expect(inspector.getByText("PPL.png → BSE.png · P-07")).toBeTruthy();
  expect(inspector.getByText("PPL.png → BSE.png · P-03")).toBeTruthy();
  expect(inspector.getByText("KIV-2 · KIV-2-A · P-08")).toBeTruthy();
  expect([...screen.getByLabelText("Сводка пакета").querySelectorAll("dd")].map((value) => value.textContent))
    .toEqual(["3", "2", "2", "1", "1"]);
  expect(requests.some(({ command }) => command === "media.import.apply")).toBe(false);
  await user.click(await enabledButton("Сохранить черновик"));
  await screen.findByText("Черновик сохранён.");
  app.unmount();
  await stopService();
  await startService();
  app = render(<App />);
  await user.click(await enabledButton("Изображения"));
  await user.click(await enabledButton("Импорт изображений"));
  await user.click(await enabledButton("Восстановить черновик"));
  await screen.findByText("Черновик восстановлен.");
  expect(screen.getByText("Неразмещённые точки (1)")).toBeTruthy();
  expect(screen.getByText(/BSE.png · KIV-5 \/ P-03 · Изображение охватывает другой образец/)).toBeTruthy();
  await user.click(await enabledButton("Назад к назначению"));
  await user.click(await enabledButton("PPL.png"));
  expect((await screen.findByRole("checkbox", { name: "BSE.png · P-07" })).checked).toBe(true);
  expect(screen.getByRole("checkbox", { name: "BSE.png · P-03" }).checked).toBe(true);
  await user.click(await enabledButton("Проверить импорт изображений"));
  await user.click(await enabledButton("Завершить без неразмещённых точек"));
  await screen.findByText("Изображений импортировано: 3. Привязок: 2. Связей фото: 2.");
  const apply = requests.find((request) => request.command === "media.import.apply").payload.plan;
  const bse = apply.items.find((item) => item.media_type === "BSE");
  const saved = (await invokePetrolab("media.preview", { ...database, media_asset_id: bse.media_asset_id })).result.annotations;
  expect(saved.map((item) => item.point_name).sort()).toEqual(["P-03", "P-07"]);
  expect(saved.find((item) => item.point_name === "P-03")).toMatchObject({
    point_sample_id: points[2].result.sample_id, cross_sample_exception: 1, exception_reason: "Изображение охватывает другой образец",
  });
  const detail = apply.items.find((item) => item.media_type === "PPL");
  for (const annotation of saved) {
    const linked = (await invokePetrolab("media.links.list", { ...database, spatial_annotation_id: annotation.spatial_annotation_id })).result;
    expect(linked).toEqual([expect.objectContaining({ media_asset_id: detail.media_asset_id })]);
  }
  expect((await invokePetrolab("media.import.draft.load", database)).result).toBeNull();
  for (const [path, bytes] of Object.entries(photos)) expect(await readFile(path)).toEqual(bytes);
  expect(app.container.querySelector(".media-provisional")).toBeNull();
  await user.click(await screen.findByRole("checkbox", { name: "Выбрать снимок BSE.png" }));
  await user.click(screen.getByRole("checkbox", { name: "Выбрать снимок XPL.png" }));
  await user.selectOptions(screen.getByLabelText("Режим пакета"), "annotated");
  await user.click(screen.getByRole("checkbox", { name: "Линейка в пикселях" }));
  await user.click(await enabledButton("Выгрузить выбранные"));
  await screen.findByText(/Снимков в архиве: 2/);
  const batch = requests.find(({ command }) => command === "media.export_batch").payload;
  expect(batch.media_asset_ids).toEqual(apply.items.filter((item) => item.media_type !== "PPL").map((item) => item.media_asset_id));
  expect(batch.options).toMatchObject({ scale_bar: true, points: true, labels: true });
  const zip = await readFile(join(folder, "copy-PetroLab-images.zip"));
  expect(zip.includes(Buffer.from("manifest.json"))).toBe(true);
  expect(zip.includes(Buffer.from("PPL.png"))).toBe(false);
}, 30000);

test("real Python mineral review separates conflicts and persists only explicit acceptance", async () => {
  await writeFile(second, "Analysis,Mineral,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%)\nB1,olivine,40,0,50,0,0,0,10\nB2,garnet,40,0,50,0,0,0,10\n");
  const raw = await readFile(second, "utf8");
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("2 · Проверить минералы"));
  await screen.findByText("Расхождение с источником");
  await user.click(await enabledButton("Рассчитать формулу"));
  const formula = within(await screen.findByRole("form", { name: "Предпросмотр формулы" }));
  await user.selectOptions(formula.getByRole("combobox"), "formula.zircon.4o");
  await user.click(formula.getByRole("button", { name: "Рассчитать", exact: true }));
  expect((await formula.findByRole("alert")).textContent).toContain("ZrO2");
  await user.selectOptions(formula.getByRole("combobox"), "formula.olivine.4o");
  await user.click(formula.getByRole("button", { name: "Рассчитать", exact: true }));
  await formula.findByText("Предварительный расчёт");
  expect(formula.getByText("Mg", { exact: true }).nextElementSibling.textContent).toMatch(/^1,8/);
  await user.click(formula.getByRole("button", { name: "Закрыть формулу" }));
  const database = { project_database_path: join(folder, "project.sqlite") };
  expect((await invokePetrolab("formula.runs.list", database)).result).toEqual([]);
  await user.click(await enabledButton("Рассчитать формулу"));
  const confirmedFormula = within(await screen.findByRole("form", { name: "Предпросмотр формулы" }));
  await user.selectOptions(confirmedFormula.getByRole("combobox"), "formula.olivine.4o");
  await user.click(confirmedFormula.getByRole("button", { name: "Рассчитать", exact: true }));
  await user.click(await confirmedFormula.findByRole("button", { name: "Принять расчёт" }));
  await user.click(await screen.findByText("Формулы к сохранению · 1"));
  await user.click(await enabledButton("Снять подтверждение"));
  await waitFor(() => expect(screen.queryByText("Формулы к сохранению · 1")).toBeNull());
  await user.click(await enabledButton("Рассчитать формулу"));
  const finalFormula = within(await screen.findByRole("form", { name: "Предпросмотр формулы" }));
  await user.selectOptions(finalFormula.getByRole("combobox"), "formula.olivine.4o");
  await user.click(finalFormula.getByRole("button", { name: "Рассчитать", exact: true }));
  await user.click(await finalFormula.findByRole("button", { name: "Принять расчёт" }));
  await screen.findByText("Формулы к сохранению · 1");
  expect((await invokePetrolab("formula.runs.list", database)).result).toEqual([]);
  await user.click(await enabledButton("Принять группу совпадений"));
  await user.click(await enabledButton("Принять предложение"));
  await user.click(screen.getByLabelText("Показать все результаты"));
  await waitFor(() => expect(screen.getAllByText("Принято пользователем")).toHaveLength(2));
  expect(screen.getAllByText("garnet").length).toBeGreaterThan(0);
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });
  const runs = (await invokePetrolab("formula.runs.list", database)).result;
  expect(runs).toHaveLength(1);
  expect(runs[0]).toMatchObject({ method_id: "formula.olivine.4o", analysis_label: "B2" });
  const savedFormula = (await invokePetrolab("formula.run.open", { ...database, run_id: runs[0].id })).result;
  expect(savedFormula.status).toBe("current");
  expect(savedFormula.result_manifest.apfu.Mg).toBeCloseTo(1.8, 1);
  app.unmount();
  render(<App />);
  await user.click(await enabledButton("Анализы"));
  const table = within(await screen.findByRole("table"));
  await user.click(table.getByText("B2", { exact: true }));
  const detail = (await screen.findByRole("heading", { name: "Идентификация минерала" })).closest("section");
  expect(within(detail).getByText("принято", { exact: true })).toBeTruthy();
  expect(within(detail).getByText("В источнике", { exact: true }).nextElementSibling.textContent).toBe("garnet");
  expect(within(detail).getByText("Принято", { exact: true }).nextElementSibling.textContent).toBe("olivine");
  expect(await readFile(second, "utf8")).toBe(raw);
}, 20000);

test("pyroxene Droop review exposes the iron assumption and preserves reported FeOt", async () => {
  const raw = "Analysis,SiO2 (wt.%),TiO2 (wt.%),Al2O3 (wt.%),FeOt (wt.%),MnO (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%)\nP1,56.21,0,10.56,6.10,0.01,7.33,12.13,7.64,0.04\n";
  await writeFile(second, raw);
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("2 · Проверить минералы"));
  await user.click(await enabledButton("Рассчитать формулу"));
  const formula = within(await screen.findByRole("form", { name: "Предпросмотр формулы" }));
  await user.selectOptions(formula.getByRole("combobox"), "formula.pyroxene.6o.droop");
  expect(formula.getByText(/Целевая сумма — 4 катионов/).closest("details").open).toBe(true);
  expect(formula.getByText(/E2 · FeOt · 6\.10 wt\.%/).closest("details").open).toBe(true);
  await user.click(formula.getByRole("button", { name: "Рассчитать", exact: true }));
  await formula.findByText("Предварительный расчёт");
  await user.click(formula.getByText("Проверка допущений Droop, APFU"));
  expect(formula.getByText("Целевая сумма катионов").nextElementSibling.textContent).toBe("4");
  expect(formula.getByText("Fe3+", { exact: true }).nextElementSibling.textContent).toMatch(/^0,09/);
  await user.click(formula.getByRole("button", { name: "Принять расчёт" }));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  await screen.findByRole("heading", { name: "Анализы" });

  const database = { project_database_path: join(folder, "project.sqlite") };
  const [run] = (await invokePetrolab("formula.runs.list", database)).result;
  const saved = (await invokePetrolab("formula.run.open", { ...database, run_id: run.id })).result;
  expect(saved).toMatchObject({ status: "current", method_id: "formula.pyroxene.6o.droop" });
  expect(saved.result_manifest.iron_partition_apfu["Fe3+"]).toBeCloseTo(0.091, 3);
  const [analysis] = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  expect(analysis.measurement_list.filter(({ reported_fe_form }) => reported_fe_form)).toMatchObject([
    { field: "FeOt", reported_fe_form: "FeOt", raw_token: "6.10", source_cell: "E2" },
  ]);
  expect(await readFile(second, "utf8")).toBe(raw);
}, 20000);

test("mineral formula batch uses the highlighted range and leaves censored rows out", async () => {
  const raw = "Analysis,Mineral,SiO2 (wt.%),MgO (wt.%),FeO (wt.%)\nA1,olivine,40,50,10\nA2,olivine,40,<DL,10\nA3,olivine,39,48,12\nA4,olivine,39,48,12\n";
  await writeFile(second, raw);
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("2 · Проверить минералы"));
  await user.click(await enabledButton("Выделить строку 2"));
  await user.keyboard("{Shift>}");
  await user.click(await enabledButton("Выделить строку 4"));
  await user.keyboard("{/Shift}");
  await user.click(await enabledButton("Рассчитать формулы · 3"));
  const form = within(await screen.findByRole("form", { name: "Предпросмотр формул для выделения" }));
  await user.selectOptions(form.getByRole("combobox"), "formula.olivine.4o");
  await user.click(form.getByRole("button", { name: "Рассчитать", exact: true }));
  await form.findByText("Готово к подтверждению · 2 из 3 · Без расчёта 1");
  expect(form.getByText(/A2 · .*строка 3/)).toBeTruthy();
  expect(form.getByText(/MgO · <DL · ниже предела обнаружения/)).toBeTruthy();
  await user.click(form.getByRole("button", { name: "Принять расчёты · 2" }));
  await screen.findByText("Формулы к сохранению · 2");
  await user.click(await enabledButton("Сохранить импорт в проект"));
  await screen.findByRole("heading", { name: "Анализы" });
  const runs = (await invokePetrolab("formula.runs.list", { project_database_path: join(folder, "project.sqlite") })).result;
  expect(runs.map(({ analysis_label }) => analysis_label).sort()).toEqual(["A1", "A3"]);
  expect(await readFile(second, "utf8")).toBe(raw);
}, 20000);

test("statistics reviews mixed domains before clustering and preserves saved cluster membership on a new run", async () => {
  await writeFile(second, "Analysis,SiO2 [wt.%],Al2O3 [wt.%],La [ppm],MgO [wt.%],FeO [wt.%]\nA,1,2,2,45,10\nB,2,3,4,45,10\nC,20,40,5,45,10\nD,21,41,6,45,10\nE,<1,2,5,45,10\nF,0,3,5,45,10\n");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton(/^(Импортировать таблицу|Сохранить импорт в проект)$/));
  const table = within(await screen.findByRole("table"));
  const database = { project_database_path: join(folder, "project.sqlite") };
  const analyses = (await invokePetrolab("project.analyses.list", database)).result.analyses;
  const analysis = analyses.find(({ identity }) => identity.Analysis === "D");
  const formulaInput = { ...database, method_id: "formula.olivine.4o", analysis_id: analysis.analysis_id,
    measurement_ids: ["SiO2", "MgO", "FeO"].map((field) => analysis.measurements[field].measurement_id) };
  const formulaReview = (await invokePetrolab("formula.review", formulaInput)).result;
  const formula = await invokePetrolab("formula.run", { ...formulaInput, input_fingerprint: formulaReview.input_fingerprint,
    method_definition_fingerprint: formulaReview.method_definition_fingerprint });
  expect(formula.result).toBeTruthy();
  for (const name of ["A", "B", "C", "D", "E", "F"]) {
    await user.click(table.getByRole("checkbox", { name: `Выбрать ${name}` }));
  }
  await user.click(await enabledButton("Статистика"));
  await user.click(await enabledButton("Проверить данные"));
  await user.click(await screen.findByRole("checkbox", { name: /SiO2 · wt\.%/ }));
  await user.click(screen.getByRole("checkbox", { name: /La · ppm/ }));
  await user.click(await enabledButton("Проверить состав"));
  await screen.findByText(/CLR и ILR недоступны/);
  await user.click(await enabledButton("К выбору метода"));
  expect(screen.getByRole("option", { name: "CLR" }).disabled).toBe(true);
  expect(screen.getByRole("option", { name: "ILR" }).disabled).toBe(true);
  await user.click(await enabledButton("Назад к данным"));
  await user.click(screen.getByRole("checkbox", { name: /La · ppm/ }));
  await user.click(screen.getByRole("checkbox", { name: /Al2O3 · wt\.%/ }));
  await user.click(await enabledButton("Проверить состав"));
  await screen.findByText("Полных положительных строк · 4");
  await user.click(await enabledButton("К выбору метода"));
  await user.selectOptions(screen.getByLabelText("Путь анализа"), "ilr");
  await user.click(await enabledButton("Запустить расчёт"));
  await screen.findByRole("heading", { name: "Результат кластеризации" });
  expect(screen.getByLabelText("PCA-проекция кластеров")).toBeTruthy();
  await user.click(await enabledButton(/^Кластер 1 ·/));
  await user.type(screen.getByLabelText("Название рабочей группы"), "Группа ILR");
  await user.click(await enabledButton("Сохранить кластер как рабочую группу"));
  await screen.findByText(/Сохранена рабочая группа «Группа ILR»/);
  await user.click(await enabledButton("Назад к методу"));
  await user.selectOptions(screen.getByLabelText("Путь анализа"), "euclidean");
  await user.selectOptions(screen.getByLabelText("Масштабирование"), "robust");
  await user.click(await enabledButton("Запустить расчёт"));
  await screen.findByText("Евклидова разведочная · Робастное");
  expect(requests.filter((request) => request.command === "statistics.cluster.run")).toHaveLength(2);
  expect(requests.filter((request) => request.command === "statistics.cluster.save_group")).toHaveLength(1);
  await user.click(await enabledButton("Добавить расчёт в публикацию"));
  await user.click(await enabledButton("Добавить «Оливин на 4 атома кислорода · D»"));
  await user.type(screen.getByLabelText("Название пакета"), "Результат исследования");
  await user.type(screen.getByLabelText("Подпись материала 1"), "Кластеризация");
  await user.type(screen.getByLabelText("Подпись материала 2"), "Формула оливина");
  await user.click(await enabledButton("Проверить пакет"));
  await screen.findByText("Анализов · 6");
  expect(screen.getByText("data/derived_values.csv")).toBeTruthy();
  await user.click(await enabledButton("Собрать ZIP"));
  await screen.findByText(/Пакет сохранён: .*petrolab-package.zip/);
  const zip = await readFile(join(folder, "petrolab-package.zip"));
  expect(zip.includes(Buffer.from("manifest.json"))).toBe(true);
  expect(zip.includes(Buffer.from("data/derived_values.csv"))).toBe(true);
}, 20000);
