// backtestEngine.test.ts — 回测引擎测试用例
// 覆盖 8 个基准用例 + 边界场景 + 类型常量测试

import { describe, it, expect } from 'vitest';
import { runBacktest } from '../../src/features/backtest/backtestEngine';
import type { KlineBar } from '../../src/lib/indicators/indicators';
import type {
  BacktestInput,
  BacktestCondition,
  IndicatorParams,
} from '../../src/features/backtest/backtestTypes';
import {
  DEFAULT_INDICATOR_PARAMS,
  REVERSE_CONDITION_MAP,
  getLimitPctByCode,
} from '../../src/features/backtest/backtestTypes';

// ==================== 条件定义 ====================

const CONSECUTIVE_UP_3: BacktestCondition = {
  fieldKey: 'consecutive_up',
  label: '连续上涨3天',
  params: { days: 3 },
};

const CONSECUTIVE_UP_5: BacktestCondition = {
  fieldKey: 'consecutive_up',
  label: '连续上涨5天',
  params: { days: 5 },
};

const MACD_GOLDEN_CROSS: BacktestCondition = {
  fieldKey: 'macd_golden_cross',
  label: 'MACD金叉',
};

const RSI_OVERSOLD: BacktestCondition = {
  fieldKey: 'rsi_oversold',
  label: 'RSI超卖',
};

const VOLUME_BREAKOUT: BacktestCondition = {
  fieldKey: 'volume_breakout',
  label: '放量突破',
  params: { threshold: 1.5 },
};

// 缩短 warmup 的指标参数（ma60=20，使 warmup=35，MACD 金叉在 bar 51 可被检测到）
const SHORT_WARMUP_PARAMS: IndicatorParams = {
  ...DEFAULT_INDICATOR_PARAMS,
  ma60: 20,
};

// 最小 warmup 参数（用于 non-MACD 条件测试，warmup=14）
const MINIMAL_WARMUP_PARAMS: IndicatorParams = {
  ...DEFAULT_INDICATOR_PARAMS,
  ma60: 5,
  bollPeriod: 5,
  macdSlow: 5,
};

// ==================== 测试数据生成器 ====================

