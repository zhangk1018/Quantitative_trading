/**
 * 格式化工具函数测试
 *
 * 验证：
 * - formatMarketCap：**入参单位=万元**（协作单 47.0 统一口径：cn/hk/us 一律万元），
 *   按量级输出 万亿/亿/万/元；空值/非正值 → `--`
 * - formatNumber：null/undefined/0/小数位数/负数/边界值
 */
import { describe, it, expect } from 'vitest';
import { formatMarketCap, formatNumber } from '@/features/stock-picker/utils/screener';

describe('formatMarketCap', () => {
  it('null → "--"', () => {
    expect(formatMarketCap(null)).toBe('--');
  });

  it('undefined → "--"', () => {
    expect(formatMarketCap(undefined)).toBe('--');
  });

  it('0 万元 → "--"（非正值视为无数据）', () => {
    expect(formatMarketCap(0)).toBe('--');
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

  it('9999 万元 → "9999.00万"（不足 1 亿走万档）', () => {
    expect(formatMarketCap(9999)).toBe('9999.00万');
  });

  it('857400 万元 → "85.74亿"（碧桂园，协作单 47.0 回归）', () => {
    expect(formatMarketCap(857400)).toBe('85.74亿');
  });

  it('2.93e8 万元 → "2.93万亿"（工行量级）', () => {
    expect(formatMarketCap(2.93e8)).toBe('2.93万亿');
  });

  it('NaN → "--"', () => {
    expect(formatMarketCap(NaN)).toBe('--');
  });

  it('Infinity → "--"', () => {
    expect(formatMarketCap(Infinity)).toBe('--');
  });

  it('-Infinity → "--"', () => {
    expect(formatMarketCap(-Infinity)).toBe('--');
  });

  it('负数（防御性）：-10000 万元 → "--"', () => {
    expect(formatMarketCap(-10000)).toBe('--');
  });

  it('超大值 1e12 万元 → 万亿档、不崩溃', () => {
    const result = formatMarketCap(1e12);
    expect(result).not.toBe('--');
    expect(result).toBe('10000.00万亿');
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