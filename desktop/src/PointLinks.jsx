import { useEffect, useState } from "react";

const LINK_TYPES = {
  same_point: "Одна аналитическая точка",
  same_grain: "Одно зерно",
  same_zone: "Одна зона",
  repeat_measurement: "Повторное измерение",
};

export function PointLinks({ sample, loadPoint, createPoint, changeLink, reloadSample, selectedIds, addToSelection, openAnalysis, busy }) {
  const [pointId, setPointId] = useState("");
  const [rows, setRows] = useState(null);
  const [name, setName] = useState("");
  const [linkType, setLinkType] = useState("same_point");
  const [actor, setActor] = useState("Локальный пользователь");
  const [status, setStatus] = useState(null);
  const [pending, setPending] = useState(false);
  const [undo, setUndo] = useState(null);
  const point = sample.points.find(({ analytical_point_id }) => analytical_point_id === pointId);
  const locked = pending || busy;
  useEffect(() => {
    if (!pointId) return;
    let active = true;
    loadPoint(pointId).then((items) => { if (active) setRows(items); })
      .catch((error) => { if (active) setStatus({ error: error.message }); });
    return () => { active = false; };
  }, [loadPoint, pointId]);
  const create = async (event) => {
    event.preventDefault();
    setPending(true);
    setStatus(null);
    try {
      const item = await createPoint({ sample_id: sample.sample_id, point_name: name, analysis_ids: selectedIds, link_type: linkType, actor });
      setRows(null);
      setPointId(item.analytical_point_id);
      setName("");
      await reloadSample();
      setStatus({ notice: `Создана точка «${item.point_name}».` });
    } catch (error) {
      setStatus({ error: error.message });
    } finally {
      setPending(false);
    }
  };
  const change = async (analysisId, type) => {
    setPending(true);
    setStatus(null);
    try {
      const entry = await changeLink(pointId, analysisId, type, actor);
      setUndo(type ? null : { pointId, analysisId, type: entry.parameters.link_type });
      setRows(await loadPoint(pointId));
      await reloadSample();
      setStatus({ notice: type ? "Связь восстановлена." : "Связь снята." });
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
          <h3>Связать выбранные анализы</h3>
          <p>В отборе: {selectedIds.length}. Для новой точки выберите в таблице минимум два анализа этого образца.</p>
          <form className="sample-form" onSubmit={create}>
            <label>Название точки<input value={name} maxLength={200} disabled={locked} onChange={(event) => setName(event.target.value)} /></label>
            <label>Тип связи<select value={linkType} disabled={locked} onChange={(event) => setLinkType(event.target.value)}>
              {Object.entries(LINK_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Автор изменения<input value={actor} maxLength={120} disabled={locked} onChange={(event) => setActor(event.target.value)} /></label>
            <div><button className="primary-button" disabled={locked || selectedIds.length < 2 || !name.trim() || !actor.trim()}>Связать анализы</button></div>
          </form>
        </section>
      </div>
      <section className="sample-card">
        <h3>{point ? `Анализы точки ${point.point_name}` : "Анализы точки"}</h3>
        {!point && <p>Выберите аналитическую точку.</p>}
        {point && !rows && !status?.error && <p role="status">Загружаю анализы точки…</p>}
        {point && rows?.length === 0 && <p>У этой точки нет связанных анализов.</p>}
        {undo?.pointId === pointId && <button className="outline-button" type="button" disabled={locked || !actor.trim()}
          onClick={() => change(undo.analysisId, undo.type)}>Восстановить снятую связь</button>}
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
              onClick={() => change(row.analysis_id, null)}>Снять связь</button>
          </div>
        </li>)}</ul>}
      </section>
    </div>
  </>;
}
