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
  const workspace = await read("src/ImportWorkspace.jsx");
  assert.match(shell, /import-staging/);
  assert.match(shell, /fs::copy\(&source, &staged\)/);
  assert.match(shell, /fn pick_import_file/);
  assert.match(shell, /async fn stage_import_file/);
  assert.match(api, /stage_import_file/);
  assert.match(api, /clear_import_staging/);
  assert.match(app, /stageImportFile\(selectedPath\)/);
  assert.match(app, /selected\.local_path/);
  assert.match(workspace, /Отменить/);
});

test("replacement import is transactional and keeps previous preview on failure", async () => {
  const app = await read("src/App.jsx");
  assert.match(app, /const previousStaged = sourcePath/);
  const chooseFile = app.match(/const chooseFile = async \(\) => \{[\s\S]*?\n  \};/)?.[0] ?? "";
  assert.doesNotMatch(chooseFile, /catch[\s\S]*resetImportState\(\)/);
  assert.match(app, /Копирую файл в рабочую область PetroLab/);
  assert.match(app, /Проверяю, соответствует ли файл PetroLab Clean Table/);
});

test("Clean Table fast path is classified by Python and skips raw review by default", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  assert.match(api, /import\.clean_table\.classify/);
  assert.match(app, /classifyCleanTable/);
  assert.match(app, /classification\.mode === "clean_table_fast"/);
  assert.match(workspace, /Таблица готова к импорту/);
  assert.match(workspace, /Импортировать таблицу/);
  assert.match(workspace, /Открыть подробную проверку/);
  assert.match(workspace, /Файл требует внимания/);
  assert.match(workspace, /Clean Table v/);
});

test("approved import workspace keeps source list, physical table, issue inspector and fixed commit bar together", async () => {
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const styles = await read("src/importWorkspace.css");
  assert.match(app, /<ImportWorkspace/);
  assert.match(workspace, /Файл и листы/);
  assert.match(workspace, /Нерешённые вопросы/);
  assert.match(workspace, /Исходный файл не изменится/);
  assert.match(workspace, /activeBlockId/);
  assert.match(workspace, /ImportMappingEditor/);
  assert.match(styles, /grid-template-columns: 235px minmax\(420px, 1fr\) 370px/);
  assert.match(styles, /import-workspace-footer/);
});

test("raw block review precedes field mapping and supports transposed orientation", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const review = await read("src/ImportBlockReview.jsx");
  assert.match(api, /import\.preview\.window/);
  assert.match(api, /import\.recipe\.revise_sections/);
  assert.match(app, /previewImportWindow/);
  assert.match(app, /reviseImportSections/);
  assert.match(workspace, /ImportBlockReview/);
  assert.match(app, /blockDraftDirty/);
  assert.match(workspace, /activeBlockId/);
  assert.match(workspace, /ImportMappingEditor/);
  assert.match(workspace, /анализы по столбцам/);
  assert.match(workspace, /Каждый лист сохраняет собственную строку заголовка/);
  assert.match(review, /По столбцам \(инвертировано\)/);
  assert.match(review, /STRUCTURE_DEBOUNCE_MS/);
  assert.match(review, /Изменения структуры применяются автоматически/);
  assert.doesNotMatch(review, />\s*Применить структуру/);
  assert.match(review, /Единица из источника/);
  assert.match(review, /raw-preview-table/);
  assert.match(review, /placeholder="до конца"/);
  assert.match(review, /invalidState/);
});

test("mapping review exposes physical fields including blank headers", async () => {
  const editor = await read("src/ImportMappingEditor.jsx");
  assert.match(editor, /Здесь показаны все физические поля выбранного блока/);
  assert.match(editor, /Без заголовка/);
  assert.match(editor, /columnLetters/);
  assert.match(editor, /колонка \$\{index \+ 1\}/);
  assert.match(editor, /Не импортировать/);
});

