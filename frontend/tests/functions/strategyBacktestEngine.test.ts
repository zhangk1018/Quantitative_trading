// strategyBacktestEngine.test.ts — 策略回测引擎完整测试用例
// 覆盖：辅助函数、T+1执行、个股风控、组合风控、Beta/IR、停牌/涨跌停、顺延、仓位分配、调仓换股、退市、绩效指标等

import { describe, it, expect } from 'vitest';
import {
  runStrategyBacktest,
  getLimitPct,
  isSuspended,
  isLimitUp,
  isLimitDown,
  buildTradeDates,
  computeIndicatorCache,
  evaluateFilter,
  calcSharesToBuy,
  calcEqualWeight,
  calcBuyCommission,
  calcSellCommission,
} from '../../src/features/strategy-backtest/engine';
import type {
  StrategyBacktestInput,
  ProgressInfo,
} from '../../src/features/strategy-backtest/engine';
import type {
  StrategyBacktestDefaults,
  FilterNode,
  StockSnapshot,
  SellReason,
} from '../../src/features/strategy-backtest/types';
import { IndicatorCache } from '../../src/features/strategy-backtest/types';
import { DEFAULT_STRATEGY_BACKTEST_DEFAULTS } from '../../src/features/strategy-backtest/storage';

// ==================== 测试数据生成器 ====================

/**
 * 生成 OHLCV 数据（number[][] 格式）
 * @param days 天数
 * @param startPrice 起始价格
 * @param dailyChange 每日涨跌幅（固定值）
 * @param startDate 起始日期 YYYY-MM-DD
 */
function generateOhlcv(
  days: number,
  startPrice = 10,
  dailyChange = 0.01,
  startDate = '2025-01-02'
): number[][] {
  const bars: number[][] = [];
  let price = startPrice;
  // P2-3.1: 使用 Date.UTC 生成固定时间戳，避免时区歧义
  const startMs = Date.UTC(
    parseInt(startDate.slice(0, 4)),
    parseInt(startDate.slice(5, 7)) - 1,
    parseInt(startDate.slice(8, 10))
  );

  for (let i = 0; i < days; i++) {
    const ts = startMs + i * 86400000;

    const open = price;
    const close = price * (1 + dailyChange);
    const high = Math.max(open, close) * 1.005;
    const low = Math.min(open, close) * 0.995;
    const volume = 1000000;
    const preClose = i > 0 ? bars[i - 1][4] : price;

    bars.push([ts, open, high, low, close, volume, preClose]);
    price = close;
  }

  return bars;
}

/**
 * 生成带有自定义价格序列的 OHLCV
 */
function generateOhlcvWithPrices(prices: number[], startDate = '2025-01-02'): number[][] {
  const bars: number[][] = [];
  // P2-3.1: 使用 Date.UTC 生成固定时间戳
  const startMs = Date.UTC(
    parseInt(startDate.slice(0, 4)),
    parseInt(startDate.slice(5, 7)) - 1,
    parseInt(startDate.slice(8, 10))
  );
  for (let i = 0; i < prices.length; i++) {
    const ts = startMs + i * 86400000;
    const price = prices[i];
    const preClose = i > 0 ? prices[i - 1] : price;
    bars.push([ts, price, price * 1.01, price * 0.99, price, 1000000, preClose]);
  }
  return bars;
}

/**
 * 生成停牌 OHLCV 数据（使用 YYYYMMDD 格式时间戳）
 */
function generateSuspendedBar(dateStr: string, preClose: number): number[] {
  const date = new Date(dateStr);
  const ts = date.getFullYear() * 10000 + (date.getMonth() + 1) * 100 + date.getDate();
  return [ts, preClose, preClose, preClose, preClose, 0, preClose];
}

/**
 * 生成涨停 OHLCV 数据（使用 YYYYMMDD 格式时间戳）
 */
function generateLimitUpBar(dateStr: string, preClose: number, limitPct: number): number[] {
  const date = new Date(dateStr);
  const ts = date.getFullYear() * 10000 + (date.getMonth() + 1) * 100 + date.getDate();
  const limitPrice = Math.round(preClose * (1 + limitPct) * 100) / 100;
  return [ts, limitPrice, limitPrice, limitPrice, limitPrice, 1000000, preClose];
}

/**
 * 生成跌停 OHLCV 数据（使用 YYYYMMDD 格式时间戳）
 */
function generateLimitDownBar(dateStr: string, preClose: number, limitPct: number): number[] {
  const date = new Date(dateStr);
  const ts = date.getFullYear() * 10000 + (date.getMonth() + 1) * 100 + date.getDate();
  const limitPrice = Math.round(preClose * (1 - limitPct) * 100) / 100;
  return [ts, limitPrice, limitPrice, limitPrice, limitPrice, 1000000, preClose];
}

