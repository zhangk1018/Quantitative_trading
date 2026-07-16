// src/features/backtest/strategies/tonghuashun6Strategy.ts
// 同花顺 6 重买入 + 分层止盈 + 单次止损策略
// 对应同花顺公式：6重买入条件 + 4%→8%→10% 分层止盈 + 强制止损/常规止损

import { ema, sma, calcRSI } from '../../../lib/indicators/indicators';
import {
  type StrategyBacktestDefaults,
  type StockSnapshot,
  type Position,
  type Trade,
  type EquityPoint,
  type StrategyBacktestResult,
  type SellReason,
} from '../strategyBacktestTypes';
import {
  parseTimestamp,
  buildTradeDates,
  isSuspended,
  isLimitUp,
  isLimitDown,
  getLimitPct,
  calcSharesToBuy,
  calcBuyCommission,
  calcSellCommission,
  calcMetrics,
  buildEmptyResult,
  OHLCV_TS,
  OHLCV_OPEN,
  OHLCV_HIGH,
  OHLCV_LOW,
  OHLCV_CLOSE,
  OHLCV_VOLUME,
  LOT_SIZE,
  type ProgressInfo,
} from '../strategyBacktestEngine';

// ==================== 参数常量（与同花顺公式对齐） ====================

const SD = 20;
const WIDTH = 2;
const SHORT = 12;
const LONG = 26;
const M = 9;
const RSI_PERIOD = 14;
const VOL_THRESHOLD = 1.05;
const RSI_LOW = 25;
const RSI_UPPER = 70;
const MIN_HOLD_DAYS = 3;
const DYNAMIC_MAX_DRAWDOWN = 0.05;
const FIRST_PROFIT_TARGET = 0.04;
const SECOND_PROFIT_TARGET = 0.08;
const FULL_PROFIT_TARGET = 0.10;
const RSI_HIGH = 80;
const MAX_CONSECUTIVE_BUYS = 3;

// ==================== 状态类型 ====================

/** 同花顺策略独有的持仓状态 */
interface ThsPositionState {
  code: string;
  buyDate: string;
  buyPrice: number;
  shares: number;
  entryDateIdx: number;
  holdDays: number;

  // 卖出标记（单次触发）
  hasForceStopped: boolean;
  hasFirstProfit: boolean;
  hasSecondProfit: boolean;
  hasFullProfit: boolean;
  hasStopLoss: boolean;

  // 连续买入计数
  entryCount: number;

  // 持仓峰值（用于计算回撤）
  peakPrice: number;
}

/** 待执行指令（T+1） */
interface PendingOrder {
  code: string;
  action: 'buy' | 'sell';
  signalDate: string;
  executionDate: string;
  /** 买入时分配的目标金额（分） */
  targetFen?: number;
  shares?: number;
  sellReason?: SellReason;
  deferCount: number;
}

/** 策略输入参数（与同花顺公式对齐，可覆盖默认值） */
export interface Tonghuashun6Params {
  rsiLow?: number;
  rsiUpper?: number;
  rsiHigh?: number;
  minHoldDays?: number;
  maxDrawdown?: number;
  firstProfitTarget?: number;
  secondProfitTarget?: number;
  fullProfitTarget?: number;
  maxConsecutiveBuys?: number;
  volThreshold?: number;
}

/** 策略输入 */
export interface Tonghuashun6Input {
  allOhlcv: Map<string, number[][]>;
  snapshots: Map<string, StockSnapshot>;
  config: StrategyBacktestDefaults;
  startDate: string;
  endDate: string;
  benchmarkOhlcv?: number[][];
  tradeDates?: string[];
  onProgress?: (info: ProgressInfo) => void;
  params?: Tonghuashun6Params;
}

// ==================== 策略计算缓存 ====================

interface ThsIndicatorCache {
  ema5: (number | null)[];
  ema20: (number | null)[];
  ema48: (number | null)[];
  macdDif: (number | null)[];
  macdDea: (number | null)[];
  macd: (number | null)[];
  rsi: (number | null)[];
  volAvg15: (number | null)[];
  hhv20: (number | null)[];
}