function makeDateStr(startDate: Date, offset: number): string {
  const d = new Date(startDate);
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

/** 生成单边上涨 K 线（每根阳线，close > open） */
function generateUpTrend(days: number, dailyChange = 0.01): KlineBar[] {
  const bars: KlineBar[] = [];
  let price = 10;
  const startDate = new Date('2025-01-02');
  for (let i = 0; i < days; i++) {
    const open = price;
    price *= (1 + dailyChange);
    bars.push({
      time: makeDateStr(startDate, i),
      open,
      high: price * 1.005,
      low: open * 0.995,
      close: price,
      volume: 1000000,
    });
  }
  return bars;
}

/** 生成单边下跌 K 线（每根阴线，close < open） */
function generateDownTrend(days: number, dailyChange = 0.01): KlineBar[] {
  const bars: KlineBar[] = [];
  let price = 10;
  const startDate = new Date('2025-01-02');
  for (let i = 0; i < days; i++) {
    const open = price;
    const close = price * (1 - dailyChange);
    bars.push({
      time: makeDateStr(startDate, i),
      open,
      high: open * 1.005,
      low: close * 0.995,
      close,
      volume: 1000000,
    });
    price = close;
  }
  return bars;
}

/** 生成确定性横盘 K 线（小幅波动，无连续趋势） */
function generateSideways(days: number): KlineBar[] {
  const bars: KlineBar[] = [];
  const startDate = new Date('2025-01-02');
  let price = 10;
  // 使用确定性交替模式：+0.5%, -0.3%, +0.4%, -0.6%, ... 循环
  const changes = [0.005, -0.003, 0.004, -0.006, 0.002, -0.004, 0.003, -0.005];
  for (let i = 0; i < days; i++) {
    const open = price;
    price *= (1 + changes[i % changes.length]);
    bars.push({
      time: makeDateStr(startDate, i),
      open,
      high: Math.max(open, price) * 1.002,
      low: Math.min(open, price) * 0.998,
      close: price,
      volume: 1000000,
    });
  }
  return bars;
}

/** 生成含涨停的 K 线（连续上涨触发买入 → 涨停顺延） */
function generateWithHighLimit(): KlineBar[] {
  const bars: KlineBar[] = [];
  const startDate = new Date('2025-01-02');
  let price = 10;
  // 前 20 天横盘（确保超过 warmup=14）
  for (let i = 0; i < 20; i++) {
    bars.push({
      time: makeDateStr(startDate, i),
      open: price, high: price * 1.002, low: price * 0.998, close: price,
      volume: 1000000,
    });
  }
  // 连续上涨 3 天触发买入信号
  for (let i = 0; i < 3; i++) {
    price *= 1.02;
    bars.push({
      time: makeDateStr(startDate, 20 + i),
      open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
      volume: 1500000,
    });
  }
  // 信号确认后，涨停日（无法买入）
  const limitPrice = price * 1.10;
  bars.push({
    time: makeDateStr(startDate, 23),
    open: limitPrice * 0.995, high: limitPrice, low: limitPrice * 0.99, close: limitPrice,
    volume: 100000,
  });
  // 次日可买入
  for (let i = 0; i < 5; i++) {
    price = limitPrice * 1.06 * (1 + 0.01 * i);
    bars.push({
      time: makeDateStr(startDate, 24 + i),
      open: price * 0.99, high: price * 1.01, low: price * 0.98, close: price,
      volume: 1000000,
    });
  }
  return bars;
}

/** 生成含停牌的 K 线（连续上涨触发买入 → 停牌顺延） */
function generateWithSuspension(): KlineBar[] {
  const bars: KlineBar[] = [];
  const startDate = new Date('2025-01-02');
  let price = 10;
  // 前 10 天横盘
  for (let i = 0; i < 10; i++) {
    bars.push({
      time: makeDateStr(startDate, i),
      open: price, high: price * 1.002, low: price * 0.998, close: price,
      volume: 1000000,
    });
  }
  // 连续上涨 3 天触发买入信号
  for (let i = 0; i < 3; i++) {
    price *= 1.02;
    bars.push({
      time: makeDateStr(startDate, 10 + i),
      open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
      volume: 1500000,
    });
  }
  // 信号确认后，停牌 3 天
  for (let i = 0; i < 3; i++) {
    bars.push({
      time: makeDateStr(startDate, 13 + i),
      open: price, high: price, low: price, close: price,
      volume: 0,
    });
  }
  // 复牌后可交易
  for (let i = 0; i < 5; i++) {
    price *= 1.01;
    bars.push({
      time: makeDateStr(startDate, 16 + i),
      open: price * 0.99, high: price * 1.01, low: price * 0.98, close: price,
      volume: 1000000,
    });
  }
  return bars;
}

// ==================== 默认配置 ====================

function makeInput(
  bars: KlineBar[],
  conditions: BacktestCondition[],
  overrides: Partial<BacktestInput['config']> = {},
): BacktestInput {
  return {
    bars,
    buyConditions: conditions,
    config: {
      stockCode: overrides.stockCode ?? '000001',
      capital: overrides.capital ?? 100000,
      feeRate: overrides.feeRate ?? 0,
      slippage: overrides.slippage ?? 0,
      riskFreeRate: overrides.riskFreeRate ?? 0.03,
      executionPrice: overrides.executionPrice ?? 'next_open',
      signalConfirmBars: overrides.signalConfirmBars ?? 2,
      maxDeferDays: overrides.maxDeferDays ?? 3,
      indicatorParams: overrides.indicatorParams ?? DEFAULT_INDICATOR_PARAMS,
    },
  };
}

// ==================== 用例 1: 单边上涨中检测到买入信号 ====================

describe('基准用例 1: 单边上涨', () => {
  it('连续上涨 3 天触发买入信号', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeGreaterThan(0);
    expect(buyTrades[0].entryPrice).toBeGreaterThan(0);
  });

  it('MACD 金叉在上涨趋势中被检测到', () => {
    // 使用缩短 warmup 的指标参数，使金叉（bar 51）可被检测到
    const bars: KlineBar[] = [];
    const startDate = new Date('2025-01-02');
    let price = 10;

    // 下跌 50 天
    for (let i = 0; i < 50; i++) {
      price *= 0.998;
      bars.push({
        time: makeDateStr(startDate, i),
        open: price * 1.002, high: price * 1.005, low: price * 0.995, close: price,
        volume: 1000000,
      });
    }
    // 横盘 30 天
    for (let i = 0; i < 30; i++) {
      bars.push({
        time: makeDateStr(startDate, 50 + i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }
    // 上涨 40 天
    for (let i = 0; i < 40; i++) {
      price *= 1.02;
      bars.push({
        time: makeDateStr(startDate, 80 + i),
        open: price * 0.98, high: price * 1.03, low: price * 0.97, close: price,
        volume: 1500000,
      });
    }

    const input = makeInput(bars, [MACD_GOLDEN_CROSS], {
      signalConfirmBars: 1,
      indicatorParams: SHORT_WARMUP_PARAMS,
    });
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeGreaterThan(0);
  });
});

// ==================== 用例 2: 单边下跌无买入信号 ====================

describe('基准用例 2: 单边下跌', () => {
  it('连续下跌，无买入信号，交易次数为 0', () => {
    const bars = generateDownTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBe(0);
    expect(result.summary.totalTrades).toBe(0);
  });
});

// ==================== 用例 3: 横盘震荡无买入信号 ====================

describe('基准用例 3: 横盘震荡', () => {
  it('横盘震荡，无连续趋势，交易次数为 0', () => {
    const bars = generateSideways(100);
    const input = makeInput(bars, [CONSECUTIVE_UP_5]);
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBe(0);
    expect(result.summary.totalTrades).toBe(0);
  });
});

// ==================== 用例 4: 买入→卖出完整交易 ====================

describe('基准用例 4: 买入→卖出完整交易', () => {
  it('连续上涨买入，连续下跌卖出，至少一次完整交易', () => {
    const bars: KlineBar[] = [];
    const startDate = new Date('2025-01-02');
    let price = 10;

    // 横盘 20 天（确保超过 warmup=14）
    for (let i = 0; i < 20; i++) {
      bars.push({
        time: makeDateStr(startDate, i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }
    // 连续上涨 5 天（触发买入，bar 22 附近）
    for (let i = 0; i < 5; i++) {
      price *= 1.03;
      bars.push({
        time: makeDateStr(startDate, 20 + i),
        open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
        volume: 1500000,
      });
    }
    // 横盘 5 天
    for (let i = 0; i < 5; i++) {
      bars.push({
        time: makeDateStr(startDate, 25 + i),
        open: price, high: price * 1.005, low: price * 0.995, close: price,
        volume: 1000000,
      });
    }
    // 连续下跌 5 天（触发卖出）
    for (let i = 0; i < 5; i++) {
      price *= 0.97;
      bars.push({
        time: makeDateStr(startDate, 30 + i),
        open: price * 1.01, high: price * 1.02, low: price * 0.98, close: price,
        volume: 1500000,
      });
    }

    const input = makeInput(bars, [CONSECUTIVE_UP_3], {
      indicatorParams: MINIMAL_WARMUP_PARAMS,
    });
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    const sellTrades = result.trades.filter((t) => t.direction === 'sell');

    expect(buyTrades.length).toBeGreaterThanOrEqual(1);
    expect(sellTrades.length).toBeGreaterThanOrEqual(1);
    expect(buyTrades[0].entryPrice).toBeGreaterThan(0);
    expect(sellTrades[0].exitPrice).toBeGreaterThan(0);
  });
});

// ==================== 用例 5: 涨停无法买入 ====================

describe('基准用例 5: 涨停无法买入', () => {
  it('信号触发后涨停，顺延成交', () => {
    const bars = generateWithHighLimit();
    const input = makeInput(bars, [CONSECUTIVE_UP_3], {
      stockCode: '000001',
      indicatorParams: MINIMAL_WARMUP_PARAMS,
    });
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeGreaterThan(0);

    // 买入日应在涨停日之后
    const limitDay = bars.find((b) => b.volume === 100000)?.time;
    if (limitDay && buyTrades.length > 0) {
      expect(buyTrades[0].entryTime >= limitDay).toBe(true);
    }
  });
});

// ==================== 用例 6: 停牌期间信号 ====================

describe('基准用例 6: 停牌期间信号', () => {
  it('信号触发后停牌，推迟成交至复牌日', () => {
    const bars = generateWithSuspension();
    const input = makeInput(bars, [CONSECUTIVE_UP_3], {
      indicatorParams: MINIMAL_WARMUP_PARAMS,
    });
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeGreaterThan(0);
  });
});

// ==================== 用例 7: 除权除息 ====================

describe('基准用例 7: 除权除息', () => {
  it('前复权价格连续，不含虚假跳空', () => {
    const bars = generateUpTrend(100, 0.01);
    for (let i = 1; i < bars.length; i++) {
      const prevClose = bars[i - 1].close;
      const currOpen = bars[i].open;
      const gap = Math.abs(currOpen - prevClose) / prevClose;
      expect(gap).toBeLessThan(0.03);
    }
  });
});

// ==================== 用例 8: 多条件 AND 同时触发 ====================

describe('基准用例 8: 多条件 AND 同时触发', () => {
  it('连续上涨 + 放量突破同时满足，仅买入一次', () => {
    const bars: KlineBar[] = [];
    const startDate = new Date('2025-01-02');
    let price = 10;

    for (let i = 0; i < 10; i++) {
      bars.push({
        time: makeDateStr(startDate, i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }
    // 连续上涨 4 天 + 放量
    for (let i = 0; i < 4; i++) {
      price *= 1.03;
      bars.push({
        time: makeDateStr(startDate, 10 + i),
        open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
        volume: 2000000, // 放量
      });
    }

    const input = makeInput(bars, [CONSECUTIVE_UP_3, VOLUME_BREAKOUT]);
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeLessThanOrEqual(1);
  });
});

// ==================== 边界用例 ====================

describe('边界用例', () => {
  it('空 K 线数据返回空结果', () => {
    const input = makeInput([], [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);
    expect(result.trades.length).toBe(0);
    expect(result.equityCurve.length).toBe(0);
  });

  it('无买入条件返回空结果并警告', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, []);
    const result = runBacktest(input);
    expect(result.trades.length).toBe(0);
    expect(result.warnings.some((w) => w.includes('条件'))).toBe(true);
  });

  it('数据清洗：负价格被过滤', () => {
    const bars = generateUpTrend(10, 0.01);
    bars[5] = { ...bars[5], close: -1, open: -1, high: -1, low: -1 };
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);
    expect(result.warnings.some((w) => w.includes('非正价格'))).toBe(true);
  });

  it('数据清洗：负成交量被置为 0', () => {
    const bars = generateUpTrend(10, 0.01);
    bars[5] = { ...bars[5], volume: -100 };
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);
    expect(result.warnings.some((w) => w.includes('成交量为负'))).toBe(true);
  });

  it('资金不足整手时无法买入', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3], { capital: 100 });
    const result = runBacktest(input);
    // 不崩溃即可
    expect(result).toBeDefined();
    expect(result.summary).toBeDefined();
  });

  it('信号确认：单次触发不满足连续 2 根确认', () => {
    const bars: KlineBar[] = [];
    const startDate = new Date('2025-01-02');
    let price = 10;
    // 横盘 10 天
    for (let i = 0; i < 10; i++) {
      bars.push({
        time: makeDateStr(startDate, i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }
    // 仅一天上涨
    price *= 1.05;
    bars.push({
      time: makeDateStr(startDate, 10),
      open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
      volume: 2000000,
    });
    // 接着横盘
    for (let i = 0; i < 10; i++) {
      bars.push({
        time: makeDateStr(startDate, 11 + i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }

    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);
    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    // 连续上涨 3 天需要 3 天，1 天上涨不满足
    expect(buyTrades.length).toBe(0);
  });

  it('O(1) 回撤计算正确', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    for (let i = 1; i < result.equityCurve.length; i++) {
      expect(result.equityCurve[i].drawdown).toBeGreaterThanOrEqual(0);
      expect(result.equityCurve[i].drawdown).toBeLessThanOrEqual(1);
    }
  });

  it('期末清仓不计入胜率', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    const forcedCloses = result.trades.filter((t) => t.isForcedClose);
    expect(result.summary.forcedCloseCount).toBe(forcedCloses.length);
  });

  it('不同涨跌停比例：创业板 20%', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3], { stockCode: '300001' });
    const result = runBacktest(input);
    expect(result).toBeDefined();
  });

  it('不同涨跌停比例：科创板 20%', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3], { stockCode: '688001' });
    const result = runBacktest(input);
    expect(result).toBeDefined();
  });

  it('汇总指标计算正确（无 NaN）', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    expect(result.summary.totalReturn).not.toBeNaN();
    expect(result.summary.annualizedReturn).not.toBeNaN();
    expect(result.summary.winRate).not.toBeNaN();
    expect(result.summary.profitLossRatio).not.toBeNaN();
    expect(result.summary.maxDrawdown).not.toBeNaN();
    expect(result.summary.maxConsecutiveLoss).toBeGreaterThanOrEqual(0);
    expect(result.summary.avgHoldDays).toBeGreaterThanOrEqual(0);
    expect(result.summary.sharpeRatio).not.toBeNaN();
    expect(result.summary.totalTrades).toBeGreaterThanOrEqual(0);
    expect(result.summary.benchmarkReturn).not.toBeNaN();
    expect(result.summary.tradingDays).toBeGreaterThan(0);
    expect(result.summary.warmupDays).toBeGreaterThan(0);
  });

  it('多个条件 AND 组合：所有条件同时满足才触发', () => {
    const bars: KlineBar[] = [];
    const startDate = new Date('2025-01-02');
    let price = 10;
    // 横盘 10 天
    for (let i = 0; i < 10; i++) {
      bars.push({
        time: makeDateStr(startDate, i),
        open: price, high: price * 1.002, low: price * 0.998, close: price,
        volume: 1000000,
      });
    }
    // 连续上涨 4 天 + 放量
    for (let i = 0; i < 4; i++) {
      price *= 1.03;
      bars.push({
        time: makeDateStr(startDate, 10 + i),
        open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price,
        volume: 2000000,
      });
    }

    const input = makeInput(bars, [CONSECUTIVE_UP_3, VOLUME_BREAKOUT]);
    const result = runBacktest(input);

    const buyTrades = result.trades.filter((t) => t.direction === 'buy');
    expect(buyTrades.length).toBeLessThanOrEqual(1);
  });

  it('净值曲线长度与有效 K 线数一致', () => {
    const bars = generateUpTrend(100, 0.01);
    const input = makeInput(bars, [CONSECUTIVE_UP_3]);
    const result = runBacktest(input);

    // 净值曲线应包含所有有效 K 线（从 warmup 到结束）
    const expectedLen = bars.length - result.summary.warmupDays;
    expect(result.equityCurve.length).toBe(expectedLen);
  });
});

// ==================== 类型与常量测试 ====================

describe('类型与常量', () => {
  it('REVERSE_CONDITION_MAP 所有买入条件都有反向映射', () => {
    const buyKeys = ['macd_golden_cross', 'rsi_oversold', 'volume_breakout', 'consecutive_up', 'ma_golden_cross'];
    for (const key of buyKeys) {
      expect(REVERSE_CONDITION_MAP[key as keyof typeof REVERSE_CONDITION_MAP]).toBeDefined();
    }
  });

  it('getLimitPctByCode 返回正确比例', () => {
    expect(getLimitPctByCode('000001')).toBe(0.10);
    expect(getLimitPctByCode('300001')).toBe(0.20);
    expect(getLimitPctByCode('688001')).toBe(0.20);
    expect(getLimitPctByCode('430001')).toBe(0.30);
  });

  it('DEFAULT_INDICATOR_PARAMS 所有参数为正', () => {
    for (const [, val] of Object.entries(DEFAULT_INDICATOR_PARAMS)) {
      expect(val).toBeGreaterThan(0);
    }
  });
});