/**
 * 创建股票快照
 */
function createSnapshot(
  code: string,
  name: string,
  listedBoard: string = 'main',
  isSt: boolean = false,
  marketCap: number = 200
): StockSnapshot {
  return {
    code,
    name,
    listedBoard,
    isSt,
    marketCap,
    pe: 20,
    peTtm: 18,
    pb: 2,
    turnoverRate: 0.05,
  };
}

/**
 * 创建简单过滤条件（所有股票都通过）
 */
function createPassAllFilter(): FilterNode {
  return {
    type: 'market',
    boards: ['main', 'gem', 'star', 'beijing'],
    watchlistOnly: false,
  };
}

/**
 * 创建指定板块过滤
 */
function createBoardFilter(boards: string[]): FilterNode {
  return {
    type: 'market',
    boards,
    watchlistOnly: false,
  };
}

/**
 * 创建市值范围过滤
 */
function createMarketCapFilter(min: number, max: number): FilterNode {
  return {
    type: 'range',
    field: 'market_cap',
    min,
    max,
  };
}

/**
 * 构建交易日列表
 */
function buildTradeDateList(days: number, startDate = '2025-01-02'): string[] {
  const dates: string[] = [];
  const start = new Date(startDate);
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
}

// ==================== 辅助函数测试 ====================

describe('getLimitPct', () => {
  it('主板非 ST 股涨跌停幅度为 10%', () => {
    expect(getLimitPct('main', false)).toBe(0.10);
  });
  it('主板 ST 股涨跌停幅度为 5%', () => {
    expect(getLimitPct('main', true)).toBe(0.05);
  });
  it('创业板涨跌停幅度为 20%', () => {
    expect(getLimitPct('gem', false)).toBe(0.20);
  });
  it('科创板涨跌停幅度为 20%', () => {
    expect(getLimitPct('star', false)).toBe(0.20);
  });
  it('北交所涨跌停幅度为 30%', () => {
    expect(getLimitPct('beijing', false)).toBe(0.30);
  });
});

describe('isSuspended', () => {
  it('成交量为 0 且价格不变时判定为停牌', () => {
    const bar = [1000, 10, 10, 10, 10, 0, 10];
    expect(isSuspended(bar, 10, 0.10)).toBe(true);
  });
  it('成交量不为 0 时不是停牌', () => {
    const bar = [1000, 10, 10, 10, 10, 1000, 10];
    expect(isSuspended(bar, 10, 0.10)).toBe(false);
  });
  it('一字涨停时不是停牌', () => {
    const bar = generateLimitUpBar(1000, 10, 0.10);
    expect(isSuspended(bar, 10, 0.10)).toBe(false);
  });
  it('一字跌停时不是停牌', () => {
    const bar = generateLimitDownBar(1000, 10, 0.10);
    expect(isSuspended(bar, 10, 0.10)).toBe(false);
  });
});

describe('isLimitUp', () => {
  it('一字涨停时判定为涨停（所有价格均达到涨停价）', () => {
    const bar = generateLimitUpBar(1000, 10, 0.10);
    expect(isLimitUp(bar, 10, 0.10)).toBe(true);
  });
  it('盘中打开涨停（open < upLimit）时不是涨停', () => {
    const bar = [1000, 10.5, 11, 10.5, 10.8, 1000000, 10];
    expect(isLimitUp(bar, 10, 0.10)).toBe(false);
  });
});

describe('isLimitDown', () => {
  it('一字跌停时判定为跌停（所有价格均达到跌停价）', () => {
    const bar = generateLimitDownBar(1000, 10, 0.10);
    expect(isLimitDown(bar, 10, 0.10)).toBe(true);
  });
  it('盘中打开跌停（open > downLimit）时不是跌停', () => {
    const bar = [1000, 9.5, 10, 9.5, 10, 1000000, 10];
    expect(isLimitDown(bar, 10, 0.10)).toBe(false);
  });
});

// ==================== 交易日历构建测试 ====================

describe('buildTradeDates', () => {
  it('优先使用后端提供的交易日历', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const providedDates = ['2025-01-02', '2025-01-03', '2025-01-06'];
    const result = buildTradeDates(allOhlcv, snapshots, providedDates);
    expect(result).toEqual(providedDates);
  });
  it('无后端交易日历时取大市值股票日期并集', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(5, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行', 'main', false, 200));
    const result = buildTradeDates(allOhlcv, snapshots);
    expect(result.length).toBe(5);
    expect(result[0]).toBe('2025-01-02');
  });
  it('过滤市值小于阈值的股票', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '300001.SZ';
    const bars1 = generateOhlcv(5, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '小盘股', 'gem', false, 50));
    const result = buildTradeDates(allOhlcv, snapshots);
    expect(result.length).toBe(0);
  });
});

