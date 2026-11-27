import {useEffect,useState} from "react";
import {compatibleMeasured, measuredCalculation, measuredKey, formulaCalculation, uniqueFormulaRuns} from "./calculatedAxes";
const label=a=>[a.field,a.unit,a.measurement_set,a.method].filter(Boolean).join(" · ");
export function CalculatedAxisEditor({axes,loadCatalog,panel,apply}) {
  const [opened,setOpened]=useState(false),[target,setTarget]=useState(0),[operation,setOperation]=useState("ratio");
  const [keys,setKeys]=useState(["",""]),[groups,setGroups]=useState(null),[groupIndex,setGroupIndex]=useState(""),[field,setField]=useState(""),[runIds,setRunIds]=useState([]),[error,setError]=useState("");
  const eligible=axes.filter(a=>["wt.%","ppm","ppb"].includes(a.unit));
  const first=eligible.find(a=>measuredKey(a)===keys[0]);
  const series=groups?.[Number(groupIndex)];
  const candidates=series?.runs.filter(run=>run.fields.includes(field))||[];
  const fields=[...new Set((series?.runs||[]).flatMap(run=>run.fields))].sort();
  useEffect(()=>{
    if(!opened||operation!=="apfu")return;
    let active=true;setGroups(null);setGroupIndex("");setField("");setRunIds([]);setError("");
    loadCatalog(false,true).then(catalog=>{if(active)setGroups(catalog.formula_series||[]);},err=>{if(active)setError(err.message||String(err));});
    return()=>{active=false;};
  },[opened,operation,loadCatalog]);
  const commit=()=>{
    try{
      const axis=operation==="apfu"?formulaCalculation(series,field,runIds):measuredCalculation(operation,keys.map(key=>eligible.find(a=>measuredKey(a)===key)).filter(Boolean));
      if(target>=panel.axes.length || panel.axes.some((a,i)=>i!==target && measuredKey(a)===measuredKey(axis)))throw Error("Оси должны быть различными.");
      apply(target,axis);setError("");setOpened(false);
    }catch(e){setError(e.message);}
  };
  return <details className="plot-calculated-axis" open={opened} onToggle={event=>setOpened(event.currentTarget.open)}>
    <summary>Расчётная ось</summary>
    {opened&&<>
      <label>Заменить ось<select value={target} onChange={e=>setTarget(Number(e.target.value))}>{panel.axes.map((a,i)=><option key={i} value={i}>{i+1}: {label(a)}</option>)}</select></label>
      <label>Расчёт<select value={operation} onChange={e=>{setOperation(e.target.value);setKeys(["",""]);setError("");}}><option value="ratio">Отношение A / B</option><option value="sum">Сумма компонентов</option><option value="apfu">APFU из сохранённых формул</option></select></label>
      {operation!=="apfu"?<>
        {keys.map((key,index)=><label key={index}>Компонент {index+1}<select value={key} onChange={e=>setKeys(current=>index===0?current.map((_,i)=>i===0?e.target.value:""):current.map((value,i)=>i===index?e.target.value:value))}>
          <option value="">Выбрать измеренное поле</option>
          {eligible.filter(a=>index===0||compatibleMeasured(first,a)&&!keys.some((other,i)=>i!==index&&other===measuredKey(a))).map(a=><option key={measuredKey(a)} value={measuredKey(a)}>{label(a)}</option>)}
        </select></label>)}
        {operation==="sum"&&<div className="plot-style-actions"><button type="button" disabled={keys.length>=16} onClick={()=>setKeys(current=>[...current,""])}>+ Компонент</button><button type="button" disabled={keys.length<=2} onClick={()=>setKeys(current=>current.slice(0,-1))}>− Компонент</button></div>}
        <small>Сумма или отношение массовых концентраций. Не Mg#; молярные отношения требуют отдельного метода.</small>
      </>:<>
        {!groups&&!error&&<small>Загружаю сохранённые расчёты…</small>}
        {groups?.length===0&&<small>Нет сохранённых расчётов формул в этом входном наборе.</small>}
        <label>Метод формулы<select value={groupIndex} onChange={e=>{setGroupIndex(e.target.value);setField("");setRunIds([]);}}><option value="">Выбрать метод</option>{groups?.map((g,i)=><option key={i} value={i}>{g.name} · {g.method_version} · {g.method_definition_fingerprint.slice(0,8)}</option>)}</select></label>
        <label>Компонент APFU<select value={field} disabled={groupIndex===""} onChange={e=>{setField(e.target.value);setRunIds([]);}}><option value="">Выбрать компонент</option>{fields.map(f=><option key={f}>{f}</option>)}</select></label>
        <button type="button" disabled={!field} onClick={()=>setRunIds(uniqueFormulaRuns(series,field))}>Выбрать однозначные расчёты</button>
        <small>Выбрано {runIds.length}. При нескольких версиях для одного анализа выберите одну явно. Устаревшие расчёты исключаются сервисом.</small>
        <div className="plot-formula-run-list">{field&&candidates.map(row=><label key={row.run_id}><input type="checkbox" checked={runIds.includes(row.run_id)}
          onChange={e=>setRunIds(current=>e.target.checked?[...current.filter(id=>!series.runs.some(other=>other.run_id===id&&other.analysis_id===row.analysis_id)),row.run_id]:current.filter(id=>id!==row.run_id))}/>{row.analysis_id.slice(0,8)} · {row.created_at} · {row.run_id.slice(0,8)}</label>)}</div>
      </>}
      {error&&<p role="alert">{error}</p>}
      <button className="outline-button" type="button" disabled={operation==="apfu"?!runIds.length:keys.some(key=>!key)} onClick={commit}>Применить расчётную ось</button>
    </>}
  </details>;
}
