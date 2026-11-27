import { useEffect, useMemo, useState } from "react";
import "./importMapping.css";
import {ImportBatchContext} from "./ImportBatchContext";

const TARGETS = ["Ignore", "Analysis", "Sample", "Sample name", "Point", "Mineral", "Method", "Generation", "Rock", "Source", "Comment", "Position", "Photo number", "Size (µm)", "Measurement"];
const UNITS = ["wt.%", "at.%", "ppm", "ppb", "apfu", "mol%", "ratio", "epsilon", "permil"];

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
  if (mapping.target_role === "metadata" && TARGETS.includes(mapping.canonical_field)) return mapping.canonical_field;
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
      // Recognition is also stored on the mapping; warning lists may be
      // filtered independently. Never revive a deliberately ignored field.
      const suggestedField = mapping.suggested_target === "measurement"
        ? mapping.suggested_canonical_field || suggestions.get(key) : suggestions.get(key);
      draft[key] = current.target === "Ignore" && current.reviewDecision !== "explicit_ignore" && suggestedField
        ? { target: "Measurement", field: suggestedField, unit: "", method: "", measurementSet: "", reviewDecision: "unresolved" }
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
    && left.measurementSet === right.measurementSet
    && left.reviewDecision === right.reviewDecision;
}

function MappingRow({ mapping, value, busy, onChange }) {
  const measurement = value.target === "Measurement";
  const invalid = measurement && (!value.field.trim() || !value.unit);
  const unresolved = (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore") || invalid;
  return (
    <article className={`mapping-review-item${unresolved ? " unresolved" : ""}${invalid ? " mapping-invalid" : ""}`}>
      <div className="mapping-review-source">
        <div>
          <b className={mapping.source_header ? "" : "blank-source-header"}>{sourceTitle(mapping)}</b>
          <small>{sourceCoordinate(mapping)}</small>
        </div>
        <span className={unresolved ? "needs-decision" : "ready"}>{invalid ? "Нужна единица" : unresolved ? "Нужно решить" : "Готово"}</span>
      </div>
      <label className="mapping-control mapping-target-control">
        <span>Что это</span>
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
              reviewDecision: target === "Ignore" ? "explicit_ignore" : "assigned",
            });
          }}
          disabled={busy}
        >
          {TARGETS.map((item) => <option key={item} value={item}>{item === "Ignore" ? "Не импортировать" : item}</option>)}
        </select>
      </label>
      {measurement && (
        <div className="mapping-measurement-controls">
          <label className="mapping-control">
            <span>Поле PetroLab</span>
            <input value={value.field} onChange={(event) => onChange({ ...value, field: event.target.value })} disabled={busy} aria-label={`Поле ${sourceTitle(mapping)}`} placeholder={mapping.source_header ? "" : "Введите название поля"} />
          </label>
          <label className="mapping-control">
            <span>Единица</span>
            <select aria-label={`Единица ${sourceTitle(mapping)}`} value={value.unit} onChange={(event) => onChange({ ...value, unit: event.target.value, reviewDecision: event.target.value ? "assigned" : "unresolved" })} disabled={busy}>
              <option value="">Выбрать…</option>
              {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <details className="mapping-advanced">
            <summary>Метод и набор</summary>
            <label className="mapping-control"><span>Метод</span><input value={value.method} onChange={(event) => onChange({ ...value, method: event.target.value })} disabled={busy} placeholder="EPMA / WDS / SIMS…" aria-label={`Метод ${sourceTitle(mapping)}`} /></label>
            <label className="mapping-control"><span>Набор</span><input value={value.measurementSet} onChange={(event) => onChange({ ...value, measurementSet: event.target.value })} disabled={busy} placeholder="major / trace…" aria-label={`Набор ${sourceTitle(mapping)}`} /></label>
          </details>
        </div>
      )}
      {value.target === "Ignore" && value.reviewDecision === "explicit_ignore" && <p className="mapping-ignore-note">Поле будет сохранено только в исходном файле и не попадёт в Analysis.</p>}
    </article>
  );
}

