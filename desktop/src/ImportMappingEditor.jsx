import { useEffect, useMemo, useState } from "react";
import "./importMapping.css";

const TARGETS = ["Ignore", "Analysis", "Sample", "Sample name", "Point", "Mineral", "Method", "Generation", "Rock", "Source", "Comment", "Position", "Photo number", "Size (µm)", "Metadata", "Measurement"];
const UNITS = ["wt.%", "mass%", "at.%", "ppm", "ppb", "apfu", "mol%", "ratio", "epsilon", "permil"];
const UNIT_LABELS = { "wt.%": "wt.% · массовые %", "mass%": "mass% · массовые %", "at.%": "at.% · атомные %", "mol%": "mol% · мольные %", apfu: "apfu · атомы на формулу", ratio: "ratio · отношение", permil: "permil · ‰" };
const FE_FORM_OPTIONS = [
  ["FeO", "FeO · двухвалентное железо как FeO"],
  ["FeOt", "FeOt · суммарное железо как FeO"],
  ["Fe2O3", "Fe₂O₃ · трёхвалентное железо"],
  ["Fe2O3t", "Fe₂O₃t · суммарное железо как Fe₂O₃"],
  ["Fe", "Неизвестно · сохранить Fe без расчётов"],
];

function countNoun(count, one, few, many) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${count} ${many}`;
  if (last === 1) return `${count} ${one}`;
  if (last >= 2 && last <= 4) return `${count} ${few}`;
  return `${count} ${many}`;
}

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
  if (mapping.target_role === "metadata") return TARGETS.includes(mapping.canonical_field) ? mapping.canonical_field : "Metadata";
  return "Ignore";
}

function appliedState(mapping) {
  const target = targetFromMapping(mapping);
  return {
    target,
    field: ["Measurement", "Metadata"].includes(target) ? (mapping.canonical_field || mapping.source_header || "") : target,
    unit: target === "Measurement" ? (mapping.unit || "") : "",
    method: target === "Measurement" ? (mapping.method || "") : "",
    measurementSet: target === "Measurement" ? (mapping.measurement_set || "") : "",
    reviewDecision: mapping.review_decision || (target === "Ignore" ? "unresolved" : "recognized"),
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
      const unresolvedFe = warnings.some((warning) => warning.code === "FE_STRICTLY_REPORTED" && warning.blocking && warningKey(warning) === key);
      draft[key] = current.target === "Ignore" && suggestedField
        ? { target: "Measurement", field: suggestedField, unit: "", method: "", measurementSet: "", reviewDecision: "unresolved" }
        : unresolvedFe ? { ...current, reviewDecision: "unresolved" } : current;
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
    && left.measurementSet === right.measurementSet
    && left.reviewDecision === right.reviewDecision;
}

function MappingRow({ mapping, value, busy, onChange, feFormRequired = false, guided = false }) {
  const measurement = value.target === "Measurement";
  const customMetadata = value.target === "Metadata";
  const invalid = (measurement && (!value.field.trim() || !value.unit)) || (customMetadata && !value.field.trim());
  const unresolved = value.reviewDecision === "unresolved" || (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore") || invalid;
  return (
    <article className={`mapping-review-item${guided ? " guided" : ""}${unresolved ? " unresolved" : ""}${invalid ? " mapping-invalid" : ""}`}>
      {!guided && <div className="mapping-review-source">
        <div>
          <b className={mapping.source_header ? "" : "blank-source-header"}>{sourceTitle(mapping)}</b>
          <small>{sourceCoordinate(mapping)}</small>
        </div>
        <span className={unresolved ? "needs-decision" : "ready"}>{invalid ? (customMetadata ? "Нужно название" : "Нужна единица") : unresolved ? "Нужно решить" : "Готово"}</span>
      </div>}
      {!(guided && feFormRequired) && <label className="mapping-control mapping-target-control">
        <span>Что это</span>
        <select
          value={value.target}
          onChange={(event) => {
            const target = event.target.value;
            const previousNamedField = ["Measurement", "Metadata"].includes(value.target) ? value.field : "";
            onChange({
              ...value,
              target,
              field: ["Measurement", "Metadata"].includes(target) ? (previousNamedField || mapping.source_header || "") : target,
              unit: target === "Measurement" ? value.unit : "",
              method: target === "Measurement" ? value.method : "",
              measurementSet: target === "Measurement" ? value.measurementSet : "",
              reviewDecision: target === "Ignore" ? "explicit_ignore" : "assigned",
            });
          }}
          disabled={busy}
        >
          {TARGETS.map((item) => <option key={item} value={item}>{item === "Ignore" ? "Не импортировать" : item === "Metadata" ? "Пользовательская колонка" : item}</option>)}
        </select>
      </label>}
      {customMetadata && <label className="mapping-control mapping-custom-field-control">
        <span>Название колонки в PetroLab</span>
        <input value={value.field} onChange={(event) => onChange({ ...value, field: event.target.value, reviewDecision: event.target.value.trim() ? "assigned" : "unresolved" })} disabled={busy} aria-label={`Название пользовательской колонки ${sourceTitle(mapping)}`} placeholder={mapping.source_header || "Введите название"} />
      </label>}
      {measurement && (
        <div className="mapping-measurement-controls">
          <label className="mapping-control">
            <span>{feFormRequired ? "Форма железа" : "Поле PetroLab"}</span>
            {feFormRequired ? (
              <select
                value={value.reviewDecision === "unresolved" ? "" : value.field}
                onChange={(event) => onChange({ ...value, field: event.target.value, reviewDecision: event.target.value ? "assigned" : "unresolved" })}
                disabled={busy}
                aria-label={`Форма железа ${sourceTitle(mapping)}`}
              >
                <option value="">Выбрать, что означает Fe…</option>
                {FE_FORM_OPTIONS.map(([field, label]) => <option key={field} value={field}>{label}</option>)}
              </select>
            ) : <input value={value.field} onChange={(event) => onChange({ ...value, field: event.target.value })} disabled={busy} aria-label={`Поле ${sourceTitle(mapping)}`} placeholder={mapping.source_header ? "" : "Введите название поля"} />}
          </label>
          {!(guided && feFormRequired) && <label className="mapping-control">
            <span>Единица</span>
            <select aria-label={`Единица ${sourceTitle(mapping)}`} value={value.unit} onChange={(event) => onChange({ ...value, unit: event.target.value, reviewDecision: event.target.value ? "assigned" : "unresolved" })} disabled={busy}>
              <option value="">Выбрать…</option>
              {UNITS.map((item) => <option key={item} value={item}>{UNIT_LABELS[item] || item}</option>)}
            </select>
          </label>}
          {!guided && <details className="mapping-advanced">
            <summary>Метод и набор</summary>
            <label className="mapping-control"><span>Метод</span><input value={value.method} onChange={(event) => onChange({ ...value, method: event.target.value })} disabled={busy} placeholder="EPMA / WDS / SIMS…" aria-label={`Метод ${sourceTitle(mapping)}`} /></label>
            <label className="mapping-control"><span>Набор</span><input value={value.measurementSet} onChange={(event) => onChange({ ...value, measurementSet: event.target.value })} disabled={busy} placeholder="major / trace…" aria-label={`Набор ${sourceTitle(mapping)}`} /></label>
          </details>}
          {feFormRequired && <p className="mapping-fe-note">{guided ? `Единица ${value.unit || "не указана"} уже распознана. Исходные числа не изменятся.` : "Единица описывает числа и уже распознана отдельно. Выберите, в какой форме источник сообщает железо — PetroLab сохранит исходные значения без пересчёта."}</p>}
        </div>
      )}
      {value.target === "Ignore" && value.reviewDecision === "explicit_ignore" && <p className="mapping-ignore-note">Поле будет сохранено только в исходном файле и не попадёт в Analysis.</p>}
    </article>
  );
}

export function ImportMappingEditor({ recipe, warnings = [], activeBlockId = null, focusedIssue = null, groupedUnitTargets = [], guided = false, busy, onApplyAll, onDirtyChange }) {
  const [draft, setDraft] = useState(() => buildDraft(recipe, warnings));
  const [blockUnits, setBlockUnits] = useState({});
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setDraft(buildDraft(recipe, warnings));
    setBlockUnits({});
    setShowAll(false);
  }, [recipe, warnings]);

  // Service suggestions are initial display state, not unapplied user edits.
  const applied = useMemo(() => buildDraft(recipe, warnings), [recipe, warnings]);
  const feFormKeys = useMemo(() => new Set(warnings.filter((warning) => warning.code === "FE_STRICTLY_REPORTED").map(warningKey)), [warnings]);
  const groupedUnitKeys = useMemo(() => new Set(groupedUnitTargets.map((target) => (
    keyFor(target.block_id, target.source_axis || "column", target.source_index)
  ))), [groupedUnitTargets]);
  const focusedMappingKey = useMemo(() => {
    if (!focusedIssue?.blocking || !focusedIssue.block_id) return null;
    const axis = focusedIssue.source_axis || "column";
    const index = axis === "column" ? focusedIssue.source_column_index : focusedIssue.source_row_index;
    return Number.isInteger(index) ? keyFor(focusedIssue.block_id, axis, index) : null;
  }, [focusedIssue]);

  useEffect(() => { setShowAll(false); }, [activeBlockId, focusedMappingKey]);

  const dirtyKeys = useMemo(() => Object.keys(draft).filter((key) => !statesEqual(draft[key], applied[key])), [draft, applied]);
  const invalidCount = useMemo(
    () => Object.values(draft).filter((value) => (value.target === "Measurement" && (!value.field.trim() || !value.unit)) || (value.target === "Metadata" && !value.field.trim())).length,
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
        if (next[key]?.target === "Measurement" && !next[key]?.unit) next[key] = { ...next[key], unit, reviewDecision: "assigned" };
      }
      return next;
    });
  };

  const resetDraft = () => {
    setDraft(buildDraft(recipe, warnings));
    setBlockUnits({});
  };

  const explicitlyIgnoreUnresolved = (section) => {
    setDraft((current) => {
      const next = { ...current };
      for (const mapping of section.mappings) {
        const key = keyForMapping(section.block_id, mapping);
        if (next[key]?.target === "Ignore" && next[key]?.reviewDecision !== "explicit_ignore") {
          next[key] = { ...next[key], reviewDecision: "explicit_ignore" };
        }
      }
      return next;
    });
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
        canonical_field: ["Measurement", "Metadata"].includes(value.target) ? value.field.trim() : null,
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
          <b>Уточните поля, которые требуют решения.</b>
          <span>Выберите назначение и единицу из исходной таблицы, затем примените изменения. Остальные поля доступны в разделе «Все».</span>
        </div>
        <div className="mapping-summary">
          <span>Изменений: <b>{dirtyKeys.length}</b></span>
          {invalidCount > 0 && <span className="mapping-needs-review">Без единицы: <b>{invalidCount}</b></span>}
        </div>
      </div>

      {enabledSections.map((section) => (
        <section className="mapping-sheet" key={section.block_id}>
          {(() => {
            const unresolvedCount = section.mappings.filter((mapping) => {
              const value = draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping);
              return value.reviewDecision === "unresolved"
                || (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore")
                || (value.target === "Measurement" && (!value.field.trim() || !value.unit))
                || (value.target === "Metadata" && !value.field.trim());
            }).length;
            const groupedCount = section.mappings.filter((mapping) => groupedUnitKeys.has(keyForMapping(section.block_id, mapping))).length;
            const individualUnresolvedCount = Math.max(0, unresolvedCount - groupedCount);
            const focusedMappingExists = Boolean(focusedMappingKey && section.mappings.some((mapping) => keyForMapping(section.block_id, mapping) === focusedMappingKey));
            const focusedOnly = guided && focusedMappingExists && !showAll;
            const shownMappings = showAll ? section.mappings : section.mappings.filter((mapping) => {
              if (groupedUnitKeys.has(keyForMapping(section.block_id, mapping))) return false;
              if (focusedMappingExists) return keyForMapping(section.block_id, mapping) === focusedMappingKey
                || dirtyKeys.includes(keyForMapping(section.block_id, mapping));
              const value = draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping);
              return dirtyKeys.includes(keyForMapping(section.block_id, mapping))
                || value.reviewDecision === "unresolved"
                || (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore")
                || (value.target === "Measurement" && (!value.field.trim() || !value.unit))
                || (value.target === "Metadata" && !value.field.trim());
            });
            return (
          <>
            {!focusedOnly && <div className="mapping-sheet-head">
              <div>
                <b>{section.sheet_name}</b>
                <span>{section.orientation === "columns_are_analyses" ? "анализы по столбцам" : `заголовок: строка ${section.header_row}`} · полей: {section.mappings.length}</span>
              </div>
              <div className="mapping-view-toggle" role="group" aria-label="Какие поля показывать">
                <button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAll(false)}>{focusedMappingExists ? "Текущий вопрос" : groupedCount ? `Отдельно ${individualUnresolvedCount}` : `Нужно решить ${unresolvedCount}`}</button>
                <button type="button" className={showAll ? "active" : ""} onClick={() => setShowAll(true)}>Все {section.mappings.length}</button>
              </div>
              <details className="mapping-bulk-options">
              <summary>Настроить несколько полей сразу</summary>
              <div className="sheet-unit-control">
                <label>Одна единица для полей без единицы</label>
                <select value={blockUnits[section.block_id] || ""} onChange={(event) => setBlockUnits((current) => ({ ...current, [section.block_id]: event.target.value }))} disabled={busy}>
                  <option value="">Выбрать…</option>
                  {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <button className="compact-button" onClick={() => applyUnitToBlock(section)} disabled={busy || !blockUnits[section.block_id]}>
                  Назначить полям без единицы
                </button>
              </div>
              {section.mappings.some((mapping) => { const value = draft[keyForMapping(section.block_id, mapping)]; return value?.target === 'Ignore' && value.reviewDecision !== 'explicit_ignore'; }) && <button className="mapping-ignore-all" onClick={() => explicitlyIgnoreUnresolved(section)} disabled={busy}>Не импортировать нераспознанные поля</button>}
              </details>
            </div>}
            <div className="mapping-review-list">
              {shownMappings.length ? shownMappings.map((mapping) => (
                <MappingRow
                  key={keyForMapping(section.block_id, mapping)}
                  mapping={mapping}
                  value={draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping)}
                  busy={busy}
                  feFormRequired={feFormKeys.has(keyForMapping(section.block_id, mapping))}
                  guided={focusedOnly}
                  onChange={(nextValue) => update(section, mapping, nextValue)}
                />
              )) : groupedCount && !showAll ? (
                <div className="mapping-group-covered">
                  <b>{countNoun(groupedCount, "поле", "поля", "полей")} этой таблицы {groupedCount === 1 ? "входит" : "входят"} в один вопрос выше</b>
                  <span>Выберите общую единицу. Если единицы различаются, настройте поля по одному.</span>
                  <button type="button" onClick={() => setShowAll(true)}>Настроить поля по одному</button>
                </div>
              ) : <div className="mapping-all-resolved"><b>Все поля этого блока разобраны</b><span>Открой «Все», чтобы проверить автоматические сопоставления.</span></div>}
            </div>
            {focusedOnly && <button className="mapping-manual-toggle" type="button" onClick={() => setShowAll(true)}>Изменить роль или единицу</button>}
          </>
            );
          })()}
        </section>
      ))}

      <div className={`mapping-actions${guided ? " guided" : ""}`}>
        {dirtyKeys.length > 0 && !guided && <p role="status">Изменения ещё не применены. Проверьте выбранные значения и нажмите «Применить сопоставление».</p>}
        {dirtyKeys.length > 0 && <button className="outline-button" onClick={resetDraft} disabled={busy}>Сбросить</button>}
        <button className="primary-button" onClick={submit} disabled={busy || dirtyKeys.length === 0 || dirtyKeys.some((key) => (draft[key].target === 'Measurement' && (!draft[key].field.trim() || !draft[key].unit)) || (draft[key].target === 'Metadata' && !draft[key].field.trim()))}>
          {guided ? "Сохранить ответ" : `Применить сопоставление (${dirtyKeys.length})`}
        </button>
      </div>
    </div>
  );
}
