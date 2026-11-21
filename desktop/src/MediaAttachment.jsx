import { useEffect, useState } from "react";

export function MediaAttachment({ target, images, actions, previewMedia, reloadSample }) {
  const [links, setLinks] = useState(null);
  const [assetId, setAssetId] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoType, setPhotoType] = useState("Другое");
  const [opened, setOpened] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const id = target.spatial_annotation_id;
  const list = actions.list;
  useEffect(() => {
    let active = true;
    list(id).then((rows) => { if (active) setLinks(rows); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [id, list]);

  const perform = async (task) => {
    setPending(true);
    setError("");
    try { await task(); }
    catch (caught) { setError(caught.message); }
    finally { setPending(false); }
  };
  const candidates = images.filter((item) => !links?.some((link) => link.media_asset_id === item.media_asset_id));
  const name = target.point_name || target.label || (target.geometry_kind === "point" ? "Точка" : "Область");
  return <aside className="sample-card media-attachment" aria-label="Медиа и привязка">
    <h3>Медиа и привязка</h3>
    <p>Цель привязки: <b>{name}</b></p>
    {error && <p role="alert">{error}</p>}
    {!links && !error && <p role="status">Загружаю связанные фото…</p>}
    {links && <>
      {candidates.length > 0 && <div className="sample-form">
        <label>Фото из проекта<select value={assetId} onChange={(event) => setAssetId(event.target.value)} disabled={pending}>
          <option value="">Выберите фотографию</option>
          {candidates.map((item) => <option key={item.media_asset_id} value={item.media_asset_id}>{item.display_name}</option>)}
        </select></label>
        <button type="button" className="outline-button" disabled={!assetId || pending} onClick={() => perform(async () => {
          await actions.change(id, assetId, true); setAssetId(""); setLinks(await list(id));
        })}>Прикрепить из проекта</button>
      </div>}
      {actions.pick && <button className="outline-button" type="button" disabled={pending} onClick={() => perform(async () => {
        const paths = await actions.pick();
        if (paths.length > 1) throw new Error("Выберите одну фотографию.");
        if (paths.length === 1) setPhoto(await actions.previewInput(paths[0]));
      })}>Выбрать файл фото</button>}
      {photo && <div className="sample-form media-selected-photo">
        <b>{photo.display_name}</b>
        <img src={photo.preview_url} alt="Выбранная фотография" />
        <label>Тип фото<select value={photoType} disabled={pending} onChange={(event) => setPhotoType(event.target.value)}>
          {["Другое", "BSE", "PPL", "XPL"].map((type) => <option key={type}>{type}</option>)}
        </select></label>
        <div className="point-row-actions">
          <button className="primary-button" disabled={pending} onClick={() => perform(async () => {
            await actions.importPhoto(id, photo, photoType);
            setPhoto(null);
            setLinks(await list(id));
            await reloadSample();
          })}>Прикрепить фото</button>
          <button className="outline-button" disabled={pending} onClick={() => setPhoto(null)}>Отмена</button>
        </div>
      </div>}
      <h4>Связанные фото ({links.length})</h4>
      {!links.length && <p>К этой цели ещё не прикреплены фото.</p>}
      <ul className="sample-items">{links.map((item) => <li key={item.media_link_id}>
        <div><b>{item.display_name}</b><p>{item.media_type} · {item.width_px} × {item.height_px}</p></div>
        <div className="point-row-actions">
          <button className="outline-button" disabled={pending} onClick={() => perform(async () => {
            const image = await previewMedia(item.media_asset_id);
            setOpened({ ...image, name: item.display_name });
          })}>Открыть фото</button>
          <button className="outline-button" disabled={pending} onClick={() => perform(async () => {
            await actions.change(id, item.media_asset_id, false);
            setOpened(null);
            setLinks(await list(id));
          })}>Снять привязку</button>
        </div>
      </li>)}</ul>
      {opened && <figure className="media-selected-photo"><img src={opened.preview_url} alt={opened.name} />
        <figcaption><button className="outline-button" onClick={() => setOpened(null)}>Закрыть фото</button></figcaption>
      </figure>}
    </>}
  </aside>;
}
