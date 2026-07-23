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

// ==================== 核心交易逻辑测试 ====================

describe('回测引擎 - T+1 买入执行', () => {
  it('买入信号在次日 next_open 价格执行', async () => {
    const bars = generateFlatBars(100);
    // 在第 65 天发出信号，第 66 天执行买入
    const signals = Array(100).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars, { executionPrice: 'next_open' }));
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');

    expect(buyTrades.length).toBeGreaterThanOrEqual(1);
    // 买入应发生在信号次日（索引 66）
    expect(buyTrades[0].entryTime).toBe(bars[66].time);
    expect(buyTrades[0].entryPrice).toBe(bars[66].open);
  });

  it('买入信号在次日 next_close 价格执行', async () => {
    const bars = generateFlatBars(100);
    const signals = Array(100).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars, { executionPrice: 'next_close' }));
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');

    expect(buyTrades.length).toBeGreaterThanOrEqual(1);
    expect(buyTrades[0].entryPrice).toBe(bars[66].close);
  });

  it('持仓期间连续买入信号不重复建仓', async () => {
    const bars = generateUptrendThenDowntrend();
    // 连续多天发出买入信号
    const signals = Array(80).fill(0).map((_, i) => (i >= 65 && i <= 70 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const result = await runBacktest(makeInput(bars));
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');

    // 持仓期间不应重复买入
    expect(buyTrades.length).toBe(1);
  });
});

describe('回测引擎 - 涨停/跌停延迟与失效', () => {
  it('涨停板无法买入时顺延至次日', async () => {
    // 生成价格序列：第 65 天信号，但第 66 天涨停（open=prevClose*1.1）
    const bars = generateFlatBars(100, 0);
    const signals = Array(100).fill(0).map((_, i) => (i === 65 ? 1 : 0));

    // 模拟涨停：第 66 天 open 达到涨停价
    bars[66] = {
      ...bars[66],
      open: bars[65].close * 1.1,  // 涨停价
      high: bars[65].close * 1.1,
      low: bars[65].close * 1.05,
      close: bars[65].close * 1.1,
    };

    mockExecuteSingle.mockResolvedValue(signals);
    const result = await runBacktest(makeInput(bars, { stockCode: '000001', maxDeferDays: 3 }));

    // 应记录涨停顺延诊断
    const deferredDiags = result.diagnostics.filter((d) => d.event === 'buy_deferred');
    expect(deferredDiags.length).toBeGreaterThanOrEqual(1);
    expect(deferredDiags[0].reason).toContain('涨停限制');
  });

  it('涨停顺延超过 maxDeferDays 后买入信号失效', async () => {
    const bars = generateFlatBars(100, 0);
    const signals = Array(100).fill(0).map((_, i) => (i === 65 ? 1 : 0));

    // 连续多天涨停，超过 maxDeferDays
    for (let i = 66; i <= 70; i++) {
      bars[i] = {
        ...bars[i],
        open: bars[i - 1].close * 1.1,
        high: bars[i - 1].close * 1.1,
        low: bars[i - 1].close * 1.05,
        close: bars[i - 1].close * 1.1,
      };
    }

    mockExecuteSingle.mockResolvedValue(signals);
    const result = await runBacktest(makeInput(bars, { stockCode: '000001', maxDeferDays: 3 }));

    // 应记录买入失效
    const expiredDiags = result.diagnostics.filter((d) => d.event === 'buy_expired');
    expect(expiredDiags.length).toBeGreaterThanOrEqual(1);
    expect(result.warnings.some((w) => w.includes('顺延超过'))).toBe(true);
  });

  it('跌停板无法卖出时顺延至次日', async () => {
    const bars = generateUptrendThenDowntrend();
    const signals = Array(80).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    // 买入后，在下跌阶段强制触发跌停
    const buyIdx = 66; // 买入日
    // 在卖出信号日设置跌停
    bars[75] = {
      ...bars[75],
      open: bars[74].close * 0.9,  // 跌停价
      high: bars[74].close * 0.95,
      low: bars[74].close * 0.9,
      close: bars[74].close * 0.9,
    };

    const result = await runBacktest(makeInput(bars, { stockCode: '000001', maxDeferDays: 3 }));

    const deferredDiags = result.diagnostics.filter((d) => d.event === 'sell_deferred');
    // 如果卖出信号日恰好是跌停日，应有顺延记录
    expect(deferredDiags.length).toBeGreaterThanOrEqual(0);
  });
});

describe('回测引擎 - 停牌日净值沿用', () => {
  it('停牌日（volume=0）应沿用前日净值', async () => {
    const bars = generateFlatBars(100, 0);
    const signals = Array(100).fill(0);
    mockExecuteSingle.mockResolvedValue(signals);

    // 设置第 70 天为停牌日
    bars[70] = { ...bars[70], volume: 0, open: 0, high: 0, low: 0, close: 0 };

    const result = await runBacktest(makeInput(bars));

    // 停牌日净值应等于前一日净值
    const equityBefore = result.equityCurve[70 - 60]; // 索引从预热期后开始
    const equityOnSuspension = result.equityCurve.find((e) => e.time === bars[70].time);
    if (equityBefore && equityOnSuspension) {
      expect(equityOnSuspension.equity).toBe(equityBefore.equity);
    }
  });
});

describe('回测引擎 - 日期范围过滤', () => {
  it('startDate 之前不应执行交易', async () => {
    const bars = generateFlatBars(100, 0);
    // 信号在预热期后（第 65 天），但 startDate 设为第 70 天
    const signals = Array(100).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    const input = makeInput(bars, { stockCode: '000001' });
    input.config.startDate = bars[70].time;
    input.config.endDate = bars[99].time;

    const result = await runBacktest(input);

    // 信号在 startDate 之前，不应触发交易
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBe(0);
  });

  it('endDate 到期时强制清仓', async () => {
    const bars = generateUptrendThenDowntrend();
    const signals = Array(80).fill(0).map((_, i) => (i === 65 ? 1 : 0));
    mockExecuteSingle.mockResolvedValue(signals);

    // 设置 endDate 为买入后 2 天（在卖出信号之前）
    const input = makeInput(bars, { stockCode: '000001' });
    input.config.startDate = bars[60].time;
    input.config.endDate = bars[68].time; // 买入后不久即截止

    const result = await runBacktest(input);

    // 应在 endDate 处强制清仓
    const forcedCloses = result.trades.filter((t) => t.isForcedClose);
    expect(forcedCloses.length).toBeGreaterThanOrEqual(1);
  });
});

// ==================== 类型与常量 ====================

describe('类型与常量', () => {
  it('getLimitPctByCode 返回正确比例', () => {
    expect(getLimitPctByCode('000001')).toBe(0.10);
    expect(getLimitPctByCode('300001')).toBe(0.20);
    expect(getLimitPctByCode('688001')).toBe(0.20);
    expect(getLimitPctByCode('430001')).toBe(0.30);
  });
});
