// @vitest-environment jsdom
import {afterEach,expect,test,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {useState} from "react";
import {PhotoPlot} from "../src/PhotoPlot";
afterEach(cleanup);
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
