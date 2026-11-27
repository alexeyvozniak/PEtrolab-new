import test from "node:test";
import assert from "node:assert/strict";
import {measuredCalculation,formulaCalculation,uniqueFormulaRuns} from "../src/calculatedAxes.js";
const a=(field,unit="wt.%",method="EPMA",measurement_set="set")=>({field,unit,method,measurement_set});
test("exact measured operands and unit, no silent mixing",()=>{
 const result=measuredCalculation("ratio",[a("MgO"),a("FeO")]);assert.equal(result.unit,"ratio");assert.deepEqual(result.calculation.operands,[a("MgO"),a("FeO")]);
 assert.equal(measuredCalculation("sum",[a("Na2O"),a("K2O")]).unit,"wt.%");
 assert.throws(()=>measuredCalculation("sum",[a("MgO"),a("FeO","wt.%","EDS")]));
 assert.throws(()=>measuredCalculation("ratio",[a("MgO"),a("MgO")]));
 assert.equal(measuredCalculation("ratio",[a("La","ppm"),a("Yb","ppb")]).calculation.operands[1].unit,"ppb");
});
test("APFU requires explicit exact runs, never silently picks ambiguous",()=>{
 const series={method_id:"formula.mica",method_version:"1",method_definition_fingerprint:"a".repeat(64),runs:[{run_id:"r1",analysis_id:"a",fields:["apfu.Mg"]},{run_id:"r2",analysis_id:"a",fields:["apfu.Mg"]},{run_id:"r3",analysis_id:"b",fields:["apfu.Mg"]}]};
 assert.deepEqual(uniqueFormulaRuns(series,"apfu.Mg"),["r3"]);assert.throws(()=>formulaCalculation(series,"apfu.Mg",["r1","r2"]));
 assert.deepEqual(formulaCalculation(series,"apfu.Mg",["r2","r3"]).formula.run_ids,["r2","r3"]);
});
