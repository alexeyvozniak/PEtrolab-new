// Local presentation preferences, never a scientific workspace snapshot.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SCREENS = new Set(["Обзор","Анализы","Образцы"]);
const TABS = new Set(["Обзор","Полевые данные","Источники","Точки","Шлифы","Изображения","Заметки"]);
const column = value => typeof value==="string" && value.length>0 && value.length<=300;
const bounded = (value,min,max) => typeof value==="number" && Number.isFinite(value) ? Math.max(min,Math.min(max,Math.round(value))) : min;
export const sessionKey = projectId => typeof projectId==="string" && UUID.test(projectId) ? "petrolab.presentation.v1."+projectId : "";
export function sanitizeSession(value) {
  const table=value?.table || {}, samples=value?.samples || {}, plot=value?.plot || {};
  return {version:1, screen:SCREENS.has(value?.screen)?value.screen:"Обзор",
    table:{
      visibleColumnIds:Array.isArray(table.visibleColumnIds)?[...new Set(table.visibleColumnIds.filter(column))].slice(0,500):[],
      columnWidths:Object.fromEntries(Object.entries(table.columnWidths || {}).filter(([key,width])=>column(key)&&typeof width==="number"&&Number.isFinite(width)).slice(0,500).map(([key,width])=>[key,bounded(width,104,600)])),
      pinnedColumnId:column(table.pinnedColumnId)?table.pinnedColumnId:"",
      scrollLeft:bounded(table.scrollLeft,0,300000),
    },
    samples:{tab:TABS.has(samples.tab)?samples.tab:"Обзор"},
    plot:{mode:["replace","union","subtract"].includes(plot.mode)?plot.mode:"union",
      shape:["rectangle","lasso"].includes(plot.shape)?plot.shape:"rectangle",
      selectionExpanded:plot.selectionExpanded===true}
  };
}
export function readSession(storage,key) {
  if(!key)return null;
  try {const raw=storage.getItem(key);if(!raw||raw.length>200000)return null;
    const parsed=JSON.parse(raw);return parsed?.version===1?sanitizeSession(parsed):null;
  } catch {return null;}
}
export function writeSession(storage,key,state) {
  if(!key)return false;
  try {const encoded=JSON.stringify(sanitizeSession(state));
    if(storage.getItem(key)!==encoded)storage.setItem(key,encoded);
    return true;
  } catch {return false;}
}
export function memoryFromSession(saved) {
  return {table:{...saved?.table},samples:{...saved?.samples},plot:{...saved?.plot,views:new Map()}};
}
