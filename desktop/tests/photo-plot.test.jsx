// @vitest-environment jsdom
import {afterEach,expect,test,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {useState} from "react";
import {PhotoPlot} from "../src/PhotoPlot";
import {ZoningProfile} from "../src/ZoningProfile";
import {GrainPreview} from "../src/GrainPreview";
afterEach(cleanup);
test("grain preview crops original pixels at the edge and prefers the explicitly selected photo",async()=>{
  const links=["other","chosen"].map(media_asset_id=>({
    media_asset_id, display_name:media_asset_id, point_name:"P7", link_type:"same_point",
    geometry_kind:"point", cross_sample_exception:0, image_width_px:1000, image_height_px:200, x_px:997, y_px:12,
  }));
  const loadPhotos=vi.fn(async()=>links);
  const previewPhoto=vi.fn(async()=>({preview_url:"/fragment.png"}));
  const {rerender}=render(<GrainPreview id="a" loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>);
  await screen.findByText(/Точных привязок: 2/);
  expect(previewPhoto).not.toHaveBeenCalled();
  rerender(<GrainPreview id="a" mediaId="chosen" loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>);
  expect((await screen.findByRole("img",{name:"Фрагмент вокруг точки P7"})).getAttribute("src")).toBe("/fragment.png");
  expect(previewPhoto).toHaveBeenCalledWith("chosen",{left:680,top:0,width:320,height:200});
});

test("a late response does not display a previous analysis or use a context link",async()=>{
  let resolveOld;
  const location={media_asset_id:"m",point_name:"old",geometry_kind:"point",cross_sample_exception:0,
    image_width_px:500,image_height_px:500,x_px:240,y_px:240};
  const loadPhotos=vi.fn(id=>id==="old"
    ? new Promise(resolve=>{resolveOld=resolve;})
    : Promise.resolve([{...location,link_type:"same_zone"}]));
  const previewPhoto=vi.fn();
  const {rerender}=render(<GrainPreview id="old" loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>);
  await waitFor(()=>expect(loadPhotos).toHaveBeenCalledWith("old"));
  rerender(<GrainPreview id="new" loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>);
  await waitFor(()=>expect(loadPhotos).toHaveBeenCalledWith("new"));
  resolveOld([{...location,link_type:"same_point"}]);
  await waitFor(()=>expect(screen.queryByText("Загружаю фото…")).toBeNull());
  expect(previewPhoto).not.toHaveBeenCalled();
});
test("profile submits ordered exact IDs and displays a gap without joining across it",async()=>{
  const axis={field:"MgO",unit:"wt.%"};
  const rows=["a","b","c","context"].map((id,index)=>({
    spatial_annotation_id:id,analysis_id:"id-"+id,point_name:id,geometry_kind:"point",
    cross_sample_exception:0,link_type:index===3?"same_zone":"same_point",x_px:index,y_px:0,
  }));
  const load=vi.fn(async request=>({axis,points:request.points.map((point,index)=>({
    ...point,distance_um:10*index,value:index===1?null:index+1,reason:"missing",
  }))}));
  const {container}=render(<ZoningProfile mediaId="m" rows={rows} focusedIds={[]} panels={[{axes:[axis]}]} load={load} onFocus={()=>{}}
    calibration={{points:[{x_px:1,y_px:1},{x_px:4,y_px:5}]}}/>);
  fireEvent.click(screen.getByText("Профиль зональности"));
  const point=screen.getByLabelText("Точка и Analysis ID");
  expect([...point.options].map(option=>option.textContent)).not.toContain("context · id-context");
  for(const id of ["a","b","c"]){
    fireEvent.change(point,{target:{value:JSON.stringify([id,"id-"+id])}});
    fireEvent.click(screen.getByRole("button",{name:"Добавить точку в маршрут"}));
  }
  fireEvent.change(screen.getByLabelText("Ось профиля"),{target:{value:JSON.stringify(axis)}});
  expect(screen.getByText("Длина на оригинале: 5 px")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Длина в микрометрах"),{target:{value:"10"}});
  fireEvent.click(screen.getByRole("button",{name:"Построить профиль"}));
  await screen.findByText("10 мкм · нет значения");
  expect(load.mock.calls[0][0].points.map(point=>point.analysis_id)).toEqual(["id-a","id-b","id-c"]);
  expect(load.mock.calls[0][0].reference_px).toBe(5);
  expect(container.querySelectorAll("svg circle")).toHaveLength(2);
  expect(container.querySelectorAll("svg line")).toHaveLength(0);
});
const link={media_asset_id:"m",display_name:"BSE",sample_name:"S",point_name:"P",
  spatial_annotation_id:"a",analytical_point_id:"p",x_px:120,y_px:240,link_type:"same_zone"};
const preview=vi.fn(async()=>({width_px:1000,height_px:800,preview_url:"/test.png",
  annotations:[{...link,geometry_kind:"point"}]}));
test("annotation exposes every exact ID and contextual link; selection changes only on explicit add",async()=>{
  const add=vi.fn();
  const loadPhotos=vi.fn(async id=>[{...link,link_type:id==="id1"?"same_point":"same_zone"}]);
  function Harness(){
    const [view,setView]=useState({media_asset_id:"m",panel_ids:["plot"]});
    const [focus,setFocus]=useState([]);
    return <PhotoPlot inputIds={["id1","id2"]} loadPhotos={loadPhotos} preview={preview}
      view={view} setView={setView} panels={[{id:"plot",axes:[{field:"MgO"}]}]}
      focusedIds={focus} setFocusedIds={setFocus} addToSelection={add}/>;
  }
  render(<Harness/>);
  await waitFor(()=>expect(loadPhotos).toHaveBeenCalledTimes(2));
  fireEvent.click(await screen.findByRole("button",{name:"Открыть точку P"}));
  expect(await screen.findByText("Analysis ID: id1")).toBeTruthy();
  expect(screen.getByText("Analysis ID: id2")).toBeTruthy();
  expect(screen.getByText("Эта связь не подтверждает точное место измерения.")).toBeTruthy();
  expect(add).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Добавить в отбор · 2"}));
  expect(add).toHaveBeenCalledWith(["id1","id2"]);
  expect(screen.getAllByText(/x 120, y 240/)).toHaveLength(2);
});
test("plot focus never substitutes a similarly named analysis or another photo",async()=>{
  render(<PhotoPlot inputIds={["other"]} loadPhotos={async()=>[{...link,media_asset_id:"other-photo"}]}
    preview={preview} view={{media_asset_id:"m",panel_ids:["plot"]}} setView={()=>{}}
    panels={[]} focusedIds={["other"]} setFocusedIds={()=>{}} addToSelection={()=>{}}/>);
  expect(await screen.findByText(/Для этих Analysis ID/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"Добавить в отбор · 0"}).disabled).toBe(true);
});