export function ImportMappingEditor({ recipe, warnings = [], activeBlockId = null, busy, onApplyAll, onDirtyChange }) {
  const [draft, setDraft] = useState(() => buildDraft(recipe, warnings));
  const [blockUnits, setBlockUnits] = useState({});
  const [showAll, setShowAll] = useState(false);
  const [bookUnit,setBookUnit]=useState("");
  const [bookBlocks,setBookBlocks]=useState([]);

  useEffect(() => {
    setDraft(buildDraft(recipe, warnings));
    setBlockUnits({});
    setShowAll(false);
    setBookUnit("");setBookBlocks([]);
  }, [recipe, warnings]);

  // Service suggestions are initial display state, not unapplied user edits.
  const applied = useMemo(() => buildDraft(recipe, warnings), [recipe, warnings]);

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
        if (next[key]?.target === "Measurement" && next[key].field.trim() && !next[key]?.unit) next[key] = { ...next[key], unit, reviewDecision: "assigned" };
      }
      return next;
    });
  };

  const resetDraft = () => {
    setDraft(buildDraft(recipe, warnings));
    setBlockUnits({});
    setBookUnit("");setBookBlocks([]);
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
        canonical_field: value.target === "Measurement" ? value.field.trim() : null,
        unit: value.target === "Measurement" ? value.unit : null,
        method: value.target === "Measurement" ? (value.method.trim() || null) : null,
        measurement_set: value.target === "Measurement" ? (value.measurementSet.trim() || null) : null,
      };
    });
    onApplyAll(decisions);
  };

  const enabledSections = recipe.sections.filter((section) => section.enabled !== false && (!activeBlockId || section.block_id === activeBlockId));
  // Entire active workbook, not merely the visible sheet. Only explicit
  // recognition suggestions with no unit are eligible for this action.
  const bookCandidates=useMemo(()=>recipe.sections.filter(section=>section.enabled!==false).map(section=>{
    const fields=section.mappings.flatMap(mapping=>{
      const key=keyForMapping(section.block_id,mapping), value=draft[key], original=applied[key];
      return original?.target==="Measurement" && !original.unit && value?.target==="Measurement" &&
        value.field===original.field && !value.unit ? [{key,field:value.field}] : [];
    });
    const signature=JSON.stringify([section.orientation,section.mappings.map(mapping=>{
      const original=applied[keyForMapping(section.block_id,mapping)];
      return [mappingAxis(mapping),mappingIndex(mapping),mapping.source_header,original?.target,original?.field,original?.unit,original?.method,original?.measurementSet];
    })]);
    return {id:section.block_id,name:section.sheet_name,header:section.header_row,fields,signature};
  }).filter(item=>item.fields.length),[recipe,draft,applied]);
  const contextBlocks=useMemo(()=>recipe.sections.filter(section=>section.enabled!==false).map(section=>{
    const fields=section.mappings.flatMap(mapping=>{
      const key=keyForMapping(section.block_id,mapping),value=draft[key];
      return value?.target==="Measurement"&&value.field.trim()&&UNITS.includes(value.unit)?[{key,...value}]:[];
    });
    const signature=JSON.stringify([section.orientation,section.mappings.map(mapping=>{
      const value=draft[keyForMapping(section.block_id,mapping)];
      return [mappingAxis(mapping),mappingIndex(mapping),mapping.source_header,value?.target,value?.field,value?.unit];
    })]);
    return {id:section.block_id,name:section.sheet_name,header:section.header_row,fields,signature};
  }).filter(block=>block.fields.length),[recipe,draft]);
  const applyContext=(keys,patch)=>{
    const selected=new Set(keys);
    setDraft(current=>{
      const next={...current};
      for(const block of contextBlocks)for(const field of block.fields){
        const value=current[field.key];
        if(!selected.has(field.key)||value?.target!=="Measurement"||!UNITS.includes(value.unit)||!value.field.trim())continue;
        next[field.key]={...value,
          method:value.method.trim()?value.method:patch.method,
          measurementSet:value.measurementSet.trim()?value.measurementSet:patch.measurementSet,
          reviewDecision:"assigned"};
      }
      return next;
    });
  };
  const chosenBlocks=bookCandidates.filter(item=>bookBlocks.includes(item.id));
  const bookCount=chosenBlocks.reduce((sum,item)=>sum+item.fields.length,0);
  const applyBookUnit=()=>{
    if(!UNITS.includes(bookUnit)||!bookCount)return;
    const keys=new Set(chosenBlocks.flatMap(item=>item.fields.map(field=>field.key)));
    setDraft(current=>{
      const next={...current};
      for(const key of keys){
        const value=current[key],original=applied[key];
        if(value?.target==="Measurement"&&original?.target==="Measurement"&&!original.unit&&value.field===original.field&&!value.unit)
          next[key]={...value,unit:bookUnit,reviewDecision:"assigned"};
      }
      return next;
    });
    setBookBlocks([]);
  };
  const selectSimilar=()=>{
    const reference=bookCandidates.find(item=>item.id===activeBlockId);
    if(reference)setBookBlocks(bookCandidates.filter(item=>item.signature===reference.signature).map(item=>item.id));
  };

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

      {bookCandidates.length>1&&<details className="mapping-book-bulk">
        <summary>Распознавание по всей книге · {new Set(bookCandidates.map(item=>item.name)).size} листов · {bookCandidates.reduce((sum,item)=>sum+item.fields.length,0)} полей без единиц</summary>
        <small>Выберите таблицы с одинаковой единицей. Явно заданные единицы, неизвестные поля и исключённые таблицы не меняются.</small>
        <div className="mapping-book-buttons">
          <button className="outline-button" type="button" disabled={busy||!bookCandidates.some(item=>item.id===activeBlockId)} onClick={selectSimilar}>Выбрать блоки такой же структуры</button>
          <button className="outline-button" type="button" disabled={busy} onClick={()=>setBookBlocks(bookCandidates.map(item=>item.id))}>Выбрать все блоки с неуказанными единицами</button>
          <button className="outline-button" type="button" disabled={busy||!chosenBlocks.length} onClick={()=>setBookBlocks([])}>Снять выбор блоков</button>
        </div>
        <div className="mapping-book-list" aria-label="Блоки книги для назначения единицы">
          {bookCandidates.map(item=><label key={item.id}>
            <input type="checkbox" checked={bookBlocks.includes(item.id)} disabled={busy} onChange={event=>setBookBlocks(current=>event.target.checked?[...new Set([...current,item.id])]:current.filter(id=>id!==item.id))}/>
            <span><b>{item.name} · заголовок {item.header ?? "—"} · {item.fields.length} полей</b><small>{item.fields.map(field=>field.field).join(", ")}</small></span>
          </label>)}
        </div>
        <label className="mapping-book-unit">Единица выбранных блоков<select aria-label="Общая единица выбранных блоков" value={bookUnit} disabled={busy} onChange={event=>setBookUnit(event.target.value)}>
          <option value="">Выбрать…</option>{UNITS.map(unit=><option key={unit}>{unit}</option>)}
        </select></label>
        <button className="primary-button" type="button" disabled={busy||!bookUnit||!bookCount} onClick={applyBookUnit}>Назначить единицу · {bookCount} полей в {chosenBlocks.length} блоках</button>
        <small>Затем нажмите «Применить сопоставление» один раз для всей книги. Проверяйте, что одинаковая структура действительно означает одинаковые единицы.</small>
      </details>}
      <ImportBatchContext key={recipe.source_file_sha256||"book"} blocks={contextBlocks} activeBlockId={activeBlockId} busy={busy} onApply={applyContext}/>
      {enabledSections.map((section, sectionIndex) => (
        <section className="mapping-sheet" key={section.block_id}>
          {(() => {
            const unresolvedCount = section.mappings.filter((mapping) => {
              const value = draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping);
              return (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore")
                || (value.target === "Measurement" && (!value.field.trim() || !value.unit));
            }).length;
            const missingUnits=section.mappings.filter(mapping=>{
              const value=draft[keyForMapping(section.block_id,mapping)];
              return value?.target==="Measurement" && Boolean(value.field.trim()) && !value.unit;
            });
            const shownMappings = showAll ? section.mappings : section.mappings.filter((mapping) => {
              const value = draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping);
              return (value.target === "Ignore" && value.reviewDecision !== "explicit_ignore")
                || (value.target === "Measurement" && (!value.field.trim() || !value.unit));
            });
            return (
          <>
            <div className="mapping-sheet-head">
              <div>
                <b>{section.sheet_name} · блок {sectionIndex + 1}</b>
                <span>{section.orientation === "columns_are_analyses" ? "анализы по столбцам" : `заголовок: строка ${section.header_row}`} · полей: {section.mappings.length}</span>
              </div>
              <div className="mapping-view-toggle" role="group" aria-label="Какие поля показывать">
                <button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAll(false)}>Нужно решить {unresolvedCount}</button>
                <button type="button" className={showAll ? "active" : ""} onClick={() => setShowAll(true)}>Все {section.mappings.length}</button>
              </div>
              <div className="sheet-unit-control">
                <label>Общая единица для распознанных компонентов · {missingUnits.length}</label>
                <select aria-label={`Общая единица распознанных компонентов: ${section.sheet_name}`} value={blockUnits[section.block_id] || ""} onChange={(event) => setBlockUnits((current) => ({ ...current, [section.block_id]: event.target.value }))} disabled={busy}>
                  <option value="">Выбрать…</option>
                  {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <button className="compact-button" onClick={() => applyUnitToBlock(section)} disabled={busy || !blockUnits[section.block_id] || !missingUnits.length}>
                  Назначить полям без единицы
                </button>
                <small>Применяйте только если у перечисленных компонентов одна единица. Уже заданные единицы не меняются.</small>
              </div>
              {section.mappings.some((mapping) => { const value = draft[keyForMapping(section.block_id, mapping)]; return value?.target === 'Ignore' && value.reviewDecision !== 'explicit_ignore'; }) && <button className="mapping-ignore-all" onClick={() => explicitlyIgnoreUnresolved(section)} disabled={busy}>Не импортировать нераспознанные поля</button>}
            </div>
            <div className="mapping-review-list">
              {shownMappings.length ? shownMappings.map((mapping) => (
                <MappingRow
                  key={keyForMapping(section.block_id, mapping)}
                  mapping={mapping}
                  value={draft[keyForMapping(section.block_id, mapping)] || appliedState(mapping)}
                  busy={busy}
                  onChange={(nextValue) => update(section, mapping, nextValue)}
                />
              )) : <div className="mapping-all-resolved"><b>Все поля этого блока разобраны</b><span>Открой «Все», чтобы проверить автоматические сопоставления.</span></div>}
            </div>
          </>
            );
          })()}
        </section>
      ))}

      <div className="mapping-actions">
        <button className="outline-button" onClick={resetDraft} disabled={busy || dirtyKeys.length === 0}>Сбросить изменения</button>
        <button className="primary-button" onClick={submit} disabled={busy || dirtyKeys.length === 0 || dirtyKeys.some((key) => draft[key].target === 'Measurement' && (!draft[key].field.trim() || !draft[key].unit))}>
          Применить сопоставление ({dirtyKeys.length})
        </button>
      </div>
    </div>
  );
}
