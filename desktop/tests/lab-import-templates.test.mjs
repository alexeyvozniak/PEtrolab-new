import test from "node:test";
import assert from "node:assert/strict";
import {makeLabTemplate,templateChanges,readLabTemplates,writeLabTemplates,STORAGE_KEY} from "../src/labImportTemplates.js";
const block=(unit="",method="",measurementSet="")=>({orientation:"rows_are_analyses",rows:[
 {key:"new:a",axis:"column",index:0,header:"Analysis",target:"Analysis",field:"Analysis"},
 {key:"new:b",axis:"column",index:1,header:"MgO",target:"Measurement",field:"MgO",unit,method,measurementSet,raw_token:"secret"}]});
test("portable lab template contains no source IDs, keys or values",()=>{
 const saved=makeLabTemplate("Lab A","t",block("wt.%","EPMA","major"));
 assert.equal(saved.rows[1].raw_token,undefined);assert.equal(saved.rows[1].key,undefined);
 assert.deepEqual(templateChanges(saved,block()).changes,[{key:"new:b",patch:{unit:"wt.%",method:"EPMA",measurementSet:"major"}}]);
 assert.deepEqual(templateChanges(saved,block("wt.%","EPMA","major")).changes,[]);
});
test("explicit conflict and changed physical structure block the entire template",()=>{
 const saved=makeLabTemplate("Lab A","t",block("wt.%","EPMA","major"));
 for(const target of [block("at.%"),block("","EDS"),block("","","trace")])assert.equal(templateChanges(saved,target).compatible,false);
 const changed=block();changed.rows[1].header="Mg";assert.equal(templateChanges(saved,changed).compatible,false);
 assert.throws(()=>makeLabTemplate("unfinished","t",block()),/единицы/);
});
test("local storage roundtrip and malformed records fail closed",()=>{
 const store=new Map(),storage={getItem:key=>store.get(key),setItem:(key,value)=>store.set(key,value)};
 const saved=makeLabTemplate("Lab A","t",block("wt.%","EPMA","major"));
 writeLabTemplates(storage,[saved]);assert.deepEqual(readLabTemplates(storage),[saved]);
 store.set(STORAGE_KEY,"{}");assert.throws(()=>readLabTemplates(storage));
});
