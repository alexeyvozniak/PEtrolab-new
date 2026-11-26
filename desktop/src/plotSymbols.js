export const SYMBOL_LABELS={circle:"Круг",square:"Квадрат",triangle:"Треугольник",diamond:"Ромб"};
// All vertices fit the same circumscribed radius as the circle, so hit
// testing and selection halos retain their geometric meaning.
export function symbolGeometry(symbol,x,y,r) {
  if(symbol==="square") {
    const d=r/Math.SQRT2;
    return {tag:"polygon",attrs:{points:[[x-d,y-d],[x+d,y-d],[x+d,y+d],[x-d,y+d]].map(p=>p.join(",")).join(" ")}};
  }
  if(symbol==="triangle")return {tag:"polygon",attrs:{points:[[x,y-r],[x+r*Math.sqrt(3)/2,y+r/2],[x-r*Math.sqrt(3)/2,y+r/2]].map(p=>p.join(",")).join(" ")}};
  if(symbol==="diamond")return {tag:"polygon",attrs:{points:[[x,y-r],[x+r,y],[x,y+r],[x-r,y]].map(p=>p.join(",")).join(" ")}};
  return {tag:"circle",attrs:{cx:x,cy:y,r}};
}
