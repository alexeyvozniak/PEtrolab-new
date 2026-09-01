import { useEffect, useMemo, useState } from "react";
import "./importMapping.css";

const TARGETS = ["Ignore", "Analysis", "Sample", "Point", "Mineral", "Generation", "Measurement"];
const UNITS = ["wt.%", "at.%", "ppm", "ppb", "apfu", "mol%", "ratio"];

function mappingAxis(mapping) {
  return mapping.source_axis || (Number.isInteger(mapping.source_column_index) ? "column" : "row");
}

function mappingIndex(mapping) {
  return mappingAxis(mapping) === "column" ? mapping.source_column_index : mapping.source_row_index;
}

function columnLetters(index) {
  let value = Number(index) + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result || "?";
}

function sourceCoordinate(mapping) {
  const index = mappingIndex(mapping);
  return mappingAxis(mapping) === "column"
    ? `${columnLetters(index)} · колонка ${index + 1}`
    : `строка ${index + 1}`;
}

function sourceTitle(mapping) {
  const header = mapping.source_header;
  return header == null || String(header).trim() === "" ? "Без заголовка" : String(header);
}

const keyFor = (blockId, axis, index) => `${blockId}::${axis}::${index}`;
const keyForMapping = (blockId, mapping) => keyFor(blockId, mappingAxis(mapping), mappingIndex(mapping));

function targetFromMapping(mapping) {
  if (mapping.target_role === "measurement") return "Measurement";
  if (mapping.target_role === "identity" && ["Analysis", "Sample", "Point"].includes(mapping.canonical_field)) return mapping.canonical_field;
  if (mapping.target_role === "metadata" && ["Mineral", "Generation"].includes(mapping.canonical_field)) return mapping.canonical_field;
  return "Ignore";
}

function appliedState(mapping) {
  const target = targetFromMapping(mapping);
  return {
    target,
    field: target === "Measurement" ? (mapping.canonical_field || mapping.source_header || "") : target,
    unit: target === "Measurement" ? (mapping.unit || "") : "",
    method: target === "Measurement" ? (mapping.method || "") : "",
    measurementSet: target === "Measurement" ? (mapping.measurement_set || "") : "",
  };
}

function warningKey(warning) {
  const axis = warning.source_axis || "column";
  const index = axis === "column" ? warning.source_column_index : warning.source_row_index;
  return keyFor(warning.block_id || warning.sheet_name || "", axis, index);
}

function buildDraft(recipe, warnings) {
  const suggestions = new Map(
    warnings
      .filter((warning) => warning.code === "UNIT_REQUIRES_REVIEW")
      .map((warning) => [warningKey(warning), warning.canonical_field || warning.source_header]),
  );
  const draft = {};
  for (const section of recipe.sections) {
    for (const mapping of section.mappings) {
      const key = keyForMapping(section.block_id, mapping);
      const current = appliedState(mapping);
      const suggestedField = suggestions.get(key);
      draft[key] = current.target === "Ignore" && suggestedField
        ? { target: "Measurement", field: suggestedField, unit: "", method: "", measurementSet: "" }
        : current;
    }
  }
  return draft;
}

function statesEqual(left, right) {
  return Boolean(left && right)
    && left.target === right.target
    && left.field === right.field
    && left.unit === right.unit
    && left.method === right.method
    && left.measurementSet === right.measurementSet;
}

