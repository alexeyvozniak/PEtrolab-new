// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";

const bridge = vi.hoisted(() => ({ invoke: null }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args) => bridge.invoke(...args) }));
import { App } from "../src/App";
configure({ asyncUtilTimeout: 15000 });

let child, folder, first, second, queue, original, pending, lines, requests, stopService;
beforeEach(async () => {
  folder = await mkdtemp(join(tmpdir(), "petrolab-workspace-ui-"));
  first = join(folder, "first.csv"); second = join(folder, "second.csv");
  original = "Analysis,Fe (wt.%),F (wt.%)\nA1,10,<DL\nA2,11,n.d.\n";
  await writeFile(first, original);
  await writeFile(second, "Analysis,SiO2 [wt.%]\nB1,40\nB2,41\n");
  queue = [first, second]; pending = new Map(); requests = [];
  const pythonPath = resolve(process.cwd(), "../src");
  const pathSeparator = process.platform === "win32" ? ";" : ":";
  child = spawn("python", ["-m", "petrolab.ndjson_service"], {
    cwd: resolve(process.cwd(), ".."), windowsHide: true,
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(pathSeparator),
    },
  });
  const service = child;
  const callbacks = pending;
  let closingService = false;
  let stderr = '';
  service.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-4000); });
  const rejectPending = error => {
    for (const callback of callbacks.values()) callback.reject(error);
    callbacks.clear();
  };
  service.on('error', rejectPending);
  service.stdin.on('error', rejectPending);
  service.on('exit', code => rejectPending(new Error(`Python service exited (${code}): ${stderr}`)));
  stopService = () => { closingService = true; service.stdin.end(); };
  lines = createInterface({ input: child.stdout });
  lines.on("line", (line) => {
    const response = JSON.parse(line);
    const callback = callbacks.get(response.request_id);
    if (callback) { callbacks.delete(response.request_id); callback.resolve(response); }
  });
  bridge.invoke = async (command, args) => {
    if (command === "project_database_path") return join(folder, "project.sqlite");
    if (command === "pick_import_file") return queue.shift() || null;
    if (command === "stage_import_file") return { local_path: args.sourcePath, original_path: args.sourcePath };
    if (command === "clear_import_staging") return;
    if (command !== "petrolab_command") throw new Error(command);
    requests.push(args.envelope);
    if (closingService || service.exitCode !== null) throw new Error('Python service is closed');
    return new Promise((resolve, reject) => {
      callbacks.set(args.envelope.request_id, { resolve, reject });
      service.stdin.write(JSON.stringify(args.envelope) + "\n", error => {
        if (error) { callbacks.delete(args.envelope.request_id); reject(error); }
      });
    });
  };
  window.__TAURI_INTERNALS__ = { invoke: () => {} };
  // Wait for scientific imports/startup before timing user interactions on Windows.
  await bridge.invoke('petrolab_command', { envelope: { protocol_version: '1.0',
    request_id: crypto.randomUUID(), command: 'formula.methods.list', payload: {} } });
}, 60000);

afterEach(async () => {
  cleanup();
  stopService();
  await new Promise((resolve) => { if (child.exitCode !== null) resolve(); else child.once("exit", resolve); });
  lines.close();
  delete window.__TAURI_INTERNALS__;
  await rm(folder, { recursive: true, force: true });
});

async function enabledButton(name) {
  const button = await screen.findByRole("button", { name });
  // The integration bridge starts a real Python process. On a busy Windows
  // runner its valid response can exceed Testing Library's 1 s default.
  await waitFor(() => expect(button.disabled).toBe(false), { timeout: 10000 });
  return button;
}

test("real Python workspace retains two sources and mapping, identity repair and raw tokens", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await enabledButton("Добавить файл");
  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  expect(within(await screen.findByRole("table")).getByText("<DL")).toBeTruthy();
  expect(screen.getAllByText(/Что означает колонка Fe/).length).toBeGreaterThan(0);
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
  expect(screen.getByRole("button", { name: "Импортировать после проверки" }).disabled).toBe(true);
  expect(requests.filter(r => r.command === "import.plan.apply")).toHaveLength(0);
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
  expect(requests.filter(r => r.command === "import.plan.apply")).toHaveLength(1);
}, 20000);

