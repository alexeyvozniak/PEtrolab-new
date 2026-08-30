import { useEffect, useState } from "react";
import "./importMapping.css";

const TARGETS = ["Ignore", "Analysis", "Sample", "Point", "Measurement"];
const UNITS = ["wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"];

function targetFromMapping(mapping) {
  if (mapping.target_role === "measurement") return "Measurement";
  if (mapping.target_role === "identity" && ["Analysis", "Sample", "Point"].includes(mapping.canonical_field)) return mapping.canonical_field;
  return "Ignore";
}

function MappingRow({ sheetName, mapping, busy, onApply }) {
  const appliedTarget = targetFromMapping(mapping);
  const [target, setTarget] = useState(appliedTarget);
  const [field, setField] = useState(mapping.canonical_field || mapping.source_header || "");
  const [unit, setUnit] = useState(mapping.unit || "");

  useEffect(() => {
    setTarget(targetFromMapping(mapping));
    setField(mapping.canonical_field || mapping.source_header || "");
    setUnit(mapping.unit || "");
  }, [mapping]);

  const measurement = target === "Measurement";
  const dirty = target !== appliedTarget
    || (measurement && (field !== (mapping.canonical_field || mapping.source_header || "") || unit !== (mapping.unit || "")));
  const invalid = measurement && (!field.trim() || !unit);

  return (
    <tr className={mapping.target_role === "ignore" ? "muted-row mapping-review-row" : "mapping-review-row"}>
      <td>{sheetName}</td>
      <td><b>{mapping.source_header}</b></td>
      <td>
        <select value={target} onChange={(event) => setTarget(event.target.value)} disabled={busy}>
          {TARGETS.map((item) => <option key={item} value={item}>{item === "Ignore" ? "Не импортировать" : item}</option>)}
        </select>
      </td>
      <td>
        {measurement ? (
          <input value={field} onChange={(event) => setField(event.target.value)} disabled={busy} aria-label={`Поле ${mapping.source_header}`} />
        ) : (
          <span>{target === "Ignore" ? "—" : target}</span>
        )}
      </td>
      <td>
        {measurement ? (
          <select value={unit} onChange={(event) => setUnit(event.target.value)} disabled={busy}>
            <option value="">Выбрать…</option>
            {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        ) : "—"}
      </td>
      <td>
        <button
          className="compact-button"
          disabled={busy || invalid || !dirty}
          onClick={() => onApply(sheetName, mapping.source_column_index, target, measurement ? field.trim() : null, measurement ? unit : null)}
        >
          Применить
        </button>
      </td>
    </tr>
  );
}

export function ImportMappingEditor({ recipe, busy, onApply }) {
  return (
    <div className="mapping-table-wrap">
      <table className="mapping-table editable-mapping-table">
        <thead>
          <tr><th>Лист</th><th>Колонка файла</th><th>Что это</th><th>Поле PetroLab</th><th>Единица</th><th /></tr>
        </thead>
        <tbody>
          {recipe.sections.flatMap((section) => section.mappings.map((mapping) => (
            <MappingRow
              key={`${section.sheet_name}-${mapping.source_column_index}`}
              sheetName={section.sheet_name}
              mapping={mapping}
              busy={busy}
              onApply={onApply}
            />
          )))}
        </tbody>
      </table>
    </div>
  );
}
