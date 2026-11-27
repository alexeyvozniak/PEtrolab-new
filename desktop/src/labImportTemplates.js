const UNITS=new Set(["wt.%","at.%","ppm","ppb","apfu","mol%","ratio","epsilon","permil"]);
export const STORAGE_KEY="petrolab.lab-import-templates.v1";
const txt=(value,max)=>typeof value==="string"&&value.length<=max;
const rowKey=row=>JSON.stringify([row.axis,row.index]);
const signature=block=>JSON.stringify([block.orientation,block.rows.map(({axis,index,header,target,field})=>[axis,index,header,target,field])]);
function validate(template){
  if(!template||template.version!==1||!txt(template.id,128)||!template.id||!txt(template.name,120)||!template.name.trim()||
     !txt(template.orientation,80)||!Array.isArray(template.rows)||!template.rows.length||template.rows.length>500)throw Error("Некорректный лабораторный шаблон.");
  const keys=new Set();
  for(const row of template.rows){
    if(!row||!["column","row"].includes(row.axis)||!Number.isInteger(row.index)||row.index<0||
       !(row.header===null||txt(row.header,512))||!txt(row.target,80)||!txt(row.field,512)||keys.has(rowKey(row)))throw Error("Некорректная структура шаблона.");
    keys.add(rowKey(row));
    if(row.target==="Measurement"&&(!row.field.trim()||!UNITS.has(row.unit)||!txt(row.method,120)||!txt(row.measurementSet,120)))throw Error("Сначала подтвердите единицы всех измерений блока.");
  }
  if(!template.rows.some(row=>row.target==="Measurement"))throw Error("В шаблоне нет измерений.");
  return template;
}
export function makeLabTemplate(name,id,block){
  return validate({version:1,id,name:name.trim(),orientation:block.orientation,
    rows:block.rows.map(({axis,index,header,target,field,unit,method,measurementSet})=>({axis,index,header,target,field,
      ...(target==="Measurement"?{unit,method:method.trim(),measurementSet:measurementSet.trim()}:{} )}))});
}
export function templateChanges(template,block){
  validate(template);
  if(signature(template)!==signature(block))return {compatible:false,reason:"Отличаются заголовки, позиции или сопоставления.",changes:[]};
  const changes=[];
  for(let i=0;i<template.rows.length;i++){
    const saved=template.rows[i],row=block.rows[i];
    if(saved.target!=="Measurement")continue;
    const patch={};
    for(const key of ["unit","method","measurementSet"]){
      if(saved[key]&&row[key]&&saved[key]!==row[key])return {compatible:false,reason:"Конфликт: "+row.field+" · "+key,changes:[]};
      if(saved[key]&&!row[key])patch[key]=saved[key];
    }
    if(Object.keys(patch).length)changes.push({key:row.key,patch});
  }
  return {compatible:true,changes};
}
export function readLabTemplates(storage){
  const raw=storage.getItem(STORAGE_KEY);
  if(!raw)return [];
  if(raw.length>4000000)throw Error("Слишком большой список шаблонов.");
  const parsed=JSON.parse(raw);
  if(!Array.isArray(parsed)||parsed.length>24)throw Error("Некорректный список шаблонов.");
  return parsed.map(validate);
}
export function writeLabTemplates(storage,templates){
  if(templates.length>24)throw Error("Можно сохранить до 24 шаблонов.");
  const value=JSON.stringify(templates.map(validate));
  if(value.length>4000000)throw Error("Слишком большой список шаблонов.");
  storage.setItem(STORAGE_KEY,value);
}
