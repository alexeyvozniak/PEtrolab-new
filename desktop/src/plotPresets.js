// Presets are UI recipes, not classifications or scientific calculations.
// Match exact catalogue identity; never infer a different Fe form or unit.
export const axisIdentity = axis => JSON.stringify([axis.field, axis.unit, axis.measurement_set ?? null, axis.method ?? null]);
const calculated = axis => Boolean(axis?.calculation || axis?.formula);
export const presetKey = preset => JSON.stringify([preset.kind, preset.keys, preset.normalization ?? null]);
export function makePreset(panel) {
  if (!panel?.axes?.length || panel.axes.some(calculated)) return null;
  return { kind: panel.kind, keys: panel.axes.map(axisIdentity), ...(panel.normalization ? { normalization: panel.normalization } : {}) };
}
export function rememberPreset(items, preset, limit = 12) {
  return preset ? [preset, ...items.filter(item => presetKey(item) !== presetKey(preset))].slice(0, limit) : items;
}
export function resolvePreset(preset, axes, patterns) {
  if (!preset || !Array.isArray(preset.keys)) return null;
  const map = new Map(axes.filter(axis => !calculated(axis)).map(axis => [axisIdentity(axis), axis]));
  const selected = preset.keys.map(key => map.get(key));
  if (selected.some(axis => !axis)) return null;
  const expected = { binary: 2, ternary: 3, histogram: 1 }[preset.kind];
  if (expected && (selected.length !== expected || new Set(preset.keys).size !== expected)) return null;
  if (preset.kind === "ternary" && !selected.every(axis => ["wt.%", "ppm", "ppb"].includes(axis.unit)
      && axis.unit === selected[0].unit && (axis.method ?? null) === (selected[0].method ?? null)
      && (axis.measurement_set ?? null) === (selected[0].measurement_set ?? null))) return null;
  if (!expected) {
    const pattern = patterns[preset.kind];
    if (!pattern || !pattern.normalizations.some(ref => ref.id === preset.normalization)
        || !pattern.groups.some(group => selected.length >= 2 && selected.every(axis => group.fields.get(axis.field)?.some(candidate => axisIdentity(candidate) === axisIdentity(axis))))) return null;
  }
  return { kind: preset.kind, axes: selected, ...(!expected ? { normalization: preset.normalization } : {}) };
}
export const MINERAL_TEMPLATES = [
  { name: "Оливины", pairs: [["MgO", "SiO2"], ["MgO", "NiO"], ["MgO", "MnO"], ["MgO", "CaO"]] },
  { name: "Слюды", pairs: [["SiO2", "Al2O3"], ["MgO", "TiO2"], ["MgO", "Al2O3"], ["K2O", "Na2O"]] },
  { name: "Пироксены", pairs: [["CaO", "MgO"], ["Na2O", "Al2O3"], ["TiO2", "Al2O3"], ["SiO2", "MgO"]] },
  { name: "Гранаты", pairs: [["CaO", "MgO"], ["CaO", "MnO"], ["Cr2O3", "Al2O3"], ["TiO2", "Al2O3"]] },
];
export function templateGroups(template, axes) {
  const groups = new Map();
  for (const axis of axes) {
    if (calculated(axis) || axis.unit !== "wt.%") continue;
    const key = JSON.stringify([axis.method ?? null, axis.measurement_set ?? null]);
    if (!groups.has(key)) groups.set(key, { key, label: [axis.method, axis.measurement_set].filter(Boolean).join(" · ") || "Без обозначения", fields: new Map() });
    const fields = groups.get(key).fields;
    if (!fields.has(axis.field)) fields.set(axis.field, []);
    fields.get(axis.field).push(axis);
  }
  return [...groups.values()].map(({ key, label, fields }) => ({
    key, label,
    presets: template.pairs.flatMap(pair => {
      const matches = pair.map(field => fields.get(field));
      return matches.every(items => items?.length === 1)
        ? [{ kind: "binary", keys: matches.map(items => axisIdentity(items[0])) }] : [];
    }),
  })).filter(group => group.presets.length);
}