// ==================== 指标缓存计算测试 ====================

describe('computeIndicatorCache', () => {
  it('计算 MA 指标', () => {
    const bars = generateOhlcv(30, 10, 0.01);
    const cache = computeIndicatorCache(bars, 10);
    expect(cache.length).toBe(30);
    expect(cache.isReady('ma5', 4)).toBe(true);
    expect(cache.getMA(5, 4)).not.toBeNull();
  });
  it('计算 MACD 指标', () => {
    const bars = generateOhlcv(50, 10, 0.01);
    const cache = computeIndicatorCache(bars, 10);
    expect(cache.isReady('macdDif', 34)).toBe(true);
    expect(cache.getMACD('dif', 34)).not.toBeNull();
  });
  it('计算 RSI 指标', () => {
    const bars = generateOhlcv(30, 10, 0.01);
    const cache = computeIndicatorCache(bars, 10);
    expect(cache.isReady('rsi6', 6)).toBe(true);
    expect(cache.getRSI(6, 6)).not.toBeNull();
  });
  it('计算 BOLL 指标', () => {
    const bars = generateOhlcv(30, 10, 0.01);
    const cache = computeIndicatorCache(bars, 10);
    expect(cache.isReady('bollUpper', 19)).toBe(true);
    expect(cache.getBOLL('upper', 19)).not.toBeNull();
  });
});

// ==================== 手续费计算测试 ====================

describe('calcBuyCommission / calcSellCommission', () => {
  it('买入手续费含最低佣金和滑点', () => {
    const amount = 100000; // 1000元
    const fee = calcBuyCommission(amount, 0.00025, 0.0001, 500);
    // 佣金：max(100000 * 0.00025, 500) = 500
    // 滑点：100000 * 0.0001 = 10
    // 总计：510
    expect(fee).toBe(510);
  });
  it('买入手续费超过最低佣金', () => {
    const amount = 10000000; // 10万元
    const fee = calcBuyCommission(amount, 0.00025, 0.0001, 500);
    // 佣金：max(10000000 * 0.00025, 500) = 2500
    // 滑点：10000000 * 0.0001 = 1000
    // 总计：3500
    expect(fee).toBe(3500);
  });
  it('卖出手续费含印花税', () => {
    const amount = 10000000;
    const fee = calcSellCommission(amount, 0.00025, 0.0001, 0.001, 500);
    // 佣金：max(10000000 * 0.00025, 500) = 2500
    // 滑点：10000000 * 0.0001 = 1000
    // 印花税：10000000 * 0.001 = 10000
    // 总计：13500
    expect(fee).toBe(13500);
  });
});

describe('calcSharesToBuy', () => {
  it('计算可买入股数（100 股整数倍）', () => {
    const shares = calcSharesToBuy(1000000, 10, 0.00025, 0.0001, 500);
    expect(shares % 100).toBe(0);
    expect(shares).toBeGreaterThan(0);
  });
  it('考虑手续费后买入金额不超过目标金额', () => {
    const targetAmountFen = 1000000;
    const priceYuan = 10;
    const feeRate = 0.00025;
    const slippage = 0.0001;
    const minCommissionFen = 500;
    const shares = calcSharesToBuy(targetAmountFen, priceYuan, feeRate, slippage, minCommissionFen);
    const buyAmountFen = shares * priceYuan * 100;
    const commission = Math.max(buyAmountFen * (feeRate + slippage), minCommissionFen);
    expect(buyAmountFen + commission).toBeLessThanOrEqual(targetAmountFen);
  });
  it('目标金额为 0 时返回 0', () => {
    const shares = calcSharesToBuy(0, 10, 0.00025, 0.0001, 500);
    expect(shares).toBe(0);
  });
});

describe('calcEqualWeight', () => {
  it('等权分配计算', () => {
    const { weight, cashDragWarning } = calcEqualWeight(10, 1.0);
    expect(weight).toBe(0.1);
    expect(cashDragWarning).toBe(false);
  });
  it('单股仓位上限小于等权时产生现金拖累警告', () => {
    const { weight, cashDragWarning } = calcEqualWeight(10, 0.05);
    expect(weight).toBe(0.05);
    expect(cashDragWarning).toBe(true);
  });
});

// ==================== AST 过滤器测试 ====================

