import test from "node:test";
import assert from "node:assert/strict";
import {duplicatePanel,selectionView} from "../src/plotQuickActions.js";
const full={x:0,y:0,width:460,height:280};
test("duplicate uses independent definition and inserts after original",()=>{
 const first={id:"a",kind:"binary",axes:[{field:"Mg#",calculation:{operands:[{field:"MgO"}]}}],point_style:{symbol:"diamond",opacity:.4,size_scale:1}};
 const panels=[first,{id:"b"}],next=duplicatePanel(panels,"a","c");
 assert.deepEqual(next.map(p=>p.id),["a","c","b"]);
 assert.deepEqual(next[1],{...first,id:"c"});
 next[1].axes[0].calculation.operands[0].field="SiO2";next[1].point_style.opacity=.8;
 assert.equal(first.axes[0].calculation.operands[0].field,"MgO");assert.equal(first.point_style.opacity,.4);
 assert.equal(duplicatePanel(panels,"a","c",2),panels);
 assert.equal(duplicatePanel(panels,"a","b"),panels);
});
test("zoom bounds include selection with padding and preserve aspect",()=>{
 const v=selectionView([{x:150,y:100},{x:200,y:130}],full);
 assert.ok(v.width<full.width);assert.ok(v.x<150 && v.x+v.width>200);assert.ok(v.y<100 && v.y+v.height>130);
 assert.ok(Math.abs(v.width/v.height-full.width/full.height)<1e-12);
 assert.equal(selectionView([],full),null);
 const one=selectionView([{x:425,y:235}],full);
 assert.ok(one.width>=full.width/8);assert.ok(one.x+one.width<=full.width+1e-9);assert.ok(one.y+one.height<=full.height+1e-9);
 const all=selectionView([{x:0,y:0},{x:460,y:280}],full);
 assert.equal(all.width,460);assert.ok(Math.abs(all.height-280)<1e-9);
});
