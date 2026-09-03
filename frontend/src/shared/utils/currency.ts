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
 * 格式化带币种的价格：`HK$ 400.00`、`$ 180.00`、`¥ 10.00`
 * @param value 价格
 * @param currency 币种代码（CNY/HKD/USD）；缺省不前缀
 * @param precision 小数位，默认 2
 */
export function formatPriceWithCurrency(
  value: number | null | undefined,
  currency?: string,
  precision = 2,
): string {
  if (value == null || !Number.isFinite(value)) return '--';
  const num = value.toFixed(precision);
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