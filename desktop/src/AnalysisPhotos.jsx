import {useEffect,useState} from "react";
import {MediaViewer} from "./MediaWorkspace";
export function AnalysisPhotos({id,load,preview,close}) {
  const [rows,setRows]=useState(null),[target,setTarget]=useState(null),[image,setImage]=useState(null),[error,setError]=useState("");
  useEffect(()=>{
    let active=true;setRows(null);setTarget(null);setImage(null);setError("");
    load(id).then(result=>{if(active){setRows(result);if(result.length===1)setTarget(result[0]);}},
      err=>{if(active)setError(err.message||String(err));});
    return()=>{active=false;};
  },[id]);
  useEffect(()=>{
    if(!target)return;
    let active=true;setImage(null);setError("");
    preview(target.media_asset_id).then(result=>{
      if(!active)return;
      if(!result.annotations.some(a=>a.spatial_annotation_id===target.spatial_annotation_id&&a.analytical_point_id===target.analytical_point_id)){
        setError("Привязка изменилась. Откройте список фотографий повторно.");return;
      }
      setImage(result);
    },err=>{if(active)setError(err.message||String(err));});
    return()=>{active=false;};
  },[target]);
  useEffect(()=>{
    const escape=e=>{if(e.key==="Escape"){e.preventDefault();e.stopImmediatePropagation();close();}};
    window.addEventListener("keydown",escape,true);return()=>window.removeEventListener("keydown",escape,true);
  },[close]);
  const focus=image?.annotations.find(a=>a.spatial_annotation_id===target?.spatial_annotation_id&&a.analytical_point_id===target?.analytical_point_id);
  return <div className="import-result-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)close();}}>
    <section role="dialog" aria-modal="true" aria-label="Фотографии анализа" className="import-result-dialog analysis-photos-dialog">
      <header><div><h2>Фотографии анализа</h2><p>Только сохранённые пространственные связи, без поиска по имени.</p></div>
        <button type="button" aria-label="Закрыть фотографии анализа" onClick={close}>×</button></header>
      {error&&<p role="alert">{error}</p>}
      {!rows&&!error&&<p role="status">Ищу сохранённые привязки…</p>}
      {rows?.length===0&&<p>У анализа нет активной пространственной привязки к фотографии.</p>}
      {rows?.length>0&&<div className="analysis-photo-choices">
        {rows.map(row=><button type="button" className="outline-button" key={row.spatial_annotation_id+":"+row.analytical_point_id}
          aria-pressed={target===row} onClick={()=>setTarget(row)}>{row.display_name} · {row.point_name} · {row.link_type}{row.cross_sample_exception?" · другой образец":""}</button>)}
      </div>}
      {target&&!image&&!error&&<p role="status">Загружаю оригинальные координаты…</p>}
      {image&&focus&&<>
        <p>{target.sample_name} · {target.point_name} · x {focus.x_px}, y {focus.y_px} px</p>
        {target.link_type!=="same_point"&&<small>Связь «{target.link_type}» не означает, что измерение выполнено точно в этой точке.</small>}
        {target.cross_sample_exception===1&&<p>Подтверждённое исключение: {target.exception_reason}</p>}
        <MediaViewer key={target.media_asset_id+":"+target.spatial_annotation_id} image={image} focus={focus}
          loadRegion={region=>preview(target.media_asset_id,region)}
          annotations={image.annotations.map(a=>({...a,id:a.spatial_annotation_id,kind:a.geometry_kind,label:a.point_name||a.label,
            highlighted:a.spatial_annotation_id===focus.spatial_annotation_id}))}/>
      </>}
    </section>
  </div>;
}
