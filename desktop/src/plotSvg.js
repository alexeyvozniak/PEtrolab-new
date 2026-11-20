const SVG = "http://www.w3.org/2000/svg";
export const PLOT_SIZE = { width: 460, height: 280 };
const COPY_ATTRIBUTES = ["x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "d", "text-anchor", "transform",
  "points", "fill-opacity", "stroke", "stroke-width", "opacity"];

export function buildPlotSvg(canvases) {
  const { width, height } = PLOT_SIZE;
  const columns = Math.min(canvases.length, 2);
  const rows = Math.ceil(canvases.length / columns);
  const document = canvases[0].svg.ownerDocument;
  const create = (tag, attributes = {}) => {
    const element = document.createElementNS(SVG, tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    return element;
  };
  const root = create("svg", {
    width: columns * width, height: rows * height, viewBox: `0 0 ${columns * width} ${rows * height}`,
  });
  for (const [index, { svg, panelIndex }] of canvases.entries()) {
    const offsetX = (index % columns) * width;
    const offsetY = Math.floor(index / columns) * height;
    const label = panelIndex < 26 ? String.fromCharCode(97 + panelIndex) : `a${String.fromCharCode(97 + panelIndex - 26)}`;
    const group = create("g", { id: `panel-${label}`, transform: `translate(${offsetX} ${offsetY})` });
    const letter = create("text", { x: 10, y: 17, fill: "#24392d", "font-size": 13, "font-family": "Arial" });
    letter.textContent = label;
    group.append(letter);
    for (const source of svg.querySelectorAll("path.plot-frame, line, text, circle.plot-point, polygon.plot-field")) {
      const element = create(source.localName);
      for (const name of COPY_ATTRIBUTES) {
        if (source.hasAttribute(name)) element.setAttribute(name, source.getAttribute(name));
      }
      if (source.localName === "path") {
        element.setAttribute("fill", "none");
        element.setAttribute("stroke", "#76897b");
      } else if (source.localName === "line") {
        element.setAttribute("stroke", "#e2e8e2");
      } else if (source.localName === "text") {
        element.setAttribute("fill", "#31473a");
        element.setAttribute("font-size", "10");
        element.setAttribute("font-family", "Arial");
        element.textContent = source.textContent;
      } else {
        const fill = source.getAttribute("fill") || "";
        element.setAttribute("fill", /^#[0-9a-f]{6}$/i.test(fill) ? fill : "#527eac");
      }
      group.append(element);
    }
    root.append(group);
  }
  return new XMLSerializer().serializeToString(root);
}