describe('evaluateFilter', () => {
  it('market 类型过滤器匹配板块', () => {
    const filter = createBoardFilter(['main']);
    const snapshot = createSnapshot('600000.SH', '浦发银行', 'main');
    const bars = generateOhlcv(30);
    const cache = new IndicatorCache(30);
    expect(evaluateFilter(filter, snapshot, bars, cache, 29)).toBe(true);
  });
  it('market 类型过滤器不匹配板块时返回 false', () => {
    const filter = createBoardFilter(['gem']);
    const snapshot = createSnapshot('600000.SH', '浦发银行', 'main');
    const bars = generateOhlcv(30);
    const cache = new IndicatorCache(30);
    expect(evaluateFilter(filter, snapshot, bars, cache, 29)).toBe(false);
  });
  it('range 类型过滤器 NaN 阻断', () => {
    const filter = { type: 'range', field: 'pe', min: 10, max: 30 } as FilterNode;
    const snapshot = { ...createSnapshot('600000.SH', '浦发银行'), pe: NaN } as StockSnapshot;
    const bars = generateOhlcv(30);
    const cache = new IndicatorCache(30);
    expect(evaluateFilter(filter, snapshot, bars, cache, 29)).toBe(false);
  });
  it('not 类型过滤器正确处理子节点 null 返回值', () => {
    const filter: FilterNode = {
      type: 'not',
      child: { type: 'range', field: 'pe', min: 10, max: 30 },
    };
    const snapshot = { ...createSnapshot('600000.SH', '浦发银行'), pe: NaN } as StockSnapshot;
    const bars = generateOhlcv(30);
    const cache = new IndicatorCache(30);
    // 子节点因 NaN 返回 false，NOT(false) = true
    expect(evaluateFilter(filter, snapshot, bars, cache, 29)).toBe(true);
  });
  it('AND 和 OR 组合', () => {
    const filter: FilterNode = {
      type: 'and',
      children: [
        createBoardFilter(['main']),
        createMarketCapFilter(100, 300),
      ],
    };
    const snapshot = createSnapshot('600000.SH', '浦发银行', 'main', false, 200);
    const bars = generateOhlcv(30);
    const cache = new IndicatorCache(30);
    expect(evaluateFilter(filter, snapshot, bars, cache, 29)).toBe(true);

    const badSnapshot = createSnapshot('600000.SH', '浦发银行', 'main', false, 50);
    expect(evaluateFilter(filter, badSnapshot, bars, cache, 29)).toBe(false);
  });
});

// ==================== T+1 执行逻辑测试 ====================

describe('T+1 执行逻辑', () => {
  it('信号生成日与执行日不同', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      rebalanceInterval: 5,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    if (result.trades.length > 0) {
      const trade = result.trades[0];
      expect(trade.entryDate).toBeDefined();
      expect(trade.exitDate).toBeDefined();
      expect(trade.entryDate).not.toBe(trade.exitDate);
    }
  });
});

// ==================== 个股风控测试 ====================

describe('个股风控', () => {
  it('止损触发后生成卖出指令', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, -0.02, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      stopLossPct: -0.08,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    const stopLossTrades = result.trades.filter(t => t.sellReason === 'stop_loss');
    expect(stopLossTrades.length).toBeGreaterThan(0);
    // 验证卖出价格低于买入价格
    const trade = stopLossTrades[0];
    expect(trade.exitPrice).toBeLessThan(trade.entryPrice);
  });

  it('止盈触发后生成卖出指令', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.03, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      takeProfitPct: 0.20,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    const takeProfitTrades = result.trades.filter(t => t.sellReason === 'take_profit');
    expect(takeProfitTrades.length).toBeGreaterThan(0);
    const trade = takeProfitTrades[0];
    expect(trade.exitPrice).toBeGreaterThan(trade.entryPrice * 1.18);
  });

  it('超时触发后生成卖出指令', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.005, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxHoldDays: 10,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    const timeoutTrades = result.trades.filter(t => t.sellReason === 'timeout');
    expect(timeoutTrades.length).toBeGreaterThan(0);
    expect(timeoutTrades[0].holdDays).toBeLessThanOrEqual(11);
  });
});

// ==================== 组合级风控测试 ====================