function computeThsCache(bars: number[][], warmupDays: number): ThsIndicatorCache {
  const n = bars.length;
  const closes = bars.map(b => b[OHLCV_CLOSE]);
  const highs = bars.map(b => b[OHLCV_HIGH]);
  const volumes = bars.map(b => b[OHLCV_VOLUME]);

  // EMA 系列
  const ema5 = ema(closes as (number | null)[], 5);
  const ema20 = ema(closes as (number | null)[], 20);
  const ema48 = ema(closes as (number | null)[], 48);

  // MACD (12, 26, 9)
  const ema12 = ema(closes as (number | null)[], SHORT);
  const ema26 = ema(closes as (number | null)[], LONG);
  const macdDif: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (ema12[i] !== null && ema26[i] !== null) {
      macdDif[i] = ema12[i]! - ema26[i]!;
    }
  }
  const macdDea = ema(macdDif, M);
  const macd: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (macdDif[i] !== null && macdDea[i] !== null) {
      macd[i] = (macdDif[i]! - macdDea[i]!) * 2;
    }
  }

  // RSI (14)
  const rsi = calcRSI(closes, RSI_PERIOD);

  // 均量 (15日)
  const volAvg15 = sma(volumes, 15);

  // 20日最高价
  const hhv20: (number | null)[] = new Array(n).fill(null);
  for (let i = SD - 1; i < n; i++) {
    let maxH = highs[i - SD + 1];
    for (let j = i - SD + 2; j <= i; j++) {
      if (highs[j] > maxH) maxH = highs[j];
    }
    hhv20[i] = maxH;
  }

  return { ema5, ema20, ema48, macdDif, macdDea, macd, rsi, volAvg15, hhv20 };
}

// ==================== 信号判断 ====================

function checkBuySignal(
  cache: ThsIndicatorCache,
  bars: number[][],
  idx: number,
  prevIdx: number, // 前一个有效索引（用于 CROSS 判断）
  params: Required<Tonghuashun6Params>,
): boolean {
  if (idx < 1 || idx >= bars.length) return false;

  const c = cache;
  const close = bars[idx][OHLCV_CLOSE];
  const volume = bars[idx][OHLCV_VOLUME];
  const prevClose = prevIdx >= 0 ? bars[prevIdx][OHLCV_CLOSE] : null;

  // TREND_UP = EMA5 > EMA48
  if (c.ema5[idx] === null || c.ema48[idx] === null) return false;
  const trendUp = c.ema5[idx]! > c.ema48[idx]!;

  // MACD_GOLD = DIF > DEA AND MACD > 0
  if (c.macdDif[idx] === null || c.macdDea[idx] === null || c.macd[idx] === null) return false;
  const macdGold = c.macdDif[idx]! > c.macdDea[idx]! && c.macd[idx]! > 0;

  // RSI_VALID = RSI > RSI_LOW AND RSI < RSI_UPPER
  if (c.rsi[idx] === null) return false;
  const rsiValid = c.rsi[idx]! > params.rsiLow && c.rsi[idx]! < params.rsiUpper;

  // VOL_UP = VOL > VOL_THRESHOLD * VOL_AVG15
  if (c.volAvg15[idx] === null || c.volAvg15[idx]! <= 0) return false;
  const volUp = volume > params.volThreshold * c.volAvg15[idx]!;

  // PRICE_BREAK = CLOSE >= HHV20 * 0.98
  if (c.hhv20[idx] === null) return false;
  const priceBreak = close >= c.hhv20[idx]! * 0.98;

  const buyCond = trendUp && macdGold && rsiValid && volUp && priceBreak;

  // CROSS: 当前为 true 且前一日为 false
  if (!buyCond) return false;
  if (prevClose === null) return true; // 无前一日数据，首次触发视为信号

  // 检查前一日是否也满足条件
  const prevClosePrice = bars[prevIdx][OHLCV_CLOSE];
  const prevVol = bars[prevIdx][OHLCV_VOLUME];
  const prevTrendUp = c.ema5[prevIdx] !== null && c.ema48[prevIdx] !== null && c.ema5[prevIdx]! > c.ema48[prevIdx]!;
  const prevMacdGold = c.macdDif[prevIdx] !== null && c.macdDea[prevIdx] !== null && c.macd[prevIdx] !== null
    && c.macdDif[prevIdx]! > c.macdDea[prevIdx]! && c.macd[prevIdx]! > 0;
  const prevRsiValid = c.rsi[prevIdx] !== null && c.rsi[prevIdx]! > params.rsiLow && c.rsi[prevIdx]! < params.rsiUpper;
  const prevVolUp = c.volAvg15[prevIdx] !== null && c.volAvg15[prevIdx]! > 0
    && prevVol > params.volThreshold * c.volAvg15[prevIdx]!;
  const prevPriceBreak = c.hhv20[prevIdx] !== null && prevClosePrice >= c.hhv20[prevIdx]! * 0.98;
  const prevBuyCond = prevTrendUp && prevMacdGold && prevRsiValid && prevVolUp && prevPriceBreak;

  return !prevBuyCond; // CROSS: 从 false 到 true
}

