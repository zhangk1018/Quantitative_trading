import { describe, it, expect } from 'vitest';
import { isExcludedStockName } from '../../../src/lib/stocks/exclusion';

describe('isExcludedStockName', () => {
  it('排除名称含 ST 的股票', () => {
    expect(isExcludedStockName('ST康美')).toBe(true);
    expect(isExcludedStockName('st中安')).toBe(true);
    expect(isExcludedStockName('平安银行')).toBe(false);
  });

  it('排除名称含 *ST 的股票', () => {
    expect(isExcludedStockName('*ST高斯')).toBe(true);
    expect(isExcludedStockName('*st达意')).toBe(true);
  });

  it('排除名称含 退 的股票（退市/退市整理）', () => {
    expect(isExcludedStockName('退市海医')).toBe(true);
    expect(isExcludedStockName('金亚退')).toBe(true);
  });

  it('正常股票不排除', () => {
    expect(isExcludedStockName('贵州茅台')).toBe(false);
    expect(isExcludedStockName('老板电器')).toBe(false);
  });

  it('空值返回 false', () => {
    expect(isExcludedStockName(undefined)).toBe(false);
    expect(isExcludedStockName(null)).toBe(false);
    expect(isExcludedStockName('')).toBe(false);
  });

  it('大小写不敏感（英文包含 ST）', () => {
    expect(isExcludedStockName('AbcSTDef')).toBe(true);
    expect(isExcludedStockName('AbcDef')).toBe(false);
  });
});