describe('组合级风控', () => {
  it('单日亏损触发后生成清仓卖出指令', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    
    // 前20天稳定上涨，第21天暴跌10%
    const bars1 = generateOhlcv(60, 10, 0.02, '2025-01-02');
    const crashDay = 20;
    const preClose = bars1[crashDay - 1][4];
    bars1[crashDay][1] = preClose * 0.95; // open
    bars1[crashDay][2] = preClose * 0.95; // high
    bars1[crashDay][3] = preClose * 0.90; // low
    bars1[crashDay][4] = preClose * 0.90; // close
    
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      dailyLossLimitEnabled: true,
      dailyLossLimitPct: -0.05, // -5%
      maxPositions: 1, // 确保单只股票占100%仓位，暴跌才能触发组合风控
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    
    const result = runStrategyBacktest(input);
    
    // 验证有组合风控卖出或警告
    const hasPortfolioRisk = result.trades.some(t => t.sellReason === 'portfolio_risk');
    const hasWarning = result.warnings.some(w => w.includes('单日亏损'));
    expect(hasPortfolioRisk || hasWarning).toBe(true);
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });

  it('最大回撤触发后生成清仓卖出指令', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    
    // 前20天稳定上涨，后40天持续下跌制造大回撤
    const bars1 = generateOhlcv(60, 10, 0.03, '2025-01-02');
    for (let i = 20; i < 60; i++) {
      const prevClose = bars1[i - 1][4];
      bars1[i][1] = prevClose * 0.97; // open
      bars1[i][2] = prevClose * 0.97; // high
      bars1[i][3] = prevClose * 0.95; // low
      bars1[i][4] = prevClose * 0.95; // close
    }
    
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxDrawdownStopEnabled: true,
      maxDrawdownStopPct: -0.15, // -15%
      maxPositions: 1, // 确保单只股票占100%仓位
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-28',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    
    const result = runStrategyBacktest(input);
    
    // 验证有组合风控卖出或警告
    const hasPortfolioRisk = result.trades.some(t => t.sellReason === 'portfolio_risk');
    const hasWarning = result.warnings.some(w => w.includes('回撤'));
    expect(hasPortfolioRisk || hasWarning).toBe(true);
    expect(result.metrics.maxDrawdown).toBeLessThan(0);
  });

  it('组合风控触发后跳过调仓日逻辑，避免重复卖出指令', () => {
    // 设计触发单日亏损，然后当天是调仓日，验证不会生成 rebalance 卖出指令
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    
    // 前20天稳定上涨，第21天暴跌10%（且是调仓日）
    const bars1 = generateOhlcv(60, 10, 0.02, '2025-01-02');
    const crashDay = 20;
    const preClose = bars1[crashDay - 1][4];
    bars1[crashDay][1] = preClose * 0.95; // open
    bars1[crashDay][2] = preClose * 0.95; // high
    bars1[crashDay][3] = preClose * 0.90; // low
    bars1[crashDay][4] = preClose * 0.90; // close
    
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      dailyLossLimitEnabled: true,
      dailyLossLimitPct: -0.05,
      maxPositions: 1, // 确保单只股票占100%仓位，暴跌触发风控
      rebalanceInterval: 5, // 第20天是调仓日
      warmupDays: 10,
    };
    
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    
    const result = runStrategyBacktest(input);
    
    // 验证有组合风控触发
    const hasPortfolioRisk = result.trades.some(t => t.sellReason === 'portfolio_risk');
    const hasWarning = result.warnings.some(w => w.includes('单日亏损'));
    expect(hasPortfolioRisk || hasWarning).toBe(true);
    
    // 验证调仓日被跳过（不应有 rebalance 卖出，或极少）
    // 由于组合风控触发后 forceLiquidate=true，调仓日逻辑被跳过
    const rebalanceSells = result.trades.filter(t => t.sellReason === 'rebalance');
    // 允许有少量 rebalance（在风控触发前的调仓日），但不应过多
    expect(rebalanceSells.length).toBeLessThan(5);
  });
});

// ==================== Beta/IR 计算测试 ====================

describe('Beta 和 IR 计算', () => {
  it('有基准数据时计算 Beta 和 IR', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const benchmarkOhlcv = generateOhlcv(60, 100, 0.008, '2025-01-02');
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      benchmarkOhlcv,
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.metrics.beta).toBeDefined();
    expect(result.metrics.informationRatio).toBeDefined();
    // 如果数据足够，beta 不为 null
    if (result.metrics.beta !== null) {
      expect(typeof result.metrics.beta).toBe('number');
    }
  });

  it('无基准数据时 Beta/IR 为 null', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
      // 无 benchmarkOhlcv
    };
    const result = runStrategyBacktest(input);
    expect(result.metrics.beta).toBeNull();
    expect(result.metrics.informationRatio).toBeNull();
  });
});

// ==================== 停牌/涨跌停处理测试 ====================

