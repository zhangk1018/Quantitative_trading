import { describe, it, expect } from 'vitest';
import {
  formatStockCodeForDisplay,
  detectMarketGroup,
} from '@/features/watchlist/utils/stock-utils';

describe('formatStockCodeForDisplay', () => {
  it('港股数字代码补零至 5 位（4 位码）', () => {
    expect(formatStockCodeForDisplay('9988.HK')).toBe('09988.HK');
  });

  it('港股数字代码补零至 5 位（3 位码）', () => {
    expect(formatStockCodeForDisplay('700.HK')).toBe('00700.HK');
  });

  it('港股数字代码补零至 5 位（1 位码）', () => {
    expect(formatStockCodeForDisplay('1.HK')).toBe('00001.HK');
  });

  it('港股已为 5 位时不改变', () => {
    expect(formatStockCodeForDisplay('09988.HK')).toBe('09988.HK');
  });

  it('通过 market 参数判定港股', () => {
    expect(formatStockCodeForDisplay('9999.HK', 'hk')).toBe('09999.HK');
  });

  it('A股原样返回', () => {
    expect(formatStockCodeForDisplay('600519.SH')).toBe('600519.SH');
    expect(formatStockCodeForDisplay('000001.SZ')).toBe('000001.SZ');
  });

  it('美股原样返回', () => {
    expect(formatStockCodeForDisplay('AAPL')).toBe('AAPL');
  });
});

describe('detectMarketGroup', () => {
  it('A股识别沪深', () => {
    expect(detectMarketGroup('600519')).toBe('沪深');
    expect(detectMarketGroup('000001')).toBe('沪深');
    expect(detectMarketGroup('300750')).toBe('沪深');
  });

  it('港股识别', () => {
    expect(detectMarketGroup('9988.HK')).toBe('港股');
    expect(detectMarketGroup('700.HK')).toBe('港股');
  });

  it('美股识别', () => {
    expect(detectMarketGroup('AAPL')).toBe('美股');
  });
});