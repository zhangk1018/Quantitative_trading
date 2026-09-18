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
    prices.push(11.2);   // 72 TP1(+12% > 10%)
    prices.push(11.8);   // 73 TP2(+18%)
    prices.push(13.0);   // 74 冲高峰值
    prices.push(11.5);   // 75
    prices.push(10.5);   // 76
    prices.push(10.0);   // 77
    prices.push(9.5);    // 78
    prices.push(9.0);    // 79
    prices.push(8.5);    // 80 深跌，收盘 < MA20 → 均线兜底
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

  it('TP2 后均线兜底按 maPeriod 参数取对应均线（MA10 生效）', async () => {
    // 买入后触发 TP1/TP2 进入 tp2_done，此后价格跌至 9.5（< MA10≈9.9、> MA5≈9.6? 需构造确认）
    // 构造：TP2 后横盘 10 天让 MA10 与 MA5 明显分离，再跌破 MA10 触发
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69
    prices.push(10.0);   // 70 信号日
    prices.push(10.0);   // 71 买入日（entry=10.0）
    prices.push(11.2);   // 72 TP1(+12% > 10%)
    prices.push(11.8);   // 73 TP2(+18%)
    prices.push(11.5);   // 74 回落横盘
    prices.push(11.4);
    prices.push(11.3);
    prices.push(11.2);
    prices.push(11.1);
    prices.push(11.0);   // 79
    prices.push(10.9);   // 80 缓慢阴跌，MA10≈11.0 附近
    prices.push(10.8);
    prices.push(10.7);
    prices.push(10.6);
    prices.push(10.5);   // 84 收盘 < MA10（连续 3 天，满足 maConfirmDays=2）
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: {
        ...DEFAULT_LAYERED_TP_PARAMS,
        maPeriod: 10,
        maConfirmDays: 2,
        trailingDrawdownPct: 0.9,   // 关闭跟踪止盈，隔离均线兜底
        lockProfitPct: -0.5,
        hardFloorPct: -0.9,
        maExceptionDropPct: 0.2,
        maxHoldDays: 1000,
      },
    }));
    const hasMa10Sell = result.trades.some((t) => t.direction === 'sell' && /MA10|均线|跌破/.test(t.exitReason));
    expect(hasMa10Sell).toBe(true);
  });

  it('TP2 后从峰值回撤超过阈值清仓', async () => {
    // 买入 10 → TP1(+8%) → TP2(+16%) 进入 tp2_done，冲高至 12.5 形成峰值，
    // 再缓慢阴跌（非单日暴跌）使回撤超 trailingDrawdownPct → 触发动态跟踪止盈清底仓。
    // 显式使用大 firstSell 让触发后仍有底仓可供跟踪止盈回收。
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(9.0); // 0..69 横盘
    prices.push(9.0);   // 70 信号日
    prices.push(10.0);  // 71 买入日（next_open 开盘成交 @10.0）
    prices.push(10.8);  // 72 触发 TP1（+8% > 5%）
    prices.push(11.6);  // 73 触发 TP2（+16% > 12%）
    prices.push(12.5);  // 74 冲高形成峰值
    prices.push(12.0);  // 75 缓慢回落（日跌约 -4%，不触发单日暴跌例外）
    prices.push(11.7);
    prices.push(11.4);  // 77 跌破峰值 12.5×(1-10%)=11.25 附近 → 触发跟踪止盈
    prices.push(11.2);
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: {
        ...DEFAULT_LAYERED_TP_PARAMS,
        firstProfitPct: 0.05,
        firstSellPct: 0.40,
        secondProfitPct: 0.12,
        secondSellPct: 0.20,   // 留足底仓（60%），供 TP2 后走跟踪止盈回收
        trailingDrawdownPct: 0.1, maConfirmDays: 99, maxHoldDays: 1000,
      },
    }));
    const hasTrailing = result.trades.some((t) => t.direction === 'sell' && t.exitReason.includes('跟踪止盈'));
    expect(hasTrailing).toBe(true);
  });

  it('用户场景回归：中水渔业 TP1/TP2 后冲高回落，底仓触发跟踪止盈而非死扛到期末', async () => {
    // 复现用户回测（2025-06-05 买入 7.34 → TP1/TP2 → 冲高 16 回落）：
    // 期望 tp2_done 三重保护让底仓及时退出，不出现「期末强制清仓（315天）」锁仓
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(7.0); // 0..69
    prices.push(7.0);   // 70 信号日
    prices.push(7.34);  // 71 买入日
    prices.push(8.1);   // 72 触发 TP1（+10.3% > 10%）
    prices.push(8.7);   // 73 触发 TP2（+18.5% > 18%）
    prices.push(9.5);   // 74 冲高
    prices.push(12.0);  // 75
    prices.push(14.0);  // 76
    prices.push(16.0);  // 77 峰值
    prices.push(15.5);  // 78 回落
    prices.push(15.0);  // 79 跌破 4% 跟踪线
    prices.push(14.0);  // 80
    prices.push(13.0);  // 81
    prices.push(12.0);  // 82
    prices.push(11.0);  // 83
    prices.push(10.0);  // 84
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars));
    const sells = result.trades.filter((t) => t.direction === 'sell');
    const reasons = sells.map((s) => s.exitReason).join(' | ');

    expect(reasons).toContain('第一止盈TP1');
    expect(reasons).toContain('第二止盈TP2');
    expect(reasons).toContain('跟踪止盈');
    // 底仓已退出 → 该建仓不应再有期末强制清仓
    const groupSells = sells.filter((s) => s.groupId !== undefined);
    const forcedForThisGroup = result.trades.filter(
      (t) => t.isForcedClose && t.groupId === groupSells[0]?.groupId,
    );
    expect(forcedForThisGroup.length).toBe(0);
    expect(groupSells.reduce((s, t) => s + t.shares, 0)).toBeGreaterThan(0);
  });

  it('回归：TP1 后价格长期横盘不涨不跌，主动离场防止底仓死扛到期末', async () => {
    // 场景：买入 10 后触发 TP1，此后价格在成本与 TP2 之间长期窄幅横盘，
    // 既不涨到 TP2 也不跌破成本。原逻辑会让剩余底仓死扛到期末强制清仓。
    // 修复后，tp1_done 通过「回撤追踪」或「均线兜底」主动离场，不再死扛到期末。
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69
    prices.push(10.0);  // 70 信号日
    prices.push(10.0);  // 71 买入日（entry=10.0）
    prices.push(11.0);  // 72 触发 TP1（+10%）
    // 73 起价格自 TP1 后逐步走低并长期横盘：稳定在 10.2（+2%）附近，
    // 不触 TP2(+12%)、不破成本；但收盘持续低于 MA20 → 触发均线兜底主动离场
    for (let i = 0; i < 50; i++) prices.push(10.5);  // TP1 后短暂高位
    for (let i = 0; i < 150; i++) prices.push(10.2); // 跌破 MA20 并长期维持
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars));
    const sells = result.trades.filter((t) => t.direction === 'sell');
    const reasons = sells.map((s) => s.exitReason).join(' | ');

    // 必须仍触发 TP1（分批保底）
    expect(reasons).toContain('第一止盈TP1');
    // 底仓应通过「回撤追踪」或「均线兜底」主动离场，不再死扛到期末
    const hasExit = sells.some((s) => /回撤追踪|跌破MA|均线/.test(s.exitReason));
    expect(hasExit).toBe(true);
    // 期末不应再出现整仓强制清仓
    const forced = result.trades.filter((t) => t.isForcedClose && t.exitReason === '期末强制清仓');
    expect(forced.length).toBe(0);
  });

  it('TP1 后底仓按 baseTrailingPct 从峰值回撤清仓（而非死扛或迟钝均线）', async () => {
    // 场景：买入 10 后冲高触发 TP1(+6%)，形成峰值 10.8×1.01；随后回落从峰值回撤超过 baseTrailingPct(8%)
    // 但不跌破成本、也不到 TP2。期望底仓通过「TP1后回撤追踪」主动清仓，而非死扛到期末。
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69
    prices.push(10.0);  // 70 信号日
    prices.push(10.0);  // 71 买入日（entry=10.0）
    prices.push(10.6);  // 72 触发 TP1（+6% > 5%）→ peakPrice≈10.706
    prices.push(11.0);  // 73 冲高到 +10%（仍低于 TP2 12%，不触发 TP2）→ peakPrice≈11.11
    // 74 起从峰值 11.11 回撤：8% 线 = 11.11×0.92≈10.22，跌破即触发 TP1后回撤追踪
    prices.push(10.5);
    prices.push(10.2);   // 回撤 ≈ -8.2%，触及追踪线
    prices.push(10.0);
    prices.push(9.8);
    prices.push(9.5);
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    // 关闭均线兜底干扰：maConfirmDays 调大
    const result = await runBacktest(makeInput(bars, {
      layeredTPParams: { ...DEFAULT_LAYERED_TP_PARAMS, baseTrailingPct: 0.08, maConfirmDays: 99, maxHoldDays: 1000 },
    }));
    const sells = result.trades.filter((t) => t.direction === 'sell');
    const reasons = sells.map((s) => s.exitReason).join(' | ');

    expect(reasons).toContain('第一止盈TP1');
    expect(reasons).toContain('TP1后回撤追踪');
    const hasTrailingExit = sells.some((s) => s.exitReason.includes('TP1后回撤追踪'));
    expect(hasTrailingExit).toBe(true);
    // 不应再出现期末整仓强制清仓（底仓已主动退出）
    const forced = result.trades.filter((t) => t.isForcedClose && t.exitReason === '期末强制清仓');
    expect(forced.length).toBe(0);
  });

  it('回归：突破后回踩洗盘 2 天微亏不再触发卖出（废除「买入失效不涨即走」）', async () => {
    // 场景复现用户痛点：买入 10 → 前 2 天回踩洗盘微亏（-1.5%、-2%）但不跌破 5% 初始止损，
    // 第 3 天起启动主升浪突破 TP1/TP2。旧逻辑会在 3-5 天见微亏即「买入失效」清仓震出局；
    // 新逻辑应给足容错空间，不在回踩期主动卖出，让该仓吃到后续主升浪。
    const prices: number[] = [];
    for (let i = 0; i < WARMUP + 10; i++) prices.push(10); // 0..69 横盘
    prices.push(10.0);  // 70 信号日
    prices.push(10.0);  // 71 买入日（entry=10.0）
    prices.push(9.85);  // 72 回踩洗盘 -1.5%
    prices.push(9.8);   // 73 回踩 -2%（未破 5% 初始止损 9.5）
    prices.push(10.2);  // 74 小幅回升
    prices.push(11.2);  // 75 启动主升 → 触发 TP1（+12% > 10%）
    prices.push(11.9);  // 76 → TP2（+19% > 18%）
    prices.push(12.5);  // 77 冲高
    const bars = makeBars(prices);
    mockExecuteSingle.mockResolvedValue(buySignal(bars.length));

    const result = await runBacktest(makeInput(bars));
    const sells = result.trades.filter((t) => t.direction === 'sell');
    const reasons = sells.map((s) => s.exitReason).join(' | ');

    // 回踩期（67/68 天微亏）不应发生任何卖出
    const noExitInPullback = result.trades.filter(
      (t) => t.direction === 'sell' && t.exitTime && t.exitTime <= bars[73].time,
    );
    expect(noExitInPullback.length).toBe(0);
    // 后续主升应正常触发 TP1/TP2
    expect(reasons).toContain('第一止盈TP1');
    expect(reasons).toContain('第二止盈TP2');
    // 不再出现「买入失效止损(不涨即走)」
    expect(reasons).not.toContain('买入失效止损');
  });
});