import test from "node:test";
import assert from "node:assert/strict";
import {applyBatchStyle} from "../src/plotBatchStyle.js";
const rows=[{key:"a",color:"#aaaaaa",symbol:"diamond"},{key:"b",color:"#bbbbbb"},{key:null,color:"#8c9590"}];
const initial=[{mode:"mineral",key:"a",color:"#aaaaaa",symbol:"diamond"},{mode:"generation",key:"a",color:"#112233"},{mode:"mineral",key:"old",color:"#123456"}];
test("bulk color preserves symbols, other modes, absent categories and null",()=>{
 const result=applyBatchStyle(initial,"mineral",rows,["a","b",null,"old"],{color:"#ABCDEF"});
 assert.deepEqual(result.find(e=>e.mode==="mineral"&&e.key==="a"),{mode:"mineral",key:"a",color:"#abcdef",symbol:"diamond"});
 assert.deepEqual(result.find(e=>e.key==="b"),{mode:"mineral",key:"b",color:"#abcdef"});
 assert.deepEqual(result.slice(1,3),initial.slice(1,3));assert.equal(result.length,4);
 assert.equal(initial[0].color,"#aaaaaa");
});
test("symbol-only edit preserves current or default colors",()=>{
 const result=applyBatchStyle(initial,"mineral",rows,["a","b"],{symbol:"star_open"});
 assert.equal(result[0].color,"#aaaaaa");assert.equal(result.at(-1).color,"#bbbbbb");assert.equal(result.at(-1).symbol,"star_open");
 assert.throws(()=>applyBatchStyle(initial,"source",rows,["a"],{symbol:"star"}));
 assert.throws(()=>applyBatchStyle(initial,"mineral",rows,["a"],{color:"red"}));
});
