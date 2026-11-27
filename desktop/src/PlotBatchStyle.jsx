import {useState} from "react";
import {SYMBOL_LABELS} from "./plotSymbols";
export function PlotBatchStyle({mode,entries,disabled,onApply}){
  const [chosen,setChosen]=useState([]),[color,setColor]=useState("#356ca2"),[symbol,setSymbol]=useState("circle");
  const [useColor,setUseColor]=useState(true),[useSymbol,setUseSymbol]=useState(false),[notice,setNotice]=useState(null);
  const available=entries.filter(entry=>typeof entry.key==="string");
  const active=new Set(available.map(entry=>entry.key));
  const selection=chosen.filter(key=>active.has(key));
  const allowSymbol=mode!=="source";
  if(!available.length)return null;
  const apply=()=>{
    try{
      onApply(selection,{...(useColor?{color}:{}),...(allowSymbol&&useSymbol?{symbol}:{})});
      setNotice({text:"Оформлено категорий: "+selection.length+". Сохраните цветовую схему, чтобы использовать после перезапуска."});
    }catch(error){setNotice({error:true,text:error.message||String(error)});}
  };
  return <details className="plot-batch-style">
    <summary>Пакетное оформление</summary>
    <div className="plot-style-actions">
      <button type="button" className="outline-button" disabled={disabled} onClick={()=>{setChosen([...active]);setNotice(null);}}>Выбрать все категории</button>
      <button type="button" className="outline-button" disabled={disabled||!selection.length} onClick={()=>{setChosen([]);setNotice(null);}}>Снять выбор категорий</button>
    </div>
    <small>Выбрано {selection.length} из {available.length}. Это выбор оформления, не отбор анализов.</small>
    <div className="plot-batch-list" aria-label="Категории для оформления">
      {available.map(entry=><label key={entry.key}><input type="checkbox" disabled={disabled} checked={selection.includes(entry.key)}
        aria-label={"Оформить: "+entry.label} onChange={e=>{setChosen(current=>e.target.checked?[...new Set([...current,entry.key])]:current.filter(key=>key!==entry.key));setNotice(null);}}/>
        <i style={{background:entry.color}} aria-hidden="true"/><span>{entry.label}</span></label>)}
    </div>
    <label><input type="checkbox" checked={useColor} disabled={disabled} onChange={e=>{setUseColor(e.target.checked);setNotice(null);}}/> Изменить цвет</label>
    {useColor&&<input type="color" value={color} aria-label="Общий цвет категорий" disabled={disabled} onChange={e=>{setColor(e.target.value);setNotice(null);}}/>}
    {allowSymbol&&<><label><input type="checkbox" checked={useSymbol} disabled={disabled} onChange={e=>{setUseSymbol(e.target.checked);setNotice(null);}}/> Изменить символ</label>
      {useSymbol&&<select value={symbol} aria-label="Общий символ категорий" disabled={disabled} onChange={e=>{setSymbol(e.target.value);setNotice(null);}}>
        {Object.entries(SYMBOL_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}
      </select>}</>}
    <button type="button" className="outline-button" disabled={disabled||!selection.length||!(useColor||allowSymbol&&useSymbol)} onClick={apply}>Применить оформление к категориям</button>
    {notice&&<small role={notice.error?"alert":"status"}>{notice.text}</small>}
  </details>;
}
