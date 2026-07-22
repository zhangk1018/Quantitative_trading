// backtestEngine.test.ts — 回测引擎测试用例（新版：自编指标买入 + MA5下穿MA20卖出）
//
// 覆盖场景：
//   - 空数据 / 无信号
//   - 完整买入→卖出周期
//   - 数据清洗（负价格、负成交量）
//   - 资金不足无法买入
//   - 期末强制清仓
//   - 涨跌停比例常量

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runBacktest } from '../../src/features/backtest/backtestEngine';
import type { KlineBar } from '../../src/lib/indicators/indicators';
import type { BacktestInput, BacktestCondition } from '../../src/features/backtest/backtestTypes';
import { DEFAULT_INDICATOR_PARAMS, getLimitPctByCode } from '../../src/features/backtest/backtestTypes';

// ==================== Mock 自编指标依赖 ====================

vi.mock('../../src/features/strategy-backtest/utils/customIndicatorRunner', () => ({
  getCustomIndicatorRunner: vi.fn(),
}));

import { getCustomIndicatorRunner } from '../../src/features/strategy-backtest/utils/customIndicatorRunner';

const mockExecuteSingle = vi.fn();
const mockRunner = {
  isReady: () => true,
  init: vi.fn(),
  executeSingle: mockExecuteSingle,
};

beforeEach(() => {
  vi.mocked(getCustomIndicatorRunner).mockReturnValue(mockRunner as any);
  mockExecuteSingle.mockReset();
});

// ==================== 测试数据生成器 ====================

const TEST_CONDITION: BacktestCondition = {
  indicatorId: 'test-indicator',
  indicatorName: '测试指标',
  formula: 'return [1 if c > 0 else 0 for c in close]',
};

