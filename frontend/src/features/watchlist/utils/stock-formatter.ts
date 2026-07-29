/**
 * utils/stock-formatter.ts — 股票数值格式化纯函数
 *
 * 所有格式化函数统一处理 null / NaN / Infinity，返回安全的显示字符串。
 */

/** 格式化普通数值，精度 2 位 */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '--';
  return value.toFixed(2);
}

/** 格式化涨跌幅，带正负号 */
export function formatChangePct(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '--';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

/** 格式化涨跌额，带正负号 */
export function formatChangeAmount(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '--';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

/** 根据 close 和 change_pct 反算涨跌额 */
export function calcChangeAmount(
  close: number | null | undefined,
  changePct: number | null | undefined,
): number | null {
  if (close == null || !isFinite(close)) return null;
  if (changePct == null || !isFinite(changePct)) return null;
  const prevClose = close / (1 + changePct / 100);
  if (!isFinite(prevClose)) return null;
  return close - prevClose;
}

/** 格式化市值 */
export function formatMarketCap(value: number | null | undefined): string {
  if (value == null || !isFinite(value) || value <= 0) return '--';
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}万亿`;
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return `${value.toFixed(2)}元`;
}