import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("..", import.meta.url);
const read = (path) => readFile(new URL(path, root), "utf8");

test("Tauri shell owns one local Python service rather than a localhost API", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  assert.match(shell, /python.*-m.*petrolab\.ndjson_service/s);
  assert.match(shell, /struct PythonService/);
  assert.match(shell, /async fn petrolab_command/);
  assert.match(shell, /petrolab-service\.exe/);
  assert.match(shell, /Arc<Mutex<PythonService>>/);
  assert.doesNotMatch(shell, /TcpListener|reqwest|localhost API/);
});

test("blocking scientific and file I/O stays off the Tauri UI thread", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  assert.match(shell, /spawn_blocking/);
  assert.match(shell, /async fn stage_import_file/);
  assert.match(shell, /async fn clear_import_staging/);
  assert.match(shell, /read_until\(b'\\n'/);
  assert.match(shell, /PYTHONUTF8/);
  assert.match(shell, /PYTHONIOENCODING/);
});

test("desktop stages selected files locally before the scientific service reads them", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  assert.match(shell, /import-staging/);
  assert.match(shell, /fs::copy\(&source, &staged\)/);
  assert.match(shell, /fn pick_import_file/);
  assert.match(shell, /async fn stage_import_file/);
  assert.match(api, /stage_import_file/);
  assert.match(api, /clear_import_staging/);
  assert.match(app, /stageImportFile\(selectedPath\)/);
  assert.match(app, /selected\.local_path/);
  assert.match(app, /Отменить импорт/);
});

test("replacement import is transactional and keeps previous preview on failure", async () => {
  const app = await read("src/App.jsx");
  assert.match(app, /const previousStaged = sourcePath/);
  const chooseFile = app.match(/const chooseFile = async \(\) => \{[\s\S]*?\n  \};/)?.[0] ?? "";
  assert.doesNotMatch(chooseFile, /catch[\s\S]*resetImportState\(\)/);
  assert.match(app, /Копирую файл в рабочую область PetroLab/);
  assert.match(app, /Читаю листы и проверяю структуру файла/);
});

test("mapping edits are applied once in bulk and unresolved draft blocks save", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const editor = await read("src/ImportMappingEditor.jsx");
  assert.match(api, /import\.recipe\.revise_mappings/);
  assert.match(app, /reviseImportMappings/);
  assert.match(app, /mappingDraftDirty/);
  assert.match(app, /Применяю сопоставление/);
  assert.match(editor, /Применить сопоставление/);
  assert.match(editor, /Назначить всем Measurement/);
  assert.match(editor, /UNIT_REQUIRES_REVIEW/);
  assert.match(editor, /canonical_field/);
  assert.doesNotMatch(editor, />Применить<\/button>/);
  assert.doesNotMatch(editor, /Mineral|Generation/);
});

test("mistaken saved import can be retracted without deleting audit history", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  assert.match(api, /project\.last_import\.retract/);
  assert.match(app, /Отменить последний импорт/);
  assert.match(app, /история импорта сохранится/);
  assert.match(app, /retractLastImport/);
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
