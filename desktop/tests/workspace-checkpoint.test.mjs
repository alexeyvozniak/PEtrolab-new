import test from "node:test";
import assert from "node:assert/strict";
import {checkpointState,tableMemoryFromView,plotMemoryFromLayout} from "../src/workspaceCheckpoint.js";
const emptyScheme = {revision:0, scheme:{colors:[]}};
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
    panels:[{id:"p",kind:"binary",axes,point_style:{opacity:.35,size_scale:1}}],layers:[{id:"cloud"}]}, emptyScheme);
  assert.equal(state.colorMode,"mineral");assert.equal(state.schemeColors.length,2);assert.equal(state.panels[0].axes[0].scale,undefined);
  assert.equal(state.panels[0].point_style.opacity,.35);assert.equal(state.layers[0].id,"cloud");assert.equal(state.views.size,0);
});

test("trace-pattern normalization is restored without substituting a reference",()=>{
 const state=plotMemoryFromLayout({legend:{entries:[]},panels:[{id:"r",kind:"ree_pattern",axes:[],normalization:"sun_mcdonough_1989_c1"}]}, emptyScheme);
 assert.equal(state.panels[0].normalization,"sun_mcdonough_1989_c1");
});

test("plot checkpoint keeps project palette entries outside the saved layout", () => {
  const mica = {mode:"mineral", key:"mica", color:"#223344", symbol:"circle"};
  const generation = {mode:"generation", key:"g1", color:"#556677", symbol:"diamond"};
  const unrelatedSource = {mode:"source", key:"other", color:"#778899"};
  const current = {revision:8, scheme:{colors:[mica, generation, unrelatedSource]}};
  const layout = {legend:{entries:[{value:"layout-source", color:"#111111"}]}, panels:[],
    category_style:{mode:"mineral", entries:[{key:"mica", color:"#aabbcc", symbol:"square"}]}};
  const restored = plotMemoryFromLayout(layout, current);
  assert.equal(restored.schemeRevision, 8);
  assert.deepEqual(restored.schemeColors, [
    {...mica, color:"#aabbcc", symbol:"square"}, generation, unrelatedSource,
    {mode:"source", key:"layout-source", color:"#111111"},
  ]);
  assert.deepEqual(current.scheme.colors, [mica, generation, unrelatedSource]);
});
