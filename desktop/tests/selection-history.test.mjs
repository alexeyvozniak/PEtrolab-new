import { test } from "node:test";
import assert from "node:assert/strict";
import { selectionHistoryReducer as reduce } from "../src/selectionHistory.js";

test("selection undo redo, no-op, branching and bounded history", () => {
  let state = { past: [], present: [], future: [] };
  state = reduce(state, { type: "set", value: ["a"] });
  state = reduce(state, { type: "set", value: current => [...current, "b"] });
  assert.deepEqual(state.present, ["a", "b"]);
  state = reduce(state, { type: "undo" });
  assert.deepEqual(state.present, ["a"]);
  assert.equal(reduce(state, { type: "set", value: ["a"] }), state);
  state = reduce(state, { type: "redo" });
  assert.deepEqual(state.present, ["a", "b"]);
  state = reduce(state, { type: "undo" });
  state = reduce(state, { type: "set", value: ["c"] });
  assert.equal(state.future.length, 0);
  for (let i = 0; i < 60; i++) state = reduce(state, { type: "set", value: [String(i)] });
  assert.equal(state.past.length, 30);
});
