// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const bridge = vi.hoisted(() => ({ invoke: null }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args) => bridge.invoke(...args) }));
import { App } from "../src/App";
import { invokePetrolab } from "../src/desktopApi";
configure({ asyncUtilTimeout: 5000 });

let child, folder, first, second, queue, mediaQueue, mediaFolder, original, pending, lines, requests, plotExports;
async function startService() {
  child = spawn("python", ["-m", "petrolab.ndjson_service"], {
    cwd: resolve(process.cwd(), ".."), windowsHide: true,
    env: { ...process.env, PYTHONPATH: resolve(process.cwd(), "../src"), PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8",
      OPENBLAS_NUM_THREADS: "1" },
  });
  lines = createInterface({ input: child.stdout });
  lines.on("line", (line) => {
    const response = JSON.parse(line);
    const callback = pending.get(response.request_id);
    if (callback) { pending.delete(response.request_id); callback(response); }
  });
  child.on("error", (error) => { throw error; });
  const readiness = await invokePetrolab("import.inspect_source", { source_path: first });
  expect(readiness.result?.source_fingerprint, JSON.stringify(readiness.error)).toBeTruthy();
}

async function stopService() {
  child.stdin.end();
  await new Promise((resolve) => { if (child.exitCode !== null) resolve(); else child.once("exit", resolve); });
  lines.close();
}

beforeEach(async () => {
  folder = await mkdtemp(join(tmpdir(), "petrolab-workspace-ui-"));
  first = join(folder, "first.csv"); second = join(folder, "second.csv");
  original = "Analysis,Fe (wt.%),F (wt.%)\nA1,10,<DL\nA2,11,n.d.\n";
  await writeFile(first, original);
  await writeFile(second, "Analysis,SiO2 [wt.%]\nB1,40\nB2,41\n");
  queue = [first, second]; mediaQueue = []; mediaFolder = null; pending = new Map(); requests = []; plotExports = [];
  bridge.invoke = async (command, args) => {
    if (command === "project_database_path") return join(folder, "project.sqlite");
    if (command === "pick_import_file") return queue.shift() || null;
    if (command === "pick_media_files") return mediaQueue.splice(0);
    if (command === "pick_media_folder") return mediaFolder;
    if (command === "pick_media_export_path") return join(folder, `copy-${args.name}`);
    if (command === "pick_publication_export_path") return join(folder, "petrolab-package.zip");
    if (command === "pick_analysis_export_path") return join(folder, "selection.xlsx");
    if (command === "pick_plot_export_path") {
      const destination = join(folder, `diagram-${plotExports.length + 1}-${args.name}`);
      plotExports.push(destination);
      return destination;
    }
    if (command === "stage_import_file") return { local_path: args.sourcePath, original_path: args.sourcePath };
    if (command === "clear_import_staging") return;
    if (command !== "petrolab_command") throw new Error(command);
    requests.push(args.envelope);
    return new Promise((resolve) => {
      pending.set(args.envelope.request_id, resolve);
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
    expect(button.disabled, String(name)).toBe(false);
    return button;
  }, name === "Выбрать файл" ? { timeout: 12000 } : undefined);
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

test("overview opens a project source and global search opens an exact analysis without clearing selection", async () => {
  await writeFile(second, "Analysis,Sample,Mineral,SiO2 [wt.%]\nB1,Sample A,apatite,40\nB2,Sample B,olivine,41\n");
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
  await user.type(screen.getByLabelText("Минерал"), "APATITE");
  await user.click(await enabledButton("Найти"));
  await screen.findByText(/Найдено анализов: 1\. Отмечено: 0\. В отборе: 1/);
  await user.click(screen.getByRole("checkbox", { name: "Отметить B1" }));
  await screen.findByText(/Отмечено: 1\. В отборе: 1/);
  await user.click(await enabledButton("Открыть анализ B1"));
  const analysis = within(await screen.findByRole("complementary", { name: "Подробности анализа" }));
  expect(analysis.getByRole("heading", { name: "B1" })).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "Выбрать B2" }).checked).toBe(true);
  expect(screen.getByRole("checkbox", { name: "Выбрать B1" }).checked).toBe(false);
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
  const canvas = point.closest("svg");
  canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 460, height: 280 });
  canvas.setPointerCapture = () => {};
  const x = Number(point.getAttribute("cx"));
  const y = Number(point.getAttribute("cy"));
  function pointer(type, clientX, clientY) {
    const event = new MouseEvent(type, { bubbles: true, clientX, clientY, button: 0 });
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
  await user.click(await enabledButton("Вернуть скрытые точки · 1"));
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
  expect(layout.querySelector("clipPath, mask, foreignObject, image, circle")).toBeNull();
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
  await user.click(await enabledButton("Добавить слой из отбора"));
  const layer = within(screen.getByRole("group", { name: "Серия · 3" }));
  await user.selectOptions(layer.getByLabelText("Метод поля"), "convex_hull");
  await user.click(layer.getByRole("checkbox", { name: "Точки" }));
  await waitFor(() => expect(container.querySelectorAll(".plot-field")).toHaveLength(2));
  expect(screen.queryByRole("button", { name: "Выбрать точку P1" })).toBeNull();
  expect(screen.getByText("Выбранные анализы · 3")).toBeTruthy();
  const svg = new DOMParser().parseFromString(await readFile(await savePlot(user), "utf8"), "image/svg+xml");
  expect(svg.querySelectorAll("polygon")).toHaveLength(2);
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
}, 20000);

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
}, 20000);