// ==================== 卖出信号判断 ====================

function checkExitSignals(
  state: ThsPositionState,
  currentPrice: number,
  currentRsi: number | null,
  currentBar: number[],
  preClose: number,
  limitPct: number,
  params: Required<Tonghuashun6Params>,
): { shouldSell: boolean; reason: SellReason } {
  // 更新持仓峰值
  if (currentPrice > state.peakPrice) {
    state.peakPrice = currentPrice;
  }

  const profitPct = (currentPrice - state.buyPrice) / state.buyPrice;
  const drawdown = (currentPrice - state.peakPrice) / state.peakPrice;

  // 排序优先级：强制止损 > 全止盈 > 第二止盈 > 第一止盈 > 常规止损

  // 1. 强制止损（持仓 < MIN_HOLD_DAYS 且回撤超过阈值）
  if (!state.hasForceStopped && state.holdDays < params.minHoldDays && drawdown < -params.maxDrawdown) {
    return { shouldSell: true, reason: 'stop_loss' };
  }

  // 2. 全止盈（profit >= FULL_PROFIT_TARGET）
  if (!state.hasFullProfit && state.holdDays >= params.minHoldDays && profitPct >= params.fullProfitTarget) {
    return { shouldSell: true, reason: 'take_profit' };
  }

  // 3. 第二止盈（需第一止盈已触发）
  if (!state.hasSecondProfit && state.hasFirstProfit
    && state.holdDays >= params.minHoldDays && profitPct >= params.secondProfitTarget) {
    return { shouldSell: true, reason: 'take_profit' };
  }

  // 4. 第一止盈
  if (!state.hasFirstProfit && state.holdDays >= params.minHoldDays && profitPct >= params.firstProfitTarget) {
    return { shouldSell: true, reason: 'take_profit' };
  }

  // 5. 常规止损（持仓 >= MIN_HOLD_DAYS 且回撤超阈值 或 RSI > RSI_HIGH）
  if (!state.hasStopLoss && state.holdDays >= params.minHoldDays) {
    const rsiTrigger = currentRsi !== null && currentRsi > params.rsiHigh;
    if (drawdown < -params.maxDrawdown || rsiTrigger) {
      return { shouldSell: true, reason: 'stop_loss' };
    }
  }

  return { shouldSell: false, reason: 'stop_loss' };
}

// ==================== 主策略函数 ====================

