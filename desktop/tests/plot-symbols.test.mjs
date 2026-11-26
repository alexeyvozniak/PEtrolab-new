import test from "node:test";
import assert from "node:assert/strict";
import {SYMBOL_LABELS,symbolGeometry,symbolPaint} from "../src/plotSymbols.js";
test("20 unique closed and open markers use finite SVG primitives and consistent radius",()=>{
 assert.equal(Object.keys(SYMBOL_LABELS).length,20);
 const geometries=new Set();
 for(const symbol of Object.keys(SYMBOL_LABELS)){
   const {tag,attrs}=symbolGeometry(symbol,20,30,5);
   const paint=symbolPaint(symbol,"#123456");
   assert.equal(paint.fill,symbol.endsWith("_open")?"none":"#123456");
   if(symbol.endsWith("_open"))assert.equal(paint.stroke,"#123456");
   if(tag==="polygon"){
     const points=attrs.points.split(" ").map(p=>p.split(",").map(Number));
     assert.ok(points.length>=3);
     for(const [x,y] of points)assert.ok(Number.isFinite(x)&&Number.isFinite(y)&&Math.hypot(x-20,y-30)<=5+1e-9);
   }else assert.deepEqual(attrs,{cx:20,cy:30,r:5});
   geometries.add(JSON.stringify([tag,attrs,paint]));
 }
 assert.equal(geometries.size,20);
});