function MappingRow({ mapping, value, busy, onChange }) {
  const measurement = value.target === "Measurement";
  const invalid = measurement && (!value.field.trim() || !value.unit);
  return (
    <tr className={`${mapping.target_role === "ignore" ? "muted-row " : ""}mapping-review-row${invalid ? " mapping-invalid" : ""}`}>
      <td>
        <b className={mapping.source_header ? "" : "blank-source-header"}>{sourceTitle(mapping)}</b>
        <small>{sourceCoordinate(mapping)}</small>
      </td>
      <td>
        <select
          value={value.target}
          onChange={(event) => {
            const target = event.target.value;
            onChange({
              ...value,
              target,
              field: target === "Measurement" ? (value.field || mapping.source_header || "") : target,
              unit: target === "Measurement" ? value.unit : "",
              method: target === "Measurement" ? value.method : "",
              measurementSet: target === "Measurement" ? value.measurementSet : "",
            });
          }}
          disabled={busy}
        >
          {TARGETS.map((item) => <option key={item} value={item}>{item === "Ignore" ? "Не импортировать" : item}</option>)}
        </select>
      </td>
      <td>
        {measurement ? (
          <input value={value.field} onChange={(event) => onChange({ ...value, field: event.target.value })} disabled={busy} aria-label={`Поле ${sourceTitle(mapping)}`} placeholder={mapping.source_header ? "" : "Введите название поля"} />
        ) : <span>{value.target === "Ignore" ? "—" : value.target}</span>}
      </td>
      <td>
        {measurement ? (
          <select value={value.unit} onChange={(event) => onChange({ ...value, unit: event.target.value })} disabled={busy}>
            <option value="">Выбрать…</option>
            {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        ) : "—"}
      </td>
      <td>
        {measurement ? (
          <input
            value={value.method}
            onChange={(event) => onChange({ ...value, method: event.target.value })}
            disabled={busy}
            placeholder="EPMA / WDS / SIMS…"
            aria-label={`Метод ${sourceTitle(mapping)}`}
          />
        ) : "—"}
      </td>
      <td>
        {measurement ? (
          <input
            value={value.measurementSet}
            onChange={(event) => onChange({ ...value, measurementSet: event.target.value })}
            disabled={busy}
            placeholder="major / trace…"
            aria-label={`Набор ${sourceTitle(mapping)}`}
          />
        ) : "—"}
      </td>
      <td className="mapping-status-cell">{invalid ? <span className="mapping-needs-review">нужна единица</span> : null}</td>
    </tr>
  );
}

export function ImportMappingEditor({ recipe, warnings = [], activeBlockId = null, busy, onApplyAll, onDirtyChange }) {
  const [draft, setDraft] = useState(() => buildDraft(recipe, warnings));
  const [blockUnits, setBlockUnits] = useState({});

  useEffect(() => {
    setDraft(buildDraft(recipe, warnings));
    setBlockUnits({});
  }, [recipe, warnings]);

  const applied = useMemo(() => {
    const result = {};
    for (const section of recipe.sections) {
      for (const mapping of section.mappings) result[keyForMapping(section.block_id, mapping)] = appliedState(mapping);
    }
    return result;
  }, [recipe]);

  const dirtyKeys = useMemo(() => Object.keys(draft).filter((key) => !statesEqual(draft[key], applied[key])), [draft, applied]);
  const invalidCount = useMemo(
    () => Object.values(draft).filter((value) => value.target === "Measurement" && (!value.field.trim() || !value.unit)).length,
    [draft],
  );

  useEffect(() => { onDirtyChange?.(dirtyKeys.length > 0); }, [dirtyKeys.length, onDirtyChange]);

  const update = (section, mapping, nextValue) => {
    const key = keyForMapping(section.block_id, mapping);
    setDraft((current) => ({ ...current, [key]: nextValue }));
  };

  const applyUnitToBlock = (section) => {
    const unit = blockUnits[section.block_id];
    if (!unit) return;
    setDraft((current) => {
      const next = { ...current };
      for (const mapping of section.mappings) {
        const key = keyForMapping(section.block_id, mapping);
        if (next[key]?.target === "Measurement") next[key] = { ...next[key], unit };
      }
      return next;
    });
  };

  const resetDraft = () => {
    setDraft(buildDraft(recipe, []));
    setBlockUnits({});
  };

  const submit = () => {
    const index = new Map();
    for (const section of recipe.sections) {
      for (const mapping of section.mappings) index.set(keyForMapping(section.block_id, mapping), { section, mapping });
    }
    const decisions = dirtyKeys.map((key) => {
      const { section, mapping } = index.get(key);
      const value = draft[key];
      return {
        block_id: section.block_id,
        source_axis: mappingAxis(mapping),
        source_index: mappingIndex(mapping),
        target: value.target,
        canonical_field: value.target === "Measurement" ? value.field.trim() : null,
        unit: value.target === "Measurement" ? value.unit : null,
        method: value.target === "Measurement" ? (value.method.trim() || null) : null,
        measurement_set: value.target === "Measurement" ? (value.measurementSet.trim() || null) : null,
      };
    });
    onApplyAll(decisions);
  };

  const enabledSections = recipe.sections.filter((section) => section.enabled !== false && (!activeBlockId || section.block_id === activeBlockId));

  return (
    <div className="mapping-editor">
      <div className="mapping-explainer">
        <div>
          <b>Здесь показаны все физические поля выбранного блока.</b>
          <span>Нераспознанные и колонки без заголовка не исчезают: они остаются видимыми как «Не импортировать», пока ты сам не назначишь им роль.</span>
        </div>
        <div className="mapping-summary">
          <span>Изменений: <b>{dirtyKeys.length}</b></span>
          {invalidCount > 0 && <span className="mapping-needs-review">Без единицы: <b>{invalidCount}</b></span>}
        </div>
      </div>

      {enabledSections.map((section, sectionIndex) => (
        <section className="mapping-sheet" key={section.block_id}>
          <div className="mapping-sheet-head">
            <div>
              <b>{section.sheet_name} · блок {sectionIndex + 1}</b>
              <span>{section.orientation === "columns_are_analyses" ? "анализы по столбцам" : `заголовок: строка ${section.header_row}`} · полей: {section.mappings.length}</span>
            </div>
            <div className="sheet-unit-control">
              <label>Единица для Measurement</label>
              <select value={blockUnits[section.block_id] || ""} onChange={(event) => setBlockUnits((current) => ({ ...current, [section.block_id]: event.target.value }))} disabled={busy}>
                <option value="">Выбрать…</option>
                {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <button className="compact-button" onClick={() => applyUnitToBlock(section)} disabled={busy || !blockUnits[section.block_id]}>
                Назначить всему блоку
              </button>
            </div>
          </div>
          <div className="mapping-table-wrap">
            <table className="mapping-table editable-mapping-table">
              <thead><tr><th>Поле источника</th><th>Что это</th><th>Поле PetroLab</th><th>Единица</th><th>Метод</th><th>Набор</th><th /></tr></thead>
              <tbody>
                {section.mappings.map((mapping) => (
                  <MappingRow
                    key={keyForMapping(section.block_id, mapping)}
                    mapping={mapping}
                    value={draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping)}
                    busy={busy}
                    onChange={(nextValue) => update(section, mapping, nextValue)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <div className="mapping-actions">
        <button className="outline-button" onClick={resetDraft} disabled={busy || dirtyKeys.length === 0}>Сбросить изменения</button>
        <button className="primary-button" onClick={submit} disabled={busy || dirtyKeys.length === 0 || invalidCount > 0}>
          Применить сопоставление ({dirtyKeys.length})
        </button>
      </div>
    </div>
  );
}
