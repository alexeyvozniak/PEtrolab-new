export function selectionRange(order, start, end) {
  const first = order.indexOf(start);
  const last = order.indexOf(end);
  return first < 0 || last < 0 ? [] : order.slice(Math.min(first, last), Math.max(first, last) + 1);
}
