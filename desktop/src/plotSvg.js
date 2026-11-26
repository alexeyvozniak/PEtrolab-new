import {symbolGeometry,symbolPaint} from "./plotSymbols";
const SVG = "http://www.w3.org/2000/svg";
export const PLOT_SIZE = { width: 460, height: 280 };
const COPY_ATTRIBUTES = ["x", "y", "width", "height", "x1", "x2", "y1", "y2", "cx", "cy", "r", "d", "text-anchor", "transform",
  "points", "fill-opacity", "stroke", "stroke-width", "opacity"];

export function plotPanelLabel(index, alphabet = "latin", uppercase = false) {
  const letters = alphabet === "cyrillic" ? "абвгдежзийклмнопрстуфхцчшщъыьэюя" : "abcdefghijklmnopqrstuvwxyz";
  const label = (index >= letters.length ? letters[0] : "") + letters[index % letters.length];
  return uppercase ? label.toUpperCase() : label;
}

export function buildPlotSvg(canvases, { showLabel = true, alphabet, uppercase, labelPosition, legend } = {}) {
  const { width, height } = PLOT_SIZE;
  const columns = Math.min(canvases.length, 2);
  const rows = Math.ceil(canvases.length / columns);
  const document = canvases[0].svg.ownerDocument;
  const create = (tag, attributes = {}) => {
    const element = document.createElementNS(SVG, tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    return element;
  };
  const legendHeight = legend ? 38 + legend.entries.length * 16 + (legend.histogramNote ? 18 : 0) : 0;
  const totalHeight = rows * height + legendHeight;
  const root = create("svg", {
    width: columns * width, height: totalHeight, viewBox: `0 0 ${columns * width} ${totalHeight}`,
  });
  for (const [index, { svg, panelIndex }] of canvases.entries()) {
    const offsetX = (index % columns) * width;
    const offsetY = Math.floor(index / columns) * height;
    const label = plotPanelLabel(panelIndex, alphabet, uppercase);
    const group = create("g", { id: `panel-${label}`, transform: `translate(${offsetX} ${offsetY})` });
    if (showLabel) {
      const right = labelPosition === "right";
      const letter = create("text", { x: right ? width - 12 : 10, y: 17, "text-anchor": right ? "end" : "start",
        fill: "#24392d", "font-size": 13, "font-family": "Arial" });
      letter.textContent = label;
      group.append(letter);
    }
    for (const source of svg.querySelectorAll("path.plot-frame, path.plot-series, line, text, circle.plot-point, rect.plot-point, polygon.plot-point, polygon.plot-field")) {
      const element = create(source.localName);
      for (const name of COPY_ATTRIBUTES) {
        if (source.hasAttribute(name)) element.setAttribute(name, source.getAttribute(name));
      }
      if (source.localName === "path") {
        element.setAttribute("fill", "none");
        if (source.classList.contains("plot-frame")) element.setAttribute("stroke", "#76897b");
      } else if (source.localName === "line") {
        element.setAttribute("stroke", "#e2e8e2");
      } else if (source.localName === "text") {
        element.setAttribute("fill", "#31473a");
        element.setAttribute("font-size", "10");
        element.setAttribute("font-family", "Arial");
        element.textContent = source.textContent;
      } else {
        const fill = source.getAttribute("fill") || "";
        element.setAttribute("fill", (source.classList.contains("plot-field") || source.classList.contains("plot-point")) && fill==="none" ? "none" : /^#[0-9a-f]{6}$/i.test(fill) ? fill : "#527eac");
      }
      group.append(element);
    }
    root.append(group);
  }
  if (legend) {
    const group = create("g", {id:"category-legend", transform:`translate(0 ${rows * height})`});
    const addText = (x,y,value) => {
      const element = create("text",{x,y,fill:"#31473a","font-size":"10","font-family":"Arial"});
      element.textContent = value;
      group.append(element);
    };
    addText(12,18,legend.title);
    legend.entries.forEach((entry,index) => {
      const y = 30 + index * 16;
      if(entry.symbol){
        const {tag,attrs}=symbolGeometry(entry.symbol,17,y+5,5);
        group.append(create(tag,{...attrs,...symbolPaint(entry.symbol,entry.color)}));
      }else group.append(create("rect",{x:12,y,width:10,height:10,fill:entry.color}));
      const label = entry.label.length > 54 ? entry.label.slice(0,51) + "…" : entry.label;
      addText(28,y+9,label + " · " + entry.count);
    });
    if (legend.histogramNote) addText(12,30 + legend.entries.length * 16 + 9,"Гистограммы окрашены по источникам.");
    root.append(group);
  }
  return new XMLSerializer().serializeToString(root);
}
