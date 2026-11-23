// Exercise AT-14 through the native PetroLab window on an isolated project.
import assert from "node:assert/strict";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { once } from "node:events";
import { mkdir, mkdtemp, readdir, readFile, writeFile } from "node:fs/promises";
import { get } from "node:http";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const [executableArg, evidenceArg] = process.argv.slice(2);
assert(executableArg && evidenceArg, "Usage: node qa_installer_ui.mjs <petrolab-desktop.exe> <new evidence directory>");
const executable = resolve(executableArg);
const service = join(dirname(executable), "binaries", "petrolab-service.exe");
const evidence = resolve(evidenceArg);
await mkdir(evidence);
const workspace = join(evidence, "workspace");
await mkdir(workspace);
const database = join(workspace, "AT-14-Project.sqlite");
const source = join(workspace, "at14-analyses.csv");
const groupName = "AT-14 рабочая группа";
const layoutName = "AT-14 две диаграммы";
const chosenLabels = ["P2", "P6", "P4", "P1", "P7"];

function serviceRequest(command, payload = {}) {
  const request = {
    protocol_version: "1.0", request_id: randomUUID(), command,
    payload: { project_database_path: database, ...payload },
  };
  const process = spawnSync(service, [], { input: JSON.stringify(request) + "\n", encoding: "utf8", windowsHide: true, timeout: 45000 });
  if (process.error) throw process.error;
  assert.equal(process.status, 0, process.stderr);
  const response = JSON.parse(process.stdout);
  assert.equal(response.request_id, request.request_id);
  assert.ok(response.result, JSON.stringify(response));
  return response.result;
}

async function until(description, check, timeout = 25000) {
  for (const end = Date.now() + timeout; Date.now() < end;) {
    const value = await check();
    if (value) return value;
    await delay(150);
  }
  throw new Error(`AT-14 timed out: ${description}`);
}

async function debuggingPort() {
  const server = createServer().listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  await new Promise((done) => server.close(done));
  return port;
}

function debugTargets(port) {
  // This request is confined to the machine running the installed app.
  // A per-request agent keeps CI proxy settings out of local discovery.
  return new Promise((resolve, reject) => {
    const request = get({ hostname: "127.0.0.1", port, path: "/json/list", agent: false }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("error", reject);
      response.on("end", () => {
        if (response.statusCode !== 200) return reject(new Error(`WebView endpoint HTTP ${response.statusCode}`));
        try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
      });
    });
    request.on("error", reject);
    request.setTimeout(2000, () => request.destroy(new Error("WebView endpoint request timed out")));
  });
}

function connect(socket) {
  let id = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const { id, result, error } = JSON.parse(event.data);
    const command = pending.get(id);
    if (!command) return;
    if (error) command.reject(new Error(error.message));
    else command.resolve(result);
  });
  return (method, params = {}) => new Promise((resolve, reject) => {
    const commandId = ++id;
    const finish = (callback) => (value) => {
      pending.delete(commandId);
      clearTimeout(timeout);
      callback(value);
    };
    const timeout = setTimeout(() => finish(reject)(new Error(`CDP timed out: ${method}`)), 10000);
    pending.set(commandId, { resolve: finish(resolve), reject: finish(reject) });
    socket.send(JSON.stringify({ id: commandId, method, params }));
  });
}