function makeDateStr(startDate: Date, offset: number): string {
  const d = new Date(startDate);
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

/** 生成基础 K 线（默认横盘，价格 10） */
function generateFlatBars(count: number, startOffset = 0): KlineBar[] {
  const startDate = new Date('2025-01-02');
  return Array.from({ length: count }, (_, i) => {
    const price = 10;
    return {
      time: makeDateStr(startDate, startOffset + i),
      open: price,
      high: price * 1.002,
      low: price * 0.998,
      close: price,
      volume: 1_000_000,
    };
  });
}

/**
 * 生成“横盘 → 上涨 → 下跌”序列，用于验证完整买入→卖出周期。
 * 上涨阶段使 MA5 > MA20，下跌阶段触发 MA5 下穿 MA20。
 */
function generateUptrendThenDowntrend(): KlineBar[] {
  const bars: KlineBar[] = [];
  const startDate = new Date('2025-01-02');
  let price = 10;

  // 60 天横盘（满足 ma60 warmup）
  for (let i = 0; i < 60; i++) {
    bars.push({
      time: makeDateStr(startDate, i),
      open: price,
      high: price * 1.002,
      low: price * 0.998,
      close: price,
      volume: 1_000_000,
    });
  }

  // 10 天上涨（+3% / 天）
  for (let i = 0; i < 10; i++) {
    price *= 1.03;
    bars.push({
      time: makeDateStr(startDate, 60 + i),
      open: price * 0.99,
      high: price * 1.02,
      low: price * 0.98,
      close: price,
      volume: 1_500_000,
    });
  }

  // 10 天下跌（-3% / 天），触发 MA5 下穿 MA20
  for (let i = 0; i < 10; i++) {
    price *= 0.97;
    bars.push({
      time: makeDateStr(startDate, 70 + i),
      open: price * 1.01,
      high: price * 1.02,
      low: price * 0.98,
      close: price,
      volume: 1_500_000,
    });
  }

  return bars;
}

function makeInput(bars: KlineBar[], overrides: Partial<BacktestInput['config']> = {}): BacktestInput {
  return {
    bars,
    buyCondition: TEST_CONDITION,
    config: {
      stockCode: overrides.stockCode ?? '000001',
      capital: overrides.capital ?? 100_000,
      feeRate: overrides.feeRate ?? 0,
      slippage: overrides.slippage ?? 0,
      riskFreeRate: overrides.riskFreeRate ?? 0.03,
      executionPrice: overrides.executionPrice ?? 'next_open',
      maxDeferDays: overrides.maxDeferDays ?? 3,
      indicatorParams: overrides.indicatorParams ?? DEFAULT_INDICATOR_PARAMS,
    },
  };
}

// ==================== 测试用例 ====================

describe('回测引擎 - 自编指标买入 + MA5下穿MA20卖出', () => {
  it('空 K 线数据返回空结果', async () => {
    const result = await runBacktest(makeInput([]));
    expect(result.trades.length).toBe(0);
    expect(result.equityCurve.length).toBe(0);
  });

  it('无买入信号时不产生交易', async () => {
    const bars = generateFlatBars(100);
    mockExecuteSingle.mockResolvedValue(Array(100).fill(0));
    const result = await runBacktest(makeInput(bars));
    expect(result.trades.filter((t) => t.direction === 'buy').length).toBe(0);
    expect(result.summary.totalTrades).toBe(0);
  });

  it('买入信号后完成完整买入→卖出交易', async () => {
    const bars = generateUptrendThenDowntrend();
    // 信号确认机制已废除：仅需信号日当天为 1，次日即可执行
    const signals = Array(80).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars));
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    const sellTrades = result.trades.filter((t) => t.direction === 'sell');

    expect(buyTrades.length).toBeGreaterThanOrEqual(1);
    expect(sellTrades.length).toBeGreaterThanOrEqual(1);
    expect(buyTrades[0].entryPrice).toBeGreaterThan(0);
    expect(sellTrades[0].exitPrice).toBeGreaterThan(0);
    expect(sellTrades[0].exitReason).toContain('MA5');
  });

  it('孤立买入信号（非连续）也能触发交易', async () => {
    const bars = generateUptrendThenDowntrend();
    // 仅在索引 65 出现一次信号，不连续
    const signals = Array(80).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars));
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');

    expect(buyTrades.length).toBeGreaterThanOrEqual(1);
    expect(result.warnings.some((w) => w.includes('条件已消失'))).toBe(false);
  });

  it('买入信号出现在回测最后交易日时无法 T+1 执行并告警', async () => {
    const bars = generateFlatBars(100);
    // 仅在最后一根 K 线出现信号
    const signals = Array(100).fill(0).map((_, i) => (i === 99 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars));
    expect(result.trades.filter((t) => t.direction === 'buy').length).toBe(0);
    expect(result.warnings.some((w) => w.includes('最后交易日') || w.includes('T+1'))).toBe(true);
  });

  it('数据清洗：负价格被过滤并告警', async () => {
    const bars = generateFlatBars(20);
    bars[10] = { ...bars[10], open: -1, high: -1, low: -1, close: -1 };
    mockExecuteSingle.mockResolvedValue(Array(20).fill(0));
    const result = await runBacktest(makeInput(bars));
    expect(result.warnings.some((w) => w.includes('非正价格'))).toBe(true);
  });

  it('数据清洗：负成交量被置为 0 并告警', async () => {
    const bars = generateFlatBars(20);
    bars[10] = { ...bars[10], volume: -100 };
    mockExecuteSingle.mockResolvedValue(Array(20).fill(0));
    const result = await runBacktest(makeInput(bars));
    expect(result.warnings.some((w) => w.includes('成交量为负'))).toBe(true);
  });

  it('资金不足 1 手时无法买入并告警', async () => {
    const bars = generateFlatBars(100).map((bar) => ({
      ...bar,
      open: 10_000,
      high: 10_100,
      low: 9_900,
      close: 10_000,
    }));
    mockExecuteSingle.mockResolvedValue(Array(100).fill(0).map((_, i) => (i === 65 || i === 66 ? 1 : 0)));
    const result = await runBacktest(makeInput(bars, { capital: 1_000 }));
    expect(result.trades.filter((t) => t.direction === 'buy').length).toBe(0);
    expect(result.warnings.some((w) => w.includes('资金不足'))).toBe(true);
  });

  it('期末强制清仓标记正确', async () => {
    const bars = generateUptrendThenDowntrend();
    mockExecuteSingle.mockResolvedValue(Array(80).fill(0).map((_, i) => (i === 65 || i === 66 ? 1 : 0)));
    const result = await runBacktest(makeInput(bars));
    const forcedCloses = result.trades.filter((t) => t.isForcedClose);
    expect(result.summary.forcedCloseCount).toBe(forcedCloses.length);
  });

  it('自编指标执行失败时返回空结果并告警', async () => {
    const bars = generateFlatBars(100);
    mockExecuteSingle.mockRejectedValue(new Error('脚本语法错误'));
    const result = await runBacktest(makeInput(bars));
    expect(result.trades.length).toBe(0);
    expect(result.warnings.some((w) => w.includes('自编指标执行失败'))).toBe(true);
  });

  it('返回的信号长度与 K 线数量不一致时告警', async () => {
    const bars = generateFlatBars(100);
    mockExecuteSingle.mockResolvedValue(Array(50).fill(0));
    const result = await runBacktest(makeInput(bars));
    expect(result.trades.length).toBe(0);
    expect(result.warnings.some((w) => w.includes('长度'))).toBe(true);
  });

  it('不同涨跌停比例均能正常执行', async () => {
    const bars = generateUptrendThenDowntrend();
    mockExecuteSingle.mockResolvedValue(Array(80).fill(0).map((_, i) => (i === 65 ? 1 : 0)));

    for (const code of ['000001', '300001', '688001', '430001']) {
      const result = await runBacktest(makeInput(bars, { stockCode: code }));
      expect(result).toBeDefined();
      expect(result.summary).toBeDefined();
    }
  });
});

describe('类型与常量', () => {
  it('getLimitPctByCode 返回正确比例', () => {
    expect(getLimitPctByCode('000001')).toBe(0.10);
    expect(getLimitPctByCode('300001')).toBe(0.20);
    expect(getLimitPctByCode('688001')).toBe(0.20);
    expect(getLimitPctByCode('430001')).toBe(0.30);
  });
});
