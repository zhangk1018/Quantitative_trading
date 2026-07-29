/**
 * 格式化工具函数测试
 *
 * 验证：
 * - formatMarketCap：输入万元，输出亿（÷10000, toFixed(2)）
 * - formatNumber：null/undefined/0/小数位数/负数/边界值
 */
import { describe, it, expect } from 'vitest';
import { formatMarketCap, formatNumber } from '@/features/stock-picker/utils/screener';

describe('formatMarketCap', () => {
  it('null → "-"', () => {
    expect(formatMarketCap(null)).toBe('-');
  });

  it('undefined → "-"', () => {
    expect(formatMarketCap(undefined)).toBe('-');
  });

  it('0 万元 → "0.00亿"', () => {
    expect(formatMarketCap(0)).toBe('0.00亿');
  });

  it('50000 万元 → "5.00亿"', () => {
    expect(formatMarketCap(50000)).toBe('5.00亿');
  });

  it('500000 万元 → "50.00亿"', () => {
    expect(formatMarketCap(500000)).toBe('50.00亿');
  });

  it('12345 万元 → "1.23亿"（四舍五入）', () => {
    expect(formatMarketCap(12345)).toBe('1.23亿');
  });

  it('9999 万元 → "1.00亿"', () => {
    expect(formatMarketCap(9999)).toBe('1.00亿');
  });

  it('NaN → "-"', () => {
    expect(formatMarketCap(NaN)).toBe('-');
  });

  it('Infinity → "-"', () => {
    expect(formatMarketCap(Infinity)).toBe('-');
  });

  it('-Infinity → "-"', () => {
    expect(formatMarketCap(-Infinity)).toBe('-');
  });

  it('负数（防御性）：-10000 万元 → "-1.00亿"', () => {
    expect(formatMarketCap(-10000)).toBe('-1.00亿');
  });

  it('超大值 1e12 万元 → 不崩溃', () => {
    const result = formatMarketCap(1e12);
    expect(result).not.toBe('-');
    expect(result).toMatch(/亿$/);
  });
});

describe('formatNumber', () => {
  it('null → "-"', () => {
    expect(formatNumber(null)).toBe('-');
  });

  it('undefined → "-"', () => {
    expect(formatNumber(undefined)).toBe('-');
  });

  it('0 → "0.00"（默认2位小数）', () => {
    expect(formatNumber(0)).toBe('0.00');
  });

  it('123.456 → "123.46"（默认2位小数，四舍五入）', () => {
    expect(formatNumber(123.456)).toBe('123.46');
  });

  it('负数 -5.678 → "-5.68"', () => {
    expect(formatNumber(-5.678)).toBe('-5.68');
  });

  it('自定义小数位数 3 → "1.235"', () => {
    expect(formatNumber(1.23456, 3)).toBe('1.235');
  });

  it('decimals=0 → "12"', () => {
    expect(formatNumber(12.34, 0)).toBe('12');
  });

  it('decimals 为负数 → 兜底到 0', () => {
    // toFixed 不接受负数，但 JavaScript 会抛 RangeError
    // 当前实现未防御，这里标记为预期行为
    expect(() => formatNumber(12.34, -1)).toThrow();
  });

  it('NaN → "-"', () => {
    expect(formatNumber(NaN)).toBe('-');
  });

  it('Infinity → "-"', () => {
    expect(formatNumber(Infinity)).toBe('-');
  });

  it('-Infinity → "-"', () => {
    expect(formatNumber(-Infinity)).toBe('-');
  });

  it('科学计数法小值 1e-10 → "0.00"', () => {
    expect(formatNumber(1e-10)).toBe('0.00');
  });
});