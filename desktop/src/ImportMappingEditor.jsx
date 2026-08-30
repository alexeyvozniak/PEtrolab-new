import { useEffect, useMemo, useState } from "react";
import "./importMapping.css";

const TARGETS = ["Ignore", "Analysis", "Sample", "Point", "Measurement"];
const UNITS = ["wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"];

const keyFor = (sheetName, columnIndex) => `${sheetName}::${columnIndex}`;

function targetFromMapping(mapping) {
  if (mapping.target_role === "measurement") return "Measurement";
  if (mapping.target_role === "identity" && ["Analysis", "Sample", "Point"].includes(mapping.canonical_field)) return mapping.canonical_field;
  return "Ignore";
}

function appliedState(mapping) {
  const target = targetFromMapping(mapping);
  return {
    target,
    field: target === "Measurement" ? (mapping.canonical_field || mapping.source_header || "") : target,
    unit: target === "Measurement" ? (mapping.unit || "") : "",
  };
}

function buildDraft(recipe, warnings) {
  const suggestions = new Map(
    warnings
      .filter((warning) => warning.code === "UNIT_REQUIRES_REVIEW")
      .map((warning) => [
        keyFor(warning.sheet_name, warning.source_column_index),
        warning.canonical_field || warning.source_header,
      ]),
  );
  const draft = {};
  for (const section of recipe.sections) {
    for (const mapping of section.mappings) {
      const key = keyFor(section.sheet_name, mapping.source_column_index);
      const current = appliedState(mapping);
      const suggestedField = suggestions.get(key);
      if (current.target === "Ignore" && suggestedField) {
        draft[key] = { target: "Measurement", field: suggestedField, unit: "" };
      } else {
        draft[key] = current;
      }
    }
  }
  return draft;
}

function statesEqual(left, right) {
  if (!left || !right) return false;
  return left.target === right.target
    && left.field === right.field
    && left.unit === right.unit;
}

