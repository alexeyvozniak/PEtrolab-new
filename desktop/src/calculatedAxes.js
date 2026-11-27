export const measuredKey = axis => JSON.stringify([axis.field,axis.unit,axis.measurement_set,axis.method]);
const exactAxis = ({field,unit,measurement_set,method}) => ({field,unit,measurement_set,method});
export function compatibleMeasured(a,b) {
  return Boolean(a && b && a.field!==b.field && a.method===b.method && a.measurement_set===b.measurement_set &&
    ((a.unit==="wt.%" && b.unit==="wt.%") || (["ppm","ppb"].includes(a.unit)&&["ppm","ppb"].includes(b.unit))));
}
export function measuredCalculation(operation, operands) {
  if(operation==="mg_number"){
    const [mg,fe]=operands;
    if(operands.length!==2||mg?.field!=="MgO"||!["FeO","FeOt"].includes(fe?.field)||mg.unit!=="wt.%"||fe.unit!=="wt.%"||!compatibleMeasured(mg,fe))
      throw Error("Mg# требует MgO и явно выбранный FeO или FeOt одного аналитического набора в wt.%.");
    return {field:fe.field==="FeO"?"Mg# (FeO)":"Mg# (FeOt, total Fe)",unit:"mol.%",measurement_set:mg.measurement_set,method:mg.method,
      calculation:{operation,version:1,operands:operands.map(exactAxis)}};
  }
  if (!["sum","ratio"].includes(operation) || operands.length<2 || operands.length>(operation==="ratio"?2:16) ||
      new Set(operands.map(a=>a.field)).size!==operands.length || operands.slice(1).some(a=>!compatibleMeasured(operands[0],a)))
    throw Error("Выберите разные совместимые измеренные компоненты одного набора и метода.");
  const [first]=operands;
  return {field:operands.map(a=>a.field).join(operation==="sum"?" + ":" / "),unit:operation==="ratio"?"ratio":first.unit,
    measurement_set:first.measurement_set,method:first.method,calculation:{operation,version:1,operands:operands.map(exactAxis)}};
}
export function formulaCalculation(series,field,runIds) {
  if(!series || !field?.startsWith("apfu.") || !runIds.length)throw Error("Выберите поле APFU и сохранённые расчёты.");
  const rows=runIds.map(id=>series.runs.find(run=>run.run_id===id));
  if(rows.some(row=>!row?.fields.includes(field)) || new Set(rows.map(row=>row.analysis_id)).size!==rows.length)
    throw Error("Выберите не более одного подходящего расчёта на анализ.");
  return {field,unit:"APFU",measurement_set:null,method:null,formula:{version:1,method_id:series.method_id,
    method_version:series.method_version,method_definition_fingerprint:series.method_definition_fingerprint,run_ids:[...runIds]}};
}
export function uniqueFormulaRuns(series,field) {
  const byAnalysis=new Map();
  for(const row of series?.runs || [])if(row.fields.includes(field)){
    const values=byAnalysis.get(row.analysis_id)||[];values.push(row.run_id);byAnalysis.set(row.analysis_id,values);
  }
  return [...byAnalysis.values()].filter(ids=>ids.length===1).map(ids=>ids[0]);
}
