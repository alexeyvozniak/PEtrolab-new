import {useEffect,useState} from "react";
import {MediaViewer} from "./MediaWorkspace";
import {photoLinks,focusLinks} from "./photoPlotLinks";
import "./photoPlot.css";

export function PhotoPlot({inputIds,loadCatalog,loadPhotos,preview,view,setView,panels,focusedIds,setFocusedIds,addToSelection}) {
  const [links,setLinks]=useState(null),[image,setImage]=useState(null),[error,setError]=useState("");
  const key=JSON.stringify(inputIds);
  useEffect(()=>{
    let active=true;setLinks(null);setError("");setImage(null);
    // Bounded concurrency; every lookup uses the exact input Analysis ID.
    (async()=>{const rows=[];let next=0;
      const ids=inputIds??(await loadCatalog(true)).categories.map(row=>row.analysis_id);
      await Promise.all(Array.from({length:Math.min(4,ids.length)},async()=>{
        while(next<ids.length){const id=ids[next++];rows.push(...(await loadPhotos(id)).map(row=>({...row,analysis_id:id})));}
      }));
      if(active)setLinks(rows);
    })().catch(e=>{if(active)setError(e.message||String(e));});
    return()=>{active=false;};
  },[key,loadPhotos,loadCatalog]);
  useEffect(()=>{
    let active=true;setImage(null);
    if(view.media_asset_id)preview(view.media_asset_id).then(result=>{if(active)setImage(result);},
      e=>{if(active)setError(e.message||String(e));});
    return()=>{active=false;};
  },[view.media_asset_id,preview]);
  const photos=[...new Map((links||[]).map(row=>[row.media_asset_id,row])).values()];
  const rows=photoLinks(links||[],view.media_asset_id);
  const focused=focusLinks(rows,focusedIds);
  const ids=[...new Set(focused.map(row=>row.analysis_id))];
  return <section className="photo-plot-photo" aria-label="Фото + диаграммы">
    <h2>Фото + диаграммы</h2>
    <p>Связи только входного набора. Фокус не меняет общий отбор.</p>
    {error&&<p role="alert">{error}</p>}
    {!links&&!error&&<p role="status">Загружаю связи…</p>}
    {links?.length===0&&<p>У входного набора нет связанных фотографий.</p>}
    <label>Фото <select value={view.media_asset_id||""} onChange={e=>{setError("");setFocusedIds([]);setView({...view,media_asset_id:e.target.value||null});}}>
      <option value="">Выберите фото</option>
      {photos.map(row=><option key={row.media_asset_id} value={row.media_asset_id}>{row.display_name} · {row.sample_name}</option>)}
      {view.media_asset_id&&!photos.some(row=>row.media_asset_id===view.media_asset_id)&&<option value={view.media_asset_id}>Сохранённое фото: {view.media_asset_id}</option>}
    </select></label>
    <fieldset><legend>Показать 1–3 графика</legend>{panels.map((panel,index)=><label key={panel.id}>
      <input type="checkbox" checked={view.panel_ids.includes(panel.id)} disabled={view.panel_ids.includes(panel.id)?view.panel_ids.length===1:view.panel_ids.length>=3}
        onChange={e=>setView({...view,panel_ids:e.target.checked?[...view.panel_ids,panel.id]:view.panel_ids.filter(id=>id!==panel.id)})}/>
      {index+1}. {panel.axes.map(axis=>axis.field).join(" / ")}
    </label>)}</fieldset>
    {view.media_asset_id&&!image&&!error&&<p role="status">Загружаю фото…</p>}
    {image&&<MediaViewer key={view.media_asset_id} image={image} loadRegion={region=>preview(view.media_asset_id,region)}
      annotations={image.annotations.map(a=>({...a,id:a.spatial_annotation_id,kind:a.geometry_kind,label:a.point_name||a.label,
        highlighted:focused.some(row=>row.spatial_annotation_id===a.spatial_annotation_id)}))}
      onFocusAnnotation={a=>setFocusedIds([...new Set(rows.filter(row=>row.spatial_annotation_id===a.id).map(row=>row.analysis_id))])}/>}
    <h3>Связи фокуса · {ids.length}</h3>
    {focusedIds.length>0&&!focused.length&&<p>Для этих Analysis ID на выбранном фото нет связи во входном наборе.</p>}
    {focused.map((row,index)=><article key={index}>
      <b>Analysis ID: {row.analysis_id}</b>
      <p>{row.sample_name} · {row.point_name} · {row.link_type}</p>
      <small>Point: {row.analytical_point_id}<br/>Annotation: {row.spatial_annotation_id}</small>
      <p>x {row.x_px}, y {row.y_px}; {row.width_px??0} × {row.height_px??0} px оригинала</p>
      {row.link_type!=="same_point"&&<p>Эта связь не подтверждает точное место измерения.</p>}
      {row.cross_sample_exception===1&&<p>Другой образец: {row.exception_reason}</p>}
    </article>)}
    <button type="button" className="primary-button" disabled={!ids.length} onClick={()=>addToSelection(ids)}>Добавить в отбор · {ids.length}</button>
  </section>;
}


