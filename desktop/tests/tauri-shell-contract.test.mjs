import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createFilter, normalizePath } from "vite";
import viteConfig from "../vite.config.mjs";

test("Windows watcher excludes native artifacts but retains source changes", () => {
  const ignored = createFilter(viteConfig.server.watch.ignored, undefined, { resolve: false });
  for (const path of [
    "src-tauri/target/debug/petrolab-desktop.exe",
    "src-tauri/target/debug/deps/example.dll",
    "src-tauri/binaries/petrolab-service.exe",
    "src-tauri/binaries/example.dll",
  ]) {
    assert.equal(ignored(normalizePath(`C:\\project\\desktop\\${path.replaceAll("/", "\\")}`)), true, path);
  }
  for (const path of ["src/App.jsx", "src-tauri/src/lib.rs"]) {
    assert.equal(ignored(normalizePath(`C:/project/desktop/${path}`)), false, path);
  }
});

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
  assert.match(shell, /\["xls", "xlsx", "csv", "tsv"\]/);
  assert.match(shell, /async fn stage_import_file/);
  assert.match(api, /stage_import_file/);
  assert.match(api, /clear_import_staging/);
  assert.match(app, /stageImportFile\(selectedPath\)/);
  assert.match(app, /selected\.local_path/);
  assert.match(workspace, /Отменить/);
});

test("desktop image import selects a batch with only supported raster extensions", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImagesWorkspace.jsx");
  assert.match(shell, /fn pick_media_files/);
  assert.match(shell, /SUPPORTED_MEDIA_EXTENSIONS[^=]*= \["png", "jpg", "jpeg", "tif", "tiff", "bmp"\]/);
  assert.match(shell, /\.pick_files\(\)/);
  assert.match(api, /pick_media_files/);
  assert.match(app, /inspectMediaSources\(paths\)/);
  assert.match(api, /analytical_point\.list/);
  assert.match(api, /media\.preview/);
  assert.match(app, /listAnalyticalPoints\(databasePath\)/);
  assert.match(workspace, /Подтвердить предложения/);
  assert.match(workspace, /Пространственные точки создаются на следующем шаге/);
  assert.match(workspace, /Point ·/);
  assert.match(workspace, /Rectangle/);
  assert.match(workspace, /Square/);
  assert.match(workspace, /Причина межобразцового исключения/);
  assert.match(workspace, /Завершить импорт изображений/);
  assert.match(workspace, /Исходные файлы не изменяются/);
});

test("desktop image import can collect a folder recursively without following links or accepting batch scripts", async () => {
  const shell = await read("src-tauri/src/lib.rs");
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImagesWorkspace.jsx");
  assert.match(shell, /async fn pick_media_folder/);
  assert.match(shell, /fn collect_media_folder/);
  assert.match(shell, /file_type\.is_symlink\(\)/);
  assert.match(shell, /pending\.push\(entry\.path\(\)\)/);
  assert.match(shell, /MAX_MEDIA_BATCH_FILES/);
  assert.match(shell, /supported_media_path/);
  assert.doesNotMatch(shell.match(/SUPPORTED_MEDIA_EXTENSIONS[^;]+/)?.[0] || "", /bat/i);
  assert.match(api, /pick_media_folder/);
  assert.match(app, /pickMediaFolder\(\)/);
  assert.match(workspace, /Выбрать папку/);
  assert.match(workspace, /вложенными папками/);
});

test("adding import is transactional and keeps the existing queue on failure", async () => {
  const app = await read("src/App.jsx");
  assert.match(app, /newlyStaged && !accepted/);
  assert.match(app, /addWorkspaceSources/);
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
  assert.match(app, /createImportWorkspace/);
  assert.match(app, /active\.classification\.mode !== "clean_table_fast"/);
  assert.match(workspace, /Таблица готова к импорту/);
  assert.match(workspace, /Импортировать таблицу/);
  assert.match(workspace, /Открыть подробную проверку/);
  assert.match(workspace, /требует внимания/);
  assert.match(workspace, /Clean Table v/);
});

