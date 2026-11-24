import { useEffect, useState } from "react";

const LINK_TYPES = {
  same_point: "Одна аналитическая точка",
  same_grain: "Одно зерно",
  same_zone: "Одна зона",
  repeat_measurement: "Повторное измерение",
};

export function PointLinks({ sample, loadPoint, createPoint, changeLink, undoLink, reloadSample, selectedIds, addToSelection,
  openAnalysis, markedIds, onClearMarked, busy }) {
  const [pointId, setPointId] = useState("");
  const [rows, setRows] = useState(null);
  const [name, setName] = useState("");
  const [targetPointId, setTargetPointId] = useState("");
  const [linkType, setLinkType] = useState("same_point");
  const [actor, setActor] = useState("Локальный пользователь");
  const [status, setStatus] = useState(null);
  const [pending, setPending] = useState(false);
  const [undo, setUndo] = useState(null);
  const point = sample.points.find(({ analytical_point_id }) => analytical_point_id === pointId);
  const locked = pending || busy;
  const inputs = markedIds ?? selectedIds;
  const attachToExisting = Boolean(markedIds && targetPointId);
  const target = attachToExisting && sample.points.find(({ analytical_point_id }) => analytical_point_id === targetPointId);
  const canLink = !locked && Boolean(actor.trim())
    && (attachToExisting ? Boolean(target) : inputs.length >= 2 && Boolean(name.trim()));
  useEffect(() => {
    if (!pointId) return;
    let active = true;
    loadPoint(pointId).then((items) => { if (active) setRows(items); })
      .catch((error) => { if (active) setStatus({ error: error.message }); });
    return () => { active = false; };
  }, [loadPoint, pointId]);
  const link = async (event) => {
    event.preventDefault();
    if (!canLink) return;
    setPending(true);
    setStatus(null);
    try {
      let notice;
      if (target) {
        const entry = await changeLink(targetPointId, inputs, linkType, actor);
        setUndo({ pointId: targetPointId, operationId: entry.id, added: true });
        if (pointId !== targetPointId) {
          setRows(null);
          setPointId(targetPointId);
        }
        notice = `К точке «${target.point_name}» привязано анализов: ${inputs.length}.`;
      } else {
        const item = await createPoint({ sample_id: sample.sample_id, point_name: name, analysis_ids: inputs, link_type: linkType, actor });
        setRows(null);
        setPointId(item.analytical_point_id);
        notice = `Создана точка «${item.point_name}».`;
      }
      setName("");
      setTargetPointId("");
      if (markedIds) onClearMarked();
      setStatus({ notice });
      if (target && pointId === targetPointId) setRows(await loadPoint(targetPointId));
      await reloadSample();
    } catch (error) {
      setStatus({ error: error.message });
    } finally {
      setPending(false);
    }
  };
  const change = async (analysisId) => {
    setPending(true);
    setStatus(null);
    try {
      const entry = await changeLink(pointId, analysisId, null, actor);
      setUndo({ pointId, operationId: entry.id });
      setRows(await loadPoint(pointId));
      await reloadSample();
      setStatus({ notice: "Связь снята." });
    } catch (error) {
      setStatus({ error: error.message });
    } finally {
      setPending(false);
    }
  };
  const restoreLink = async () => {
    setPending(true);
    setStatus(null);
    try {
      await undoLink(undo.operationId, actor);
      setUndo(null);
      setRows(await loadPoint(pointId));
      await reloadSample();
      setStatus({ notice: undo.added ? "Пакетная привязка отменена." : "Связь восстановлена." });
    } catch (error) {
      setStatus({ error: error.message });
    } finally {
      setPending(false);
    }
  };

  return <>
    {status && <p role={status.error ? "alert" : "status"}>{status.error || status.notice}</p>}
    <div className="point-workspace-grid">
      <div>
        <section className="sample-card">
          <h3>Аналитические точки</h3>
          {sample.points.length ? <ul className="sample-items">{sample.points.map((item) =>
            <li key={item.analytical_point_id}>
              <button className="outline-button" type="button" disabled={locked} aria-pressed={item.analytical_point_id === pointId}
                onClick={() => { if (item.analytical_point_id !== pointId) { setRows(null); setPointId(item.analytical_point_id); setStatus(null); } }}>
                {item.point_name}
              </button><span>Анализов · {item.analysis_count}</span>
            </li>)}</ul> : <p>У образца ещё нет аналитических точек.</p>}
        </section>
        <section className="sample-card">
          <h3>{markedIds ? "Привязать отмеченные анализы" : "Связать выбранные анализы"}</h3>
          {markedIds ? <p>Отмечено в поиске: {markedIds.length}. Для новой точки нужны минимум два анализа.</p>
            : <p>В отборе: {selectedIds.length}. Для новой точки выберите в таблице минимум два анализа этого образца.</p>}
          <form className="sample-form" onSubmit={link}>
            {markedIds && <label>Куда привязать
              <select value={targetPointId} disabled={locked} onChange={(event) => setTargetPointId(event.target.value)}>
                <option value="">Новая аналитическая точка</option>
                {sample.points.map((item) => <option key={item.analytical_point_id} value={item.analytical_point_id}>{item.point_name}</option>)}
              </select>
            </label>}
            {!attachToExisting && <label>Название точки<input value={name} maxLength={200} disabled={locked} onChange={(event) => setName(event.target.value)} /></label>}
            <label>Тип связи<select value={linkType} disabled={locked} onChange={(event) => setLinkType(event.target.value)}>
              {Object.entries(LINK_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Автор изменения<input value={actor} maxLength={120} disabled={locked} onChange={(event) => setActor(event.target.value)} /></label>
            <div>
              <button className="primary-button" disabled={!canLink}>Связать анализы</button>
              {markedIds && <button type="button" className="outline-button" disabled={locked}
                onClick={() => { setTargetPointId(""); setName(""); setStatus(null); onClearMarked(); }}>Отмена</button>}
            </div>
          </form>
        </section>
      </div>
      <section className="sample-card">
        <h3>{point ? `Анализы точки ${point.point_name}` : "Анализы точки"}</h3>
        {!point && <p>Выберите аналитическую точку.</p>}
        {point && !rows && !status?.error && <p role="status">Загружаю анализы точки…</p>}
        {point && rows?.length === 0 && <p>У этой точки нет связанных анализов.</p>}
        {undo?.pointId === pointId && <button className="outline-button" type="button" disabled={locked || !actor.trim()}
          onClick={restoreLink}>{undo.added ? "Отменить пакетную привязку" : "Восстановить снятую связь"}</button>}
        {point && rows && <ul className="sample-items point-analysis-items">{rows.map((row) => <li key={row.analysis_id}>
          <div>
            <b>{row.identity || row.analysis_id}</b>
            <p>{row.source_name} · {row.sheet_name} · {row.source_column_number ? `колонка ${row.source_column_number}` : `строка ${row.source_row_number}`}</p>
            <small>{row.method ? `${row.method} · ` : ""}{LINK_TYPES[row.link_type]}{!row.active && " · импорт отозван"}</small>
          </div>
          <div className="point-row-actions">
            <button className="outline-button" type="button" disabled={locked || !row.active} onClick={() => openAnalysis(row.analysis_id)}>Открыть анализ</button>
            <button className="outline-button" type="button" disabled={locked || !row.active || selectedIds.includes(row.analysis_id)}
              onClick={() => addToSelection(row.analysis_id)}>Добавить в отбор</button>
            <button className="outline-button" type="button" disabled={locked || !actor.trim()}
              onClick={() => change(row.analysis_id)}>Снять связь</button>
          </div>
        </li>)}</ul>}
      </section>
    </div>
  </>;
}
