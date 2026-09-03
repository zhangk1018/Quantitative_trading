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
  it('港元市值带币种（亿）', () => {
    expect(formatMarketCapWithCurrency(2.19e12, 'HKD')).toBe('HK$ 2.19万亿');
  });
  it('A股 CNY 无币种前缀', () => {
    expect(formatMarketCapWithCurrency(5e11, 'CNY')).toBe('5000.00亿');
  });
  it('空值返回 --', () => {
    expect(formatMarketCapWithCurrency(null, 'USD')).toBe('--');
  });
});

describe('CURRENCY_SYMBOL', () => {
  it('含三市场币种符号', () => {
    expect(CURRENCY_SYMBOL).toEqual({ CNY: '¥', HKD: 'HK$', USD: '$' });
  });
});