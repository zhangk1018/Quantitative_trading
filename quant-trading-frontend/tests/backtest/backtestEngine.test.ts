// tests/backtest/backtestEngine.test.ts — 回测引擎单元测试
// 覆盖：isValidTime、错误类型、常量定义、validateBacktestInput 结构性校验

import { describe, it, expect } from 'vitest';

// ==================== 1. isValidTime 测试 ====================

describe('backtestWorker - isValidTime', () => {
  it('YYYY-MM-DD 格式应返回 true', async () => {
    const { isValidTime } = await import('../../src/features/backtest/backtest.worker');
    expect(isValidTime('2025-01-15')).toBe(true);
  });

  it('空字符串应返回 false', async () => {
    const { isValidTime } = await import('../../src/features/backtest/backtest.worker');
    expect(isValidTime('')).toBe(false);
  });

  it('无效日期应返回 false', async () => {
    const { isValidTime } = await import('../../src/features/backtest/backtest.worker');
    expect(isValidTime('not-a-date')).toBe(false);
  });

  it('数字时间戳应返回 true', async () => {
    const { isValidTime } = await import('../../src/features/backtest/backtest.worker');
    expect(isValidTime(1704067200000)).toBe(true);
  });
});

// ==================== 2. validateBacktestInput 结构性校验测试 ====================

describe('backtestWorker - validateBacktestInput 结构性校验', () => {
  it('合法输入返回 null', async () => {
    const { validateBacktestInput } = await import(
      '../../src/features/backtest/backtest.worker'
    );

    const error = validateBacktestInput({
      bars: [{ time: '2025-01-02', open: 10, high: 11, low: 9, close: 10.5, volume: 100000 }],
      buyCondition: { indicatorId: 'test', formula: 'def calculate(o,h,l,c,v): return [0]*len(c)', indicatorName: 'test' },
      config: {
        stockCode: '000001', capital: 100000, feeRate: 0.0003, slippage: 0.001,
        riskFreeRate: 0.03, executionPrice: 'next_open', maxDeferDays: 3,
        indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2, macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3 },
      },
    });

    expect(error).toBeNull();
  });

  it('bars 为空时应返回错误', async () => {
    const { validateBacktestInput } = await import(
      '../../src/features/backtest/backtest.worker'
    );

    const error = validateBacktestInput({
      bars: [],
      buyCondition: { indicatorId: 'test', formula: 'x', indicatorName: 'test' },
      config: {
        stockCode: '000001', capital: 100000, feeRate: 0.0003, slippage: 0.001,
        riskFreeRate: 0.03, executionPrice: 'next_open', maxDeferDays: 3,
        indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2, macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3 },
      },
    });

    expect(error).toBe('K 线数据为空或格式错误');
  });

  it('bars 缺少 close 字段时应返回错误', async () => {
    const { validateBacktestInput } = await import(
      '../../src/features/backtest/backtest.worker'
    );

    const error = validateBacktestInput({
      bars: [{ time: '2025-01-02', open: 10, high: 11, low: 9, volume: 100000 } as any],
      buyCondition: { indicatorId: 'test', formula: 'x', indicatorName: 'test' },
      config: {
        stockCode: '000001', capital: 100000, feeRate: 0.0003, slippage: 0.001,
        riskFreeRate: 0.03, executionPrice: 'next_open', maxDeferDays: 3,
        indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2, macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3 },
      },
    });

    expect(error).toContain('缺少字段');
  });

  it('缺少 buyCondition 时应返回错误', async () => {
    const { validateBacktestInput } = await import(
      '../../src/features/backtest/backtest.worker'
    );

    const error = validateBacktestInput({
      bars: [{ time: '2025-01-02', open: 10, high: 11, low: 9, close: 10.5, volume: 100000 }],
      buyCondition: null as any,
      config: {
        stockCode: '000001', capital: 100000, feeRate: 0.0003, slippage: 0.001,
        riskFreeRate: 0.03, executionPrice: 'next_open', maxDeferDays: 3,
        indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2, macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3 },
      },
    });

    expect(error).toBe('买入条件格式错误');
  });

  it('缺少 indicatorId 时应返回错误', async () => {
    const { validateBacktestInput } = await import(
      '../../src/features/backtest/backtest.worker'
    );

    const error = validateBacktestInput({
      bars: [{ time: '2025-01-02', open: 10, high: 11, low: 9, close: 10.5, volume: 100000 }],
      buyCondition: { indicatorId: '', formula: 'x', indicatorName: 'test' },
      config: {
        stockCode: '000001', capital: 100000, feeRate: 0.0003, slippage: 0.001,
        riskFreeRate: 0.03, executionPrice: 'next_open', maxDeferDays: 3,
        indicatorParams: { ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2, macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3 },
      },
    });

    expect(error).toBe('买入条件缺少有效的自编指标 ID');
  });
});

