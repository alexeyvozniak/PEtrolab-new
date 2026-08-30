import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("..", import.meta.url);
const read = (path) => readFile(new URL(path, root), "utf8");

test("Tauri shell owns one local Python service rather than a localhost API", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  assert.match(shell, /python.*-m.*petrolab\.ndjson_service/s);
  assert.match(shell, /struct PythonService/);
  assert.match(shell, /fn petrolab_command/);
  assert.match(shell, /petrolab-service\.exe/);
  assert.match(shell, /AppHandle, Manager, State/);
  assert.doesNotMatch(shell, /TcpListener|reqwest|localhost API/);
});

test("frontend sends the versioned envelope through the one Tauri command", async () => {
  const api = await read("src/desktopApi.js");
  assert.match(api, /protocol_version: PROTOCOL_VERSION/);
  assert.match(api, /request_id: crypto\.randomUUID\(\)/);
  assert.match(api, /invoke\("petrolab_command", \{ envelope \}\)/);
  assert.match(api, /media\.inspect_sources/);
  assert.match(api, /media\.import\.plan/);
  assert.match(api, /media\.import\.apply/);
  assert.match(api, /analytical_point\.create/);
});

test("Tauri config keeps the approved desktop minimum window size", async () => {
  const config = JSON.parse(await read("src-tauri/tauri.conf.json"));
  assert.equal(config.app.windows[0].width, 1440);
  assert.equal(config.app.windows[0].height, 1024);
  assert.equal(config.app.windows[0].minWidth, 1180);
  assert.equal(config.app.windows[0].minHeight, 800);
  assert.deepEqual(config.bundle.resources, ["binaries/petrolab-service.exe"]);
  assert.deepEqual(config.bundle.icon, ["icons/icon.ico"]);
  assert.match(config.build.beforeBuildCommand, /generate_tauri_icon\.py/);
});
