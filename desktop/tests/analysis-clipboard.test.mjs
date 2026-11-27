import test from "node:test";
import assert from "node:assert/strict";
import {clipboardCell,compositionTsv,provenanceTsv,copyText} from "../src/analysisClipboard.js";
test("composition copies every measurement including duplicates, censorship and zero",()=>{
 const a={analysis_id:"a",identity:{Analysis:"P1"},source_name:"book.xlsx",sheet_name:"Mica",measurements:{MgO:{raw_token:"wrong"}},measurement_list:[
 {field:"MgO",raw_token:"0",unit:"wt.%",method:"EPMA",measurement_set:"1",source_cell:"B2",measurement_id:"m1"},
 {field:"MgO",raw_token:"<DL",unit:"ppm",method:"LA",measurement_set:"2",source_cell:"C2",measurement_id:"m2"},
 {field:"FeOt",raw_token:"-0.5",unit:"wt.%",reported_fe_form:"FeOt",source_cell:"D2",measurement_id:"m3"}]};
 const out=compositionTsv(a);assert.equal(out.split("\r\n").length,4);assert.match(out,/\tMgO\t0\twt\.%\tEPMA\t1/);
 assert.match(out,/\tMgO\t<DL\tppm\tLA\t2/);assert.match(out,/\tFeOt\t-0\.5\twt\.%/);assert.doesNotMatch(out,/wrong/);
 assert.equal(provenanceTsv(a,"C2"),"book.xlsx\tMica\tC2");assert.throws(()=>provenanceTsv(a,""));
});
test("spreadsheet text is escaped without treating signed numeric tokens as formulas",()=>{
 assert.equal(clipboardCell("=1+1"),"'=1+1");assert.equal(clipboardCell("-0.5"),"-0.5");assert.equal(clipboardCell("x\ty"),'"x\ty"');
});
test("clipboard reports failure, never falsely reports success",async()=>{
 let written;await copyText("x",{navigator:{clipboard:{writeText:async x=>{written=x;}}}});assert.equal(written,"x");
 await assert.rejects(()=>copyText("x",{}),/недоступен/);
});