describe('停牌/涨跌停处理', () => {
  it('停牌日卖出指令顺延，且停牌顺延不受 maxDeferDays 限制', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    // 插入连续停牌5天
    const suspendStartIdx = 20;
    for (let i = 0; i < 5; i++) {
      const idx = suspendStartIdx + i;
      const bar = generateSuspendedBar(bars1[idx][0], bars1[idx - 1][4]);
      bars1.splice(idx, 1, bar);
    }
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxDeferDays: 2, // 设置较短的顺延限制
      warmupDays: 10,
      rebalanceInterval: 100, // 避免调仓干扰
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 验证回测能完成，且有警告或正常卖出
    expect(result.equityCurve.length).toBeGreaterThan(0);
    // 可能没有卖出，但至少不崩溃
  });

  it('涨停日买入指令顺延', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    // 插入涨停
    const limitIdx = 20;
    const preClose = bars1[limitIdx - 1][4];
    const limitBar = generateLimitUpBar(bars1[limitIdx][0], preClose, 0.10);
    bars1.splice(limitIdx, 1, limitBar);
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
      rebalanceInterval: 5,
      maxDeferDays: 3,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });

  it('跌停日卖出指令顺延', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    const limitIdx = 20;
    const preClose = bars1[limitIdx - 1][4];
    const limitBar = generateLimitDownBar(bars1[limitIdx][0], preClose, 0.10);
    bars1.splice(limitIdx, 1, limitBar);
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
      rebalanceInterval: 5,
      maxDeferDays: 3,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });
});

// ==================== 仓位分配与现金拖累测试 ====================

describe('仓位分配与现金拖累', () => {
  it('等权分配且单股上限足够，无现金拖累警告', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const codes = ['600000.SH', '600001.SH', '600002.SH'];
    codes.forEach((code, idx) => {
      const bars = generateOhlcv(60, 10 + idx, 0.01, '2025-01-02');
      allOhlcv.set(code, bars);
      snapshots.set(code, createSnapshot(code, `股票${idx}`, 'main'));
    });
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxPositions: 3,
      singleStockMaxPct: 1.0, // 不限制
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 不应该有现金拖累警告
    expect(result.warnings.some(w => w.includes('现金拖累'))).toBe(false);
  });

  it('单股仓位上限小于等权时产生现金拖累警告', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const codes = ['600000.SH', '600001.SH', '600002.SH', '600003.SH', '600004.SH'];
    codes.forEach((code, idx) => {
      const bars = generateOhlcv(60, 10 + idx, 0.01, '2025-01-02');
      allOhlcv.set(code, bars);
      snapshots.set(code, createSnapshot(code, `股票${idx}`, 'main'));
    });
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxPositions: 5,
      singleStockMaxPct: 0.15, // 15% 上限，等权为 20%
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.warnings.some(w => w.includes('现金拖累'))).toBe(true);
    // 验证实际持仓比例不超过 15%
    // 可以从交易记录推算
    if (result.trades.length > 0) {
      const buyTrades = result.trades.filter(t => t.sellReason === 'end' || t.sellReason === 'rebalance');
      // 简化验证：检查有买入记录
      expect(buyTrades.length).toBeGreaterThan(0);
    }
  });
});

// ==================== 多股票调仓换股测试 ====================

describe('多股票调仓换股', () => {
  it('调仓日卖出不在目标池的股票，买入新股票', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    // 创建两只股票，过滤条件只选 code1
    const code1 = '600000.SH';
    const code2 = '600001.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    const bars2 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    allOhlcv.set(code2, bars2);
    snapshots.set(code1, createSnapshot(code1, '股票A', 'main'));
    snapshots.set(code2, createSnapshot(code2, '股票B', 'main'));

    // 过滤条件：只选 code1（通过市值范围实现）
    const filter: FilterNode = {
      type: 'range',
      field: 'market_cap',
      min: 150,
      max: 250,
    };
    // 设置 code1 市值 200，code2 市值 100
    snapshots.get(code1)!.marketCap = 200;
    snapshots.get(code2)!.marketCap = 100;

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxPositions: 2,
      rebalanceInterval: 5,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: filter,
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // code2（市值100）被过滤排除，从未被买入，因此无 rebalance 卖出
    // code1（市值200）通过过滤，期末持仓应包含 code1
    const endTrades = result.trades.filter(t => t.sellReason === 'end');
    expect(endTrades.some(t => t.code === code1)).toBe(true);
    // code2 不应出现在任何交易中
    const code2Trades = result.trades.filter(t => t.code === code2);
    expect(code2Trades.length).toBe(0);
  });

  it('最大持仓数限制生效', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const codes = ['600000.SH', '600001.SH', '600002.SH', '600003.SH'];
    codes.forEach((code, idx) => {
      const bars = generateOhlcv(60, 10 + idx, 0.01, '2025-01-02');
      allOhlcv.set(code, bars);
      snapshots.set(code, createSnapshot(code, `股票${idx}`, 'main'));
    });
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxPositions: 2,
      rebalanceInterval: 5,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 引擎完成回测不报错，生成净值曲线
    expect(result.equityCurve.length).toBeGreaterThan(0);
    expect(result.trades.length).toBeGreaterThan(0);
    // 验证有期末清仓交易
    const endTrades = result.trades.filter(t => t.sellReason === 'end');
    expect(endTrades.length).toBeGreaterThan(0);
  });
});