function MappingRow({ sheetName, mapping, value, busy, onChange }) {
  const measurement = value.target === "Measurement";
  const invalid = measurement && (!value.field.trim() || !value.unit);
  return (
    <tr className={`${mapping.target_role === "ignore" ? "muted-row " : ""}mapping-review-row${invalid ? " mapping-invalid" : ""}`}>
      <td><b>{mapping.source_header}</b></td>
      <td>
        <select
          value={value.target}
          onChange={(event) => onChange({
            ...value,
            target: event.target.value,
            field: event.target.value === "Measurement" ? (value.field || mapping.source_header || "") : event.target.value,
            unit: event.target.value === "Measurement" ? value.unit : "",
          })}
          disabled={busy}
        >
          {TARGETS.map((item) => <option key={item} value={item}>{item === "Ignore" ? "Не импортировать" : item}</option>)}
        </select>
      </td>
      <td>
        {measurement ? (
          <input
            value={value.field}
            onChange={(event) => onChange({ ...value, field: event.target.value })}
            disabled={busy}
            aria-label={`Поле ${mapping.source_header}`}
          />
        ) : (
          <span>{value.target === "Ignore" ? "—" : value.target}</span>
        )}
      </td>
      <td>
        {measurement ? (
          <select value={value.unit} onChange={(event) => onChange({ ...value, unit: event.target.value })} disabled={busy}>
            <option value="">Выбрать…</option>
            {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        ) : "—"}
      </td>
      <td className="mapping-status-cell">
        {invalid ? <span className="mapping-needs-review">нужна единица</span> : null}
      </td>
    </tr>
  );
}

export function ImportMappingEditor({ recipe, warnings = [], busy, onApplyAll, onDirtyChange }) {
  const [draft, setDraft] = useState(() => buildDraft(recipe, warnings));
  const [sheetUnits, setSheetUnits] = useState({});

  useEffect(() => {
    setDraft(buildDraft(recipe, warnings));
    setSheetUnits({});
  }, [recipe, warnings]);

  const applied = useMemo(() => {
    const result = {};
    for (const section of recipe.sections) {
      for (const mapping of section.mappings) {
        result[keyFor(section.sheet_name, mapping.source_column_index)] = appliedState(mapping);
      }
    }
    return result;
  }, [recipe]);

  const dirtyKeys = useMemo(
    () => Object.keys(draft).filter((key) => !statesEqual(draft[key], applied[key])),
    [draft, applied],
  );
  const invalidCount = useMemo(
    () => Object.values(draft).filter((value) => value.target === "Measurement" && (!value.field.trim() || !value.unit)).length,
    [draft],
  );

  useEffect(() => {
    onDirtyChange?.(dirtyKeys.length > 0);
  }, [dirtyKeys.length, onDirtyChange]);

  const update = (sheetName, columnIndex, nextValue) => {
    const key = keyFor(sheetName, columnIndex);
    setDraft((current) => ({ ...current, [key]: nextValue }));
  };

  const applyUnitToSheet = (sheetName) => {
    const unit = sheetUnits[sheetName];
    if (!unit) return;
    setDraft((current) => {
      const next = { ...current };
      const section = recipe.sections.find((item) => item.sheet_name === sheetName);
      for (const mapping of section?.mappings || []) {
        const key = keyFor(sheetName, mapping.source_column_index);
        if (next[key]?.target === "Measurement") {
          next[key] = { ...next[key], unit };
        }
      }
      return next;
    });
  };

  const resetDraft = () => {
    setDraft(buildDraft(recipe, []));
    setSheetUnits({});
  };

  const submit = () => {
    const decisions = dirtyKeys.map((key) => {
      const [sheetName, columnIndexText] = key.split("::");
      const value = draft[key];
      return {
        sheet_name: sheetName,
        source_column_index: Number(columnIndexText),
        target: value.target,
        canonical_field: value.target === "Measurement" ? value.field.trim() : null,
        unit: value.target === "Measurement" ? value.unit : null,
      };
    });
    onApplyAll(decisions);
  };

  return (
    <div className="mapping-editor">
      <div className="mapping-explainer">
        <div>
          <b>Сначала проверь роли, потом примени всё один раз.</b>
          <span>PetroLab уже отметил знакомые элементы и оксиды как кандидаты Measurement. Единицу нужно подтвердить явно.</span>
        </div>
        <div className="mapping-summary">
          <span>Изменений: <b>{dirtyKeys.length}</b></span>
          {invalidCount > 0 && <span className="mapping-needs-review">Без единицы: <b>{invalidCount}</b></span>}
        </div>
      </div>

      {recipe.sections.map((section) => (
        <section className="mapping-sheet" key={section.sheet_name}>
          <div className="mapping-sheet-head">
            <div><b>{section.sheet_name}</b><span>Заголовок: строка {section.header_row}</span></div>
            <div className="sheet-unit-control">
              <label>Общая единица</label>
              <select
                value={sheetUnits[section.sheet_name] || ""}
                onChange={(event) => setSheetUnits((current) => ({ ...current, [section.sheet_name]: event.target.value }))}
                disabled={busy}
              >
                <option value="">Выбрать…</option>
                {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <button
                className="compact-button"
                onClick={() => applyUnitToSheet(section.sheet_name)}
                disabled={busy || !sheetUnits[section.sheet_name]}
              >
                Назначить всем Measurement
              </button>
            </div>
          </div>
          <div className="mapping-table-wrap">
            <table className="mapping-table editable-mapping-table">
              <thead><tr><th>Колонка файла</th><th>Что это</th><th>Поле PetroLab</th><th>Единица</th><th /></tr></thead>
              <tbody>
                {section.mappings.map((mapping) => (
                  <MappingRow
                    key={mapping.source_column_index}
                    sheetName={section.sheet_name}
                    mapping={mapping}
                    value={draft[keyFor(section.sheet_name, mapping.source_column_index)] || appliedState(mapping)}
                    busy={busy}
                    onChange={(nextValue) => update(section.sheet_name, mapping.source_column_index, nextValue)}
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