async function withWindow(check, { projectPath = database, editConfirmations = null } = {}) {
  const port = await debuggingPort();
  const profile = await mkdtemp(join(workspace, "webview-"));
  const child = spawn(executable, [], {
    cwd: dirname(executable), stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PETROLAB_PROJECT_DATABASE: projectPath, WEBVIEW2_USER_DATA_FOLDER: profile,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1` },
  });
  let appOutput = "";
  for (const stream of [child.stdout, child.stderr]) {
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => { appOutput = (appOutput + chunk).slice(-4000); });
  }
  let socket, screenshot;
  let discovery = "no requests made";
  try {
    await once(child, "spawn");
    const target = await until("native WebView endpoint", async () => {
      assert.equal(child.exitCode, null, "PetroLab exited on startup");
      try {
        const pages = await debugTargets(port);
        const targets = pages.map((page) => ({ ...page, origin: URL.parse(page.url) }));
        discovery = `${pages.length} target(s) [${targets.map(({ type, origin }) =>
          `${type}: ${origin?.hostname || origin?.protocol || "empty"}`).join(", ")}]`;
        return targets.find(({ type, origin }) => type === "page" && origin?.hostname === "tauri.localhost");
      } catch (error) {
        discovery = `${error.code || "request failed"}: ${error.message}`;
        return null;
      }
    }, 60000);
    const address = new URL(target.webSocketDebuggerUrl);
    assert.equal(address.hostname, "127.0.0.1");
    socket = new WebSocket(address);
    await until("debugger connection", () => socket.readyState === WebSocket.OPEN, 5000);
    const command = connect(socket);
    if (editConfirmations) {
      socket.addEventListener("message", (event) => {
        const { method, params } = JSON.parse(event.data);
        if (method !== "Page.javascriptDialogOpening") return;
        const matches = params.type === "confirm" && params.message.startsWith("Записать правку в ячейку B2");
        editConfirmations.push(matches);
        command("Page.handleJavaScriptDialog", { accept: matches }).catch(() => {});
      });
    }
    const evaluate = async (fn, ...args) => {
      const { result, exceptionDetails } = await command("Runtime.evaluate", {
        expression: `(${fn.toString()})(...${JSON.stringify(args)})`, returnByValue: true, awaitPromise: true,
      });
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
      return result.value;
    };
    screenshot = async (name, selector) => {
      const clip = selector && await evaluate((selector) => {
        const { x, y, width, height } = document.querySelector(selector).getBoundingClientRect();
        return { x, y, width, height, scale: 1 };
      }, selector);
      const { data } = await command("Page.captureScreenshot", { format: "png", ...(clip ? { clip } : {}) });
      await writeFile(join(evidence, `${name}.png`), Buffer.from(data, "base64"));
    };
    await command("Page.enable");
    await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
    await check(evaluate, screenshot);
    const close = `$app = Get-Process -Id ${child.pid} -ErrorAction Stop; if (-not $app.CloseMainWindow() -or -not $app.WaitForExit(15000)) { exit 1 }`;
    execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", close], { windowsHide: true, timeout: 18000 });
  } catch (error) {
    if (screenshot) await screenshot("failure").catch(() => {});
    if (!socket) {
      const inspect = `
        $port = ${port}
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        $app = Get-Process -Id ${child.pid} -ErrorAction SilentlyContinue
        $workers = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'")
        $ours = @($workers | Where-Object { $_.ParentProcessId -eq ${child.pid} })
        @{
          appSession = $app.SessionId
          appHasWindow = [bool]$app.MainWindowHandle
          appWindowTitle = $app.MainWindowTitle
          listeners = $listeners.Count
          webviewChildren = $ours.Count
          webviewChildrenWithRequestedPort = @($ours | Where-Object { $_.CommandLine -like "*--remote-debugging-port=$port*" }).Count
        } | ConvertTo-Json -Compress
      `;
      let hostState;
      try {
        hostState = JSON.parse(execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", inspect], {
          encoding: "utf8", windowsHide: true, timeout: 8000,
        }));
      } catch { hostState = null; }
      const diagnostic = { port, pid: child.pid, discovery, hostState, appOutput };
      await writeFile(join(evidence, "webview-startup-failure.json"), JSON.stringify(diagnostic, null, 2));
      console.error("AT-14 WebView startup:", diagnostic);
    }
    throw error;
  } finally {
    socket?.close();
    if (child.exitCode === null) child.kill();
  }
}

async function click(evaluate, label) {
  await until(label, () => evaluate((label) => {
    const button = [...document.querySelectorAll("button")].find((button) => !button.disabled
      && (button.textContent.trim() === label || button.getAttribute("aria-label") === label));
    if (!button) return false;
    button.click();
    return true;
  }, label));
}

const selection = () => [...document.querySelectorAll('tbody input[aria-label^="Выбрать "]:checked')]
  .map((input) => input.getAttribute("aria-label").slice("Выбрать ".length)).sort();
const original = "Analysis,SiO2 [wt.%],Al2O3 [wt.%],MgO [wt.%]\n"
  + "P1,11,22,67\nP2,23,41,36\nP3,25,35,40\nP4,29,35,36\nP5,31,12,57\nP6,44,31,25\nP7,35,14,51\n";
await writeFile(source, original);
const { recipe } = serviceRequest("import.recipe.suggest", { source_path: source });
serviceRequest("import.plan.apply", { source_path: source, recipe });
const analyses = serviceRequest("project.analyses.list").analyses;
assert.equal(analyses.length, 7);
const expectedIds = chosenLabels.map((label) => analyses.find(({ identity }) => identity.Analysis === label).analysis_id);
const expectedLabels = [...chosenLabels].sort();
const point = serviceRequest("analytical_point.create", {
  sample_name: "AT-37 Sample", point_name: "AT-37 Point", analysis_ids: expectedIds.slice(0, 2), link_type: "same_point",
});

await withWindow(async (evaluate, screenshot) => {
  await until("project name, status and recent import", () => evaluate(() =>
    document.querySelector(".overview-navigation .project-name b")?.textContent === "AT 14 Project"
    && document.querySelector(".overview-navigation .overview-event")?.textContent.includes("at14-analyses.csv")
    && [...document.querySelectorAll(".overview-navigation aside dd")].map((value) => value.textContent).join(",") === "1,7"));
  await screenshot("AT-01-overview");
  await click(evaluate, "Открыть источник at14-analyses.csv");
  await until("the source opens its seven search results", () => evaluate(() => document.body.innerText.includes("Найдено анализов: 7")));
  await click(evaluate, "Анализы");
  for (const label of chosenLabels) {
    await until(`table checkbox ${label}`, () => evaluate((label) => {
      const input = document.querySelector(`tbody input[aria-label="Выбрать ${label}"]`);
      if (!input) return false;
      if (!input.checked) input.click();
      return true;
    }, label));
  }
  assert.deepEqual(await evaluate(selection), expectedLabels);
  await screenshot("AT-06-five-analyses");

  await click(evaluate, "Построить диаграммы");
  const panels = await until("both plots show the five selected analyses", () => evaluate(() => {
    const plots = [...document.querySelectorAll(".plot-panel")];
    if (plots.length !== 2) return null;
    const points = plots.map((panel) => ({ kind: panel.querySelector('select[aria-label="Тип диаграммы"]').value,
      analysisIds: [...panel.querySelectorAll('.plot-point[aria-pressed="true"]')].map((point) => point.dataset.analysisId) }));
    return points.every(({ analysisIds }) => analysisIds.length === 5) ? points : null;
  }));
  assert.deepEqual(panels.map(({ kind }) => kind), ["binary", "ternary"]);
  for (const panel of panels) assert.deepEqual([...panel.analysisIds].sort(), [...expectedIds].sort());
  await screenshot("AT-07-binary", ".plot-panel:nth-child(1)");
  await screenshot("AT-07-ternary", ".plot-panel:nth-child(2)");

  await click(evaluate, "Скрыть отбор на графиках");
  await until("the selected analyses are hidden on both panels", () => evaluate(() =>
    document.body.innerText.includes("Вернуть скрытые точки · 5") && !document.querySelector(".plot-point")));
  await screenshot("AT-37-hidden");
  await click(evaluate, "Отменить изменение видимости");
  await until("visibility inverse restores both selected series", () => evaluate(() =>
    document.querySelectorAll('.plot-point[aria-pressed="true"]').length === 10
    && !document.body.innerText.includes("Вернуть скрытые точки")));
  await screenshot("AT-37-visibility-restored");

  await evaluate((name) => {
    const details = document.querySelector(".plot-saved-layouts");
    details.open = true;
    const input = details.querySelector("input");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, name);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, layoutName);
  await click(evaluate, "Сохранить раскладку");
  await until("saved plot layout", () => evaluate((name) => document.body.innerText.includes(`Сохранена раскладка «${name}»`), layoutName));
  await click(evaluate, "Открыть в анализах");
  await click(evaluate, "Назначить Generation");
  await until("new Generation field", () => evaluate(() => Boolean(document.querySelector(".generation-assignment input"))));
  await evaluate(() => {
    const input = document.querySelector(".generation-assignment input");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "AT-37 Rim");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await click(evaluate, "Назначить");
  await until("exact Generation assignment in table", () => evaluate(() =>
    [...document.querySelectorAll("tbody tr")].filter((row) => row.textContent.includes("AT-37 Rim")).length === 5));
  await evaluate(() => [...document.querySelectorAll("th")].find((cell) => cell.textContent.includes("Generation"))
    .scrollIntoView({ block: "nearest", inline: "center" }));
  await screenshot("AT-37-generation");
  await click(evaluate, "Отменить назначение Generation");
  await until("the Generation assignment was undone", () => evaluate(() =>
    !document.querySelector("tbody")?.textContent.includes("AT-37 Rim")
    && !document.body.innerText.includes("Отменить назначение Generation")));
  assert.deepEqual(await evaluate(selection), expectedLabels);
  await click(evaluate, "Сохранить как рабочую группу");
  await evaluate((name) => {
    const form = document.querySelector('form[aria-label="Новая рабочая группа"]');
    form.elements.name.value = name;
    form.elements.created_by.value = "QA";
  }, groupName);
  await click(evaluate, "Сохранить группу");
  await until("saved work group", () => evaluate((name) => document.body.innerText.includes(`Сохранена группа «${name}»`), groupName));
});

function savedGroup() {
  const { groups } = serviceRequest("work_group.list");
  return groups.find(({ group }) => group.name === groupName).group;
}

const before = savedGroup();
assert.deepEqual(before.analysis_ids, expectedIds);
const [saved] = serviceRequest("plot_spec.list");
const layout = serviceRequest("plot_spec.open", { id: saved.id });
assert.equal(layout.name, layoutName);
assert.deepEqual(layout.input.analysis_ids, expectedIds);
assert.deepEqual(layout.panels.map(({ kind }) => kind), ["binary", "ternary"]);

await withWindow(async (evaluate, screenshot) => {
  await click(evaluate, "Анализы");
  await until("all seven analyses after restarting", () => evaluate(() => document.querySelectorAll("tbody tr").length === 7));
  assert.deepEqual(await evaluate(selection), []);
  await click(evaluate, "Рабочие группы");
  await click(evaluate, `${groupName} · 5`);
  await until("work group reinstated", () => evaluate((name) => document.body.innerText.includes(`Открыта группа «${name}»`), groupName));
  assert.deepEqual(await evaluate(selection), expectedLabels);
  await screenshot("AT-09-restored-work-group");
  await click(evaluate, "Связи");
  await click(evaluate, point.point_name);
  await until("two original point links", () => evaluate(() => document.querySelectorAll(".point-analysis-items li").length === 2));
  await evaluate((label) => [...document.querySelectorAll(".point-analysis-items li")]
    .find((row) => row.querySelector("b")?.textContent === label).querySelector("button:last-child").click(), chosenLabels[0]);
  await until("one link was removed", () => evaluate(() => document.querySelectorAll(".point-analysis-items li").length === 1
    && document.body.innerText.includes("Связь снята.")));
  await click(evaluate, "Восстановить снятую связь");
  await until("the original point link was restored", () => evaluate(() => document.querySelectorAll(".point-analysis-items li").length === 2
    && document.body.innerText.includes("Связь восстановлена.")));
  await screenshot("AT-37-link-restored");
});

const operations = serviceRequest("operation_journal.list").entries;
const journal = Object.fromEntries(["assign_generation", "hide_plot_points", "unlink_analytical_point"].map((action) => {
  const summary = operations.find((item) => item.action === action);
  const entry = serviceRequest("operation_journal.open", { operation_id: summary.id });
  assert.equal(entry.state, "undone");
  return [action, entry];
}));
assert.deepEqual([...journal.assign_generation.parameters.analysis_ids].sort(), [...expectedIds].sort());
assert.deepEqual([...journal.hide_plot_points.parameters.analysis_ids].sort(), [...expectedIds].sort());
assert.equal(journal.hide_plot_points.category, "view_only");
assert.deepEqual(journal.unlink_analytical_point.parameters.analysis_ids, expectedIds.slice(0, 1));
assert.equal(journal.unlink_analytical_point.parameters.analytical_point_id, point.analytical_point_id);
assert.deepEqual(savedGroup(), before);
assert.deepEqual(serviceRequest("plot_spec.open", { id: saved.id }), layout);
assert.deepEqual(serviceRequest("project.analyses.list").analyses, analyses);
const finalSource = await readFile(source);
assert.equal(finalSource.toString("utf8"), original);

const editDatabase = join(workspace, "AT-32-Project.sqlite");
const editProject = { project_database_path: editDatabase };
const conflictBook = join(workspace, "external-change.xlsx");
const editableBook = join(workspace, "confirmed-write.xlsx");
const python = (script, ...args) => execFileSync("python", ["-X", "utf8", "-c", script, ...args],
  { encoding: "utf8", windowsHide: true, timeout: 30000 });
python(`
import sys
from openpyxl import Workbook
for path, label, value in ((sys.argv[1], "Conflict", 4.5), (sys.argv[2], "Writable", 7.5)):
    book = Workbook()
    book.active.append(["Analysis", "F (wt.%)"])
    book.active.append([label, value])
    book.save(path)
    book.close()
`, conflictBook, editableBook);
const [originalConflict, originalEditable] = await Promise.all([readFile(conflictBook), readFile(editableBook)]);
for (const source_path of [conflictBook, editableBook]) {
  const { recipe: editRecipe } = serviceRequest("import.recipe.suggest", { source_path });
  const linkedRecipe = JSON.parse(python(`
import json, sys
from petrolab.import_preview import semantic_fingerprint
recipe = json.loads(sys.argv[1])
recipe["ownership_mode"] = "linked_external"
recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)
print(json.dumps(recipe))
`, JSON.stringify(editRecipe)));
  serviceRequest("import.plan.apply", { ...editProject, source_path, recipe: linkedRecipe });
}
const editBefore = serviceRequest("project.analyses.list", editProject).analyses;
const byLabel = Object.fromEntries(editBefore.map((row) => [row.identity.Analysis, row]));

async function openEditDrafts(evaluate, label) {
  await until(`analysis ${label}`, () => evaluate((name) => {
    const cell = [...document.querySelectorAll("tbody td")].find((item) => item.textContent === name);
    if (!cell) return false;
    cell.click();
    return true;
  }, label));
  await until(`draft panel ${label}`, () => evaluate((name) => {
    const detail = document.querySelector(".analysis-detail");
    const summary = detail?.querySelector(".analysis-edit-drafts summary");
    if (!summary || detail.querySelector("h2")?.textContent !== name) return false;
    if (!summary.parentElement.open) summary.click();
    return true;
  }, label));
}

async function saveDraft(evaluate, nextValue, expectedLine) {
  await until("draft input ready", () => evaluate(() => {
    const input = document.querySelector(".analysis-edit-drafts input[name=new_value]");
    return input && !input.disabled;
  }));
  await evaluate((value) => { document.querySelector(".analysis-edit-drafts input[name=new_value]").value = value; }, nextValue);
  await click(evaluate, "Сохранить черновик");
  await until(expectedLine, () => evaluate((line) => document.body.innerText.includes(line), expectedLine));
}

await withWindow(async (evaluate, screenshot) => {
  await click(evaluate, "Анализы");
  await openEditDrafts(evaluate, "Conflict");
  await saveDraft(evaluate, "6.5", "Было 4.5 → предлагается 6.5 wt.%");
  await screenshot("AT-32-saved-draft");
}, { projectPath: editDatabase });

python(`
import sys
from openpyxl import load_workbook
book = load_workbook(sys.argv[1])
book.active["B2"] = 99
book.save(sys.argv[1])
book.close()
`, conflictBook);
const modifiedConflict = await readFile(conflictBook);
assert.notDeepEqual(modifiedConflict, originalConflict);

async function confirmEdit(evaluate) {
  await until("edit confirmation form ready", () => evaluate(() => {
    const form = document.querySelector('.analysis-edit-draft form[aria-label^="Запись ячейки"]');
    const submit = form?.querySelector("button");
    if (!submit || submit.disabled) return false;
    form.elements.actor.value = "QA";
    form.elements.reason.value = "AT-32 verification";
    setTimeout(() => submit.click(), 0);
    return true;
  }));
}

const editConfirmations = [];
await withWindow(async (evaluate, screenshot) => {
  await click(evaluate, "Анализы");
  await openEditDrafts(evaluate, "Conflict");
  await until("draft restored after restart", () => evaluate(() =>
    document.body.innerText.includes("Было 4.5 → предлагается 6.5 wt.%")));
  await confirmEdit(evaluate);
  await until("external edit conflict", () => evaluate(() =>
    document.body.innerText.includes("Исходный файл изменился") && document.body.innerText.includes("Сейчас в файле: 99")));
  await evaluate(() => {
    const hashes = document.querySelector(".analysis-edit-draft details");
    hashes.open = true;
    hashes.scrollIntoView({ block: "end" });
  });
  await screenshot("AT-32-conflict");
  await openEditDrafts(evaluate, "Writable");
  await saveDraft(evaluate, "8.5", "Было 7.5 → предлагается 8.5 wt.%");
  await confirmEdit(evaluate);
  await until("confirmed write and backup visible", () => evaluate(() =>
    document.body.innerText.includes("Записано в XLSX") && document.body.innerText.includes("Резервная копия")));
  await screenshot("AT-32-backup");
}, { projectPath: editDatabase, editConfirmations });

assert.deepEqual(editConfirmations, [true, true]);
const sha256 = (content) => createHash("sha256").update(content).digest("hex");
const draftFor = (label) => serviceRequest("edit_draft.list", { ...editProject, analysis_id: byLabel[label].analysis_id }).drafts[0];
const blocked = draftFor("Conflict");
const storedEdit = draftFor("Writable");
assert.equal(blocked.draft.conflict.kind, "source_changed");
assert.equal(blocked.draft.source_fingerprint_at_start, sha256(originalConflict));
assert.equal(blocked.draft.conflict.current_source_fingerprint, sha256(modifiedConflict));
assert.equal(blocked.draft.changes[0].old_value, "4.5");
assert.deepEqual(await readFile(conflictBook), modifiedConflict);
assert.ok(!(await readdir(workspace)).some((name) => name.startsWith("external-change.xlsx.before-edit-")));
assert.equal(storedEdit.draft.status, "committed");
assert.deepEqual(await readFile(storedEdit.operation.parameters.backup_path), originalEditable);
assert.equal(storedEdit.operation.parameters.before_sha256, sha256(originalEditable));
assert.equal(storedEdit.operation.parameters.after_sha256, sha256(await readFile(editableBook)));
assert.equal(python(`
import sys
from openpyxl import load_workbook
with open(sys.argv[1], "rb") as stream:
    book = load_workbook(stream, read_only=True)
    print(book.active["B2"].value)
    book.close()
`, editableBook).trim(), "8.5");
assert.deepEqual(serviceRequest("project.analyses.list", editProject).analyses, editBefore);
const editDraft = {
  conflict: { draft: blocked.draft, external_file_unchanged: true },
  confirmed_write: { draft: storedEdit.draft, backup_sha256: sha256(originalEditable), value: 8.5 },
  imported_measurements_unchanged: true,
};
await writeFile(join(evidence, "acceptance.json"), JSON.stringify({
  scenarios: ["AT-01", "AT-06", "AT-07", "AT-09", "AT-32", "AT-37 (domain and visibility actions)"],
  selected: chosenLabels.map((label, index) => ({ label, analysisId: expectedIds[index] })),
  workGroup: before, plotSpecification: layout, journal, editDraft, sourceSha256: sha256(finalSource),
}, null, 2));
console.log("Native project, selection, plots, restart, AT-32 edit and AT-37 journal checks passed.");
