// Exercise AT-14 through the native PetroLab window on an isolated project.
import assert from "node:assert/strict";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { once } from "node:events";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
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

async function withWindow(check) {
  const port = await debuggingPort();
  const profile = await mkdtemp(join(workspace, "webview-"));
  const child = spawn(executable, [], {
    cwd: dirname(executable), windowsHide: true, stdio: "ignore",
    env: { ...process.env, PETROLAB_PROJECT_DATABASE: database, WEBVIEW2_USER_DATA_FOLDER: profile,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1` },
  });
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
        $workers = @(Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" |
          Where-Object { $_.CommandLine -like "*--remote-debugging-port=$port*" })
        @{ listeners = $listeners.Count; webviewProcessesWithPort = $workers.Count } | ConvertTo-Json -Compress
      `;
      let hostState;
      try {
        hostState = JSON.parse(execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", inspect], {
          encoding: "utf8", windowsHide: true, timeout: 8000,
        }));
      } catch { hostState = null; }
      const diagnostic = { port, pid: child.pid, discovery, hostState };
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
});

assert.deepEqual(savedGroup(), before);
assert.deepEqual(serviceRequest("plot_spec.open", { id: saved.id }), layout);
assert.deepEqual(serviceRequest("project.analyses.list").analyses, analyses);
const finalSource = await readFile(source);
assert.equal(finalSource.toString("utf8"), original);
await writeFile(join(evidence, "acceptance.json"), JSON.stringify({
  scenarios: ["AT-01", "AT-06", "AT-07", "AT-09"],
  selected: chosenLabels.map((label, index) => ({ label, analysisId: expectedIds[index] })),
  workGroup: before, plotSpecification: layout, sourceSha256: createHash("sha256").update(finalSource).digest("hex"),
}, null, 2));
console.log("AT-14 native project, selection, plots and restart checks passed.");
