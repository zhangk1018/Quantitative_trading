/**
 * utils/currency.ts — 币种展示统一格式化（纯函数，无副作用）
 *
 * 原则（对齐《加入港股美股改造方案_v2.md》§8）：
 * - 原始交易货币即该币种，不强行统一换算为人民币
 * - 仅在展示层按 currency 添加币种标识
 */

export type Currency = 'CNY' | 'HKD' | 'USD';

/** 币种符号映射，未知币种回退 '¥'？不，回退显示原币种代码 */
export const CURRENCY_SYMBOL: Record<string, string> = {
  CNY: '¥',
  HKD: 'HK$',
  USD: '$',
};

/**
 * 按量级自适应价格小数位。
 *
 * 港股（含仙股）价格为 4 位小数（如碧桂园 0.1830 / 0.1829 / 0.1831），若统一 `toFixed(2)`
 * 会退化成 `0.18`、丢失日内信息（协作单 46.0）。≥1 的价位 2 位已足够，<1 的价位给 4 位。
 */
export function priceDecimals(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 2;
  return Math.abs(value) < 1 ? 4 : 2;
}

/**
 * 格式化带币种的价格：`HK$ 400.00`、`$ 180.00`、`¥ 10.00`、`HK$ 0.1830`
 * @param value 价格
 * @param currency 币种代码（CNY/HKD/USD）；缺省不前缀
 * @param precision 小数位；**缺省按量级自适应**（见 priceDecimals）
 */
export function formatPriceWithCurrency(
  value: number | null | undefined,
  currency?: string,
  precision?: number,
): string {
  if (value == null || !Number.isFinite(value)) return '--';
  const num = value.toFixed(precision ?? priceDecimals(value));
  if (!currency || currency === 'CNY') return `${num}`;
  return `${CURRENCY_SYMBOL[currency] ?? `${currency} `} ${num}`;
}

/**
 * 格式化市值并带币种标识（返回原始货币，不换算）
 * @param value 市值
 * @param currency 币种代码
 */
export function formatMarketCapWithCurrency(
  value: number | null | undefined,
  currency?: string,
): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return '--';
  const symbol = currency && currency !== 'CNY' ? (CURRENCY_SYMBOL[currency] ?? `${currency} `) : '';
  let body: string;
  if (value >= 1e12) body = `${(value / 1e12).toFixed(2)}万亿`;
  else if (value >= 1e8) body = `${(value / 1e8).toFixed(2)}亿`;
  else if (value >= 1e4) body = `${(value / 1e4).toFixed(2)}万`;
  else body = value.toFixed(2);
  return symbol ? `${symbol} ${body}` : body;
}