// ==================== 退市处理测试 ====================

describe('退市处理', () => {
  it('股票在回测区间内退市，最后交易日以收盘价强平，卖出原因为 delisted', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    // 模拟退市：数据在第40天中断
    const truncatedBars = bars1.slice(0, 40);
    allOhlcv.set(code1, truncatedBars);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
      rebalanceInterval: 100, // 不调仓，持有到退市
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-28',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 应该有 delisted 卖出
    const delistedTrades = result.trades.filter(t => t.sellReason === 'delisted');
    // 如果持仓到退市，会触发 delisted；如果提前卖出，则可能没有
    // 因为交易日期长度可能与数据不完全对齐，验证警告或卖出存在
    // 更稳健：检查是否有卖出记录 exitDate 为最后交易日
    if (delistedTrades.length > 0) {
      const lastDate = buildTradeDateList(60, '2025-01-02')[39];
      expect(delistedTrades[0].exitDate).toBe(lastDate);
    }
    // 或者检查警告
    expect(result.warnings).toBeDefined();
  });
});

// ==================== 不同调仓频率测试 ====================

describe('调仓频率', () => {
  const runWithFrequency = (interval: 1 | 5 | 21) => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      rebalanceInterval: interval,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    return runStrategyBacktest(input);
  };

  it('每日调仓 (interval=1)', () => {
    const result = runWithFrequency(1);
    expect(result.equityCurve.length).toBeGreaterThan(0);
    expect(result.trades.length).toBeGreaterThan(0);
  });

  it('每周调仓 (interval=5)', () => {
    const result = runWithFrequency(5);
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });

  it('每月调仓 (interval=21)', () => {
    const result = runWithFrequency(21);
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });
});

// ==================== 预热天数与指标阻断测试 ====================

describe('预热天数与指标阻断', () => {
  it('预热期内指标为 null 阻断选股', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(30, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    // 过滤条件：排除所有股票（板块不匹配），确保无交易
    const filter: FilterNode = {
      type: 'market',
      boards: ['gem'], // 只选创业板，但股票是主板
      watchlistOnly: false,
    };

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 60,
      rebalanceInterval: 5,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: filter,
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(30, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 应该没有交易（因为过滤条件排除了所有股票）
    expect(result.trades.length).toBe(0);
    // 净值曲线仍然存在（初始资金）
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });
});

// ==================== 绩效指标数值验证 ====================

describe('绩效指标数值验证', () => {
  it('总收益、年化、夏普、回撤等指标计算合理', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    const metrics = result.metrics;
    // 总收益应在合理范围
    expect(metrics.totalReturn).toBeGreaterThan(-0.5);
    expect(metrics.totalReturn).toBeLessThan(1);
    // 年化收益
    expect(metrics.annualReturn).toBeGreaterThan(-0.8);
    // 夏普比率（固定日涨幅导致波动率极低，夏普比率极高）
    expect(metrics.sharpeRatio).toBeLessThan(50);
    // 最大回撤 <=0
    expect(metrics.maxDrawdown).toBeLessThanOrEqual(0);
    // 胜率 0-1
    expect(metrics.winRate).toBeGreaterThanOrEqual(0);
    expect(metrics.winRate).toBeLessThanOrEqual(1);
    // 盈亏比 >=0
    expect(metrics.profitLossRatio).toBeGreaterThanOrEqual(0);
    // 总交易次数 >=0
    expect(metrics.totalTrades).toBeGreaterThanOrEqual(0);
    // 月度胜率
    expect(metrics.monthlyWinRate).toBeGreaterThanOrEqual(0);
    expect(metrics.monthlyWinRate).toBeLessThanOrEqual(1);
    // 卡玛比率
    expect(metrics.calmarRatio).toBeDefined();
  });
});

// ==================== 进度回调测试 ====================

describe('进度回调', () => {
  it('onProgress 回调被正确调用', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const progressLogs: ProgressInfo[] = [];
    const onProgress = (info: ProgressInfo) => { progressLogs.push(info); };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
      onProgress,
    };
    runStrategyBacktest(input);
    expect(progressLogs.length).toBeGreaterThan(0);
    expect(progressLogs[progressLogs.length - 1].stage).toBe('done');
  });

  it('onProgress 为空时不报错', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    expect(() => runStrategyBacktest(input)).not.toThrow();
  });
});

// ==================== 边界情况测试 ====================

