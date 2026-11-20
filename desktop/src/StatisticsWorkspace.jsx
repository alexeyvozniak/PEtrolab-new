import { useEffect, useState } from "react";
import "./statisticsWorkspace.css";

const STEPS = ["Задача", "Данные", "Метод", "Результат"];
const TRANSFORMS = { euclidean: "Евклидова разведочная", clr: "CLR", ilr: "ILR" };
const SCALING = { none: "Без масштабирования", standard: "Стандартное", robust: "Робастное" };
const DOMAINS = {
  oxide_wt_percent: "Оксиды, масс. %", trace_concentration: "Концентрация элементов",
  apfu: "APFU", ratio_or_index: "Отношение или индекс", other: "Другой домен",
};
const EXCLUSIONS = {
  missing: "Нет численного значения", censored: "Ниже предела обнаружения", zero: "Ноль",
  negative: "Отрицательное значение", calculation_policy: "Неоднозначное измерение",
};
const COLORS = ["#316f52", "#c06430", "#7655a2", "#306ea1", "#b54762", "#73702c", "#527371", "#6f4d3f", "#a04781", "#5269a2", "#637b39", "#88683a"];
const fieldName = (feature) => [feature.field, feature.unit, feature.measurement_set, feature.method].filter(Boolean).join(" · ");
const keyFor = (feature) => JSON.stringify([feature.field, feature.unit, feature.measurement_set, feature.method]);
const PAGE = 30;

function DataReview({ review }) {
  const [page, setPage] = useState(0);
  const details = new Map();
  for (const item of review.logratio_excluded) {
    const reasons = details.get(item.analysis_id) || [];
    reasons.push(`${item.field}: ${EXCLUSIONS[item.reason] || item.reason}`);
    details.set(item.analysis_id, reasons);
  }
  return <>
    <h3>Состав входного набора</h3>
    <div className="statistics-table"><table>
      <thead><tr><th>Analysis ID</th>{review.features.map((item) => <th key={keyFor(item)}>{fieldName(item)}</th>)}<th>Проверка строки</th></tr></thead>
      <tbody>{review.rows.slice(page * PAGE, (page + 1) * PAGE).map((row) => <tr key={row.analysis_id}>
        <td>{row.label && <b>{row.label}<br /></b>}<small>{row.analysis_id}</small></td>
        {row.raw_tokens.map((value, index) => <td key={keyFor(review.features[index])}>{value ?? "—"}</td>)}
        <td>{details.get(row.analysis_id)?.join(" · ") || "Готово"}</td>
      </tr>)}</tbody>
    </table></div>
    {review.rows.length > PAGE && <div className="statistics-actions">
      <button type="button" className="outline-button" disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</button>
      <span>Страница {page + 1} из {Math.ceil(review.rows.length / PAGE)}</span>
      <button type="button" className="outline-button" disabled={(page + 1) * PAGE >= review.rows.length} onClick={() => setPage(page + 1)}>Далее</button>
    </div>}
  </>;
}

function DataChecks({ review }) {
  if (!review) return <p>Выберите показатели для проверки.</p>;
  return <>
    <p>Полных строк · {review.complete_count} из {review.rows.length}</p>
    <p>Полных положительных строк · {review.positive_complete_count}</p>
    <ul>{review.features.map((item, index) => <li key={keyFor(item)}>{fieldName(item)} · {DOMAINS[review.domain.domains[index]]}</li>)}</ul>
    {!review.domain.logratio_available && <p className="statistics-warning">CLR и ILR недоступны. Выберите признаки одного композиционного домена, единицы и аналитического контекста.</p>}
    {review.domain.mixed_context && <p className="statistics-warning">В признаках смешаны аналитические контексты.</p>}
    {review.domain.mixed_units && <p className="statistics-warning">Разные единицы потребуют масштабирования для евклидова пути.</p>}
    {review.domain.overlapping_iron && <p className="statistics-warning">В наборе одновременно присутствуют компоненты и суммарная форма железа.</p>}
  </>;
}

