import {useEffect,useState} from "react";
import {checkpointState} from "./workspaceCheckpoint";
export function WorkspaceCheckpoints({load,save,restore,selection,close}) {
  const [catalog,setCatalog]=useState(null),[name,setName]=useState(""),[tableId,setTableId]=useState(""),[plotId,setPlotId]=useState("");
  const [surface,setSurface]=useState("overview"),[includeSelection,setIncludeSelection]=useState(true);
  const [pending,setPending]=useState(false),[notice,setNotice]=useState(""),[error,setError]=useState("");
  useEffect(()=>{let active=true;load().then(value=>{if(active)setCatalog(value);},caught=>{if(active)setError(caught.message);});return()=>{active=false;};},[]);
  useEffect(()=>{
    const dismiss=event=>{if(event.key==="Escape"&&!pending){event.preventDefault();event.stopImmediatePropagation();close();}};
    window.addEventListener("keydown",dismiss,true);
    return()=>window.removeEventListener("keydown",dismiss,true);
  },[pending,close]);
  const submit=async event=>{
    event.preventDefault();setPending(true);setError("");setNotice("");
    try{
      const state=checkpointState({tableId,plotId,selection,restoreSelection:includeSelection,screen:surface});
      const saved=await save(name.trim(),state);
      setCatalog(current=>({...current,snapshots:[...current.snapshots,{id:saved.id,name:saved.name}]}));
      setName("");setNotice("Рабочее состояние сохранено в проекте.");
    }catch(caught){setError(caught.message);}finally{setPending(false);}
  };
  const open=async id=>{
    setPending(true);setError("");setNotice("");
    try{await restore(id);close();}catch(caught){setError(caught.message);setPending(false);}
  };
  return <div className="import-result-overlay" onMouseDown={event=>{if(!pending&&event.target===event.currentTarget)close();}}>
    <section className="import-result-dialog workspace-checkpoints" role="dialog" aria-modal="true" aria-label="Рабочие состояния проекта">
      <header><div><h2>Рабочие состояния проекта</h2><p>Точные ссылки на сохранённые представления, раскладки и отбор.</p></div>
        <button type="button" aria-label="Закрыть рабочие состояния" disabled={pending} onClick={close}>×</button></header>
      {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
      {!catalog&&!error&&<p role="status">Загружаю сохранённые состояния…</p>}
      {catalog&&<>
        <div className="checkpoint-list"><b>Открыть рабочее состояние</b>
          {!catalog.snapshots.length&&<small>Пока нет сохранённых состояний.</small>}
          {catalog.snapshots.map(item=><button key={item.id} type="button" className="outline-button" disabled={pending} onClick={()=>open(item.id)}>Открыть «{item.name}»</button>)}</div>
        <form className="checkpoint-form" onSubmit={submit}>
          <b>Сохранить новое состояние</b>
          <label>Название состояния<input value={name} maxLength={160} onChange={e=>setName(e.target.value)} required disabled={pending}/></label>
          <label>Представление таблицы<select value={tableId} onChange={e=>setTableId(e.target.value)} disabled={pending}>
            <option value="">Не включать</option>{catalog.tables.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Раскладка диаграмм<select value={plotId} onChange={e=>setPlotId(e.target.value)} disabled={pending}>
            <option value="">Не включать</option>{catalog.plots.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Открывать раздел<select value={surface} onChange={e=>setSurface(e.target.value)} disabled={pending}>
            <option value="overview">Обзор</option><option value="analyses" disabled={!tableId}>Анализы</option><option value="plotting" disabled={!plotId}>Построение</option></select></label>
          <label><input type="checkbox" checked={includeSelection} disabled={pending} onChange={e=>setIncludeSelection(e.target.checked)}/> Сохранить текущий отбор · {selection.length}</label>
          <small>Сначала сохраните нужную раскладку или представление в соответствующем разделе. Текущее несохранённое оформление не включается. При недоступных данных восстановление будет остановлено.</small>
          <button type="submit" className="outline-button" disabled={pending||!name.trim()||(surface==="plotting"&&!plotId)||(surface==="analyses"&&!tableId)}>Сохранить рабочее состояние</button>
        </form>
      </>}
    </section>
  </div>;
}