test("mapping edits are applied once in bulk per logical block", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const editor = await read("src/ImportMappingEditor.jsx");
  assert.match(api, /import\.recipe\.revise_mappings/);
  assert.match(app, /reviseImportMappings/);
  assert.match(app, /mappingDraftDirty/);
  assert.match(app, /Применяю сопоставление/);
  assert.match(editor, /Применить сопоставление/);
  assert.match(editor, /Назначить всему блоку/);
  assert.match(editor, /block_id/);
  assert.match(editor, /source_axis/);
  assert.match(editor, /source_index/);
  assert.match(editor, /at\.%/);
  assert.match(editor, /UNIT_REQUIRES_REVIEW/);
  assert.match(editor, /Mineral/);
  assert.match(editor, /Generation/);
  assert.match(editor, /measurement_set/);
  assert.match(editor, /method/);
  assert.match(editor, /Метод/);
  assert.match(editor, /Набор/);
  assert.doesNotMatch(editor, />Применить<\/button>/);
});

test("analyses view exposes source metadata, method context and truthful physical origin", async () => {
  const app = await read("src/App.jsx");
  assert.match(app, /metadataColumns/);
  assert.match(app, /source_metadata/);
  assert.match(app, /Исходное значение из файла/);
  assert.match(app, /Сохранено без интерпретации как исходный текст/);
  assert.match(app, /measurement\?\.method/);
  assert.match(app, /measurement\?\.measurement_set/);
  assert.match(app, /savedAnalysisOrigin/);
  assert.match(app, /source_orientation === "columns_are_analyses"/);
  assert.match(app, /source_column_number/);
  assert.match(app, /Источник в файле/);
});

test("duplicate candidates require explicit keep-all review before save", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const review = await read("src/ImportDuplicateReview.jsx");
  assert.match(api, /import\.recipe\.review_duplicates/);
  assert.match(app, /reviewImportDuplicates/);
  assert.match(app, /duplicateReviewRequired/);
  assert.match(app, /!duplicateReviewRequired/);
  assert.match(workspace, /ImportDuplicateReview/);
  assert.match(review, /ничего не объединяет автоматически/);
  assert.match(review, /Проверено: оставить все записи/);
});

test("save stays blocked while automatic structure validation or mapping drafts are pending", async () => {
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  assert.match(app, /!blockDraftDirty/);
  assert.match(app, /!mappingDraftDirty/);
  assert.match(workspace, /Импортировать после проверки/);
  assert.match(workspace, /blockDraftDirty/);
  assert.match(workspace, /mappingDraftDirty/);
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
  assert.match(api, /desktopInvoke\("petrolab_command", \{ envelope \}\)/);
  assert.match(api, /window\.__TAURI_INTERNALS__/);
  assert.match(api, /isPetrolabDesktop/);
  assert.match(api, /preview предназначен только для проверки интерфейса/);
  assert.match(api, /media\.inspect_sources/);
  assert.match(api, /media\.import\.plan/);
  assert.match(api, /media\.import\.apply/);
  assert.match(api, /analytical_point\.create/);
});

test("Windows release gate installs and launches the packaged application", async () => {
  const workflow = await read("../.github/workflows/windows-test-build.yml");
  const smoke = await read("../scripts/smoke_windows_installer.ps1");
  assert.match(workflow, /Install and launch packaged Windows app/);
  assert.match(workflow, /smoke_windows_installer\.ps1/);
  assert.match(smoke, /msiexec\.exe/);
  assert.match(smoke, /MainWindowHandle/);
  assert.match(smoke, /petrolab-service/);
  assert.match(smoke, /petrolab-v2\.sqlite/);
  assert.match(smoke, /Installed PetroLab smoke test passed/);
});

test("Tauri config keeps the approved desktop minimum window size and version alignment", async () => {
  const config = JSON.parse(await read("src-tauri/tauri.conf.json"));
  const cargo = await read("src-tauri/Cargo.toml");
  assert.equal(config.version, "0.1.6");
  assert.match(cargo, /version = "0\.1\.6"/);
  assert.equal(config.app.windows[0].width, 1440);
  assert.equal(config.app.windows[0].height, 1024);
  assert.equal(config.app.windows[0].minWidth, 1180);
  assert.equal(config.app.windows[0].minHeight, 800);
  assert.deepEqual(config.bundle.resources, ["binaries/petrolab-service.exe"]);
  assert.deepEqual(config.bundle.icon, ["icons/icon.ico"]);
  assert.match(config.build.beforeBuildCommand, /generate_tauri_icon\.py/);
});
