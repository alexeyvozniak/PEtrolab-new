// Spreadsheet-safe TSV; original tokens are never written back to the project.
export function clipboardCell(value) {
  let text = String(value ?? "");
  if (/^[\s]*[=+\-@]/.test(text) && !/^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$/.test(text.trim())) text = "'" + text;
  return /[\t\r\n"]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}
export const tsv = rows => rows.map(row=>row.map(clipboardCell).join("\t")).join("\r\n");
export function compositionTsv(analysis) {
  const measurements = analysis.measurement_list ?? Object.entries(analysis.measurements || {}).map(([field,value])=>({field,...value}));
  return tsv([["Analysis ID","Анализ","Компонент","Исходное значение","Единица","Метод","Набор","Статус","Форма Fe","Файл","Лист","Ячейка","Исходный заголовок","Measurement ID"],
    ...measurements.map(m=>[analysis.analysis_id,Object.values(analysis.identity||{}).filter(Boolean).join(" · "),m.field,m.raw_token,m.unit,m.method,m.measurement_set,m.value_status,m.reported_fe_form,analysis.source_name,analysis.sheet_name,m.source_cell,m.source_header,m.measurement_id])]);
}
export function provenanceTsv(analysis,cell) {
  if(!analysis?.source_name || !cell)throw Error("Нет сохранённого адреса исходной ячейки.");
  return tsv([[analysis.source_name,analysis.sheet_name,cell]]);
}
export async function copyText(text,env=globalThis) {
  try {if(env.navigator?.clipboard?.writeText){await env.navigator.clipboard.writeText(text);return;}} catch {}
  const doc=env.document;
  if(!doc?.execCommand)throw Error("Буфер обмена недоступен.");
  const prior=doc.activeElement,area=doc.createElement("textarea");
  area.value=text;area.setAttribute("readonly","");area.style.position="fixed";area.style.left="-9999px";
  doc.body.append(area);
  try {area.select();if(!doc.execCommand("copy"))throw Error("Буфер обмена недоступен.");}
  finally {area.remove();prior?.focus?.();}
}