test("approved import workspace keeps source list, physical table, issue inspector and fixed commit bar together", async () => {
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const review = await read("src/ImportBlockReview.jsx");
  const styles = await read("src/importWorkspace.css");
  assert.match(app, /<ImportWorkspace/);
  assert.match(workspace, /Файл и листы/);
  assert.match(workspace, /Вопросы · \{issueGroups\.length\} типов/);
  assert.match(workspace, /Исходный файл не изменится/);
  assert.match(workspace, /activeBlockId/);
  assert.match(workspace, /focusedIssue=\{mineralFocus \|\| selectedIssue\}/);
  assert.match(workspace, /ImportMappingEditor/);
  assert.match(review, /Исходная таблица/);
  assert.match(review, /Таблица не отображается/);
  assert.match(styles, /grid-template-columns: 210px minmax\(520px, 1fr\) 330px/);
  assert.match(styles, /import-workspace-footer/);
});

test("raw block review precedes field mapping and supports transposed orientation", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const review = await read("src/ImportBlockReview.jsx");
  assert.match(api, /import\.preview\.window/);
  assert.match(api, /import\.recipe\.revise_sections/);
  assert.match(app, /previewWorkspaceWindow/);
  assert.match(app, /kind: "sections", decisions/);
  assert.match(workspace, /ImportBlockReview/);
  assert.match(app, /blockDraftDirty/);
  assert.match(workspace, /activeBlockId/);
  assert.match(workspace, /ImportMappingEditor/);
  assert.match(workspace, /анализы по столбцам/);
  assert.match(workspace, /исходная таблица всегда должна быть видна в центре/);
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
  assert.match(app, /applyWorkspaceDecision/);
  assert.match(app, /mappingDraftDirty/);
  assert.match(app, /kind: "mappings", decisions/);
  assert.match(editor, /Применить сопоставление/);
  assert.match(editor, /Назначить полям без единицы/);
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
  assert.match(editor, /Не импортировать нераспознанные поля/);
  assert.doesNotMatch(editor, />Применить<\/button>/);
});

test("raw review groups repetitive issues and gets server-issued bulk unit scopes", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  assert.match(api, /import\.recipe\.bulk_scopes/);
  assert.match(api, /import\.recipe\.apply_bulk_unit/);
  assert.match(api, /import\.recipe\.bulk_ignore_scopes/);
  assert.match(api, /import\.recipe\.apply_bulk_ignore/);
  assert.match(app, /active.bulk_unit_scopes/);
  assert.match(app, /kind: "unit", bulk_scope_id/);
  assert.match(app, /kind: "ignore", bulk_scope_id/);
  assert.match(workspace, /Групповые решения/);
  assert.match(workspace, /REPEATABLE_ISSUE_CODES/);
  assert.match(workspace, /groupIssues/);
  assert.match(workspace, /одинаковой физической структурой/);
  assert.match(workspace, /Не импортировать все нераспознанные поля/);
});

test("analyses view exposes source metadata, method context and truthful physical origin", async () => {
  const app = await read("src/App.jsx");
  const workspace = await read("src/AnalysesWorkspace.jsx");
  assert.match(app, /<AnalysesWorkspace/);
  assert.match(workspace, /metadataFields/);
  assert.match(workspace, /source_metadata/);
  assert.match(workspace, /Исходные сведения/);
  assert.match(workspace, /Все измерения/);
  assert.match(workspace, /measurement\.method/);
  assert.match(workspace, /measurement\.measurement_set/);
  assert.match(workspace, /originLabel/);
  assert.match(workspace, /source_orientation === "columns_are_analyses"/);
  assert.match(workspace, /source_column_number/);
  assert.match(workspace, /В файле/);
  assert.match(workspace, /Выбранные строки закреплены сверху/);
  assert.match(workspace, /Поиск работает по всем полям/);
});

