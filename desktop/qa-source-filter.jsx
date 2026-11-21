import React from 'react';
import { createRoot } from 'react-dom/client';
import { AnalysesWorkspace } from './src/AnalysesWorkspace';
import { ProjectOverview, ProjectSearch } from './src/ProjectNavigation';
import { PlotWorkspace } from './src/PlotWorkspace';
import { SampleWorkspace } from './src/SampleWorkspace';
import { MediaViewer } from './src/MediaWorkspace';
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
function PrecisionFixture({ reopen = false }) {
  const [point, setPoint] = React.useState(null);
  const [selectedIds, setSelectedIds] = React.useState([]);
  const savedLinks = React.useRef([]);
  const savedPhotos = React.useRef({});
  const image = React.useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1600;
    canvas.height = 1000;
    const context = canvas.getContext("2d");
    for (let y = 0; y < canvas.height; y += 18) {
      for (let x = 0; x < canvas.width; x += 18) {
        context.fillStyle = ['#334849', '#607576', '#97a19a', '#c4c4a3'][(x / 18 + y / 18) % 4];
        context.fillRect(x, y, 18, 18);
      }
    }
    const preview = document.createElement("canvas");
    preview.width = 400;
    preview.height = 250;
    preview.getContext("2d").drawImage(canvas, 0, 0, 400, 250);
    return { canvas, width_px: canvas.width, height_px: canvas.height, preview_url: preview.toDataURL("image/jpeg") };
  }, []);
  const loadRegion = async (region) => {
    const canvas = document.createElement("canvas");
    canvas.width = region.width;
    canvas.height = region.height;
    canvas.getContext("2d").drawImage(image.canvas, region.left, region.top, region.width, region.height,
      0, 0, region.width, region.height);
    return { region, preview_url: canvas.toDataURL() };
  };
  if (reopen) {
    const photo = { thin_section_id: 'section', media_asset_id: 'ppl', display_name: 'PPL-detail.png', media_type: 'PPL',
      width_px: image.width_px, height_px: image.height_px };
    const sample = { ...qaSample, sample_name: 'KIV-2', thin_sections: [{ thin_section_id: 'section', thin_section_name: 'KIV-2-A' }],
      images: [{ thin_section_id: 'section', media_asset_id: 'bse', display_name: 'KIV-2-A-BSE.png', media_type: 'BSE',
        width_px: image.width_px, height_px: image.height_px }, photo] };
    const annotations = [{ spatial_annotation_id: 'annotation-1', analytical_point_id: 'point-1', point_sample_id: sample.sample_id,
      geometry_kind: 'point', point_name: 'P-01', x_px: 1080, y_px: 380 }];
    const candidates = [
      { analysis_id: 'epma', identity: 'EPMA #431', method: 'EPMA', mineral: 'Флогопит', source_name: 'epma.xlsx', sheet_name: 'Oxides', source_row_number: 5, active: true },
      { analysis_id: 'laser', identity: 'LA-ICP-MS #87', method: 'LA-ICP-MS', mineral: 'Флогопит', source_name: 'laser.xlsx', sheet_name: 'Trace', source_row_number: 9, active: true },
    ];
    return <SampleWorkspace initialTab="Шлифы" loadSamples={async () => [sample]} loadSample={async () => sample}
      mediaLinks={{ list: async (id) => savedPhotos.current[id] ?? [],
        createRegion: async (_, { kind, ...geometry }) => ({ ...geometry, geometry_kind: kind, spatial_annotation_id: 'area-1', label: 'Z-01' }),
        change: async (id, asset, attached) => {
          savedPhotos.current[id] = attached ? [{ ...photo, media_link_id: `${id}-${asset}` }] : [];
        } }}
      pointLinks={{ selectedIds, loadPoint: async () => savedLinks.current,
        queryProject: async (search) => ({ analyses: candidates.filter((row) => row.identity.toLowerCase().includes(search.query.toLowerCase())), has_more: false }),
        createManualAnalysis: async (_, entry) => {
          if (Object.values(entry.measurements).includes('неизвестно')) throw new Error('Введите число или значение ниже предела обнаружения.');
          savedLinks.current = [...savedLinks.current, { analysis_id: `manual-${entry.identity}`, identity: entry.identity,
            method: entry.method, source_name: 'Ручной ввод.csv', active: true }];
        },
        changeLink: async (_, ids, type) => { savedLinks.current = type
          ? candidates.filter((row) => ids.includes(row.analysis_id)) : savedLinks.current.filter((row) => row.analysis_id !== ids); },
        addToSelection: (id) => setSelectedIds((current) => [...current, id]), openAnalysis: () => {} }}
      previewMedia={(_, region) => region ? loadRegion(region) : Promise.resolve({ ...image, annotations })} />;
  }
  return <MediaViewer image={image} loadRegion={loadRegion} onPlace={setPoint}
    annotations={point ? [{ ...point, id: "qa-point", label: "P-01" }] : []} />;
}
createRoot(document.getElementById('root')).render(navigationMode === 'overview'
  ? <ProjectOverview load={qaOverview} project={project} selectionCount={1} onSource={()=>{}} onGroup={()=>{}} />
  : navigationMode === 'search'
    ? <ProjectSearch seed={{mineral:'Апатит'}} queryProject={qaSearch} selectionCount={1} onAddSelection={()=>{}} onOpenAnalysis={()=>{}} />
    : navigationMode === 'plot' ? <PlotFixture /> : navigationMode === 'sample'
      ? <SampleWorkspace loadSamples={loadQaSamples} loadSample={loadQaSample} onOpenAnalyses={()=>{}} />
      : navigationMode === 'precision' || navigationMode === 'precision-reopen'
        ? <PrecisionFixture reopen={navigationMode === 'precision-reopen'} /> : <RangeFixture />);
