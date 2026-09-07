import { useMemo, useState } from "react";
import {
  ArrowCounterClockwise,
  CheckCircle,
  Flask,
  MagnifyingGlass,
  ShieldCheck,
  Warning,
} from "@phosphor-icons/react";
import {
  mineralConfidenceLabel,
  mineralReasonLabel,
  mineralStatus,
  mineralStatusLabel,
  reportedMineral,
} from "./mineralUi";
import "./mineralsWorkspace.css";

const ATTENTION_STATUSES = new Set([
  "conflict",
  "missing_reported",
  "low_confidence",
  "insufficient_input",
  "unrecognized_reported",
  "not_checked",
  "reported_only",
]);

function mainIdentity(analysis) {
  const identity = analysis?.identity || {};
  return identity.Analysis || identity.Point || identity.Sample || Object.values(identity).find(Boolean) || "Analysis без имени";
}

function originLabel(analysis) {
  const position = analysis.source_orientation === "columns_are_analyses"
    ? `колонка ${analysis.source_column_number ?? "?"}`
    : `строка ${analysis.source_row_number ?? "?"}`;
  return `${analysis.source_name} · ${analysis.sheet_name} · ${position}`;
}

function ReviewPane({ analysis, busy, onDecide }) {
  if (!analysis) {
    return <aside className="mineral-review-pane empty"><Flask size={26} /><p>Выбери анализ из очереди проверки.</p></aside>;
  }
  const verification = analysis.mineral_verification || {};
  const reported = reportedMineral(analysis);
  const reportedTarget = verification.reported_target;
  const accepted = verification.accepted?.target || "";
  const evidence = verification.reasons?.length ? verification.reasons : (verification.issues || []);
  const canAcceptSuggestion = Boolean(verification.prediction && ["high", "medium"].includes(verification.confidence) && accepted !== verification.prediction);
  const canKeepReported = Boolean(reportedTarget && accepted !== reportedTarget);

  return <aside className="mineral-review-pane" aria-label="Проверка выбранного минерала">
    <header>
      <span>Проверка анализа</span>
      <h2>{mainIdentity(analysis)}</h2>
      <p>{originLabel(analysis)}</p>
    </header>

    <section className="mineral-decision-state">
      <div className={`mineral-status-badge status-${mineralStatus(analysis)}`}>{mineralStatusLabel(mineralStatus(analysis))}</div>
      <h3>Сравнение</h3>
      <dl>
        <div><dt>В источнике</dt><dd>{reported || "Не указано"}<small>исходный текст</small></dd></div>
        <div><dt>Предложение</dt><dd>{verification.prediction || "Не определено"}<small>уверенность: {mineralConfidenceLabel(verification.confidence)}</small></dd></div>
        <div className="accepted"><dt>Принято</dt><dd>{accepted || "Решения нет"}<small>{accepted ? "интерпретация пользователя" : "исходник не изменён"}</small></dd></div>
      </dl>
    </section>

    <section>
      <h3>Кандидаты классификатора</h3>
      <div className="mineral-candidate-list">
        {(verification.candidates || []).length === 0 && <p className="muted">Кандидаты не рассчитаны.</p>}
        {(verification.candidates || []).map((candidate, index) => <div key={candidate.target}>
          <span><b>{index + 1}</b>{candidate.target}</span>
          <small>{candidate.score} баллов правил</small>
        </div>)}
      </div>
    </section>

    <section>
      <h3>Основания и ограничения</h3>
      <div className="mineral-evidence-list">
        {evidence.length === 0 && <p className="muted">Дополнительных ограничений нет.</p>}
        {evidence.map((reason) => <p key={reason}>{mineralReasonLabel(reason)}</p>)}
      </div>
      <p className="mineral-ruleset">Версия правил: {verification.ruleset_version || "не указана"}</p>
    </section>

    <footer>
      {canAcceptSuggestion && <button className="primary-button" type="button" disabled={busy} onClick={() => onDecide(analysis, verification.prediction, "Принято предложение классификатора после проверки")}>Принять предложение</button>}
      {canKeepReported && <button className="outline-button" type="button" disabled={busy} onClick={() => onDecide(analysis, reportedTarget, "Сохранена интерпретация исходного названия после проверки")}>Оставить исходное</button>}
      {accepted && <button className="mineral-clear-button" type="button" disabled={busy} onClick={() => onDecide(analysis, null, "Решение сброшено; анализ возвращён в очередь проверки")}><ArrowCounterClockwise size={16} /> Сбросить решение</button>}
      <small>Решение сохраняется отдельно. Исходное название и измерения не меняются.</small>
    </footer>
  </aside>;
}