export function runTonghuashun6Strategy(input: Tonghuashun6Input): StrategyBacktestResult {
  const startTime = performance.now();
  const { allOhlcv, snapshots, config, startDate, endDate, benchmarkOhlcv, tradeDates } = input;
  const warnings: string[] = [];

  const params: Required<Tonghuashun6Params> = {
    rsiLow: input.params?.rsiLow ?? RSI_LOW,
    rsiUpper: input.params?.rsiUpper ?? RSI_UPPER,
    rsiHigh: input.params?.rsiHigh ?? RSI_HIGH,
    minHoldDays: input.params?.minHoldDays ?? MIN_HOLD_DAYS,
    maxDrawdown: input.params?.maxDrawdown ?? DYNAMIC_MAX_DRAWDOWN,
    firstProfitTarget: input.params?.firstProfitTarget ?? FIRST_PROFIT_TARGET,
    secondProfitTarget: input.params?.secondProfitTarget ?? SECOND_PROFIT_TARGET,
    fullProfitTarget: input.params?.fullProfitTarget ?? FULL_PROFIT_TARGET,
    maxConsecutiveBuys: input.params?.maxConsecutiveBuys ?? MAX_CONSECUTIVE_BUYS,
    volThreshold: input.params?.volThreshold ?? VOL_THRESHOLD,
  };

  const safeOnProgress = input.onProgress ?? (() => {});

  // 1. 构建交易日历
  safeOnProgress({ stage: 'data', percent: 5, message: '构建交易日历...' });
  const dataLoadStart = performance.now();
  const allTradeDates = buildTradeDates(allOhlcv, snapshots, tradeDates);
  const dataLoadTime = performance.now() - dataLoadStart;

  // 确定回测区间索引
  const startIdx = allTradeDates.findIndex(d => d >= startDate);
  const endIdx = allTradeDates.findIndex(d => d > endDate);
  const actualEndIdx = endIdx === -1 ? allTradeDates.length - 1 : endIdx - 1;

  if (startIdx === -1 || startIdx > actualEndIdx) {
    return buildEmptyResult(config, '回测区间无效');
  }

  // 2. 预计算所有股票的技术指标（阶段1：0-70%）
  safeOnProgress({ stage: 'indicators', percent: 10, message: '预计算技术指标...' });
  const indicatorCalcStart = performance.now();
  const thsCaches = new Map<string, ThsIndicatorCache>();
  const stockBars = new Map<string, number[][]>();
  const stockDateIndexMap = new Map<string, Map<string, number>>();

  let processed = 0;
  const totalStocks = allOhlcv.size;
  for (const [code, bars] of allOhlcv) {
    const warmupStart = Math.max(0, startIdx - config.warmupDays);
    const filteredBars = bars.filter(bar => {
      const ts = bar[OHLCV_TS];
      const dateStr = parseTimestamp(ts);
      const idx = allTradeDates.indexOf(dateStr);
      return idx >= warmupStart && idx <= actualEndIdx;
    });

    if (filteredBars.length > 0) {
      stockBars.set(code, filteredBars);
      const cache = computeThsCache(filteredBars, config.warmupDays);
      thsCaches.set(code, cache);

      const dateIndexMap = new Map<string, number>();
      for (let i = 0; i < filteredBars.length; i++) {
        const dateStr = parseTimestamp(filteredBars[i][OHLCV_TS]);
        dateIndexMap.set(dateStr, i);
      }
      stockDateIndexMap.set(code, dateIndexMap);
    }

    processed++;
    if (processed % 100 === 0) {
      const pct = 10 + (processed / totalStocks) * 60;
      safeOnProgress({ stage: 'indicators', percent: pct, message: `预计算指标 ${processed}/${totalStocks}` });
    }
  }

  const indicatorCalcTime = performance.now() - indicatorCalcStart;
  safeOnProgress({ stage: 'indicators', percent: 70, message: '指标预计算完成' });

  // 3. 模拟交易主循环（阶段2：70-100%）
  safeOnProgress({ stage: 'simulation', percent: 75, message: '开始模拟交易...' });
  const simulationStart = performance.now();

  let cashFen = config.initialCapital;
  const positions = new Map<string, ThsPositionState>();
  const trades: Trade[] = [];
  const equityCurve: EquityPoint[] = [];
  const holdings: Array<{ date: string; positions: Position[] }> = [];
  let pendingOrders: PendingOrder[] = [];

  let peakEquityFen = config.initialCapital;

  // 记录每个股票的买入次数（用于限制连续买入）
  const stockEntryCounts = new Map<string, number>();

  // 逐日模拟
  for (let i = startIdx; i <= actualEndIdx; i++) {
    const currentDate = allTradeDates[i];

    // 执行 T+1 指令
    const ordersToKeep: PendingOrder[] = [];

    for (const order of pendingOrders) {
      if (order.executionDate !== currentDate) {
        ordersToKeep.push(order);
        continue;
      }

      const bars = stockBars.get(order.code);
      const dateIndexMap = stockDateIndexMap.get(order.code);
      if (!bars || !dateIndexMap) continue;

      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined) {
        order.deferCount++;
        if (order.deferCount > config.maxDeferDays) {
          if (config.deferFailAction === 'abandon') {
            warnings.push(`${currentDate}: ${order.code} 顺延超时，放弃执行`);
            continue;
          } else {
            order.executionDate = currentDate;
          }
        } else {
          const nextDateIdx = allTradeDates.findIndex((d, idx) => idx > i && d > currentDate);
          if (nextDateIdx >= 0) {
            order.executionDate = allTradeDates[nextDateIdx];
            ordersToKeep.push(order);
          }
          continue;
        }
      }

      const bar = bars[barIdx!];
      const preClose = barIdx! > 0 ? bars[barIdx! - 1][OHLCV_CLOSE] : bar[OHLCV_CLOSE];
      const snapshot = snapshots.get(order.code);
      if (!snapshot) continue;

      const limitPct = getLimitPct(snapshot.listedBoard, snapshot.isSt);

      if (order.action === 'sell') {
        if (isSuspended(bar, preClose, limitPct) || isLimitDown(bar, preClose, limitPct)) {
          order.deferCount++;
          if (order.deferCount > config.maxDeferDays) {
            if (config.deferFailAction === 'abandon') {
              warnings.push(`${currentDate}: ${order.code} 卖出顺延超时，放弃`);
              continue;
            }
          } else {
            const nextDateIdx = allTradeDates.findIndex((d, idx) => idx > i && d > currentDate);
            if (nextDateIdx >= 0) {
              order.executionDate = allTradeDates[nextDateIdx];
              ordersToKeep.push(order);
            }
            continue;
          }
        }

        const pos = positions.get(order.code);
        if (!pos) continue;

        const sellPrice = bar[OHLCV_OPEN];
        const sellAmountFen = pos.shares * sellPrice * 100;
        const commission = calcSellCommission(
          sellAmountFen, config.feeRate, config.slippage, config.stampDuty, config.minCommission,
        );
        const pnlFen = sellAmountFen - pos.shares * pos.buyPrice * 100 - commission;
        cashFen += sellAmountFen - commission;

        trades.push({
          code: order.code,
          name: snapshot.name,
          entryDate: pos.buyDate,
          exitDate: currentDate,
          entryPrice: pos.buyPrice,
          exitPrice: sellPrice,
          shares: pos.shares,
          pnl: pnlFen / 100,
          pnlPct: pnlFen / (pos.shares * pos.buyPrice * 100),
          holdDays: pos.holdDays,
          sellReason: order.sellReason ?? 'stop_loss',
        });
        positions.delete(order.code);
        // 卖出后重置买入次数
        stockEntryCounts.set(order.code, 0);
      } else if (order.action === 'buy') {
        if (isLimitUp(bar, preClose, limitPct)) {
          order.deferCount++;
          if (order.deferCount > config.maxDeferDays) {
            if (config.deferFailAction === 'abandon') {
              warnings.push(`${currentDate}: ${order.code} 涨停顺延超时，放弃买入`);
              continue;
            }
          } else {
            const nextDateIdx = allTradeDates.findIndex((d, idx) => idx > i && d > currentDate);
            if (nextDateIdx >= 0) {
              order.executionDate = allTradeDates[nextDateIdx];
              ordersToKeep.push(order);
            }
            continue;
          }
        }

        const buyPrice = bar[OHLCV_OPEN];
        const targetAmountFen = order.targetFen ?? cashFen;
        const shares = calcSharesToBuy(
          Math.min(targetAmountFen, cashFen), buyPrice,
          config.feeRate, config.slippage, config.minCommission,
        );
        if (shares <= 0) {
          warnings.push(`${currentDate}: ${order.code} 买入失败，计算股数为0`);
          continue;
        }

        const buyAmountFen = shares * buyPrice * 100;
        const commission = calcBuyCommission(buyAmountFen, config.feeRate, config.slippage, config.minCommission);
        if (buyAmountFen + commission > cashFen) continue;

        cashFen -= (buyAmountFen + commission);

        // 如果已有持仓，合并（同花顺策略支持连续买入）
        const existing = positions.get(order.code);
        if (existing) {
          const totalShares = existing.shares + shares;
          const totalCost = existing.shares * existing.buyPrice + shares * buyPrice;
          existing.shares = totalShares;
          existing.buyPrice = totalCost / totalShares;
          existing.entryCount++;
          // 不重置 buyDate/entryDateIdx，保持首次建仓日期
        } else {
          const entryCount = (stockEntryCounts.get(order.code) ?? 0) + 1;
          stockEntryCounts.set(order.code, entryCount);
          positions.set(order.code, {
            code: order.code,
            buyDate: currentDate,
            buyPrice,
            shares,
            entryDateIdx: i,
            holdDays: 0,
            hasForceStopped: false,
            hasFirstProfit: false,
            hasSecondProfit: false,
            hasFullProfit: false,
            hasStopLoss: false,
            entryCount,
            peakPrice: buyPrice,
          });
        }
      }
    }

    pendingOrders = ordersToKeep;

    // a) 更新持仓市值 + 执行同花顺策略的卖出信号检查
    let marketValueFen = 0;
    const exitSignals: Array<{ code: string; reason: SellReason }> = [];

    for (const [code, state] of positions) {
      const dateIndexMap = stockDateIndexMap.get(code);
      if (!dateIndexMap) continue;
      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined) continue;

      const bars = stockBars.get(code);
      if (!bars) continue;

      const bar = bars[barIdx];
      const closePrice = bar[OHLCV_CLOSE];
      marketValueFen += state.shares * closePrice * 100;

      // 更新持仓天数
      state.holdDays++;

      // 检查卖出信号
      const preClose = barIdx > 0 ? bars[barIdx - 1][OHLCV_CLOSE] : bar[OHLCV_CLOSE];
      const snapshot = snapshots.get(code);
      if (!snapshot) continue;
      const limitPct = getLimitPct(snapshot.listedBoard, snapshot.isSt);

      if (isSuspended(bar, preClose, limitPct)) continue;

      const cache = thsCaches.get(code);
      const currentRsi = cache ? cache.rsi[barIdx] ?? null : null;

      const { shouldSell, reason } = checkExitSignals(
        state, closePrice, currentRsi, bar, preClose, limitPct, params,
      );

      if (shouldSell) {
        // 更新触发标记（防止重复触发同类型）
        if (reason === 'stop_loss') {
          if (state.holdDays < params.minHoldDays) {
            state.hasForceStopped = true;
          } else {
            state.hasStopLoss = true;
          }
        } else {
          // take_profit: 根据盈利比例区分层级
          const profitPct = (closePrice - state.buyPrice) / state.buyPrice;
          if (profitPct >= params.fullProfitTarget) state.hasFullProfit = true;
          else if (profitPct >= params.secondProfitTarget) state.hasSecondProfit = true;
          else if (profitPct >= params.firstProfitTarget) state.hasFirstProfit = true;
        }
        exitSignals.push({ code, reason });
      }
    }

    // 生成卖出指令（T+1 执行）
    for (const { code, reason } of exitSignals) {
      const state = positions.get(code);
      if (!state) continue;
      pendingOrders.push({
        code,
        action: 'sell',
        signalDate: currentDate,
        executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
        shares: state.shares,
        sellReason: reason,
        deferCount: 0,
      });
    }

    // b) 买入信号检查（同花顺策略核心）
    // 每个交易日都检查买入信号，而不是仅在调仓日
    const buySignals: Array<{ code: string }> = [];

    for (const [code, bars] of stockBars) {
      const snapshot = snapshots.get(code);
      const cache = thsCaches.get(code);
      const dateIndexMap = stockDateIndexMap.get(code);
      if (!snapshot || !cache || !dateIndexMap) continue;

      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined || barIdx < 1) continue;

      // 检查连续买入次数限制
      const entryCount = stockEntryCounts.get(code) ?? 0;
      if (entryCount >= params.maxConsecutiveBuys) continue;

      // 排除停牌、涨停（无法买入）
      const bar = bars[barIdx];
      const preClose = barIdx > 0 ? bars[barIdx - 1][OHLCV_CLOSE] : bar[OHLCV_CLOSE];
      const limitPct = getLimitPct(snapshot.listedBoard, snapshot.isSt);
      if (isSuspended(bar, preClose, limitPct)) continue;
      if (isLimitUp(bar, preClose, limitPct)) continue;

      // 前一个有效交易日索引
      let prevIdx = barIdx - 1;
      while (prevIdx >= 0) {
        const prevDateStr = parseTimestamp(bars[prevIdx][OHLCV_TS]);
        const prevGlobalIdx = allTradeDates.indexOf(prevDateStr);
        if (prevGlobalIdx >= startIdx && prevGlobalIdx <= actualEndIdx) break;
        prevIdx--;
      }

      if (checkBuySignal(cache, bars, barIdx, prevIdx, params)) {
        buySignals.push({ code });
      }
    }

    // 生成买入指令（T+1 执行）
    // 按买入信号出现顺序，等权分配现金
    if (buySignals.length > 0) {
      const cashPerStock = cashFen / Math.min(buySignals.length, config.maxPositions);
      const maxNewPositions = Math.min(buySignals.length, config.maxPositions - positions.size);

      for (let bi = 0; bi < maxNewPositions; bi++) {
        const { code } = buySignals[bi];
        // 如果已有持仓，等权分配现金给新的买入
        const targetFen = positions.has(code) ? cashPerStock * 0.5 : cashPerStock;
        pendingOrders.push({
          code,
          action: 'buy',
          signalDate: currentDate,
          executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
          targetFen: targetFen,
          deferCount: 0,
        });
      }
    }

    // c) 计算权益曲线
    let totalMarketValueFen = 0;
    for (const [code, state] of positions) {
      const dateIndexMap = stockDateIndexMap.get(code);
      if (!dateIndexMap) continue;
      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined) continue;
      const bars = stockBars.get(code);
      if (!bars) continue;
      totalMarketValueFen += state.shares * bars[barIdx][OHLCV_CLOSE] * 100;
    }

    const totalEquityFen = cashFen + totalMarketValueFen;
    const totalEquityYuan = totalEquityFen / 100;

    const prevEquityFen = i > startIdx
      ? (equityCurve[equityCurve.length - 1]?.totalEquity ?? config.initialCapital) * 100
      : config.initialCapital;
    const dayReturn = (totalEquityFen - prevEquityFen) / prevEquityFen;

    if (totalEquityFen > peakEquityFen) {
      peakEquityFen = totalEquityFen;
    }
    const drawdown = (totalEquityFen - peakEquityFen) / peakEquityFen;

    equityCurve.push({
      date: currentDate,
      totalEquity: totalEquityYuan,
      cash: cashFen / 100,
      marketValue: totalMarketValueFen / 100,
      returnPct: dayReturn,
      drawdownPct: drawdown,
    });

    // 记录持仓快照（每10天记录一次，避免过多数据）
    if ((i - startIdx) % 10 === 0) {
      holdings.push({
        date: currentDate,
        positions: Array.from(positions.values()).map(p => ({
          code: p.code,
          shares: p.shares,
          avgCost: p.buyPrice,
          entryDateIdx: p.entryDateIdx,
          holdDays: p.holdDays,
        })),
      });
    }

    // 进度报告
    if ((i - startIdx) % 10 === 0) {
      const pct = 75 + ((i - startIdx) / (actualEndIdx - startIdx)) * 25;
      safeOnProgress({ stage: 'simulation', percent: pct, message: `模拟交易 ${i - startIdx}/${actualEndIdx - startIdx}` });
    }
  }

  // 4. 期末清仓
  const lastDate = allTradeDates[actualEndIdx];
  for (const [code, state] of positions) {
    const bars = stockBars.get(code);
    if (bars) {
      const lastBar = bars[bars.length - 1];
      const sellPrice = lastBar[OHLCV_CLOSE];
      const sellAmountFen = state.shares * sellPrice * 100;
      const commission = calcSellCommission(
        sellAmountFen, config.feeRate, config.slippage, config.stampDuty, config.minCommission,
      );
      const pnlFen = sellAmountFen - state.shares * state.buyPrice * 100 - commission;
      cashFen += sellAmountFen - commission;
      trades.push({
        code,
        name: snapshots.get(code)?.name ?? code,
        entryDate: state.buyDate,
        exitDate: lastDate,
        entryPrice: state.buyPrice,
        exitPrice: sellPrice,
        shares: state.shares,
        pnl: pnlFen / 100,
        pnlPct: pnlFen / (state.shares * state.buyPrice * 100),
        holdDays: state.holdDays,
        sellReason: 'end',
      });
    }
  }
  positions.clear();

  const simulationTime = performance.now() - simulationStart;
  safeOnProgress({ stage: 'done', percent: 100, message: '回测完成' });

  // 5. 计算绩效指标
  const metrics = calcMetrics(equityCurve, trades, config, benchmarkOhlcv);

  const endTime = performance.now();
  return {
    config,
    equityCurve,
    trades,
    holdings,
    metrics,
    warnings,
    timings: {
      dataLoad: dataLoadTime,
      indicatorCalc: indicatorCalcTime,
      simulation: simulationTime,
      total: endTime - startTime,
    },
  };
}