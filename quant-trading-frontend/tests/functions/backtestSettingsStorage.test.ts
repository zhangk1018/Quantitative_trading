// backtestSettingsStorage.test.ts — 回测默认设置存储（localStorage CRUD + 费率转换）
//
// 覆盖场景：
//   - 默认设置读取
//   - 保存/恢复
//   - localStorage 异常降级
//   - 费率转换（feeRate ↔ display）
//   - 部分字段合并

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getBacktestDefaults,
  saveBacktestDefaults,
  feeRateToDisplay,
  displayToFeeRate,
  DEFAULT_BACKTEST_DEFAULTS,
  type BacktestDefaults,
} from '../../src/features/backtest/backtestSettingsStorage';
import { DEFAULT_INDICATOR_PARAMS } from '../../src/features/backtest/backtestTypes';

const STORAGE_KEY = 'backtest_defaults';

beforeEach(() => {
  localStorage.clear();
});

// ==================== getBacktestDefaults ====================

describe('getBacktestDefaults', () => {
  it('空 localStorage 返回默认值', () => {
    const defaults = getBacktestDefaults();
    expect(defaults.executionPrice).toBe(DEFAULT_BACKTEST_DEFAULTS.executionPrice);
    expect(defaults.maxDeferDays).toBe(DEFAULT_BACKTEST_DEFAULTS.maxDeferDays);
    expect(defaults.feeRate).toBe(DEFAULT_BACKTEST_DEFAULTS.feeRate);
    expect(defaults.slippage).toBe(DEFAULT_BACKTEST_DEFAULTS.slippage);
    expect(defaults.riskFreeRate).toBe(DEFAULT_BACKTEST_DEFAULTS.riskFreeRate);
  });

  it('读取已保存的设置', () => {
    const saved: BacktestDefaults = {
      executionPrice: 'next_close',
      maxDeferDays: 5,
      feeRate: 0.0003,
      slippage: 0.001,
      riskFreeRate: 0.04,
      indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, rsiPeriod: 14, macdFast: 12, macdSlow: 26, macdSignal: 9, bollPeriod: 20, bollStd: 2 },
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    const defaults = getBacktestDefaults();
    expect(defaults.executionPrice).toBe('next_close');
    expect(defaults.maxDeferDays).toBe(5);
    expect(defaults.feeRate).toBe(0.0003);
  });

  it('部分字段缺失时合并默认值', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ executionPrice: 'next_close' }));
    const defaults = getBacktestDefaults();
    expect(defaults.executionPrice).toBe('next_close');
    expect(defaults.maxDeferDays).toBe(DEFAULT_BACKTEST_DEFAULTS.maxDeferDays);
    expect(defaults.feeRate).toBe(DEFAULT_BACKTEST_DEFAULTS.feeRate);
  });

  it('损坏的 JSON 返回默认值', () => {
    localStorage.setItem(STORAGE_KEY, '{broken');
    const defaults = getBacktestDefaults();
    expect(defaults.executionPrice).toBe(DEFAULT_BACKTEST_DEFAULTS.executionPrice);
  });

  it('不抛异常', () => {
    localStorage.setItem(STORAGE_KEY, 'not-json');
    expect(() => getBacktestDefaults()).not.toThrow();
  });

  it('indicatorParams 部分覆盖时合并默认值', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      indicatorParams: { ma5: 8 },
    }));
    const defaults = getBacktestDefaults();
    expect(defaults.indicatorParams.ma5).toBe(8);
    expect(defaults.indicatorParams.ma10).toBe(DEFAULT_INDICATOR_PARAMS.ma10);
  });
});

// ==================== saveBacktestDefaults ====================

describe('saveBacktestDefaults', () => {
  it('保存后能正确读取', () => {
    const settings: BacktestDefaults = {
      ...DEFAULT_BACKTEST_DEFAULTS,
      feeRate: 0.0005,
      maxDeferDays: 2,
    };
    saveBacktestDefaults(settings);
    const restored = getBacktestDefaults();
    expect(restored.feeRate).toBe(0.0005);
    expect(restored.maxDeferDays).toBe(2);
  });

  it('覆盖已有设置', () => {
    saveBacktestDefaults({ ...DEFAULT_BACKTEST_DEFAULTS, feeRate: 0.0001 });
    saveBacktestDefaults({ ...DEFAULT_BACKTEST_DEFAULTS, feeRate: 0.0002 });
    expect(getBacktestDefaults().feeRate).toBe(0.0002);
  });
});

// ==================== feeRateToDisplay ====================

describe('feeRateToDisplay', () => {
  it('0.00015 → 1.5', () => {
    expect(feeRateToDisplay(0.00015)).toBe(1.5);
  });

  it('0.0003 → 3', () => {
    expect(feeRateToDisplay(0.0003)).toBe(3);
  });

  it('0 → 0', () => {
    expect(feeRateToDisplay(0)).toBe(0);
  });

  it('0.001 → 10', () => {
    expect(feeRateToDisplay(0.001)).toBe(10);
  });

  it('万分之 2.5 → 2.5', () => {
    expect(feeRateToDisplay(0.00025)).toBe(2.5);
  });
});

// ==================== displayToFeeRate ====================

describe('displayToFeeRate', () => {
  it('1.5 → 0.00015', () => {
    expect(displayToFeeRate(1.5)).toBe(0.00015);
  });

  it('3 → 0.0003', () => {
    expect(displayToFeeRate(3)).toBe(0.0003);
  });

  it('0 → 0', () => {
    expect(displayToFeeRate(0)).toBe(0);
  });

  it('10 → 0.001', () => {
    expect(displayToFeeRate(10)).toBe(0.001);
  });

  it('往返一致', () => {
    const rate = 0.00025;
    expect(displayToFeeRate(feeRateToDisplay(rate))).toBe(rate);
  });
});