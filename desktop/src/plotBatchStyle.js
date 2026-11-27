import {SYMBOL_LABELS} from "./plotSymbols.js";
const identity=(mode,key)=>JSON.stringify([mode,key]);
// Merge only explicit active legend keys. Preserve existing modes, styles and
// absent keys. A null category is deliberately never editable.
export function applyBatchStyle(current,mode,entries,selected,patch){
  if(!["source","sample","mineral","generation"].includes(mode))throw Error("Неизвестный режим окрашивания.");
  const keys=new Set(selected);
  const hasColor=Object.hasOwn(patch,"color"),hasSymbol=Object.hasOwn(patch,"symbol");
  if(hasColor&&!/^#[0-9a-f]{6}$/i.test(patch.color))throw Error("Неверный цвет.");
  if(hasSymbol&&(mode==="source"||!Object.hasOwn(SYMBOL_LABELS,patch.symbol)))throw Error("Недоступный символ.");
  if(!hasColor&&!hasSymbol)return current;
  const byKey=new Map(current.map(entry=>[identity(entry.mode,entry.key),entry]));
  for(const entry of entries){
    if(typeof entry.key!=="string"||!keys.has(entry.key))continue;
    const key=identity(mode,entry.key), prior=byKey.get(key);
    byKey.set(key,{mode,key:entry.key,color:entry.color,...(entry.symbol?{symbol:entry.symbol}:{}),...prior,
      ...(hasColor?{color:patch.color.toLowerCase()}:{}),...(hasSymbol?{symbol:patch.symbol}:{})});
  }
  if(byKey.size>4000)throw Error("Цветовая схема ограничена 4000 категориями.");
  return [...byKey.values()];
}