test("an edit draft survives reopening and reports external source changes without changing the analysis", async () => {
  queue = [second];
  const user = userEvent.setup();
  const app = render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("Импортировать таблицу"));
  await screen.findByRole("heading", { name: "Анализы" });
  await user.click(within(await screen.findByRole("table")).getByText("B1"));
  await user.click(screen.getByText("Черновики правок", { exact: true }));
  const form = within(screen.getByRole("form", { name: "Новый черновик правки" }));
  await user.type(form.getByLabelText("Новое значение"), "42");
  await user.click(await enabledButton("Сохранить черновик"));
  await screen.findByText("Черновик сохранён.");
  app.unmount();
  await stopService();
  await writeFile(second, "Analysis,SiO2 [wt.%]\nB1,99\nB2,41\n");
  await startService();
  render(<App />);
  await user.click(await enabledButton("Анализы"));
  await user.click(within(await screen.findByRole("table")).getByText("B1"));
  await user.click(await screen.findByText("Черновики правок", { exact: true }));
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
  await user.type(screen.getByLabelText("Имя шлифа"), "TS1");
  await user.click(await enabledButton("ppl.png"));
  await screen.findByRole("img", { name: "Изображение шлифа" });
  await user.selectOptions(screen.getByLabelText("Тип"), "Полевое фото");
  await user.click(await enabledButton("Проверить импорт изображений"));
  await screen.findByText("В пакете есть изображения без размещённых точек.");
  await user.click(await enabledButton("Импортировать изображения"));
  await screen.findByRole("heading", { name: "Образец SM-01B" });
  await user.click(within(screen.getByRole("navigation", { name: "Разделы образца" })).getByRole("button", { name: "Обзор" }));
  await user.click(await enabledButton("Редактировать паспорт"));
  await user.type(screen.getByLabelText("Местонахождение или обнажение"), "Северный массив · обнажение 12");
  await user.type(screen.getByLabelText("Хранение"), "ящик 4, кассета B");
  await user.click(await enabledButton("Сохранить паспорт"));
  await screen.findByText("Северный массив · обнажение 12");
  expect(screen.getByText("ящик 4, кассета B")).toBeTruthy();
  await user.type(screen.getByLabelText("Автор заметки"), "Иванов");
  await user.type(screen.getByLabelText("Текст заметки"), "Свежая поверхность отбора.");
  await user.click(await enabledButton("Добавить заметку"));
  await screen.findByText("Свежая поверхность отбора.");
  await user.click(await enabledButton("Открыть"));
  const preview = await screen.findByRole("img", { name: "Изображение шлифа" });
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
}, 20000);

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
  await user.click(await enabledButton("Проверить импорт изображений"));
  await screen.findByText("Неразмещённые точки (1)");
  expect(screen.getByText("KIV-2 · KIV-2-A · P-08")).toBeTruthy();
  expect(screen.getByText(/BSE.png · KIV-5 \/ P-03 · Изображение охватывает другой образец/)).toBeTruthy();
  const rows = within(screen.getByRole("table")).getAllByRole("row");
  expect(rows.map((row) => row.textContent)).toEqual(expect.arrayContaining([
    "BSE.pngKIV-2KIV-2-ABSE21", "PPL.pngKIV-2KIV-2-APPL00", "XPL.pngKIV-2KIV-2-AXPL00",
  ]));
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
  await user.click(await enabledButton("Завершить без неразмещённых точек"));
  await screen.findByText("Изображений импортировано: 3. Привязок: 2.");
  const apply = requests.find((request) => request.command === "media.import.apply").payload.plan;
  const bse = apply.items.find((item) => item.media_type === "BSE");
  const saved = (await invokePetrolab("media.preview", { ...database, media_asset_id: bse.media_asset_id })).result.annotations;
  expect(saved.map((item) => item.point_name).sort()).toEqual(["P-03", "P-07"]);
  expect(saved.find((item) => item.point_name === "P-03")).toMatchObject({
    point_sample_id: points[2].result.sample_id, cross_sample_exception: 1, exception_reason: "Изображение охватывает другой образец",
  });
  expect((await invokePetrolab("media.import.draft.load", database)).result).toBeNull();
  for (const [path, bytes] of Object.entries(photos)) expect(await readFile(path)).toEqual(bytes);
  expect(app.container.querySelector(".media-provisional")).toBeNull();
}, 30000);

test("real Python mineral review separates conflicts and persists only explicit acceptance", async () => {
  await writeFile(second, "Analysis,Mineral,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%)\nB1,olivine,40,0,50,0,0,0,10\nB2,garnet,40,0,50,0,0,0,10\n");
  const raw = await readFile(second, "utf8");
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await user.click(await enabledButton("2 · Проверить минералы"));
  await screen.findByText("Расхождение с источником");
  await user.click(await enabledButton("Принять группу совпадений"));
  await user.click(await enabledButton("Принять предложение"));
  await user.click(screen.getByLabelText("Показать все результаты"));
  await waitFor(() => expect(screen.getAllByText("Принято пользователем")).toHaveLength(2));
  expect(screen.getAllByText("garnet").length).toBeGreaterThan(0);
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
