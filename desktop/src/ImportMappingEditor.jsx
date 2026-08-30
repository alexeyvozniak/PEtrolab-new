import { useEffect, useMemo, useState } from "react";
import "./importMapping.css";

const TARGETS = ["Ignore", "Analysis", "Sample", "Point", "Measurement"];
const UNITS = ["wt.%", "ppm", "ppb", "apfu", "mol%", "ratio"];

function targetFromMapping(mapping) {
  if (mapping.target_role === "measurement") return "Measurement";
  if (mapping.target_role === "identity" && ["Analysis", "Sample", "Point"].includes(mapping.canonical_field)) return mapping.canonical_field;
  return "Ignore";
}

function mappingKey(sheetName, mapping) {
  return `${sheetName}:${mapping.source_column_index}`;
}

function MappingRow({ section, mapping, selected, busy, onToggle, onApply }) {
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
  const transposed = (section.orientation || "rows") === "columns";

  return (
    <tr className={mapping.target_role === "ignore" ? "muted-row mapping-review-row" : "mapping-review-row"}>
      <td className="mapping-check-cell">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(mappingKey(section.sheet_name, mapping))}
          disabled={busy}
          aria-label={`Выбрать ${mapping.source_header}`}
        />
      </td>
      <td>{section.sheet_name}<small className="orientation-mini">{transposed ? "столбцы = анализы" : "строки = анализы"}</small></td>
      <td>
        <b>{mapping.source_header}</b>
        {transposed && <small className="source-axis-note">исходная строка {mapping.source_column_index + 1}</small>}
      </td>
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
          onClick={() => onApply(section.sheet_name, mapping.source_column_index, target, measurement ? field.trim() : null, measurement ? unit : null)}
        >
          Применить
        </button>
      </td>
    </tr>
  );
}

export function ImportMappingEditor({ recipe, busy, onApply, onBulkApply }) {
  const [selectedKeys, setSelectedKeys] = useState(() => new Set());
  const [bulkUnit, setBulkUnit] = useState("");

  const entries = useMemo(
    () => recipe.sections.flatMap((section) => section.mappings.map((mapping) => ({ section, mapping }))),
    [recipe],
  );

  useEffect(() => {
    setSelectedKeys((current) => {
      const valid = new Set(entries.map(({ section, mapping }) => mappingKey(section.sheet_name, mapping)));
      return new Set([...current].filter((key) => valid.has(key)));
    });
  }, [entries]);

  const selectedEntries = entries.filter(({ section, mapping }) => selectedKeys.has(mappingKey(section.sheet_name, mapping)));

  const toggle = (key) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedKeys.size === entries.length) {
      setSelectedKeys(new Set());
      return;
    }
    setSelectedKeys(new Set(entries.map(({ section, mapping }) => mappingKey(section.sheet_name, mapping))));
  };

  const runBulk = async (target) => {
    if (!selectedEntries.length) return;
    await onBulkApply(
      selectedEntries.map(({ section, mapping }) => ({
        sheetName: section.sheet_name,
        sourceColumnIndex: mapping.source_column_index,
        canonicalField: mapping.canonical_field || mapping.source_header,
      })),
      target,
      target === "Measurement" ? bulkUnit : null,
    );
    setSelectedKeys(new Set());
  };

  return (
    <div>
      <div className="bulk-mapping-bar">
        <div><b>Групповое назначение</b><span>Выбрано: {selectedEntries.length}</span></div>
        <select value={bulkUnit} onChange={(event) => setBulkUnit(event.target.value)} disabled={busy} aria-label="Общая единица">
          <option value="">Общая единица…</option>
          {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <button className="outline-button" disabled={busy || !selectedEntries.length || !bulkUnit} onClick={() => runBulk("Measurement")}>Назначить Measurement</button>
        <button className="outline-button" disabled={busy || !selectedEntries.length} onClick={() => runBulk("Ignore")}>Не импортировать</button>
      </div>
      <div className="mapping-table-wrap">
        <table className="mapping-table editable-mapping-table">
          <thead>
            <tr>
              <th className="mapping-check-cell"><input type="checkbox" checked={entries.length > 0 && selectedKeys.size === entries.length} onChange={toggleAll} disabled={busy} aria-label="Выбрать все" /></th>
              <th>Лист</th><th>Поле источника</th><th>Что это</th><th>Поле PetroLab</th><th>Единица</th><th />
            </tr>
          </thead>
          <tbody>
            {entries.map(({ section, mapping }) => (
              <MappingRow
                key={mappingKey(section.sheet_name, mapping)}
                section={section}
                mapping={mapping}
                selected={selectedKeys.has(mappingKey(section.sheet_name, mapping))}
                busy={busy}
                onToggle={toggle}
                onApply={onApply}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