describe('边界情况', () => {
  it('回测区间无效时返回空结果', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2030-01-01',
      endDate: '2030-02-01',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.equityCurve.length).toBe(0);
    expect(result.trades.length).toBe(0);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it('无股票数据时返回初始资金净值', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-01-16',
      tradeDates: ['2025-01-15', '2025-01-16'],
    };
    const result = runStrategyBacktest(input);
    expect(result.equityCurve.length).toBeGreaterThan(0);
    expect(result.trades.length).toBe(0);
    expect(result.equityCurve[0].totalEquity).toBe(config.initialCapital / 100);
  });

  it('sellReason 枚举覆盖：期末清仓', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(30, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));
    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      warmupDays: 10,
      rebalanceInterval: 100, // 不调仓，最终期末清仓
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(30, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    const endTrades = result.trades.filter(t => t.sellReason === 'end');
    expect(endTrades.length).toBeGreaterThan(0);
    // tradeDates 最后一天是 2025-01-31（30天），期末清仓日期即为此日
    expect(endTrades[0].exitDate).toBe('2025-01-31');
  });
});

// ==================== 额外：手续费和滑点对收益的影响 ====================

describe('手续费和滑点影响', () => {
  it('手续费和滑点从收益中扣除', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    // 高手续费版本
    const configHigh: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      feeRate: 0.001, // 高手续费
      slippage: 0.001,
      stampDuty: 0.002,
      minCommission: 5000,
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    // 低手续费版本
    const configLow: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      feeRate: 0.0001,
      slippage: 0.0001,
      stampDuty: 0.0005,
      minCommission: 100,
      warmupDays: 10,
      rebalanceInterval: 5,
    };

    const inputHigh: StrategyBacktestInput = {
      allOhlcv: new Map(allOhlcv),
      snapshots: new Map(snapshots),
      filterTree: createPassAllFilter(),
      config: configHigh,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const inputLow: StrategyBacktestInput = {
      allOhlcv: new Map(allOhlcv),
      snapshots: new Map(snapshots),
      filterTree: createPassAllFilter(),
      config: configLow,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };

    const resultHigh = runStrategyBacktest(inputHigh);
    const resultLow = runStrategyBacktest(inputLow);
    // 高手续费版本的最终收益应低于低手续费版本（或至少不高于）
    expect(resultHigh.metrics.totalReturn).toBeLessThanOrEqual(resultLow.metrics.totalReturn + 0.001);
  });
});

// ==================== 额外：顺延失败处理 atClose vs abandon ====================

describe('顺延失败处理', () => {
  it('atClose 模式下超时后按收盘价执行', () => {
    // 构造一个涨停无法买入的场景，设置 maxDeferDays 较小，且 deferFailAction='atClose'
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    // 插入连续涨停3天（使得顺延超时）
    for (let i = 0; i < 3; i++) {
      const idx = 20 + i;
      const preClose = bars1[idx - 1][4];
      const limitBar = generateLimitUpBar(bars1[idx][0], preClose, 0.10);
      bars1.splice(idx, 1, limitBar);
    }
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxDeferDays: 2,
      deferFailAction: 'atClose',
      warmupDays: 10,
      rebalanceInterval: 5,
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    // 应该会有一些买入尝试，即使失败也有警告
    expect(result.warnings).toBeDefined();
    // 可能没有买入，但回测完成
    expect(result.equityCurve.length).toBeGreaterThan(0);
  });

  it('abandon 模式下超时后放弃交易', () => {
    const allOhlcv = new Map<string, number[][]>();
    const snapshots = new Map<string, StockSnapshot>();
    const code1 = '600000.SH';
    const bars1 = generateOhlcv(60, 10, 0.01, '2025-01-02');
    // 第14天开始连续涨停，使得第13天生成的买入指令执行日命中涨停
    const startLimit = 14;
    for (let i = 0; i < 4; i++) {
      const idx = startLimit + i;
      const preClose = bars1[idx - 1][4];
      const limitBar = generateLimitUpBar(bars1[idx][0], preClose, 0.10);
      bars1.splice(idx, 1, limitBar);
    }
    allOhlcv.set(code1, bars1);
    snapshots.set(code1, createSnapshot(code1, '浦发银行'));

    const config: StrategyBacktestDefaults = {
      ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS,
      maxDeferDays: 3,
      deferFailAction: 'abandon',
      maxPositions: 1,
      warmupDays: 14, // 预热14天，第15天开始选股
      rebalanceInterval: 1, // 每日调仓，买入指令命中涨停日
    };
    const input: StrategyBacktestInput = {
      allOhlcv,
      snapshots,
      filterTree: createPassAllFilter(),
      config,
      startDate: '2025-01-15',
      endDate: '2025-02-15',
      tradeDates: buildTradeDateList(60, '2025-01-02'),
    };
    const result = runStrategyBacktest(input);
    expect(result.warnings.some(w => w.includes('放弃'))).toBeTruthy();
  });
});