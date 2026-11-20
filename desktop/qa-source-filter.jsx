import React from 'react';
import { createRoot } from 'react-dom/client';
import { AnalysesWorkspace } from './src/AnalysesWorkspace';
import { ProjectOverview, ProjectSearch } from './src/ProjectNavigation';
import { PlotWorkspace } from './src/PlotWorkspace';
import { SampleWorkspace } from './src/SampleWorkspace';
import './src/styles.css';
const sources = ['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'];
const analyses = sources.flatMap((id, index) => Array.from({length: 5}, (_, row) => {
  const measurement = {measurement_id: `${id}-measure-${row}`, field:'F', source_cell: `B${row + 2}`, unit:'wt.%', raw_token: row === 1 ? '<0.01' : row === 2 ? null : String(row * 5), numeric_value: [1, 2].includes(row) ? null : row * 5, qualifier: row === 1 ? 'below_detection_limit' : null};
  return {analysis_id: `${id}-${row}`, source_id: id, source_name: 'одинаковое-имя.xlsx', sheet_name: `Лист ${index + 1}`, source_row_number: row + 2, source_orientation:'rows_are_analyses', identity: {Analysis: `${index ? 'B' : 'A'}${row+1}`, Sample:'Образец-1'}, source_metadata:{}, measurements:{F:measurement}, measurement_list:[measurement]};
}));
const project = {total:analyses.length, source_count:2, analyses, has_more:false};
function RangeFixture() {
  const [selectedIds, setSelectedIds] = React.useState([]);
  const groups = React.useRef([]);
  const views = React.useRef([]);
  const createGroup = async (fields) => {
    const group = {id: String(groups.current.length + 1), ...fields};
    groups.current.push({group, unavailable_analysis_ids: []});
    return group;
  };
  const saveView = async (fields) => {
    const view = {id: String(views.current.length + 1), data_universe_fingerprint: 'qa', ...fields};
    views.current = [...views.current, view];
    return view;
  };
  const exampleDraft = {id:'qa-draft', status:'draft', changes:[{field:'F', unit:'wt.%', old_value:'0', new_value:'0.02'}], conflict:{kind:'none', current_values:[]}};
  const fixtureEdit = {
    list: async () => ({drafts:[{draft:exampleDraft,source_cell:'B2',external_path:'C:/QA/example.xlsx'}]}),
    check: async () => exampleDraft,
    save: async () => exampleDraft,
    commit: async () => ({applied:true,draft:{...exampleDraft,status:'committed'},operation:{parameters:{backup_path:'C:/QA/example.xlsx.before-edit.bak'}}}),
  };
  return <div style={{height:'100vh',padding:16}}><AnalysesWorkspace project={project} selectedIds={selectedIds} setSelectedIds={setSelectedIds} onListWorkGroups={async () => ({groups: groups.current})} onCreateWorkGroup={createGroup} onExportSelection={()=>{}} onListTableViews={async () => ({views: views.current, data_universe_fingerprint: 'qa'})} onSaveTableView={saveView} editDraftActions={fixtureEdit} busy={false} onRefresh={()=>{}} onAddData={()=>{}} onLoadMore={()=>{}} /></div>;
}
const navigationMode = new URLSearchParams(location.search).get('screen');
const qaSource = {import_batch_id:'qa-import', source_id:sources[0], source_name:'Полевой журнал.xlsx', applied_at:'2026-11-20T12:00:00Z', analysis_count:5};
const qaOverview = async () => ({project_name:'Контрольный проект', recent_imports:[qaSource], recent_groups:[{id:'qa-group', name:'Контрольные измерения', created_at:'2026-11-20T13:00:00Z', analysis_count:2}]});
const qaSearch = async () => ({total:2, analyses:[
  {analysis_id:'qa-a1', identity:'KIV-01', sample_name:'KIV', mineral:'Апатит', method:'EPMA', sheet_name:'Анализы', source_row_number:2, source_name:qaSource.source_name},
  {analysis_id:'qa-a2', identity:'KIV-02', sample_name:'KIV', mineral:'Апатит', method:'EPMA', sheet_name:'Анализы', source_row_number:3, source_name:qaSource.source_name},
]});
const qaAxes = ['SiO2', 'Al2O3', 'MgO'].map((field) => ({field, unit:'wt.%', method:null, measurement_set:null}));
const qaPlotCatalog = async () => ({axes:qaAxes,sources:[qaSource]});
const qaPlotData = async (kind, axes) => ({kind, axes, input_count:3, excluded_count:0,
  ticks:[[{at:0,label:'10'},{at:0.5,label:'25'},{at:1,label:'40'}],[{at:0,label:'5'},{at:0.5,label:'15'},{at:1,label:'25'}]],
  points:[
    {analysis_id:'qa-p1',label:'KIV-01',source_id:qaSource.source_id,source_name:qaSource.source_name,values:[20,30,50],u:0.48,v:0.48},
    {analysis_id:'qa-p2',label:'KIV-02',source_id:qaSource.source_id,source_name:qaSource.source_name,values:[30,40,30],u:0.55,v:0.25},
    {analysis_id:'qa-p3',label:'KIV-03',source_id:qaSource.source_id,source_name:qaSource.source_name,values:[40,20,40],u:0.70,v:0.36},
  ]});
