export const ROW_HEIGHT = 42;
export const TABLE_HEADER_HEIGHT = 77;
const OVERSCAN = 12;
export function virtualRowRange(count, scrollTop, viewportHeight) {
  const available = Math.max(ROW_HEIGHT, viewportHeight - TABLE_HEADER_HEIGHT);
  const top = Math.max(0, Math.min(scrollTop, count * ROW_HEIGHT - available));
  return {
    start: Math.max(0, Math.floor(top / ROW_HEIGHT) - OVERSCAN),
    end: Math.min(count, Math.ceil((top + available) / ROW_HEIGHT) + OVERSCAN),
  };
}
