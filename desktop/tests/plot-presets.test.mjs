import { test } from "node:test";
import assert from "node:assert/strict";
import { axisIdentity, makePreset, rememberPreset, resolvePreset, templateGroups, MINERAL_TEMPLATES } from "../src/plotPresets.js";
const axis = (field, unit = "wt.%", method = "EPMA", measurement_set = "A") => ({field, unit, method, measurement_set});
test("recents deduplicate and restore exact fields, units and methods only", () => {
  const axes = [axis("MgO"), axis("SiO2"), axis("MgO", "ppm")];
  const p = makePreset({kind:"binary",axes:axes.slice(0,2)});
  assert.deepEqual(rememberPreset([p], p), [p]);
  assert.deepEqual(resolvePreset(p, axes, {}), {kind:"binary", axes:axes.slice(0,2)});
  assert.equal(resolvePreset(p, axes.slice(1), {}), null);
  assert.equal(resolvePreset(p, [axis("MgO","wt.%","LA"), axes[1]], {}), null);
  assert.equal(makePreset({kind:"binary",axes:[{...axes[0],calculation:{}},axes[1]]}),null);
  assert.equal(rememberPreset([p], {...p,keys:[...p.keys].reverse()},1).length,1);
});
test("mineral templates never cross units, methods, sets or ambiguous fields", () => {
  const axes = [axis("MgO"), axis("SiO2"), axis("NiO","ppm"), axis("MnO","wt.%","EPMA","B"),axis("CaO")];
  const groups = templateGroups(MINERAL_TEMPLATES[0], axes);
  assert.equal(groups.length,1);
  assert.deepEqual(groups[0].presets.map(p=>p.keys), [[axisIdentity(axes[0]),axisIdentity(axes[1])],[axisIdentity(axes[0]),axisIdentity(axes[4])]]);
  assert.equal(templateGroups(MINERAL_TEMPLATES[0], [...axes,axis("MgO")]).length,0);
  assert.equal(resolvePreset({kind:"ternary",keys:[axisIdentity(axes[0]),axisIdentity(axes[1]),axisIdentity(axes[2])]},axes,{}),null);
});
