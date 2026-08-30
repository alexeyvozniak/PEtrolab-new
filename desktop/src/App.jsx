import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle,
  Columns,
  Database,
  File,
  FileArrowUp,
  GearSix,
  Info,
  MagnifyingGlass,
  Plus,
  SpinnerGap,
  Warning,
} from "@phosphor-icons/react";
import {
  applyImportPlan,
  clearImportStaging,
  createImportPlan,
  getProjectDatabasePath,
  inspectImportSource,
  listProjectAnalyses,
  pickImportFile,
  reviseImportMapping,
  stageImportFile,
  suggestImportRecipe,
} from "./desktopApi";
import { ImportMappingEditor } from "./ImportMappingEditor";
import "./styles.css";

const navigation = [
  [MagnifyingGlass, "Поиск", false],
  [FileArrowUp, "Импорт", true],
  [Database, "Анализы", true],
  [Columns, "Образцы", false],
  [Columns, "Минералы", false],
  [Columns, "Связи", false],
  [File, "Изображения", false],
  [Columns, "Построение", false],
  [Columns, "Статистика", false],
  [Columns, "Публикации", false],
];

function unwrap(response) {
  if (!response) throw new Error("PetroLab не получил ответ от научного сервиса.");
  if (response.error) {
    const details = response.error.details ? Object.values(response.error.details).filter(Boolean).join(", ") : "";
    throw new Error(`${response.error.message}${details ? ` (${details})` : ""}`);
  }
  return response.result;
}

function fileName(path) {
  if (!path) return "";
  return path.split(/[\\/]/).pop();
}

function warningText(warning) {
  const names = {
    HEADER_NOT_DETECTED: "Табличный заголовок не распознан",
    UNIT_REQUIRES_REVIEW: "Колонка похожа на измерение, но единица не указана явно — проверь её ниже",
    MERGED_HEADERS: "В заголовке есть объединённые ячейки",
    HIDDEN_ROWS: "В файле есть скрытые строки",
    FORMULA_WITHOUT_CACHED_VALUE: "Есть формулы без сохранённого значения",
    DUPLICATE_CANDIDATES: "Найдены возможные дубликаты",
  };
  return names[warning.code] || warning.code || "Предупреждение импорта";
}

