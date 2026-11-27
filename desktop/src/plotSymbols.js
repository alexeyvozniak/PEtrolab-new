const BASE_LABELS={circle:"Круг",square:"Квадрат",triangle:"Треугольник",diamond:"Ромб",triangle_down:"Треугольник вниз",pentagon:"Пятиугольник",hexagon:"Шестиугольник",star:"Звезда",plus:"Плюс",cross:"Крест"};
export const SYMBOL_LABELS=Object.freeze({...BASE_LABELS,...Object.fromEntries(Object.entries(BASE_LABELS).map(([key,label])=>[key+"_open",label+" · контур"]))});
export function symbolPaint(symbol,color) {
  return symbol?.endsWith("_open") ? {fill:"none",stroke:color,"stroke-width":1.25} : {fill:color};
}
// All vertices fit the same circumscribed radius as the circle.
export function symbolGeometry(symbol,x,y,r) {
  const base=(symbol||"circle").replace(/_open$/,"");
  const polygon=points=>({tag:"polygon",attrs:{points:points.map(p=>p.join(",")).join(" ")}});
  if(base==="square") {
    const d=r/Math.SQRT2;
    return polygon([[x-d,y-d],[x+d,y-d],[x+d,y+d],[x-d,y+d]]);
  }
  if(base==="triangle")return polygon([[x,y-r],[x+r*Math.sqrt(3)/2,y+r/2],[x-r*Math.sqrt(3)/2,y+r/2]]);
  if(base==="triangle_down")return polygon([[x,y+r],[x-r*Math.sqrt(3)/2,y-r/2],[x+r*Math.sqrt(3)/2,y-r/2]]);
  if(base==="diamond")return polygon([[x,y-r],[x+r,y],[x,y+r],[x-r,y]]);
  if(["pentagon","hexagon","star"].includes(base)){
    const count=base==="pentagon"?5:base==="hexagon"?6:10;
    return polygon(Array.from({length:count},(_,i)=>{
      const angle=-Math.PI/2+2*Math.PI*i/count, radius=base==="star"&&i%2?r*.43:r;
      return [x+Math.cos(angle)*radius,y+Math.sin(angle)*radius];
    }));
  }
  if(base==="plus"||base==="cross"){
    const t=.28, a=Math.sqrt(1-t*t),angle=base==="cross"?Math.PI/4:0;
    const points=[[-t,-a],[t,-a],[t,-t],[a,-t],[a,t],[t,t],[t,a],[-t,a],[-t,t],[-a,t],[-a,-t],[-t,-t]];
    return polygon(points.map(([u,v])=>[x+r*(u*Math.cos(angle)-v*Math.sin(angle)),y+r*(u*Math.sin(angle)+v*Math.cos(angle))]));
  }
  return {tag:"circle",attrs:{cx:x,cy:y,r}};
}
