import { useEffect, useState, useRef } from "react";
const number = value => value == null ? "—" : Number(value).toLocaleString("ru",{maximumSignificantDigits:7,useGrouping:false});
export function SelectionSummary({ids,load,close}) {
  const loader=useRef(load);
  const [result,setResult]=useState(null),[error,setError]=useState("");
  const [query,setQuery]=useState("");
  const [comparison,setComparison]=useState(ids.length===2);
  useEffect(()=>{
    let active=true;
    loader.current(ids).then(value=>{if(active)setResult(value);},error=>{if(active)setError(error.message||String(error));});
    return ()=>{active=false;};
  },[ids]);
  useEffect(()=>{
    const key=event=>{if(event.key==="Escape"){event.preventDefault();event.stopImmediatePropagation();close();}};
    window.addEventListener("keydown",key,true);
    return ()=>window.removeEventListener("keydown",key,true);
  },[close]);
  const rows=(result?.rows||[]).filter(row=>[row.field,row.unit,row.method,row.measurement_set,row.reported_fe_form].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const raw = item => item.status==="missing" ? "—" : item.raw_tokens.map(token=>token==null || token===""?"∅":token).join(" / ") + (item.status==="duplicate"?" · неоднозначно":item.status==="excluded"?" · исключено":"");
  return <div className="import-result-overlay" onMouseDown={event=>{if(event.target===event.currentTarget)close();}}>
    <section className="import-result-dialog selection-summary-dialog" role="dialog" aria-modal="true" aria-label="Статистика и сравнение анализов">
      <header><div><h2>{comparison?"Сравнение двух анализов":"Статистика отбора"}</h2><p>Анализов в зафиксированном отборе: {ids.length}</p></div>
        <button type="button" aria-label="Закрыть статистику" onClick={close}>×</button></header>
      <div className="import-result-tools">
        <input autoFocus aria-label="Поиск поля статистики" placeholder="Поле, единица, метод…" value={query} onChange={event=>setQuery(event.target.value)}/>
        {ids.length===2 && <button type="button" className="outline-button" onClick={()=>setComparison(value=>!value)}>{comparison?"Показать статистику":"Сравнить составы"}</button>}
      </div>
      <p className="selection-summary-note">Только однозначные числовые измерения. Раздельно по полю, единице, методу, набору и сообщённой форме Fe. Без нормализации и подстановки значений ниже предела. SD — выборочное стандартное отклонение (n−1).</p>
      {error?<p role="alert">{error}</p>:!result?<p role="status">Читаю измерения из проекта…</p>:<>
        {comparison && result.pair && <p className="selection-summary-note">A: {result.pair[0].label} · {result.pair[0].source_name} → B: {result.pair[1].label} · {result.pair[1].source_name}. Δ = B−A, относительное изменение = Δ/A × 100%; при A=0 не определяется.</p>}
        <div className="import-result-table-wrap"><table className="import-result-table" aria-label={comparison?"Сравнение составов":"Статистика полей"}>
          <thead><tr><th>Поле</th><th>Единица / метод / набор / Fe</th>{comparison?<><th>A</th><th>B</th><th>Δ</th><th>Δ, %</th></>:<><th>n</th><th>Среднее</th><th>Медиана</th><th>Min</th><th>Max</th><th>SD</th><th>Нет</th><th>Нечисловые</th><th>Дубли</th></>}</tr></thead>
          <tbody>{rows.map((row,index)=><tr key={index}><th>{row.field}</th><td>{[row.unit,row.method,row.measurement_set,row.reported_fe_form].filter(Boolean).join(" · ")||"—"}</td>{comparison?<><td>{raw(row.pair[0])}</td><td>{raw(row.pair[1])}</td><td>{number(row.delta)}</td><td>{number(row.relative_percent)}</td></>:<><td>{row.n}</td><td>{number(row.mean)}</td><td>{number(row.median)}</td><td>{number(row.minimum)}</td><td>{number(row.maximum)}</td><td>{number(row.sd)}</td><td>{row.missing}</td><td>{row.excluded}</td><td>{row.duplicate}</td></>}</tr>)}</tbody>
        </table>{!rows.length&&<p>Нет измерений для отображения.</p>}</div>
      </>}
    </section>
  </div>;
}
