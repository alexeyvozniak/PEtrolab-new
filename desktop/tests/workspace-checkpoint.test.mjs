import test from "node:test";
import assert from "node:assert/strict";
import {checkpointState,tableMemoryFromView,plotMemoryFromLayout} from "../src/workspaceCheckpoint.js";
test("checkpoint records exact selection and named references",()=>{
  const state=checkpointState({tableId:"t",plotId:"p",selection:["b","a","b"],restoreSelection:true,screen:"plotting"});
  assert.deepEqual(state.selection_analysis_ids,["b","a"]);assert.deepEqual(state.plot_specification_ids,["p"]);
  assert.equal(state.table_view_id,"t");assert.throws(()=>checkpointState({screen:"plotting"}));
  assert.deepEqual(checkpointState({selection:["a"],restoreSelection:false,screen:"overview"}).selection_analysis_ids,[]);
});
test("table state is applied only with complete available fields",()=>{
  const view={columns:[{field:"measurement:MgO",visible:true}],sort:[{field:"measurement:MgO",direction:"descending"}],filters:[{field:"column:measurement:MgO",value:">10"}]};
  const project={has_more:false,analyses:[{measurements:{MgO:{raw_token:"20"}}}]};
  assert.deepEqual(tableMemoryFromView(view,project).columnFilters,{"measurement:MgO":">10"});
  assert.equal(tableMemoryFromView(view,project).sort.direction,"desc");
  assert.throws(()=>tableMemoryFromView(view,{...project,has_more:true}));
  assert.throws(()=>tableMemoryFromView(view,{...project,analyses:[]}));
});
test("plot checkpoint retains category colors, layers and exact axes but not stale zoom",()=>{
  const axes=[{field:"MgO",unit:"wt.%",scale:"linear",manual_range:null},{field:"SiO2",unit:"wt.%",scale:"linear",manual_range:null}];
  const state=plotMemoryFromLayout({legend:{entries:[{value:"s",color:"#111111"}]},category_style:{mode:"mineral",entries:[{key:"mica",color:"#123456"},{key:null,color:"#8c9590"}]},
    panels:[{id:"p",kind:"binary",axes,point_style:{opacity:.35,size_scale:1}}],layers:[{id:"cloud"}]});
  assert.equal(state.colorMode,"mineral");assert.equal(state.schemeColors.length,2);assert.equal(state.panels[0].axes[0].scale,undefined);
  assert.equal(state.panels[0].point_style.opacity,.35);assert.equal(state.layers[0].id,"cloud");assert.equal(state.views.size,0);
});