test("unit suggestions are not dirty edits and one valid mapping can be applied while others remain unresolved", async () => {
  await writeFile(second, 'Analysis,SiO2,MgO\nB1,40,50\nB2,41,49\n');
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton('Выбрать файл'));
  await enabledButton('Добавить файл');
  await user.click(await enabledButton('Настроить поля по одному'));
  const unit = await screen.findByRole('combobox', { name: 'Единица SiO2' });
  await waitFor(() => expect(unit.disabled).toBe(false));
  await user.selectOptions(unit, 'wt.%');
  expect(screen.getByRole('combobox', { name: 'Единица SiO2' }).value).toBe('wt.%');
  expect(screen.getByText(/Изменения ещё не применены/)).toBeTruthy();
  await user.selectOptions(unit, 'ppm');
  expect(screen.getByRole('combobox', { name: 'Единица SiO2' }).value).toBe('ppm');
  await user.click(await enabledButton('Сбросить изменения'));
  expect(screen.getByRole('combobox', { name: 'Единица SiO2' }).value).toBe('');
  expect(screen.queryByText(/Изменения ещё не применены/)).toBeNull();
  await user.selectOptions(unit, 'wt.%');
  await user.click(await enabledButton(/Применить сопоставление/));
  await screen.findByText('Какая единица у этих измерений?');
  expect(screen.queryByRole('combobox', { name: 'Единица SiO2' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Импортировать после проверки' }).disabled).toBe(true);
}, 20000);

test("one server-issued unit scope is presented as one guided question", async () => {
  const source = 'Analysis,SiO2,MgO\nB1,40,50\nB2,41,49\n';
  await writeFile(second, source);
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton('Выбрать файл'));
  await enabledButton('Добавить файл');

  expect(screen.getByRole('heading', { name: 'Какая единица у этих измерений?' })).toBeTruthy();
  expect(screen.getByText('1 обязательный вопрос')).toBeTruthy();
  expect(document.querySelector('.import-advisories')?.open).toBe(false);
  expect(document.querySelector('.import-field-settings')?.open).toBe(false);
  expect(screen.getByText(/2 поля этой таблицы входят в один вопрос выше/)).toBeTruthy();
  expect(screen.getByText('Записи появятся после решения вопросов выше')).toBeTruthy();
  expect(screen.queryByRole('combobox', { name: 'Единица SiO2' })).toBeNull();
  expect(document.querySelector('.footer-warning')?.textContent).toContain('1 обязательное решение · 2 поля');

  const unit = screen.getByRole('combobox', { name: /Единица для группы/ });
  await user.selectOptions(unit, 'wt.%');
  await user.click(await enabledButton('Назначить 2 полям'));
  await waitFor(() => expect(screen.queryByText('Какая единица у этих измерений?')).toBeNull());
  expect(requests.some((request) => request.command === 'import.workspace.apply_bulk_decision'
    && request.payload.decision?.kind === 'unit'
    && request.payload.decision?.unit === 'wt.%')).toBe(true);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить импорт в проект' }).disabled).toBe(false), { timeout: 10000 });
  expect(await readFile(second, 'utf8')).toBe(source);
}, 20000);

test("ambiguous Fe is one guided decision and preserves source numbers", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton("Выбрать файл"));
  await enabledButton("Добавить файл");
  expect(screen.getByRole("button", { name: "Текущий вопрос" })).toBeTruthy();
  expect(document.querySelectorAll(".mapping-review-item")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Все 3" })).toBeTruthy();
  expect(screen.getAllByText(/Что означает колонка Fe/).length).toBeGreaterThan(0);
  const form = await screen.findByRole("combobox", { name: "Форма железа Fe (wt.%)" });
  const unit = screen.getByRole("combobox", { name: "Единица Fe (wt.%)" });
  expect(form.value).toBe("");
  expect(unit.value).toBe("wt.%");
  expect(screen.getByText(/Единица описывает числа и уже распознана отдельно/)).toBeTruthy();
  await user.selectOptions(form, "FeOt");
  expect(screen.getByRole("combobox", { name: "Форма железа Fe (wt.%)" }).value).toBe("FeOt");
  expect(screen.getByText(/Изменения ещё не применены/)).toBeTruthy();
  expect(document.querySelector(".footer-warning")?.textContent).toContain("1 обязательное решение · правки не применены");
  await user.click(await enabledButton(/Применить сопоставление/));
  await waitFor(() => expect(screen.queryAllByText(/Что означает колонка Fe/)).toHaveLength(0));
  expect(requests.some((request) => request.command === "import.workspace.apply_decision"
    && request.payload.decision?.decisions?.some((decision) => decision.canonical_field === "FeOt"))).toBe(true);
  expect(await readFile(first, "utf8")).toBe(original);
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

test('real formula path saves APFU, reopens history and invalidates a changed Fe preview', async () => {
  await writeFile(second, 'Analysis,Mineral,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%)\nB1,olivine,40,0,50,0,0,0,10\n');
  const raw = await readFile(second, 'utf8');
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton('Выбрать файл'));
  await user.click(await enabledButton('2 · Проверить минералы'));
  await user.click(await enabledButton('Принять группу совпадений'));
  await user.click(await enabledButton('Сохранить импорт в проект'));
  await screen.findByRole('heading', { name: 'Анализы' });
  await user.click(await enabledButton('Минералы'));
  await user.click(await enabledButton('Приняты пользователем 1'));
  await user.click(await enabledButton('Рассчитать формулу'));
  const fe = screen.getByRole('combobox', { name: 'Режим железа', hidden: true });
  expect(fe.value).toBe('all_fe2');
  const calculated = await screen.findByRole('table', { name: 'Рассчитанные значения' });
  expect(within(calculated).getByText('Fo')).toBeTruthy();
  await user.click(await enabledButton('Сохранить результат формулы'));
  await screen.findByText('Сохранённые расчёты · 1');
  await user.click(await enabledButton('Анализы'));
  await user.click(await enabledButton('Минералы'));
  await user.click(await enabledButton('Приняты пользователем 1'));
  await screen.findByText('Сохранённые расчёты · 1');
  await user.click(screen.getByText('Настроить расчёт', { selector: 'summary' }));
  const restoredFe = screen.getByRole('combobox', { name: 'Режим железа' });
  await user.selectOptions(restoredFe, 'all_fe2');
  await user.click(await enabledButton('Рассчитать с этими настройками'));
  await enabledButton('Сохранить результат формулы');
  await user.selectOptions(restoredFe, 'reported_split');
  expect(screen.queryByRole('button', { name: 'Сохранить результат формулы' })).toBeNull();
  await user.click(await enabledButton('Рассчитать с этими настройками'));
  await screen.findByText(/Fe2O3: нет пригодного/);
  expect(screen.getByRole('button', { name: 'Сохранить результат формулы' }).disabled).toBe(true);
  expect(requests.filter(r => r.command === 'formula.save')).toHaveLength(1);
  expect(await readFile(second, 'utf8')).toBe(raw);
}, 60000);

test('real mica formula requires three choices, saves OH provenance and preserves choices after an error', async () => {
  const mica = 'Analysis,Mineral,SiO2 (wt.%),Al2O3 (wt.%),MgO (wt.%),CaO (wt.%),Na2O (wt.%),K2O (wt.%),FeO (wt.%),F (wt.%),Cl (wt.%)\nPhl-1,phlogopite,43.19886687724983,12.218097369947321,28.97803256529596,0,0,11.287489155286707,0,0,0\n';
  await writeFile(second, mica);
  const raw = await readFile(second, 'utf8');
  queue = [second];
  const user = userEvent.setup();
  render(<App />);
  await user.click(await enabledButton('Выбрать файл'));
  await user.click(await enabledButton('2 · Проверить минералы'));
  await user.click(await enabledButton('Принять группу совпадений'));
  await user.click(await enabledButton('Сохранить импорт в проект'));
  await screen.findByRole('heading', { name: 'Анализы' });
  await user.click(await enabledButton('Минералы'));
  await user.click(await enabledButton('Приняты пользователем 1'));
  await user.click(await enabledButton('Рассчитать формулу'));
  const quickResult = await screen.findByRole('table', { name: 'Рассчитанные значения' });
  expect(within(quickResult).queryByText('OH (оценка)')).toBeNull();
  await user.click(screen.getByText('Настроить расчёт', { selector: 'summary' }));
  expect(screen.queryByRole('combobox', { name: 'Метод формулы' })).toBeNull();
  const fe = screen.getByRole('combobox', { name: 'Режим железа' });
  const basis = screen.getByRole('combobox', { name: 'Анионный базис' });
  const oh = screen.getByRole('combobox', { name: 'Расчёт OH' });
  expect(fe.value).toBe('all_fe2');
  expect(basis.value).toBe('ideal_O10_W2');
  expect(oh.value).toBe('not_calculated');
  expect(fe.selectedOptions[0].textContent).toBe('Всё Fe как Fe²⁺ · FeO/FeOt');
  expect(basis.selectedOptions[0].textContent).toBe('O₁₀W₂ · 22 положительных заряда');
  expect(oh.selectedOptions[0].textContent).toBe('OH не рассчитывать');
  expect(fe.title).toBe('Всё железо как Fe²⁺ (FeO или FeOt)');
  expect(screen.getByText('Идеальная группа O₁₀W₂; нормировка на 22 положительных заряда', { selector: '.formula-parameter-help' })).toBeTruthy();
  await user.selectOptions(oh, 'ideal_2_minus_f_cl');
  await user.click(await enabledButton('Рассчитать с этими настройками'));
  await screen.findByText('OH (оценка)');
  expect(screen.getByLabelText('Основание оценки OH').textContent).toContain('F = 0 wt.%');
  expect(screen.getByLabelText('Основание оценки OH').textContent).toContain('Cl = 0 wt.%');
  await user.click(await enabledButton('Сохранить результат формулы'));
  await screen.findByText('Сохранённые расчёты · 1');
  await user.click(await enabledButton('Анализы'));
  await user.click(await enabledButton('Минералы'));
  await user.click(await enabledButton('Приняты пользователем 1'));
  await screen.findByText('Сохранённые расчёты · 1');
  const historySummary = await screen.findByText(/Сохранён · Слюды · 22 заряда · bulk APFU · v0\.1\.0/, { selector: 'summary' });
  await user.click(historySummary);
  const history = historySummary.closest('details');
  expect(within(history).getByText('Идеальная группа O₁₀W₂; нормировка на 22 положительных заряда')).toBeTruthy();
  expect(within(history).getByText('Оценить OH = 2 − F − Cl по измеренным F и Cl')).toBeTruthy();
  await user.click(screen.getByText('Настроить расчёт', { selector: 'summary' }));
  const restoredFe = screen.getByRole('combobox', { name: 'Режим железа' });
  const restoredBasis = screen.getByRole('combobox', { name: 'Анионный базис' });
  const restoredOh = screen.getByRole('combobox', { name: 'Расчёт OH' });
  await user.selectOptions(restoredFe, 'all_fe2');
  await user.selectOptions(restoredBasis, 'ideal_O10_W2');
  await user.selectOptions(restoredOh, 'ideal_2_minus_f_cl');
  await user.click(await enabledButton('Рассчитать с этими настройками'));
  await enabledButton('Сохранить результат формулы');
  await user.selectOptions(restoredFe, 'reported_split');
  expect(screen.queryByRole('button', { name: 'Сохранить результат формулы' })).toBeNull();
  await user.click(await enabledButton('Рассчитать с этими настройками'));
  await screen.findByText(/Fe2O3: нет пригодного/);
  expect(restoredFe.value).toBe('reported_split');
  expect(restoredBasis.value).toBe('ideal_O10_W2');
  expect(restoredOh.value).toBe('ideal_2_minus_f_cl');
  expect(await readFile(second, 'utf8')).toBe(raw);
}, 60000);
