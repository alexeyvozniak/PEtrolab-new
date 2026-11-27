import test from "node:test";
import assert from "node:assert/strict";
import {sessionKey,sanitizeSession,readSession,writeSession,memoryFromSession} from "../src/sessionPreferences.js";
const store=()=>{const data=new Map();return{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value)};};
test("presentation session survives restart and is isolated by verified project UUID",()=>{
  const storage=store(), a=sessionKey("00000000-0000-4000-8000-000000000001"), b=sessionKey("00000000-0000-4000-8000-000000000002");
  assert.notEqual(a,b);assert.equal(sessionKey(""),"");
  const state={screen:"Анализы",table:{visibleColumnIds:["identity:Analysis","measurement:MgO"],columnWidths:{"identity:Analysis":180},pinnedColumnId:"identity:Analysis",scrollLeft:260,focusedId:"secret",query:"old"},samples:{tab:"Изображения",sampleId:"old"},plot:{shape:"lasso",mode:"replace",panels:[{id:"old"}]},selection:["old"]};
  assert.equal(writeSession(storage,a,state),true);
  const saved=readSession(storage,a);
  assert.equal(saved.screen,"Анализы");assert.equal(saved.table.columnWidths["identity:Analysis"],180);
  assert.equal(saved.table.pinnedColumnId,"identity:Analysis");assert.equal(saved.table.scrollLeft,260);
  assert.equal(saved.samples.tab,"Изображения");assert.equal(saved.plot.shape,"lasso");
  assert.equal(saved.table.query,undefined);assert.equal(saved.table.focusedId,undefined);assert.equal(saved.samples.sampleId,undefined);assert.equal(saved.plot.panels,undefined);assert.equal(saved.selection,undefined);
  assert.equal(readSession(storage,b),null);assert.ok(memoryFromSession(saved).plot.views instanceof Map);
});
test("invalid or outdated preferences never become scientific state",()=>{
  const storage=store(),key=sessionKey("00000000-0000-4000-8000-000000000001");
  storage.setItem(key,'{"version":2}');assert.equal(readSession(storage,key),null);
  storage.setItem(key,'broken');assert.equal(readSession(storage,key),null);
  const safe=sanitizeSession({screen:"Импорт",table:{columnWidths:{a:9999,b:-2,c:"bad"},visibleColumnIds:["x","x",4],scrollLeft:-50},plot:{mode:"bad"}});
  assert.equal(safe.screen,"Обзор");assert.deepEqual(safe.table.columnWidths,{a:600,b:104});assert.deepEqual(safe.table.visibleColumnIds,["x"]);assert.equal(safe.table.scrollLeft,0);
  assert.equal(safe.plot.mode,"union");
  const inaccessible={getItem:()=>{throw Error("blocked");}};
  assert.equal(readSession(inaccessible,key),null);assert.equal(writeSession(inaccessible,key,safe),false);
});

test("multiple pins preserve order, reject duplicates, migrate the legacy preference",()=>{
 const saved=sanitizeSession({table:{pinnedColumnIds:["identity:Analysis","source","source","measurement:MgO","sheet"]}});
 assert.deepEqual(saved.table.pinnedColumnIds,["identity:Analysis","source","measurement:MgO"]);
 assert.equal(saved.table.pinnedColumnId,"identity:Analysis");
 assert.deepEqual(sanitizeSession({table:{pinnedColumnId:"source"}}).table.pinnedColumnIds,["source"]);
});
