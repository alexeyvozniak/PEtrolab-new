import { useCallback, useReducer } from "react";

const LIMIT = 30;
const initial = { past: [], present: [], future: [] };

export function selectionHistoryReducer(state, action) {
  if (action.type === "undo") {
    if (!state.past.length) return state;
    return { past: state.past.slice(0, -1), present: state.past.at(-1), future: [state.present, ...state.future].slice(0, LIMIT) };
  }
  if (action.type === "redo") {
    if (!state.future.length) return state;
    return { past: [...state.past, state.present].slice(-LIMIT), present: state.future[0], future: state.future.slice(1) };
  }
  const next = typeof action.value === "function" ? action.value(state.present) : action.value;
  if (next === state.present || (next.length === state.present.length && next.every((id, index) => id === state.present[index]))) return state;
  return { past: [...state.past, state.present].slice(-LIMIT), present: next, future: [] };
}

export function useSelectionHistory() {
  const [state, dispatch] = useReducer(selectionHistoryReducer, initial);
  const set = useCallback(value => dispatch({ type: "set", value }), []);
  const undo = useCallback(() => dispatch({ type: "undo" }), []);
  const redo = useCallback(() => dispatch({ type: "redo" }), []);
  return [state.present, set, undo, redo];
}