function ClusterGroup({ cluster, members, selectedCluster, setSelectedCluster, run, saveGroup, busy }) {
  const [name, setName] = useState("");
  const [author, setAuthor] = useState("Локальный пользователь");
  const [message, setMessage] = useState(null);
  const [pending, setPending] = useState(false);
  const open = selectedCluster === cluster;
  const save = async (event) => {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      const group = await saveGroup(run.id, cluster, name, author);
      setMessage({ notice: `Сохранена рабочая группа «${group.name}» · ${group.analysis_ids.length}.` });
    } catch (error) {
      setMessage({ error: error.message });
    } finally {
      setPending(false);
    }
  };
  return <section className="statistics-cluster">
    <button type="button" className="outline-button" aria-expanded={open} onClick={() => setSelectedCluster(open ? null : cluster)}>
      <span className="statistics-dot" style={{ backgroundColor: COLORS[cluster] }} /> Кластер {cluster + 1} · {members.length}
    </button>
    {open && <>
      <div className="statistics-members"><ul>
        {members.map((item) => <li key={item.analysis_id}>{item.label || "Анализ"}<br /><small>{item.analysis_id}</small></li>)}
      </ul></div>
      <form className="statistics-form" onSubmit={save}>
        <label>Название рабочей группы<input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>
        <label>Автор<input value={author} maxLength={120} onChange={(event) => setAuthor(event.target.value)} /></label>
        <button className="primary-button" disabled={busy || pending || run.status !== "current" || !name.trim() || !author.trim()}>Сохранить кластер как рабочую группу</button>
      </form>
      {message && <p role={message.error ? "alert" : "status"}>{message.error || message.notice}</p>}
    </>}
  </section>;
}

function ClusterResult({ run, saveGroup, busy }) {
  const [selectedCluster, setSelectedCluster] = useState(null);
  const { members, fit, pca } = run.result_manifest;
  const groups = Array.from({ length: run.parameters.clusters }, (_, cluster) => members.filter((item) => item.cluster === cluster));
  return <div className="statistics-result">
    <section className="statistics-card">
      <h3>Параметры расчёта</h3>
      <p>{TRANSFORMS[run.parameters.transform]} · {SCALING[run.parameters.scaling]}</p>
      <p>Seed · {run.seed}</p>
      <p>Использовано · {members.length} из {run.input.analysis_ids.length}</p>
      <p>Инерция · {fit.inertia.toPrecision(5)}</p>
      <ul>{run.parameters.features.map((feature) => <li key={keyFor(feature)}>{fieldName(feature)}</li>)}</ul>
      {run.excluded.length > 0 && <details><summary>Исключения</summary><ul>{run.excluded.map((item) =>
        <li key={`${item.analysis_id}/${item.field}/${item.reason}`}>{item.analysis_id} · {item.field} · {EXCLUSIONS[item.reason]}</li>
      )}</ul></details>}
      <small>{run.id}</small>
    </section>
    <section className="statistics-card">
      <h3>Результат кластеризации</h3>
      {run.status === "stale" && <p className="statistics-warning" role="status">{run.stale_reasons.join(" ")}</p>}
      <svg className="statistics-scatter" viewBox="0 0 470 320" aria-label="PCA-проекция кластеров">
        <path d="M 44 20 V 275 H 442" fill="none" stroke="#82998a" />
        {members.map((item) => <circle key={item.analysis_id} cx={44 + 398 * item.u} cy={275 - 255 * item.v} r={4.5}
          fill={COLORS[item.cluster]} opacity={selectedCluster === null || selectedCluster === item.cluster ? 1 : 0.25}>
          <title>{item.label || item.analysis_id} · кластер {item.cluster + 1}</title>
        </circle>)}
        <text x="240" y="302" textAnchor="middle">PC1 · {(pca.explained_variance_ratio[0] * 100).toFixed(1)}%</text>
        <text transform="translate(15 155) rotate(-90)" textAnchor="middle">PC2 · {(pca.explained_variance_ratio[1] * 100).toFixed(1)}%</text>
      </svg>
    </section>
    <section className="statistics-card"><h3>Рабочие группы</h3>
      {groups.map((items, cluster) => <ClusterGroup key={cluster} cluster={cluster} members={items} run={run}
        busy={busy} saveGroup={saveGroup} selectedCluster={selectedCluster} setSelectedCluster={setSelectedCluster} />)}
    </section>
  </div>;
}

