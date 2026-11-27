import {useState} from "react";
import {GrainPreview} from "./GrainPreview";

const format = new Intl.NumberFormat("ru", {maximumSignificantDigits: 7});
const pointKey = point => JSON.stringify([point.spatial_annotation_id, point.analysis_id]);
const axisLabel = axis => [axis.field, axis.unit, axis.measurement_set, axis.method].filter(Boolean).join(" · ");
const reasons = {
  below_detection_limit: "ниже предела обнаружения",
  duplicate_measurements: "несколько измерений",
  missing: "нет измерения",
  no_matching_axes: "нет данных для выбранной оси",
  zero_denominator: "нулевой знаменатель",
  incompatible_iron_form: "другая форма железа",
};

function ProfileChart({result, onFocus, loadPhotos, previewPhoto}) {
  const [hover, setHover] = useState(null);
  const {points, axis} = result;
  const shown = points.filter(point => point.value !== null);
  const minimum = Math.min(...shown.map(point => point.value));
  const maximum = Math.max(...shown.map(point => point.value));
  const end = points.at(-1).distance_um;
  const x = point => 55 + (end ? 325 * point.distance_um / end : 0);
  const magnitude = Math.max(Math.abs(minimum), Math.abs(maximum));
  const y = point => maximum === minimum ? 90
    : 155 - 130 * (point.value / magnitude - minimum / magnitude) / (maximum / magnitude - minimum / magnitude);
  return <>
    {shown.length ? <figure className="zoning-profile-chart">
      <figcaption>{axisLabel(axis)}</figcaption>
      <svg viewBox="0 0 400 195" role="img" aria-label={axisLabel(axis) + " по расстоянию в мкм"}>
      <path d="M55 25 V155 H380" stroke="currentColor" fill="none"/>
      <text x="55" y="18">{format.format(maximum)}</text>
      {maximum !== minimum && <text x="5" y="155">{format.format(minimum)}</text>}
      <text x="55" y="178">0</text><text x="380" y="178" textAnchor="end">{format.format(end)} мкм</text>
      {points.map((point, index) => {
        if (point.value === null) return null;
        const previous = points[index - 1];
        return <g key={pointKey(point)}>
          {previous?.value != null && <line x1={x(previous)} y1={y(previous)} x2={x(point)} y2={y(point)} stroke="#34704e"/>}
          <circle cx={x(point)} cy={y(point)} r="4" fill="#34704e" tabIndex={0}
            aria-label={`${format.format(point.distance_um)} мкм · ${format.format(point.value)}`}
            onMouseEnter={() => setHover(point.analysis_id)} onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(point.analysis_id)} onBlur={() => setHover(null)}>
            <title>{point.analysis_id}</title>
          </circle>
        </g>;
      })}
      </svg>
      {hover && loadPhotos && <div className="profile-grain-tooltip" role="tooltip">
        <GrainPreview key={hover} id={hover} mediaId={result.media_asset_id} loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>
      </div>}
    </figure> : <p>Для выбранной оси нет пригодных значений.</p>}
    <ol>{points.map(point => <li key={pointKey(point)}>
      <button type="button" className="outline-button" onClick={() => onFocus([point.analysis_id])}>
        {format.format(point.distance_um)} мкм · {point.value === null ? "нет значения" : format.format(point.value)}
      </button>
      {point.value === null && <small> {reasons[point.reason] || "значение непригодно для этой оси"}</small>}
    </li>)}</ol>
  </>;
}