function PlotFixture() {
  const [selectedIds,setSelectedIds] = React.useState([]);
  const [sourceHidden,setSourceHidden] = React.useState(false);
  const [hidden,setHidden] = React.useState([]);
  const layouts = React.useRef([]);
  const loadLayouts = React.useCallback(async () => layouts.current,[]);
  const saveLayout = async (draft) => {
    const saved = {...draft,id:crypto.randomUUID(),
      legend:{entries:Object.entries(draft.colors).map(([value,color]) => ({value,color}))}};
    layouts.current = [...layouts.current,saved];
    return saved;
  };
  const openLayout = async (id) => {
    const saved = layouts.current.find(item => item.id === id);
    setHidden(saved.hidden_analysis_ids);
    setSourceHidden(saved.hidden_source_ids.length > 0);
    return saved;
  };
  const loadData = React.useCallback(async (kind,axes,layers) => {
    const data = await qaPlotData(kind,axes);
    const points = sourceHidden ? [] : data.points.filter(point => !hidden.includes(point.analysis_id));
    const fields = layers.filter(layer => layer.field?.visible).map(layer => ({
      layer_id:layer.id, vertices:points.filter(point => layer.analysis_ids.includes(point.analysis_id)).map(({u,v}) => [u,v]),
    }));
    return {...data, points, fields, hidden_count:data.input_count-points.length};
  },[sourceHidden,hidden]);
  return <PlotWorkspace loadCatalog={qaPlotCatalog} loadData={loadData} selectedIds={selectedIds} setSelectedIds={setSelectedIds}
    loadLayouts={loadLayouts} saveLayout={saveLayout} openLayout={openLayout} onExportSvg={async () => "PetroLab-plot.svg"}
    hiddenSourceIds={sourceHidden ? [qaSource.source_id] : []} onToggleSource={() => setSourceHidden(value => !value)}
    hiddenAnalysisIds={hidden} onSetVisibility={(ids,hide) => setHidden(current => hide ? [...new Set([...current,...ids])] : current.filter(id => !ids.includes(id)))}
    onBack={()=>{}} />;
}
const qaSample = {
  sample_id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd', sample_name:'SM-01B',
  minerals:['Плагиоклаз','Пироксен'], analysis_count:24, sources:[{...qaSource,analysis_count:24}],
  context:{locality:'Северный массив · обнажение 12',storage:'ящик 4, кассета В',collection_position:'2,4 м от подошвы',
    collector:'Иванов А. С.',collection_date:'2024-05-15',revision:1},
  notes:[{note_id:'note-1',author:'Иванов А. С.',body:'Свежая поверхность отбора, без заметных следов выветривания.',created_at:'2026-11-19T09:35:00Z'}],
  points:[{analytical_point_id:'qa-point',point_name:'P-01',analysis_count:2}], thin_sections:[], images:[],
};
const loadQaSamples = async () => [qaSample];
const loadQaSample = async () => qaSample;
createRoot(document.getElementById('root')).render(navigationMode === 'overview'
  ? <ProjectOverview load={qaOverview} project={project} selectionCount={1} onSource={()=>{}} onGroup={()=>{}} />
  : navigationMode === 'search'
    ? <ProjectSearch seed={{mineral:'Апатит'}} queryProject={qaSearch} selectionCount={1} onAddSelection={()=>{}} onOpenAnalysis={()=>{}} />
    : navigationMode === 'plot' ? <PlotFixture /> : navigationMode === 'sample'
      ? <SampleWorkspace loadSamples={loadQaSamples} loadSample={loadQaSample} onOpenAnalyses={()=>{}} />
      : <RangeFixture />);
