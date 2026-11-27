export function duplicatePanel(panels,id,newId,max=32) {
  const index=panels.findIndex(p=>p.id===id);
  if(index<0 || panels.length>=max || !newId || panels.some(p=>p.id===newId))return panels;
  const next=[...panels];
  next.splice(index+1,0,{...JSON.parse(JSON.stringify(panels[index])),id:newId});
  return next;
}
const clamp=(v,min,max)=>Math.max(min,Math.min(v,max));
// Display-only viewport: no change to scientific coordinates.
export function selectionView(points,full,padding=18,maxZoom=8) {
  let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
  for(const point of points){
    if(!Number.isFinite(point.x)||!Number.isFinite(point.y))continue;
    left=Math.min(left,point.x);right=Math.max(right,point.x);
    top=Math.min(top,point.y);bottom=Math.max(bottom,point.y);
  }
  if(!Number.isFinite(left))return null;
  const aspect=full.width/full.height;
  const width=clamp(Math.max(right-left+2*padding,(bottom-top+2*padding)*aspect),full.width/maxZoom,full.width);
  const height=width/aspect;
  return {x:clamp((left+right-width)/2,full.x,full.x+full.width-width),
    y:clamp((top+bottom-height)/2,full.y,full.y+full.height-height),width,height};
}