export function ZoningProfile({mediaId, rows, focusedIds, panels, load, onFocus, loadPhotos, previewPhoto,
  calibration, onPickScale, onClearScale}) {
  const [route, setRoute] = useState([]);
  const [choice, setChoice] = useState("");
  const [axisKey, setAxisKey] = useState("");
  const [pixels, setPixels] = useState("");
  const [length, setLength] = useState("");
  const [pending, setPending] = useState(false);
  const [response, setResponse] = useState(null);
  const axes = new Map(panels.flatMap(panel => panel.axes).map(axis => [JSON.stringify(axis), axis]));
  const allowed = rows.filter(row => row.geometry_kind === "point" && row.link_type === "same_point"
    && row.cross_sample_exception === 0);
  const candidates = allowed.filter(row => !route.some(point =>
    point.analysis_id === row.analysis_id || point.spatial_annotation_id === row.spatial_annotation_id));
  const selected = candidates.find(row => pointKey(row) === choice);
  const axis = axes.get(axisKey);
  const [first, second] = calibration?.points || [];
  const measuredPixels = second ? Math.hypot(second.x_px-first.x_px, second.y_px-first.y_px) : null;
  const referencePixels = calibration ? measuredPixels : Number(pixels);
  const request = {media_asset_id: mediaId, points: route.map(({spatial_annotation_id, analysis_id}) =>
    ({spatial_annotation_id, analysis_id})), axis, reference_px: referencePixels, reference_um: Number(length)};
  const signature = JSON.stringify(request);
  const current = response?.signature === signature ? response : null;
  const move = (index, delta) => {
    setResponse(null);
    setRoute(items => {
      const next = [...items];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    });
  };
  const submit = async event => {
    event.preventDefault();
    setPending(true);
    setResponse(null);
    try { setResponse({signature, result: await load(request)}); }
    catch (error) { setResponse({signature, error: error.message || String(error)}); }
    finally { setPending(false); }
  };
  return <details>
    <summary>Профиль зональности</summary>
    <form onSubmit={submit}>
      <fieldset disabled={pending}>
        <legend>Маршрут и масштаб</legend>
        <label>Точка и Analysis ID <select value={selected ? choice : ""} onChange={e => setChoice(e.target.value)}>
          <option value="">Выберите связь</option>
          {candidates.filter(row => focusedIds.includes(row.analysis_id)).map(row =>
            <option key={pointKey(row)} value={pointKey(row)}>{row.point_name} · {row.analysis_id}</option>)}
          {candidates.filter(row => !focusedIds.includes(row.analysis_id)).map(row =>
            <option key={pointKey(row)} value={pointKey(row)}>{row.point_name} · {row.analysis_id}</option>)}
        </select></label>
        <button type="button" disabled={!selected || route.length >= 100} onClick={() => {
          setRoute(items => [...items, selected]); setChoice(""); setResponse(null);
        }}>Добавить точку в маршрут</button>
        {!allowed.length && <p>Для профиля нужны точечные связи same_point на этом фото.</p>}
        <ol>{route.map((point, index) => <li key={pointKey(point)}>
          {point.point_name} · {point.analysis_id} · {point.x_px}, {point.y_px} px
          <button type="button" disabled={index === 0} onClick={() => move(index, -1)}>Выше</button>
          <button type="button" disabled={index === route.length - 1} onClick={() => move(index, 1)}>Ниже</button>
          <button type="button" onClick={() => {
            setRoute(items => items.filter(item => item !== point)); setResponse(null);
          }}>Убрать</button>
        </li>)}</ol>
        <label>Ось профиля <select value={axis ? axisKey : ""} onChange={e => {setAxisKey(e.target.value); setResponse(null);}}>
          <option value="">Выберите ось</option>
          {[...axes].map(([key, value]) => <option key={key} value={key}>{axisLabel(value)}</option>)}
        </select></label>
        {onPickScale&&<button type="button" className="outline-button" onClick={()=>{setResponse(null);onPickScale();}}>Указать концы линейки на фото</button>}
        {calibration ? <p>
          {measuredPixels === null ? "Выберите две точки на фото." : measuredPixels === 0
            ? "Концы линейки совпадают. Выберите их заново." : `Длина на оригинале: ${format.format(measuredPixels)} px`}
          <button type="button" className="outline-button" onClick={()=>{setResponse(null);onClearScale();}}>Ввести пиксели вручную</button>
        </p> : <label>Длина на оригинале, px <input type="number" min="0" step="any" required value={pixels} onChange={e => {setPixels(e.target.value); setResponse(null);}}/></label>}
        <label>Длина в микрометрах <input type="number" min="0" step="any" required value={length} onChange={e => {setLength(e.target.value); setResponse(null);}}/></label>
        <button type="submit" className="primary-button" disabled={route.length < 2 || !axis || !(referencePixels > 0 && Number(length) > 0)}>
          Построить профиль
        </button>
      </fieldset>
    </form>
    {pending && <p role="status">Строю профиль…</p>}
    {current?.error && <p role="alert">{current.error}</p>}
    {current?.result && <ProfileChart result={current.result} onFocus={onFocus} loadPhotos={loadPhotos} previewPhoto={previewPhoto}/>}
  </details>;
}