export function MineralsWorkspace({ project, busy, onRefresh, onDecide, onLoadMore, onAddData }) {
  const analyses = project.analyses || [];
  const [queue, setQueue] = useState("attention");
  const [query, setQuery] = useState("");
  const [focusedId, setFocusedId] = useState("");
  const counts = useMemo(() => analyses.reduce((result, analysis) => {
    const status = mineralStatus(analysis);
    result[status] = (result[status] || 0) + 1;
    return result;
  }, {}), [analyses]);
  const attentionCount = Object.entries(counts).filter(([status]) => ATTENTION_STATUSES.has(status)).reduce((sum, [, count]) => sum + count, 0);
  const verifiedCount = (counts.verified || 0) + (counts.consistent || 0);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    return analyses.filter((analysis) => {
      const status = mineralStatus(analysis);
      if (queue === "attention" && !ATTENTION_STATUSES.has(status)) return false;
      if (queue === "resolved" && !["consistent", "verified"].includes(status)) return false;
      if (queue.startsWith("status:") && status !== queue.slice(7)) return false;
      return !needle || JSON.stringify(analysis).toLocaleLowerCase("ru").includes(needle);
    });
  }, [analyses, query, queue]);
  const focused = analyses.find((item) => item.analysis_id === focusedId && filtered.includes(item)) || filtered[0] || null;

  if (project.total === 0) {
    return <div className="minerals-empty"><Flask size={48} weight="duotone" /><h2>Сначала добавь анализы</h2><p>Проверка минералов использует импортированные составы и никогда не меняет исходную таблицу.</p><button className="primary-button" type="button" onClick={onAddData}>Добавить данные</button></div>;
  }

  return <div className="minerals-workspace">
    <aside className="mineral-queues">
      <div className="mineral-pane-title"><span>Очереди</span><b>{analyses.length}</b></div>
      <button className={queue === "attention" ? "active" : ""} type="button" onClick={() => setQueue("attention")}><Warning size={17} /><span>Требуют решения</span><b>{attentionCount}</b></button>
      <button className={queue === "all" ? "active" : ""} type="button" onClick={() => setQueue("all")}><Flask size={17} /><span>Все проверки</span><b>{analyses.length}</b></button>
      <button className={queue === "resolved" ? "active" : ""} type="button" onClick={() => setQueue("resolved")}><ShieldCheck size={17} /><span>Согласованы</span><b>{verifiedCount}</b></button>
      <div className="mineral-queue-divider">По статусу</div>
      {Object.entries(counts).sort(([left], [right]) => mineralStatusLabel(left).localeCompare(mineralStatusLabel(right), "ru")).map(([status, count]) => <button className={queue === `status:${status}` ? "active" : ""} type="button" key={status} onClick={() => setQueue(`status:${status}`)}><span>{mineralStatusLabel(status)}</span><b>{count}</b></button>)}
      <div className="mineral-queue-note"><ShieldCheck size={18} /><p>Название из файла, предложение правил и принятое решение хранятся раздельно.</p></div>
    </aside>

    <main className="mineral-list-pane">
      <div className="mineral-toolbar">
        <div className="mineral-search"><MagnifyingGlass size={18} /><input aria-label="Поиск в проверке минералов" placeholder="Analysis, Sample, минерал, источник…" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <span>{filtered.length} из {project.total}</span>
        <button className="outline-button" type="button" onClick={onRefresh} disabled={busy}>Обновить</button>
      </div>
      <div className="mineral-list-head"><span>Анализ</span><span>В источнике</span><span>Предложение</span><span>Статус</span></div>
      <div className="mineral-list" role="listbox" aria-label="Очередь проверки минералов">
        {filtered.map((analysis) => {
          const verification = analysis.mineral_verification || {};
          const isFocused = focused?.analysis_id === analysis.analysis_id;
          return <button type="button" role="option" aria-selected={isFocused} className={isFocused ? "focused" : ""} key={analysis.analysis_id} onClick={() => setFocusedId(analysis.analysis_id)}>
            <span><b>{mainIdentity(analysis)}</b><small>{analysis.identity?.Sample || originLabel(analysis)}</small></span>
            <span>{reportedMineral(analysis) || "—"}</span>
            <span><b>{verification.prediction || "—"}</b><small>{mineralConfidenceLabel(verification.confidence)}</small></span>
            <span className={`mineral-row-status status-${mineralStatus(analysis)}`}>{mineralStatusLabel(mineralStatus(analysis))}</span>
          </button>;
        })}
        {filtered.length === 0 && <div className="mineral-no-results"><CheckCircle size={30} /><b>В этой очереди ничего нет</b><span>Смени очередь или сбрось поиск.</span></div>}
      </div>
      {project.has_more && <button className="minerals-load-more" type="button" onClick={onLoadMore} disabled={busy}>Загрузить ещё анализы</button>}
    </main>

    <ReviewPane analysis={focused} busy={busy} onDecide={onDecide} />
  </div>;
}
