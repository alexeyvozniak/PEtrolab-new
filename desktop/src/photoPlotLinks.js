// These helpers only match persisted identifiers; they never infer spatial truth.
export const photoLinks=(rows,mediaId)=>rows.filter(row=>row.media_asset_id===mediaId);
export const focusLinks=(rows,ids)=>{const set=new Set(ids);return rows.filter(row=>set.has(row.analysis_id));};