export function App() {
  const [screen, setScreen] = useState("Импорт");
  const [databasePath, setDatabasePath] = useState("");
  const [project, setProject] = useState({ total: 0, source_count: 0, import_batch_count: 0, analyses: [] });
  const [sourcePath, setSourcePath] = useState("");
  const [sourceDisplayPath, setSourceDisplayPath] = useState("");
  const [inspection, setInspection] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [recipeWarnings, setRecipeWarnings] = useState([]);
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [query, setQuery] = useState("");

  const refreshAnalyses = async (path = databasePath) => {
    if (!path) return;
    const result = unwrap(await listProjectAnalyses(path));
    setProject(result);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const path = await getProjectDatabasePath();
        if (cancelled) return;
        setDatabasePath(path);
        const result = unwrap(await listProjectAnalyses(path));
        if (!cancelled) setProject(result);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const identityColumns = useMemo(() => {
    const fields = new Set();
    project.analyses.forEach((analysis) => Object.keys(analysis.identity || {}).forEach((field) => fields.add(field)));
    return [...fields];
  }, [project.analyses]);

  const measurementColumns = useMemo(() => {
    const fields = new Set();
    project.analyses.forEach((analysis) => Object.keys(analysis.measurements || {}).forEach((field) => fields.add(field)));
    return [...fields].slice(0, 14);
  }, [project.analyses]);

  const filteredAnalyses = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return project.analyses;
    return project.analyses.filter((analysis) => JSON.stringify(analysis).toLowerCase().includes(needle));
  }, [project.analyses, query]);

  const plannedMeasurementCount = useMemo(
    () => plan ? plan.planned_records.reduce((total, record) => total + record.measurements.length, 0) : 0,
    [plan],
  );

  const visibleRecipeWarnings = useMemo(() => {
    if (!recipe) return recipeWarnings;
    return recipeWarnings.filter((warning) => {
      if (warning.code !== "UNIT_REQUIRES_REVIEW") return true;
      const section = recipe.sections.find((item) => item.sheet_name === warning.sheet_name);
      const mapping = section?.mappings.find((item) => item.source_column_index === warning.source_column_index);
      return !mapping || mapping.target_role === "ignore";
    });
  }, [recipe, recipeWarnings]);

  const canSaveImport = Boolean(
    plan && plan.summary.planned_analysis_count > 0 && plannedMeasurementCount > 0,
  );

  const resetImportState = () => {
    setSourcePath("");
    setSourceDisplayPath("");
    setInspection(null);
    setRecipe(null);
    setRecipeWarnings([]);
    setPlan(null);
  };

  const chooseFile = async () => {
    if (busy) return;
    setBusy(true);
    setActivity("Выберите файл…");
    setError("");
    setSuccess("");
    const previousStaged = sourcePath;
    let newlyStaged = "";
    try {
      const selectedPath = await pickImportFile();
      if (!selectedPath) return;
      setActivity("Копирую файл в рабочую область PetroLab…");
      const selected = await stageImportFile(selectedPath);
      newlyStaged = selected.local_path;
      setActivity("Читаю листы и проверяю структуру файла…");
      const inspected = unwrap(await inspectImportSource(newlyStaged));
      setActivity("Распознаю колонки и создаю план импорта…");
      const suggestion = unwrap(await suggestImportRecipe(newlyStaged));
      const planned = unwrap(await createImportPlan(newlyStaged, suggestion.recipe));

      setSourcePath(newlyStaged);
      setSourceDisplayPath(selected.original_path || selectedPath);
      setInspection(inspected);
      setRecipe(suggestion.recipe);
      setRecipeWarnings(suggestion.warnings || []);
      setPlan(planned);
      setScreen("Импорт");

      if (previousStaged && previousStaged !== newlyStaged) {
        clearImportStaging(previousStaged).catch(() => {});
      }
    } catch (caught) {
      if (newlyStaged) clearImportStaging(newlyStaged).catch(() => {});
      setScreen("Импорт");
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const applyMapping = async (sheetName, sourceColumnIndex, target, canonicalField, unit) => {
    if (busy || !sourcePath || !recipe) return;
    setBusy(true);
    setActivity(`Обновляю сопоставление: ${sheetName}…`);
    setError("");
    setSuccess("");
    try {
      const revised = unwrap(await reviseImportMapping(
        sourcePath,
        recipe,
        sheetName,
        sourceColumnIndex,
        target,
        canonicalField,
        unit,
      ));
      const planned = unwrap(await createImportPlan(sourcePath, revised.recipe));
      setRecipe(revised.recipe);
      setPlan(planned);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const commitImport = async () => {
    if (busy || !canSaveImport || !databasePath || !sourcePath || !recipe || !plan) return;
    const stagedPath = sourcePath;
    setBusy(true);
    setActivity("Сохраняю импорт в проект…");
    setError("");
    setSuccess("");
    try {
      const result = unwrap(await applyImportPlan(databasePath, stagedPath, recipe));
      await refreshAnalyses(databasePath);
      resetImportState();
      clearImportStaging(stagedPath).catch(() => {});
      setSuccess(`Импорт сохранён: ${result.analysis_count} Analysis, ${result.measurement_count} Measurement.`);
      setScreen("Анализы");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setActivity("");
      setBusy(false);
    }
  };

  const startNewImport = () => {
    if (busy) return;
    const stagedPath = sourcePath;
    resetImportState();
    if (stagedPath) clearImportStaging(stagedPath).catch(() => {});
    setError("");
    setSuccess("");
    setScreen("Импорт");
  };

  const goTo = (label, enabled) => {
    if (!enabled || busy) return;
    setError("");
    setScreen(label);
    if (label === "Анализы") refreshAnalyses().catch((caught) => setError(caught.message));
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Database size={30} weight="duotone" /></div>
          <div><strong>PetroLab</strong><span>Desktop v2 alpha</span></div>
        </div>
        <nav>
          {navigation.map(([Icon, label, enabled]) => (
            <button
              className={`${screen === label ? "nav-item active" : "nav-item"}${enabled ? "" : " disabled"}`}
              key={label}
              disabled={!enabled || busy}
              onClick={() => goTo(label, enabled)}
              title={enabled ? label : "Экран ещё не подключён в этой alpha-сборке"}
            >
              <Icon size={19} />
              <span>{label}</span>
              {!enabled && <small>скоро</small>}
            </button>
          ))}
        </nav>
        <div className="side-footer"><Info size={18} /><span>Сейчас оживлены: импорт и анализы</span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{screen}</h2>
            <p>Источников: <b>{project.source_count}</b> · импортов: <b>{project.import_batch_count}</b> · анализов: <b>{project.total}</b></p>
          </div>
          <div className="top-actions">
            <button className="outline-button" onClick={startNewImport} disabled={busy}><Plus size={18} /> Добавить данные</button>
            <button className="icon-button" disabled title="Настройки будут подключены позже"><GearSix size={21} /></button>
          </div>
        </header>

        {activity && <div className="global-message activity"><SpinnerGap className="spin" size={20} /><span>{activity}</span></div>}
        {error && <div className="global-message error"><Warning size={20} weight="fill" /><span>{error}</span></div>}
        {success && <div className="global-message success"><CheckCircle size={20} weight="fill" /><span>{success}</span></div>}

        {screen === "Импорт" && (
          <section className="live-page">
            {!sourcePath && (
              <div className="file-start-card">
                <div className="file-start-icon"><FileArrowUp size={46} weight="duotone" /></div>
                <h1>Добавить настоящий файл</h1>
                <p>PetroLab прочитает XLSX, CSV или TSV, покажет распознанные листы и создаст план до записи в проект.</p>
                <button className="primary-button large" onClick={chooseFile} disabled={busy}>
                  {busy ? <SpinnerGap className="spin" size={20} /> : <FileArrowUp size={20} />}
                  {busy ? "Открываю файл…" : "Выбрать файл"}
                </button>
                <small>Исходный файл не изменяется. Перед чтением PetroLab создаёт локальную временную копию, поэтому поддерживаются и подключённые сетевые диски.</small>
              </div>
            )}

            {sourcePath && inspection && recipe && plan && (
              <>
                <div className="source-heading">
                  <div className="source-file"><File size={32} weight="duotone" /><div><b>{fileName(sourceDisplayPath || sourcePath)}</b><span title={sourceDisplayPath}>{inspection.source_format.toUpperCase()} · SHA-256 {inspection.source_fingerprint.slice(0, 12)}…</span></div></div>
                  <div className="top-actions">
                    <button className="outline-button" onClick={startNewImport} disabled={busy}>Отменить импорт</button>
                    <button className="outline-button" onClick={chooseFile} disabled={busy}>Выбрать другой файл</button>
                  </div>
                </div>

                <div className="metric-row">
                  <div className="metric"><span>Листов в файле</span><b>{inspection.sheets.length}</b></div>
                  <div className="metric"><span>Распознано таблиц</span><b>{recipe.sections.length}</b></div>
                  <div className="metric"><span>Будет Analysis</span><b>{plan.summary.planned_analysis_count}</b></div>
                  <div className="metric"><span>Будет Measurement</span><b>{plannedMeasurementCount}</b></div>
                  <div className="metric"><span>Групп дубликатов</span><b>{plan.summary.duplicate_candidate_groups}</b></div>
                </div>

                <div className="live-card">
                  <div className="section-title"><div><h3>1. Листы и распознавание</h3><p>Это данные из выбранного файла, а не демонстрационный пример.</p></div></div>
                  <div className="sheet-grid">
                    {inspection.sheets.map((sheet) => {
                      const section = recipe.sections.find((item) => item.sheet_name === sheet.name);
                      return (
                        <div className={section ? "real-sheet ready" : "real-sheet skipped"} key={sheet.name}>
                          <File size={22} />
                          <div><b>{sheet.name}</b><span>{sheet.used_range.rows} строк × {sheet.used_range.columns} колонок</span></div>
                          {section ? <em><CheckCircle size={16} weight="fill" /> заголовок: строка {section.header_row}</em> : <em><Warning size={16} /> пока пропущен</em>}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="live-card">
                  <div className="section-title"><div><h3>2. Сопоставление колонок</h3><p>Автораспознавание не угадывает единицы. Здесь можно явно исправить решение PetroLab перед сохранением.</p></div></div>
                  <ImportMappingEditor recipe={recipe} busy={busy} onApply={applyMapping} />
                </div>

                {plannedMeasurementCount === 0 && plan.summary.planned_analysis_count > 0 && (
                  <div className="import-blocker">
                    <Warning size={22} weight="fill" />
                    <div><b>Импорт пока нельзя сохранить</b><span>PetroLab нашёл {plan.summary.planned_analysis_count} Analysis, но ни одного Measurement. Назначь аналитические колонки как Measurement и явно выбери единицы.</span></div>
                  </div>
                )}

                {(visibleRecipeWarnings.length > 0 || plan.warnings.length > 0) && (
                  <div className="live-card warning-card">
                    <div className="section-title"><div><h3>Предупреждения</h3><p>Они не скрываются перед сохранением.</p></div></div>
                    <div className="warning-list">
                      {[...visibleRecipeWarnings, ...plan.warnings].map((warning, index) => (
                        <div key={`${warning.code}-${index}`}><Warning size={18} weight="fill" /><span><b>{warningText(warning)}</b>{warning.sheet_name ? ` · ${warning.sheet_name}` : ""}{warning.source_header ? ` · ${warning.source_header}` : ""}</span></div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="live-card">
                  <div className="section-title"><div><h3>3. Предпросмотр реального плана</h3><p>Первые записи, которые будут созданы в локальной базе.</p></div></div>
                  <div className="analysis-preview-list">
                    {plan.planned_records.slice(0, 12).map((record) => (
                      <div className="analysis-preview-row" key={record.preview_id}>
                        <span className="row-origin">{record.sheet_name} · строка {record.row_number}</span>
                        <b>{record.identity.filter(Boolean).join(" · ") || "Analysis без распознанного идентификатора"}</b>
                        <span>{record.measurements.slice(0, 6).map((measurement) => `${measurement.field}=${measurement.raw_token ?? "∅"} ${measurement.unit}`).join(" · ") || "Нет Measurement"}</span>
                      </div>
                    ))}
                  </div>
                  {plan.planned_records.length > 12 && <p className="more-note">Показано 12 из {plan.planned_records.length} записей.</p>}
                </div>

                <div className={`commit-bar${canSaveImport ? "" : " blocked"}`}>
                  <div>
                    <b>Готово к записи: {plan.summary.planned_analysis_count} Analysis · {plannedMeasurementCount} Measurement</b>
                    <span>{canSaveImport ? "Исходник не меняется; PetroLab сохранит собственную управляемую копию импортируемого файла." : "Сначала назначь хотя бы одну аналитическую колонку как Measurement и укажи её единицу."}</span>
                  </div>
                  <button className="primary-button large" onClick={commitImport} disabled={busy || !canSaveImport} title={canSaveImport ? "" : "Нельзя сохранять Analysis без Measurement"}>
                    {busy ? <SpinnerGap className="spin" size={20} /> : <CheckCircle size={20} />}
                    Сохранить импорт в проект
                  </button>
                </div>
              </>
            )}
          </section>
        )}

        {screen === "Анализы" && (
          <section className="live-page analyses-page">
            <div className="analysis-toolbar">
              <div className="search-box"><MagnifyingGlass size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти по Sample, Analysis, Source, значению…" /></div>
              <span>Показано {filteredAnalyses.length} из {project.total}</span>
              <button className="outline-button" onClick={() => refreshAnalyses().catch((caught) => setError(caught.message))} disabled={busy}>Обновить</button>
            </div>

            {project.total === 0 ? (
              <div className="empty-analyses"><Database size={48} weight="duotone" /><h2>В проекте пока нет анализов</h2><p>Импортируй первый Excel — после сохранения строки появятся здесь и останутся после перезапуска PetroLab.</p><button className="primary-button" onClick={startNewImport} disabled={busy}>Добавить данные</button></div>
            ) : (
              <div className="analysis-table-wrap">
                <table className="analysis-table">
                  <thead><tr><th>Source</th><th>Лист</th><th>Строка</th>{identityColumns.map((field) => <th key={field}>{field}</th>)}{measurementColumns.map((field) => <th key={field}>{field}</th>)}</tr></thead>
                  <tbody>
                    {filteredAnalyses.map((analysis) => (
                      <tr key={analysis.analysis_id} title={analysis.analysis_id}>
                        <td><b>{analysis.source_name}</b></td>
                        <td>{analysis.sheet_name}</td>
                        <td>{analysis.source_row_number}</td>
                        {identityColumns.map((field) => <td key={field}>{analysis.identity?.[field] || ""}</td>)}
                        {measurementColumns.map((field) => {
                          const measurement = analysis.measurements?.[field];
                          return <td key={field}>{measurement ? <><span>{measurement.raw_token ?? "∅"}</span><small>{measurement.unit}</small></> : ""}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