test("analyses view exposes mineral identification status and evidence", async () => {
  const workspace = await read("src/AnalysesWorkspace.jsx");
  const styles = await read("src/analysesWorkspace.css");
  assert.match(workspace, /Идентификация минерала/);
  assert.match(workspace, /Статус идентификации минерала/);
  assert.match(workspace, /Кандидаты/);
  assert.match(workspace, /ruleset_version/);
  assert.match(workspace, /mineralStatusFilter/);
  assert.match(styles, /analysis-mineral-review/);
});

test("duplicate candidates require explicit keep-all review before save", async () => {
  const api = await read("src/desktopApi.js");
  const app = await read("src/App.jsx");
  const workspace = await read("src/ImportWorkspace.jsx");
  const review = await read("src/ImportDuplicateReview.jsx");
  assert.match(api, /import\.recipe\.review_duplicates/);
  assert.match(app, /kind: "duplicates"/);
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
  assert.match(api, /project\.mineral_identification\.list/);
  assert.match(api, /media\.import\.plan/);
  assert.match(api, /media\.import\.apply/);
  assert.match(api, /analytical_point\.create/);
});

test("Windows release gate installs and launches the packaged application", async () => {
  const workflow = await read("../.github/workflows/windows-test-build.yml");
  const smoke = await read("../scripts/smoke_windows_installer.ps1");
  const uiSmoke = await read("tests/import-ui.e2e.test.jsx");
  assert.match(workflow, /Install and launch packaged Windows app/);
  assert.match(workflow, /smoke_windows_installer\.ps1/);
  assert.match(workflow, /npm run test:ui/);
  assert.match(smoke, /msiexec\.exe/);
  assert.match(smoke, /MainWindowHandle/);
  assert.match(smoke, /petrolab-service/);
  assert.match(smoke, /petrolab-v2\.sqlite/);
  assert.match(smoke, /Installed PetroLab smoke test passed/);
  assert.match(uiSmoke, /user clicks through Clean Table import/);
  assert.match(uiSmoke, /complex import always shows the source table/);
  assert.match(uiSmoke, /Выбрать файл/);
  assert.match(uiSmoke, /Импортировать таблицу/);
  assert.match(uiSmoke, /UI-1/);
  assert.match(uiSmoke, /Windows UI smoke/);
  assert.match(uiSmoke, /applyImportPlan/);
});

test("Tauri config keeps the approved desktop minimum window size and version alignment", async () => {
  const config = JSON.parse(await read("src-tauri/tauri.conf.json"));
  const cargo = await read("src-tauri/Cargo.toml");
  assert.equal(config.version, "0.1.7");
  assert.match(cargo, /version = "0\.1\.7"/);
  assert.equal(config.app.windows[0].width, 1440);
  assert.equal(config.app.windows[0].height, 1024);
  assert.equal(config.app.windows[0].minWidth, 1180);
  assert.equal(config.app.windows[0].minHeight, 800);
  assert.deepEqual(config.bundle.resources, ["binaries/petrolab-service.exe"]);
  assert.deepEqual(config.bundle.icon, ["icons/icon.ico"]);
  assert.match(config.build.beforeBuildCommand, /generate_tauri_icon\.py/);
});

test("compact import reserves space for physical rows and accessible range actions", async () => {
  const styles = await read("src/importBlockReview.css");
  const workspace = await read("src/importWorkspace.css");
  const app = await read("src/App.jsx");
  assert.match(styles, /\.raw-preview-wrap\s*\{[^}]*min-height: 180px/s);
  assert.match(styles, /\.semantic-tool-panel\s*\{[^}]*min-height: 64px/s);
  assert.match(styles, /@media \(max-height: 850px\)/);
  assert.match(workspace, /\.import-bulk-scope > div\s*\{[^}]*flex-wrap: wrap/s);
  assert.match(app, /section\.sheet_name, Math\.max\(1, section\.header_row\), 12/);
});