// ==================== 3. 错误类型测试 ====================

describe('backtest - 错误类型', () => {
  it('BacktestError 应携带错误码和上下文', async () => {
    const { BacktestError, BacktestErrorCode } = await import(
      '../../src/features/backtest/errors'
    );

    const error = new BacktestError(
      BacktestErrorCode.PARAM_INVALID,
      '参数无效',
      { field: 'capital', value: -100 },
    );

    expect(error.code).toBe(BacktestErrorCode.PARAM_INVALID);
    expect(error.message).toBe('参数无效');
    expect(error.context.field).toBe('capital');
    expect(error.name).toBe('BacktestError');
  });

  it('ParamError 应继承 BacktestError', async () => {
    const { ParamError, BacktestErrorCode } = await import(
      '../../src/features/backtest/errors'
    );

    const error = new ParamError(
      BacktestErrorCode.PARAM_OUT_OF_RANGE,
      '资金超出范围',
      { field: 'capital', value: 0 },
    );

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('ParamError');
    expect(error.code).toBe(BacktestErrorCode.PARAM_OUT_OF_RANGE);
  });

  it('SignalError 应继承 BacktestError', async () => {
    const { SignalError, BacktestErrorCode } = await import(
      '../../src/features/backtest/errors'
    );

    const error = new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      '脚本执行失败',
      { indicatorName: 'test' },
    );

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('SignalError');
    expect(error.code).toBe(BacktestErrorCode.SIGNAL_SCRIPT_ERROR);
  });

  it('isFatalError 应对致命错误返回 true，SignalError 返回 false', async () => {
    const {
      ParamError,
      DataError,
      SignalError,
      BacktestErrorCode,
      isFatalError,
    } = await import('../../src/features/backtest/errors');

    const paramError = new ParamError(BacktestErrorCode.PARAM_INVALID, 'x');
    const dataError = new DataError(BacktestErrorCode.DATA_EMPTY, 'x');
    const signalError = new SignalError(BacktestErrorCode.SIGNAL_SCRIPT_ERROR, 'x');

    expect(isFatalError(paramError)).toBe(true);
    expect(isFatalError(dataError)).toBe(true);
    expect(isFatalError(signalError)).toBe(false);
  });
});

// ==================== 4. 常量定义测试 ====================

describe('backtest - 常量', () => {
  it('LOT_SIZE 应为 100', async () => {
    const { LOT_SIZE } = await import('../../src/features/backtest/constants');
    expect(LOT_SIZE).toBe(100);
  });

  it('TRADING_DAYS_PER_YEAR 应为 252', async () => {
    const { TRADING_DAYS_PER_YEAR } = await import('../../src/features/backtest/constants');
    expect(TRADING_DAYS_PER_YEAR).toBe(252);
  });

  it('STORAGE_SCHEMA_VERSION 应为正整数', async () => {
    const { STORAGE_SCHEMA_VERSION } = await import('../../src/features/backtest/constants');
    expect(STORAGE_SCHEMA_VERSION).toBeGreaterThan(0);
    expect(Number.isInteger(STORAGE_SCHEMA_VERSION)).toBe(true);
  });

  it('参数边界值应合理', async () => {
    const {
      MIN_CAPITAL, MAX_CAPITAL,
      MIN_FEE_RATE, MAX_FEE_RATE,
      MIN_SLIPPAGE, MAX_SLIPPAGE,
      MIN_MAX_DEFER_DAYS, MAX_MAX_DEFER_DAYS,
    } = await import('../../src/features/backtest/constants');

    expect(MIN_CAPITAL).toBeGreaterThan(0);
    expect(MAX_CAPITAL).toBeGreaterThan(MIN_CAPITAL);
    expect(MIN_FEE_RATE).toBeGreaterThanOrEqual(0);
    expect(MAX_FEE_RATE).toBeLessThan(1);
    expect(MIN_MAX_DEFER_DAYS).toBeGreaterThanOrEqual(0);
    expect(MAX_MAX_DEFER_DAYS).toBeGreaterThan(MIN_MAX_DEFER_DAYS);
  });
});