export function StatisticsWorkspace({ selectedIds, loadGroups, loadCatalog, loadRuns, openRun, reviewInput, runClustering, saveGroup, onPublishRun }) {
  const [step, setStep] = useState(0);
  const [groups, setGroups] = useState([]);
  const [runs, setRuns] = useState([]);
  const [source, setSource] = useState("selection");
  const [catalog, setCatalog] = useState([]);
  const [features, setFeatures] = useState([]);
  const [review, setReview] = useState(null);
  const [run, setRun] = useState(null);
  const [method, setMethod] = useState("euclidean");
  const [scaling, setScaling] = useState("standard");
  const [clusters, setClusters] = useState("2");
  const [seed, setSeed] = useState("42");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const group = groups.find((item) => item.group.id === source);
  const ids = source === "selection" ? selectedIds : group?.group.analysis_ids;
  const input = source === "selection" ? { kind: "analysis_snapshot", analysis_ids: ids } : { kind: "work_group", work_group_id: source };
  const size = ids?.length || 0;
  useEffect(() => {
    let active = true;
    Promise.all([loadGroups(), loadRuns()]).then(([groupList, history]) => {
      if (active) { setGroups(groupList.groups); setRuns(history); }
    }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [loadGroups, loadRuns]);
  const perform = async (fn) => {
    setPending(true);
    setError("");
    try { await fn(); }
    catch (caught) { setError(caught.message); }
    finally { setPending(false); }
  };
  const chooseInput = () => perform(async () => {
    const response = await loadCatalog(ids);
    setCatalog(response.axes);
    setFeatures([]);
    setReview(null);
    setStep(1);
  });
  const check = () => perform(async () => {
    const result = await reviewInput(input, features);
    setReview(result);
    if (!result.domain.logratio_available) setMethod("euclidean");
    if (result.domain.mixed_units && scaling === "none") setScaling("standard");
  });
  const calculate = (event) => {
    event.preventDefault();
    perform(async () => {
      const result = await runClustering(review, { transform: method, scaling: method === "euclidean" ? scaling : "none",
        clusters: Number(clusters), seed: Number(seed) });
      setRun(result);
      setStep(3);
      setRuns(await loadRuns());
    });
  };
  const open = (id) => perform(async () => { setRun(await openRun(id)); setStep(3); setReview(null); });
  const rowCount = method === "euclidean" ? review?.complete_count : review?.positive_complete_count;
  const clusterNumber = Number(clusters);
  const seedNumber = Number(seed);
  return <section className="statistics-workspace">
    <h2>Статистика</h2>
    <nav className="statistics-steps" aria-label="Этапы расчёта">
      {STEPS.map((label, index) => <span key={label} aria-current={step === index ? "step" : undefined}>{index + 1} {label}</span>)}
    </nav>
    {error && <p role="alert">{error}</p>}
    {pending && <p role="status">Выполняю запрос…</p>}
    {step === 0 && <div className="statistics-task">
      <section className="statistics-card">
        <h3>Найти группы внутри одного набора</h3>
        <label className="statistics-form">Входной набор<select value={source} disabled={pending} onChange={(event) => setSource(event.target.value)}>
          <option value="selection">Текущий отбор · {selectedIds.length}</option>
          {groups.map(({ group: item, unavailable_analysis_ids }) => <option key={item.id} value={item.id} disabled={unavailable_analysis_ids.length > 0}>
            {item.name} · {item.analysis_ids.length}{unavailable_analysis_ids.length ? " · часть входа недоступна" : ""}
          </option>)}
        </select></label>
        <button className="primary-button" type="button" disabled={pending || size < 2 || size > 10000}
          onClick={chooseInput}>Проверить данные</button>
        {size < 2 && <p>Выберите рабочую группу или отберите не менее двух анализов в таблице.</p>}
        {size > 10000 && <p>Выберите до 10 000 анализов.</p>}
      </section>
      <aside className="statistics-card"><h3>Последние расчёты</h3>
        {runs.length ? <ul>{runs.map((item) => <li key={item.id}><button className="outline-button" type="button" disabled={pending}
          onClick={() => open(item.id)}>{TRANSFORMS[item.transform]} · {SCALING[item.scaling]} · {item.clusters} кластера · {item.created_at.slice(0, 10)}</button></li>)}</ul>
          : <p>Сохранённых расчётов пока нет.</p>}
      </aside>
    </div>}
    {step === 1 && <>
      <button className="outline-button" type="button" disabled={pending} onClick={() => setStep(0)}>Назад к задаче</button>
      <div className="statistics-review">
        <aside className="statistics-card"><h3>Входной набор</h3><p>{group?.group.name || "Текущий отбор"} · {size}</p></aside>
        <section className="statistics-card">
          <h3>Признаки</h3>
          {!catalog.length && <p>В выбранном наборе нет подходящих измерений.</p>}
          <div className="statistics-features">
            {catalog.map((feature) => {
              const key = keyFor(feature);
              const index = features.findIndex((item) => keyFor(item) === key);
              return <label key={key}><input type="checkbox" checked={index >= 0} disabled={pending || (features.length >= 24 && index < 0)}
                onChange={() => { setFeatures(index < 0 ? [...features, feature] : features.filter((item) => keyFor(item) !== key)); setReview(null); }} />
                {fieldName(feature)}{index >= 0 && ` · ${index + 1}`}</label>;
            })}
          </div>
          <div className="statistics-actions">
            <button className="outline-button" type="button" disabled={pending || features.length < 2} onClick={check}>Проверить состав</button>
            <button className="primary-button" type="button" disabled={pending || !review || !review.domain.euclidean_available}
              onClick={() => setStep(2)}>К выбору метода</button>
          </div>
          {review && <DataReview key={review.input_fingerprint} review={review} />}
        </section>
        <aside className="statistics-card"><h3>Проверки перед расчётом</h3><DataChecks review={review} /></aside>
      </div>
    </>}
    {step === 2 && <>
      <button className="outline-button" type="button" disabled={pending} onClick={() => setStep(1)}>Назад к данным</button>
      <div className="statistics-task">
        <form className="statistics-card statistics-form" onSubmit={calculate}>
          <h3>K-means (Ллойд)</h3>
          <label>Путь анализа<select value={method} disabled={pending} onChange={(event) => setMethod(event.target.value)}>
            {Object.entries(TRANSFORMS).map(([key, label]) => <option key={key} value={key}
              disabled={key !== "euclidean" && !review.domain.logratio_available}>{label}</option>)}
          </select></label>
          {method === "euclidean" && <label>Масштабирование<select value={scaling} disabled={pending} onChange={(event) => setScaling(event.target.value)}>
            {Object.entries(SCALING).map(([key, label]) => <option key={key} value={key} disabled={key === "none" && review.domain.mixed_units}>{label}</option>)}
          </select></label>}
          <label>Число кластеров<input type="number" min="2" max="12" step="1" value={clusters} onChange={(event) => setClusters(event.target.value)} /></label>
          <label>Seed<input type="number" min="0" max="4294967295" step="1" value={seed} onChange={(event) => setSeed(event.target.value)} /></label>
          <p>Доступно строк · {rowCount}. Неполные и цензурированные значения исключаются.
            {method !== "euclidean" && " Для CLR и ILR также исключаются нули и отрицательные значения."}</p>
          <button className="primary-button" disabled={pending || !Number.isInteger(clusterNumber) || clusterNumber < 2 || clusterNumber > 12
            || clusterNumber > rowCount || !seed || !Number.isInteger(seedNumber) || seedNumber < 0 || seedNumber > 4294967295}>Запустить расчёт</button>
        </form>
        <aside className="statistics-card"><h3>Проверки перед расчётом</h3><DataChecks review={review} /></aside>
      </div>
    </>}
    {step === 3 && run && <>
      <div className="statistics-actions">
        <button className="outline-button" type="button" disabled={pending} onClick={() => setStep(review ? 2 : 0)}>{review ? "Назад к методу" : "К задаче и истории"}</button>
        {onPublishRun && <button className="outline-button" type="button" disabled={pending || run.status !== "current"} onClick={() => onPublishRun(run)}>
          Добавить расчёт в публикацию
        </button>}
      </div>
      <ClusterResult key={run.id} run={run} saveGroup={saveGroup} busy={pending} />
    </>}
  </section>;
}
