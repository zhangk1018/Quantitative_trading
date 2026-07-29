// backtestWorker.test.ts — 回测 Worker 输入校验单元测试

import { describe, it, expect } from 'vitest';
import { validateBacktestInput, isValidTime } from '../../src/features/backtest/backtest.worker';
import type { BacktestInput } from '../../src/features/backtest/backtestTypes';
import { DEFAULT_INDICATOR_PARAMS } from '../../src/features/backtest/backtestTypes';

function makeValidInput(): BacktestInput {
  return {
    bars: [
      {
        time: '2025-01-02',
        open: 10,
        high: 11,
        low: 9,
        close: 10,
        volume: 1_000_000,
      },
    ],
    buyCondition: { indicatorId: 'test-indicator', indicatorName: '测试指标', formula: 'return [1]' },
    config: {
      stockCode: '000001',
      capital: 100_000,
      feeRate: 0,
      slippage: 0,
      riskFreeRate: 0.03,
      executionPrice: 'next_open',
      maxDeferDays: 3,
      indicatorParams: DEFAULT_INDICATOR_PARAMS,
    },
  };
}

// ==================== isValidTime ====================

describe('isValidTime', () => {
  it('接受 YYYY-MM-DD 字符串', () => {
    expect(isValidTime('2025-01-02')).toBe(true);
  });

  it('接受 ISO 日期字符串', () => {
    expect(isValidTime('2025-01-02T00:00:00.000Z')).toBe(true);
  });

  it('接受数字时间戳', () => {
    expect(isValidTime(1_704_153_600_000)).toBe(true);
  });

  it('拒绝空字符串', () => {
    expect(isValidTime('')).toBe(false);
  });

  it('拒绝空白字符串', () => {
    expect(isValidTime('   ')).toBe(false);
  });

  it('拒绝非日期字符串', () => {
    expect(isValidTime('not-a-date')).toBe(false);
  });

  it('拒绝 null / undefined', () => {
    expect(isValidTime(null)).toBe(false);
    expect(isValidTime(undefined)).toBe(false);
  });

  it('拒绝对象和数组', () => {
    expect(isValidTime({})).toBe(false);
    expect(isValidTime([])).toBe(false);
  });
});

// ==================== validateBacktestInput ====================

describe('validateBacktestInput', () => {
  it('合法输入返回 null', () => {
    expect(validateBacktestInput(makeValidInput())).toBeNull();
  });

  it('非对象输入返回错误', () => {
    expect(validateBacktestInput(null)).toContain('expected object');
    expect(validateBacktestInput('string')).toContain('expected object');
    expect(validateBacktestInput(123)).toContain('expected object');
  });

  it('空 bars 返回错误', () => {
    const input = makeValidInput();
    input.bars = [];
    expect(validateBacktestInput(input)).toContain('K 线数据为空');
  });

  it('bar 不是对象返回错误', () => {
    const input = makeValidInput();
    input.bars = [null as any];
    expect(validateBacktestInput(input)).toContain('格式错误');
  });

  it('缺失 bar 字段返回错误', () => {
    const input = makeValidInput();
    input.bars = [{ time: '2025-01-02', open: 10, high: 11, low: 9, close: 10 } as any];
    expect(validateBacktestInput(input)).toContain('缺少字段');
  });

  it('价格字段类型错误返回错误', () => {
    const input = makeValidInput();
    input.bars[0].open = '10' as any;
    expect(validateBacktestInput(input)).toContain('价格/成交量类型错误');
  });

  it('无效 time 返回错误', () => {
    const input = makeValidInput();
    input.bars[0].time = 'invalid-date';
    expect(validateBacktestInput(input)).toContain('time');
  });

  it('缺失 buyCondition 返回错误', () => {
    const input = makeValidInput();
    delete (input as any).buyCondition;
    expect(validateBacktestInput(input)).toContain('买入条件');
  });

  it('buyCondition 缺少 indicatorId 返回错误', () => {
    const input = makeValidInput();
    input.buyCondition = { indicatorId: '', indicatorName: '测试指标', formula: 'return [1]' };
    expect(validateBacktestInput(input)).toContain('自编指标 ID');
  });

  it('buyCondition 缺少 formula 返回错误', () => {
    const input = makeValidInput();
    input.buyCondition = { indicatorId: 'test-indicator', indicatorName: '测试指标', formula: '' };
    expect(validateBacktestInput(input)).toContain('自编指标公式');
  });

  it('缺失 config 返回错误', () => {
    const input = makeValidInput();
    delete (input as any).config;
    expect(validateBacktestInput(input)).toContain('回测配置为空');
  });

  it('config 缺少 capital 返回错误', () => {
    const input = makeValidInput();
    delete (input.config as any).capital;
    expect(validateBacktestInput(input)).toContain('capital');
  });

  it('config 缺少 stockCode 返回错误', () => {
    const input = makeValidInput();
    delete (input.config as any).stockCode;
    expect(validateBacktestInput(input)).toContain('stockCode');
  });
});
