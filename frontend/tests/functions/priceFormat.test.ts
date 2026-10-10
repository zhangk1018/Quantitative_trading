// priceFormat.test.ts — 价格格式化精度（协作单 46.0）
// 港股/仙股价格为 4 位小数，统一 toFixed(2) 会把碧桂园 0.1830 截成 0.18，丢失日内信息。

import { describe, it, expect } from 'vitest';
import { priceDecimals, formatPriceWithCurrency } from '@/shared/utils/currency';
import { formatPrice, formatNumber } from '@/features/watchlist/utils/stock-formatter';

describe('priceDecimals — 按量级自适应小数位', () => {
  it('绝对值 <1 用 4 位（港股仙股），否则 2 位', () => {
    expect(priceDecimals(0.183)).toBe(4);
    expect(priceDecimals(0.05)).toBe(4);
    expect(priceDecimals(0.9999)).toBe(4);
    expect(priceDecimals(1)).toBe(2);
    expect(priceDecimals(424.8)).toBe(2);
    expect(priceDecimals(1263)).toBe(2);
  });

  it('非法值回退 2 位', () => {
    expect(priceDecimals(null)).toBe(2);
    expect(priceDecimals(undefined)).toBe(2);
    expect(priceDecimals(NaN)).toBe(2);
  });
});

describe('formatPrice — 价格展示不截断', () => {
  it('碧桂园式仙股保留 4 位，不被截成 0.18', () => {
    expect(formatPrice(0.183)).toBe('0.1830');
    expect(formatPrice(0.1829)).toBe('0.1829');
    expect(formatPrice(0.1831)).toBe('0.1831');
  });

  it('常规价位仍 2 位', () => {
    expect(formatPrice(424.8)).toBe('424.80');
    expect(formatPrice(1263)).toBe('1263.00');
  });

  it('空值安全', () => {
    expect(formatPrice(null)).toBe('--');
    expect(formatPrice(undefined)).toBe('--');
  });

  it('formatNumber（比值类）不受影响，仍固定 2 位', () => {
    expect(formatNumber(0.183)).toBe('0.18');
    expect(formatNumber(4.8291)).toBe('4.83');
  });
});

describe('formatPriceWithCurrency — 带币种且精度自适应', () => {
  it('港股仙股 4 位 + 币种前缀', () => {
    expect(formatPriceWithCurrency(0.183, 'HKD')).toBe('HK$ 0.1830');
  });

  it('常规价位 2 位', () => {
    expect(formatPriceWithCurrency(424.8, 'HKD')).toBe('HK$ 424.80');
    expect(formatPriceWithCurrency(1263, 'CNY')).toBe('1263.00');
  });

  it('显式传 precision 时以显式值为准（向后兼容）', () => {
    expect(formatPriceWithCurrency(0.183, 'HKD', 2)).toBe('HK$ 0.18');
  });

  it('空值安全', () => {
    expect(formatPriceWithCurrency(null)).toBe('--');
  });
});