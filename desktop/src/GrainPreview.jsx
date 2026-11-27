import {useEffect, useState} from "react";

export function grainPreviewRegion(row) {
  const {image_width_px: width, image_height_px: height, x_px: x, y_px: y} = row;
  if (![width, height].every(value => Number.isInteger(value) && value > 0)
      || ![x, y].every(Number.isFinite) || x < 0 || x >= width || y < 0 || y >= height) return null;
  const cropWidth = Math.min(width, 320);
  const cropHeight = Math.min(height, 320);
  return {
    left: Math.max(0, Math.min(width - cropWidth, Math.floor(x - cropWidth / 2))),
    top: Math.max(0, Math.min(height - cropHeight, Math.floor(y - cropHeight / 2))),
    width: cropWidth, height: cropHeight,
  };
}

export function GrainPreview({id, mediaId, loadPhotos, previewPhoto}) {
  const [state, setState] = useState(null);
  const current = state?.id === id && state.mediaId === mediaId ? state : null;
  useEffect(() => {
    if (!id || !loadPhotos || !previewPhoto) return;
    let active = true;
    const show = result => { if (active) setState({id, mediaId, ...result}); };
    const timer = setTimeout(async () => {
      show({loading: true});
      try {
        const rows = await loadPhotos(id);
        if (!active) return;
        const matches = rows.filter(row => (!mediaId || row.media_asset_id === mediaId)
          && row.link_type === "same_point" && row.geometry_kind === "point" && row.cross_sample_exception === 0);
        if (matches.length !== 1) {
          show({message: matches.length > 1 ? `Точных привязок: ${matches.length}. Выберите фото через меню точки.` : ""});
          return;
        }
        const row = matches[0];
        const region = grainPreviewRegion(row);
        if (!region) { show({message: "Координаты метки недоступны."}); return; }
        const image = await previewPhoto(row.media_asset_id, region);
        show({row, region, url: image.preview_url});
      } catch {
        show({message: "Фото недоступно."});
      }
    }, 180);
    return () => { active = false; clearTimeout(timer); };
  }, [id, mediaId, loadPhotos, previewPhoto]);
  if (current?.loading) return <small>Загружаю фото…</small>;
  if (current?.message) return <small>{current.message}</small>;
  if (!current?.url) return null;
  const {row, region} = current;
  return <figure className="plot-grain-preview">
    <div>
      <img src={current.url} alt={`Фрагмент вокруг точки ${row.point_name}`} width={region.width} height={region.height}/>
      <span aria-hidden="true" style={{
        left: `${100 * (row.x_px - region.left) / region.width}%`,
        top: `${100 * (row.y_px - region.top) / region.height}%`,
      }}/>
    </div>
    <figcaption>{row.display_name} · {row.point_name}</figcaption>
  </figure>;
}
