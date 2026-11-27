// Named workspace snapshots are references to validated saved definitions.
export function checkpointState({tableId,plotId,selection,restoreSelection,screen}) {
  if (screen==="plotting" && !plotId) throw new Error("Выберите сохранённую раскладку диаграмм.");
  if (screen==="analyses" && !tableId) throw new Error("Выберите сохранённое представление таблицы.");
  const ids=restoreSelection?[...new Set(selection)]:[];
  return {
    data_universe:{dataset_ids:[],work_group_ids:[],analysis_ids:[]},
    table_view_id:tableId||null,plot_specification_ids:plotId?[plotId]:[],
    source_visibility:[],selection_restore_policy:restoreSelection?"restore_exact_if_available":"clear",
    selection_analysis_ids:ids,active_calculation_run_id:null,active_surface:screen
  };
}
export function tableMemoryFromView(view,project) {
  if(project.has_more)throw new Error("Сначала загрузите все страницы анализов для точного восстановления представления таблицы.");
  const fields=new Set(["source","sheet","origin","mineral","generation","mineral-status"]);
  for(const row of project.analyses)for(const [kind,key] of [["identity","identity"],["metadata","source_metadata"],["measurement","measurements"]])
    for(const field of Object.keys(row[key]||{}))fields.add(kind+":"+field);
  const required=[...view.columns.filter(col=>col.visible).map(col=>col.field),view.sort[0].field,
    ...view.filters.filter(rule=>rule.field.startsWith("column:")).map(rule=>rule.field.slice(7))];
  if(required.some(field=>!fields.has(field)))throw new Error("Часть полей сохранённого представления недоступна.");
  const rules=new Map(view.filters.map(({field,value})=>[field,value]));
  if(rules.has("source")&&!project.analyses.some(row=>row.source_id===rules.get("source")))throw new Error("Источник сохранённого представления недоступен.");
  return {visibleColumnIds:view.columns.filter(col=>col.visible).map(col=>col.field),sort:{id:view.sort[0].field,direction:view.sort[0].direction==="ascending"?"asc":"desc"},
    query:rules.get("query")||"",sourceFilter:rules.get("source")||"all",sheetFilter:rules.get("sheet")||"all",
    mineralStatusFilter:rules.get("mineral-status")||[],statusQuery:"",sampleLinkFilter:rules.get("sample-link")||"all",
    columnFilters:Object.fromEntries(view.filters.filter(rule=>rule.field.startsWith("column:")).map(rule=>[rule.field.slice(7),rule.value])),
    focusedId:"",scrollTop:0,scrollLeft:0};
}
export function plotMemoryFromLayout(layout) {
  const colors=layout.legend.entries.map(({value,color})=>({mode:"source",key:value,color}));
  const category=layout.category_style;
  if(category)for(const entry of category.entries)if(entry.key!==null)colors.push({mode:category.mode,key:entry.key,color:entry.color,...(entry.symbol?{symbol:entry.symbol}:{})});
  return {opened:true,panels:layout.panels.map(({id,kind,axes,normalization,point_style})=>({
    id,kind,axes:axes.map(({scale,manual_range,...axis})=>axis),
    ...(["ree_pattern","spider"].includes(kind)?{normalization}:{}),...(point_style?{point_style}:{})
  })),layers:layout.layers||[],views:new Map(),scrollTop:0,scrollLeft:0,
    photoView:layout.photo_view||null,
    savedColors:Object.fromEntries(layout.legend.entries.map(({value,color})=>[value,color])),
    colorMode:category?.mode||"source",schemeColors:colors,schemeLoaded:true,schemeRevision:null};
}

