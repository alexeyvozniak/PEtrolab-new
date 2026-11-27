import {useState} from "react";
export function ImportBatchContext({blocks,activeBlockId,busy,onApply}){
  const [chosen,setChosen]=useState([]),[unit,setUnit]=useState(""),[method,setMethod]=useState(""),[measurementSet,setMeasurementSet]=useState("");
  const units=[...new Set(blocks.flatMap(block=>block.fields.map(field=>field.unit)))].sort();
  const scoped=blocks.filter(block=>chosen.includes(block.id)).flatMap(block=>block.fields.filter(field=>!unit||field.unit===unit));
  const eligible=scoped.filter(field=>(method.trim()&&!field.method.trim())||(measurementSet.trim()&&!field.measurementSet.trim()));
  const chooseSimilar=()=>{
    const active=blocks.find(block=>block.id===activeBlockId);
    if(active)setChosen(blocks.filter(block=>block.signature===active.signature).map(block=>block.id));
  };
  if(!blocks.length)return null;
  return <details className="mapping-book-bulk">
    <summary>Метод и аналитический набор для нескольких таблиц</summary>
    <small>Заполняются только пустые настройки измерений с подтверждённой единицей. Уже заданные значения сохраняются.</small>
    <div className="mapping-book-buttons">
      <button type="button" className="outline-button" disabled={busy||!blocks.some(block=>block.id===activeBlockId)} onClick={chooseSimilar}>Выбрать такие же таблицы</button>
      <button type="button" className="outline-button" disabled={busy} onClick={()=>setChosen(blocks.map(block=>block.id))}>Выбрать все таблицы</button>
      <button type="button" className="outline-button" disabled={busy||!chosen.length} onClick={()=>setChosen([])}>Снять выбор таблиц</button>
    </div>
    <div className="mapping-book-list" aria-label="Таблицы для метода и набора">
      {blocks.map(block=><label key={block.id}><input type="checkbox" disabled={busy} checked={chosen.includes(block.id)}
        onChange={event=>setChosen(current=>event.target.checked?[...new Set([...current,block.id])]:current.filter(id=>id!==block.id))}/>
        <span><b>{block.name} · заголовок {block.header ?? "—"}</b><small>{block.fields.length} полей · {[...new Set(block.fields.map(field=>field.unit))].join(", ")}</small></span></label>)}
    </div>
    <label className="mapping-book-unit">Ограничить по единице<select aria-label="Единица для метода и набора" value={unit} disabled={busy} onChange={event=>setUnit(event.target.value)}>
      <option value="">Все подтверждённые единицы</option>{units.map(value=><option key={value}>{value}</option>)}
    </select></label>
    <label className="mapping-book-unit">Метод<input aria-label="Общий метод измерений" value={method} maxLength={120} disabled={busy} onChange={event=>setMethod(event.target.value)} placeholder="EPMA / LA-ICP-MS"/></label>
    <label className="mapping-book-unit">Аналитический набор<input aria-label="Общий аналитический набор" value={measurementSet} maxLength={120} disabled={busy} onChange={event=>setMeasurementSet(event.target.value)} placeholder="major / trace"/></label>
    <small>Проверьте, что выбранные поля действительно измерены одним методом. Не назначайте метод только по сходству заголовков.</small>
    <button type="button" className="primary-button" disabled={busy||!eligible.length} onClick={()=>onApply(eligible.map(field=>field.key),{method:method.trim(),measurementSet:measurementSet.trim()})}>Заполнить метод и набор · {eligible.length} полей</button>
  </details>;
}
