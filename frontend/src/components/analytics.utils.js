export function pct(x, digits = 0) {
  const n = Number(x);
  if (!Number.isFinite(n)) return null;
  return Math.round(n * 100 * Math.pow(10, digits)) / Math.pow(10, digits);
}
