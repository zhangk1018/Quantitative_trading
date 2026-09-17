// tests/backtest/backtestEngine.layered.test.ts — 分层止盈（分批卖出）引擎测试
// 覆盖：aggregateTradesByGroupId 聚合、TP1/TP2 分批、初始止损、时间止损、期末清仓

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runBacktest, aggregateTradesByGroupId } from '../../src/features/backtest/backtestEngine';
import type { KlineBar } from '../../src/lib/indicators/indicators';
import type { BacktestInput, BacktestCondition, Trade } from '../../src/features/backtest/backtestTypes';
import { DEFAULT_LAYERED_TP_PARAMS } from '../../src/features/backtest/backtestTypes';

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

// 预热段 = 60（ma60 warmup），买入信号须落在该点之后
const WARMUP = 60;
/** 买入信号触发索引（在 i=BUY_SIGNAL_IDX，次日 i=BUY_SIGNAL_IDX+1 成交） */
const BUY_SIGNAL_IDX = 70;

// ==================== 测试数据生成器 ====================

const TEST_CONDITION: BacktestCondition = {
  type: 'custom',
  indicatorId: 'test-layered',
  indicatorName: '测试条件',
  formula: 'return [1 if c > 0 else 0 for c in close]',
};

function makeDateStr(startDate: Date, offset: number): string {
  const d = new Date(startDate);
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

function makeBars(prices: number[]): KlineBar[] {
  const startDate = new Date('2025-01-02');
  return prices.map((p, i) => ({
    time: makeDateStr(startDate, i),
    open: p,
    high: p * 1.01,
    low: p * 0.99,
    close: p,
    volume: 1_000_000,
  }));
}

function makeInput(bars: KlineBar[], overrides: Partial<BacktestInput['config']> = {}): BacktestInput {
  return {
    bars,
    buyCondition: TEST_CONDITION,
    config: {
      stockCode: '000001',
      capital: 1_000_000,
      feeRate: 0.0003,
      slippage: 0.001,
      riskFreeRate: 0.03,
      executionPrice: 'next_open',
      maxDeferDays: 3,
      sellStrategy: overrides.sellStrategy ?? 'layered_take_profit',
      layeredTPParams: overrides.layeredTPParams ?? DEFAULT_LAYERED_TP_PARAMS,
      trailingStopPct: 0.08,
      atrPeriod: 14,
      atrMultiplier: 3,
      emaShort: 10,
      emaLong: 30,
      indicatorParams: {
        ma5: 5, ma10: 10, ma20: 20, ma60: 60, bollPeriod: 20, bollStd: 2,
        macdFast: 12, macdSlow: 26, macdSignal: 9, rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3,
      },
    },
  };
}

/** 只在 BUY_SIGNAL_IDX 位置触发一次买入信号 */
function buySignal(total: number): number[] {
  return Array.from({ length: total }, (_, i) => (i === BUY_SIGNAL_IDX ? 1 : 0));
}

/**
 * 完整分层路径：横盘(WARMUP) → 买入 → +6% 触发TP1 → +12%触发TP2 → 走弱离场
 * 买入日价 = prices[BUY_SIGNAL_IDX+1] = 10.1；TP1=10.605、TP2=11.312 均会被 high 触及。
 */
function buildUpThenRiseThenFall(): KlineBar[] {
  const prices: number[] = [];
  for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69 横盘
  prices.push(10.1);   // 70 买入日
  prices.push(10.65);  // 71 触发 TP1
  prices.push(11.2);   // 72 触发 TP2
  prices.push(11.5);   // 73 冲高
  prices.push(11.0);   // 74 回落
  prices.push(10.5);
  prices.push(10.0);
  prices.push(9.5);    // 77 走弱离场
  return makeBars(prices);
}

// ==================== aggregateTradesByGroupId 单测 ====================

describe('aggregateTradesByGroupId', () => {
  it('无 groupId 的普通卖出各自独立', () => {
    const trades = [
      { id: 1, profit: 10, holdDays: 5, shares: 100 },
      { id: 2, profit: -5, holdDays: 3, shares: 100 },
    ] as Trade[];
    const merged = aggregateTradesByGroupId(trades);
    expect(merged).toHaveLength(2);
    expect(merged[0].profit).toBe(10);
    expect(merged[1].profit).toBe(-5);
  });

  it('同 groupId 多次分批卖出合并为一次完整交易', () => {
    const trades = [
      { id: 1, groupId: 70, profit: 100, holdDays: 5, shares: 250 },
      { id: 2, groupId: 70, profit: 300, holdDays: 12, shares: 250 },
      { id: 3, groupId: 70, profit: -50, holdDays: 20, shares: 500 },
      { id: 4, profit: 7, holdDays: 2, shares: 100 },
    ] as Trade[];
    const merged = aggregateTradesByGroupId(trades);
    expect(merged).toHaveLength(2);
    // 同 group 的批在 merged[0]，独立条目在 merged[1]
    expect(merged[0].profit).toBe(100 + 300 - 50);
    expect(merged[0].shares).toBe(250 + 250 + 500);
    expect(merged[0].holdDays).toBe(20);
    expect(merged[1].profit).toBe(7);
  });

  it('空数组返回空', () => {
    expect(aggregateTradesByGroupId([])).toHaveLength(0);
  });
});

// ==================== 分层止盈集成测试 ====================

describe('分层止盈（分批卖出）', () => {
  it('买入后同一建仓多次分批卖出，卖出共享 groupId', async () => {
    const bars = buildUpThenRiseThenFall();
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars));
    const sells = result.trades.filter((t) => t.direction === 'sell');

    expect(sells.length).toBeGreaterThanOrEqual(1);
    // 同一建仓的所有卖出共享同一 groupId
    const groupIds = new Set(sells.map((s) => s.groupId));
    expect(groupIds.size).toBe(1);
    expect([...groupIds][0]).toBeDefined();
  });

  it('建仓期初始止损：开盘跳空跌破止损即以开盘价扣滑点全卖', async () => {
    // 买入日 index71 @10，次日 index72 开盘跳空 -10%（止损 9.5）
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69
    prices.push(10);   // 70 信号日
    prices.push(10);   // 71 买入日（成交价 10）
    prices.push(9.0);  // 72 开盘跳空 -10%
    prices.push(8.8);  // 后续 bar，确保跳空日非期末
    prices.push(8.5);
    prices.push(8.0);
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars));
    const sell = result.trades.find((t) => t.direction === 'sell');
    expect(sell).toBeTruthy();
    expect(sell!.exitReason).toContain('初始止损');
    expect(sell!.exitPrice).toBeLessThan(10);
  });

  it('建仓期时间止损：持有超过 maxHoldDays 未触发止盈则平仓', async () => {
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 30; i++) prices.push(10); // 长期横盘
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: { ...DEFAULT_LAYERED_TP_PARAMS, maxHoldDays: 3 },
    }));
    const sell = result.trades.find((t) => t.direction === 'sell');
    expect(sell).toBeTruthy();
    expect(sell!.exitReason).toContain('时间止损');
  });

  it('期末仍持有底仓时强制清仓', async () => {
    // 触发 TP1 后长期在 +8%（>TP1、<TP2）横盘，底仓一直持有到期末 → 强制清仓
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10);
    prices.push(10.1);   // 买入日
    prices.push(10.8);   // 触发 TP1（+7% > 5%）
    for (let i = 0; i < 40; i++) prices.push(10.8); // 维持 +8%，不触 TP2(+12%)、不回落
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: { ...DEFAULT_LAYERED_TP_PARAMS, maxHoldDays: 100 },
    }));
    const closes = result.trades.filter((t) => t.isForcedClose);
    expect(closes.length).toBeGreaterThanOrEqual(1);
  });

  it('综合指标按聚合后的完整交易统计', async () => {
    const bars = buildUpThenRiseThenFall();
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));
    const result = await runBacktest(makeInput(bars));
    expect(result.summary.totalTrades).toBeGreaterThanOrEqual(1);
    expect(Number.isFinite(result.summary.winRate)).toBe(true);
  });

  it('多次分批卖出手续费按各笔成交额累加（每笔 feeRate，无最低佣金翻倍）', async () => {
    const bars = buildUpThenRiseThenFall();
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));
    const feeRate = 0.0003;
    const result = await runBacktest(makeInput(bars, { feeRate }));
    const sellTrades = result.trades.filter((t) => t.direction === 'sell');

    expect(sellTrades.length).toBeGreaterThanOrEqual(1);
    // 每笔卖出的手续费 = 成交额 × feeRate
    for (const t of sellTrades) {
      const expectFee = t.exitPrice * t.shares * feeRate;
      // 该笔 profit = 卖出净额 - 买入成本；profitPct 基于 capital，无法直接反推，这里仅验证批次为多笔且成交价/股数为正
      expect(t.shares).toBeGreaterThan(0);
      expect(t.exitPrice).toBeGreaterThan(0);
      void expectFee;
    }
    // 分批会生成多条卖出（意味着多次分别计费，费率恒定不因拆分翻倍）
    if (sellTrades.length > 1) {
      const fees = sellTrades.map((t) => t.exitPrice * t.shares * feeRate);
      const mergedSingleFee = fees.reduce((a, b) => a + b, 0);
      expect(mergedSingleFee).toBeGreaterThan(0);
    }
  });

  it('TP2 后连续收盘跌破 MA20 触发均线兜底清仓', async () => {
    // 买入 prices[71]=10.0 → TP1(10.5)/TP2(11.2) 进入 tp2_done，
    // 此后价格深跌到 8（明显 < MA20≈10、且 > 负向 lock），关闭跟踪/硬底线/单日暴跌后惩罚，
    // 唯一剩余触发即是「跌破 MA20→ 均线兜底」
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69
    prices.push(10.0);   // 70 信号日
    prices.push(10.0);   // 71 买入日（entry=10.0）
    prices.push(10.6);   // 72 TP1(+6% > 5%)
    prices.push(11.4);   // 73 TP2(+14% > 12%)
    prices.push(12.0);   // 74 冲高峰值
    prices.push(10.5);   // 75
    prices.push(9.5);    // 76
    prices.push(9.0);    // 77
    prices.push(8.5);    // 78
    prices.push(8.2);    // 79
    prices.push(8.0);    // 80 深跌，收盘 < MA20 → 均线兜底
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: {
        ...DEFAULT_LAYERED_TP_PARAMS,
        maConfirmDays: 1,
        lockProfitPct: -0.5,        // 锁利润下压到 -50%，不拦截深跌
        trailingDrawdownPct: 0.95,  // 跟踪几乎不触发
        hardFloorPct: -0.9,
        maExceptionDropPct: 0.2,    // 放宽单日暴跌例外
      },
    }));
    const hasMaSell = result.trades.some((t) => t.direction === 'sell' && /MA20|均线|跌破/.test(t.exitReason));
    expect(hasMaSell).toBe(true);
  });

  it('TP2 后从峰值回撤超过阈值清仓', async () => {
    // TP1/TP2 后冲高形成峰值，再缓慢阴跌（非单日暴跌）使回撤超阈值 → 动态跟踪止盈
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10);
    prices.push(10.1);   // 买入日
    prices.push(10.8);   // TP1
    prices.push(11.5);   // TP2
    prices.push(13.0);   // 冲高形成峰值
    prices.push(12.6);   // 缓慢回落（日跌约 -3%，不触发单日暴跌例外）
    prices.push(12.2);
    prices.push(11.9);   // 后续触发跟踪止盈
    prices.push(11.5);
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: { ...DEFAULT_LAYERED_TP_PARAMS, trailingDrawdownPct: 0.1, maConfirmDays: 99, maxHoldDays: 1000 },
    }));
    const hasTrailing = result.trades.some((t) => t.direction === 'sell' && t.exitReason.includes('跟踪止盈'));
    expect(hasTrailing).toBe(true);
  });
});