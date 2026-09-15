// tests/backtest/customSellEngine.test.ts — 自编卖出策略引擎行为测试
// 覆盖：custom 卖出信号在持仓时触发卖出、全 false 不触发、脚本错误回退内置、长度不符回退内置

import { describe, it, expect, vi, beforeEach } from 'vitest';

// mock Pyodide 执行器：不加载真 Pyodide，按脚本内容返回确定信号
const executeSingleMock = vi.fn();

vi.mock('../../src/features/strategy-backtest/utils/customIndicatorRunner', () => ({
  getCustomIndicatorRunner: () => ({
    isReady: () => true,
    init: async () => {},
    executeSingle: executeSingleMock,
  }),
}));

// 构造 200 根日 K 线（简单上升序列）。预热期 = ma60(60)+ → 信号须落在 60 之后
function makeBars(n = 200): Array<{
  time: string; open: number; high: number; low: number; close: number; volume: number;
}> {
  const bars = [];
  const start = new Date('2025-01-02');
  for (let i = 0; i < n; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const close = 10 + i * 0.1;
    bars.push({
      time: d.toISOString().slice(0, 10),
      open: close - 0.1,
      high: close + 0.2,
      low: close - 0.2,
      close,
      volume: 1000000,
    });
  }
  return bars;
}

const BUY = makeBars();
/** 买入信号出现日（i>=100 恒 true，超过预热期 60） */
const BUY_START = 100;
/** 自编卖出信号触发日 */
const SELL_AT = 120;

/** 构造合法回测输入（买入信号默认全 true → 开仓后 custom 卖出信号决定何时平仓） */
function makeInput(
  sellFormula: string,
  sellSignals: (number | null)[] | null,
  opts: { buyAllTrue?: boolean } = {},
) {
  const buyAllTrue = opts.buyAllTrue ?? true;
  executeSingleMock
    .mockReset()
    // 第一次调用 = 买入信号计算
    .mockImplementationOnce(() =>
      Promise.resolve(buyAllTrue ? BUY.map((_, i) => (i < BUY_START ? 0 : 1)) : []),
    );
  if (sellSignals !== null) {
    executeSingleMock.mockImplementationOnce(() => Promise.resolve(sellSignals));
  }

  return {
    bars: BUY,
    buyCondition: {
      type: 'custom',
      indicatorId: 'test_ind',
      indicatorName: '测试买入',
      formula: 'def calculate(o,h,l,c,v): return [0]*len(c)',
    },
    config: {
      stockCode: '600032',
      startDate: '2025-01-02',
      endDate: '2025-12-31',
      capital: 100000,
      sellStrategy: 'custom',
      customSellStrategy: sellFormula
        ? { type: 'custom', strategyId: 'sell_1', strategyName: '测试卖出', formula: sellFormula }
        : undefined,
      trailingStopPct: 0.08,
      atrPeriod: 14,
      atrMultiplier: 3,
      emaShort: 10,
      emaLong: 30,
      feeRate: 0.00025,
      slippage: 0.0001,
      riskFreeRate: 0.03,
      executionPrice: 'next_close',
      maxDeferDays: 3,
      indicatorParams: {
        ma5: 5, ma10: 10, ma20: 20, ma60: 60,
        bollPeriod: 20, bollStd: 2,
        macdFast: 12, macdSlow: 26, macdSignal: 9,
        rsiPeriod: 6, kdjK: 9, kdjD: 3, kdjJ: 3,
      },
    },
  };
}

beforeEach(() => {
  executeSingleMock.mockReset();
});

describe('自编卖出策略（纯信号协议）', () => {
  it('持仓时遇 custom 卖出信号触发卖出交易', async () => {
    const { runBacktest } = await import('../../src/features/backtest/backtestEngine');
    // 买入：BUY_START 起全 true；卖出：SELL_AT 触发（true），其余 false
    const sellSignals = BUY.map((_, i) => (i === SELL_AT ? 1 : 0));
    const input = makeInput('SELL_SCRIPT', sellSignals);

    const output = await runBacktest(input);
    const sells = output.trades.filter((t) => t.direction === 'sell');
    expect(sells.length).toBeGreaterThanOrEqual(1);
  });

  it('卖出信号全 false 时不触发卖出（无完整交易或被期末清仓）', async () => {
    const { runBacktest } = await import('../../src/features/backtest/backtestEngine');
    const sellSignals = BUY.map(() => 0);
    const input = makeInput('SELL_SCRIPT_NONE', sellSignals);

    const output = await runBacktest(input);
    const sells = output.trades.filter((t) => t.direction === 'sell');
    expect(sells.length).toBe(0);
  });

  it('executeSingle 抛错 → 回退内置 trailing_stop、warnings 提示、回测仍完成', async () => {
    const { runBacktest } = await import('../../src/features/backtest/backtestEngine');
    const input = makeInput('SELL_SCRIPT_ERROR', null);
    // 覆盖第一次买入成功后，第二次（卖出）抛错
    executeSingleMock
      .mockReset()
      .mockImplementationOnce(() => Promise.resolve(BUY.map((_, i) => (i < BUY_START ? 0 : 1))))
      .mockImplementationOnce(() => Promise.reject(new Error('脚本执行超时')));

    const output = await runBacktest(input);
    expect(output.warnings.some((w) => w.includes('已回退内置策略'))).toBe(true);
  });

  it('卖出信号长度与 K 线不符 → 回退内置 + warnings', async () => {
    const { runBacktest } = await import('../../src/features/backtest/backtestEngine');
    const input = makeInput('SELL_SCRIPT_SHORT', [1, 0, 1]); // 长度 3 ≠ 200

    const output = await runBacktest(input);
    expect(output.warnings.some((w) => w.includes('信号长度'))).toBe(true);
    expect(output.warnings.some((w) => w.includes('回退'))).toBe(true);
  });
});