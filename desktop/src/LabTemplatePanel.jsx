import {useState} from "react";
import {makeLabTemplate,templateChanges,readLabTemplates,writeLabTemplates} from "./labImportTemplates";
export function LabTemplatePanel({blocks,activeBlockId,busy,onApply}){
  const [initial]=useState(()=>{try{return {templates:readLabTemplates(globalThis.localStorage),error:""};}catch(e){return {templates:[],error:e.message||String(e)};}});
  const [templates,setTemplates]=useState(initial.templates),[error,setError]=useState(initial.error),[notice,setNotice]=useState("");
  const [name,setName]=useState(""),[selected,setSelected]=useState(""),[chosen,setChosen]=useState([]);
  const active=blocks.find(block=>block.id===activeBlockId)||(!activeBlockId&&blocks.length===1?blocks[0]:null);
  const template=templates.find(item=>item.id===selected);
  const results=template?blocks.map(block=>({block,...templateChanges(template,block)})):[];
  const available=results.filter(item=>item.compatible&&item.changes.length);
  const changes=available.filter(item=>chosen.includes(item.block.id)).flatMap(item=>item.changes);
  const save=()=>{
    try{
      if(initial.error)throw Error("Не удалось прочитать старые шаблоны. Запись отключена, чтобы не потерять их.");
      const next=makeLabTemplate(name,crypto.randomUUID(),active);
      if(templates.some(item=>item.name===next.name))throw Error("Такое название уже используется.");
      const list=[...templates,next];writeLabTemplates(globalThis.localStorage,list);
      setTemplates(list);setSelected(next.id);setChosen([]);setName("");setError("");setNotice("Лабораторный шаблон сохранён на этом компьютере.");
    }catch(e){setError(e.message||String(e));setNotice("");}
  };
  return <details className="mapping-book-bulk">
    <summary>Лабораторные шаблоны импорта</summary>
    <small>Локальные шаблоны содержат заголовки и настройки полей, но не измерения, файлы или идентификаторы анализов. Применение только по явному выбору.</small>
    <label className="mapping-book-unit">Название шаблона<input aria-label="Название лабораторного шаблона" value={name} maxLength={120} disabled={busy} onChange={e=>setName(e.target.value)}/></label>
    <button type="button" className="outline-button" disabled={busy||!name.trim()||!active||Boolean(initial.error)} onClick={save}>Сохранить шаблон текущего блока</button>
    <small>{active?"Текущий блок: "+active.name:"Выберите блок, который станет образцом."} Сохраняются текущие настройки, включая несохранённые правки сопоставления.</small>
    {templates.length>0&&<>
      <label className="mapping-book-unit">Применить шаблон<select aria-label="Лабораторный шаблон" value={selected} disabled={busy} onChange={e=>{setSelected(e.target.value);setChosen([]);setNotice("");}}>
        <option value="">Выбрать…</option>{templates.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      {template&&<>
        <button type="button" className="outline-button" disabled={busy||!available.length} onClick={()=>setChosen(available.map(item=>item.block.id))}>Выбрать все совместимые таблицы</button>
        <div className="mapping-book-list" aria-label="Совместимость лабораторного шаблона">
          {results.map(item=><label key={item.block.id}><input type="checkbox" disabled={busy||!item.compatible||!item.changes.length} checked={chosen.includes(item.block.id)&&item.compatible&&Boolean(item.changes.length)}
            onChange={e=>setChosen(current=>e.target.checked?[...new Set([...current,item.block.id])]:current.filter(id=>id!==item.block.id))}/>
            <span><b>{item.block.name} · заголовок {item.block.header??"—"}</b><small>{item.compatible?item.changes.length+" полей для заполнения":item.reason}</small></span></label>)}
        </div>
        <button className="primary-button" type="button" disabled={busy||!changes.length} onClick={()=>{onApply(changes);setChosen([]);setNotice("Настройки перенесены в черновик. Проверьте и примените сопоставление.");}}>Применить шаблон · {changes.length} полей</button>
        <small>Заполняются только отсутствующие единицы, методы и наборы. Конфликтующие блоки не изменяются.</small>
      </>}
    </>}
    {error&&<small role="alert">{error}</small>}{notice&&<small role="status">{notice}</small>}
  </details>;
}
