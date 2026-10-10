import { describe, it, expect } from 'vitest';
import {
  CURRENCY_SYMBOL,
  formatPriceWithCurrency,
  formatMarketCapWithCurrency,
} from '@/shared/utils/currency';

describe('formatPriceWithCurrency', () => {
  it('港股带 HK$ 前缀', () => {
    expect(formatPriceWithCurrency(400.05, 'HKD')).toBe('HK$ 400.05');
  });
  it('美股带 $ 前缀', () => {
    expect(formatPriceWithCurrency(180.5, 'USD')).toBe('$ 180.50');
  });
  it('A股 CNY 不加前缀', () => {
    expect(formatPriceWithCurrency(10, 'CNY')).toBe('10.00');
  });
  it('缺省币种不加前缀', () => {
    expect(formatPriceWithCurrency(10)).toBe('10.00');
  });
  it('保留小数位精度', () => {
    expect(formatPriceWithCurrency(123.456, 'HKD', 3)).toBe('HK$ 123.456');
  });
  it('空值/非法返回 --', () => {
    expect(formatPriceWithCurrency(null, 'HKD')).toBe('--');
    expect(formatPriceWithCurrency(NaN, 'HKD')).toBe('--');
  });
});

describe('formatMarketCapWithCurrency', () => {
  // 入参单位=**万元**（协作单 47.0 统一口径：cn/hk/us 一律万元，与后端契约一致）
  it('港元市值带币种（万元 → 万亿）', () => {
    expect(formatMarketCapWithCurrency(3.86e8, 'HKD')).toBe('HK$ 3.86万亿');
  });
  it('A股 CNY 无币种前缀', () => {
    expect(formatMarketCapWithCurrency(5e7, 'CNY')).toBe('5000.00亿');
  });
  it('仙股市值（万元 → 亿）', () => {
    expect(formatMarketCapWithCurrency(857400, 'HKD')).toBe('HK$ 85.74亿');
  });
  it('空值返回 --', () => {
    expect(formatMarketCapWithCurrency(null, 'USD')).toBe('--');
    expect(formatMarketCapWithCurrency(0, 'USD')).toBe('--');
  });
});

describe('CURRENCY_SYMBOL', () => {
  it('含三市场币种符号', () => {
    expect(CURRENCY_SYMBOL).toEqual({ CNY: '¥', HKD: 'HK$', USD: '$' });
  });
});