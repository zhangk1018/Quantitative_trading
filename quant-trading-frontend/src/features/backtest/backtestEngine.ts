// backtestEngine.ts — 回测引擎（买入条件仅支持自编指标）

import {
  calcRSI,
  sma,
  ema,
  type KlineBar,
} from '../../lib/indicators/indicators';
import {
  getLimitPctByCode,
  type BacktestInput,
  type BacktestOutput,
  type Trade,
  type EquityPoint,
  type BacktestSummary,
  type BacktestCondition,
  type IndicatorParams,
  type ProgressInfo,
} from './backtestTypes';
import { getCustomIndicatorRunner } from '../strategy-backtest/utils/customIndicatorRunner';

const TRADING_DAYS_PER_YEAR = 252;
const LOT_SIZE = 100;

// ==================== 数据清洗 ====================

function sanitizeBars(bars: KlineBar[]): { cleaned: KlineBar[]; warnings: string[] } {
  const warnings: string[] = [];
  const cleaned = bars.map((bar, idx) => {
    const { open, high, low, close, volume } = bar;
    // 检查价格有效性
    if (open <= 0 || high <= 0 || low <= 0 || close <= 0) {
      warnings.push(`第 ${idx} 根 K 线包含非正价格，已忽略该日数据`);
      return null;
    }
    if (high < low || high < open || high < close || low > open || low > close) {
      warnings.push(`第 ${idx} 根 K 线价格逻辑错误（high/low 不合法），已修正为相邻值`);
      // 简单修正：调整 high 和 low
      const correctedHigh = Math.max(open, close, high);
      const correctedLow = Math.min(open, close, low);
      return { ...bar, high: correctedHigh, low: correctedLow };
    }
    if (volume < 0) {
      warnings.push(`第 ${idx} 根 K 线成交量为负，已置为 0`);
      return { ...bar, volume: 0 };
    }
    return bar;
  }).filter((b): b is KlineBar => b !== null);

  if (cleaned.length === 0) {
    warnings.push('所有 K 线数据无效，回测无法继续');
  }
  return { cleaned, warnings };
}

// ==================== 指标计算缓存 ====================

interface IndicatorCache {
  closes: number[];
  opens: number[];
  highs: number[];
  lows: number[];
  volumes: number[];
  ma5: (number | null)[];
  ma10: (number | null)[];
  ma20: (number | null)[];
  ma60: (number | null)[];
  macd: { dif: (number | null)[]; dea: (number | null)[]; macd: (number | null)[] };
  rsi: (number | null)[];
  volRatio5: (number | null)[];
  consecUpDays: (number | null)[];
  consecDownDays: (number | null)[];
  bollUpper: (number | null)[];
  bollLower: (number | null)[];
  bollMid: (number | null)[];
}

function computeIndicators(bars: KlineBar[], params: IndicatorParams): IndicatorCache {
  const closes = bars.map((b) => b.close);
  const opens = bars.map((b) => b.open);
  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  const volumes = bars.map((b) => b.volume);
  const n = bars.length;

  const ma5 = sma(closes, params.ma5);
  const ma10 = sma(closes, params.ma10);
  const ma20 = sma(closes, params.ma20);
  const ma60 = sma(closes, params.ma60);

  const rsi = calcRSI(closes, params.rsiPeriod);

  // MACD
  const emaFast = ema(closes as (number | null)[], params.macdFast);
  const emaSlow = ema(closes as (number | null)[], params.macdSlow);
  const dif: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (emaFast[i] !== null && emaSlow[i] !== null) {
      dif[i] = emaFast[i]! - emaSlow[i]!;
    }
  }
  const dea = ema(dif, params.macdSignal);
  const macdHist: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (dif[i] !== null && dea[i] !== null) {
      macdHist[i] = 2 * (dif[i]! - dea[i]!);
    }
  }
  const macd = { dif, dea, macd: macdHist };

  // 成交量比例（5 日均量）
  const volMa5 = sma(volumes, 5);
  const volRatio5: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (volMa5[i] !== null && volMa5[i]! > 0) {
      volRatio5[i] = volumes[i] / volMa5[i]!;
    }
  }

  // 连续涨跌天数
  const consecUpDays: (number | null)[] = new Array(n).fill(null);
  const consecDownDays: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i === 0) {
      consecUpDays[i] = closes[i] > opens[i] ? 1 : 0;
      consecDownDays[i] = closes[i] < opens[i] ? 1 : 0;
    } else {
      consecUpDays[i] = closes[i] > closes[i - 1] ? (consecUpDays[i - 1] ?? 0) + 1 : 0;
      consecDownDays[i] = closes[i] < closes[i - 1] ? (consecDownDays[i - 1] ?? 0) + 1 : 0;
    }
  }

  // BOLL 滑动窗口优化
  const period = params.bollPeriod;
  const bollMid = sma(closes, period);
  const bollUpper: (number | null)[] = new Array(n).fill(null);
  const bollLower: (number | null)[] = new Array(n).fill(null);
  if (n >= period) {
    let sum = 0;
    let sumSq = 0;
    for (let i = 0; i < period; i++) {
      sum += closes[i];
      sumSq += closes[i] * closes[i];
    }
    for (let i = period - 1; i < n; i++) {
      if (i >= period) {
        const out = closes[i - period];
        const inc = closes[i];
        sum += inc - out;
        sumSq += inc * inc - out * out;
      }
      const mean = sum / period;
      const variance = sumSq / period - mean * mean;
      const std = Math.sqrt(variance);
      bollUpper[i] = mean + params.bollStd * std;
      bollLower[i] = mean - params.bollStd * std;
    }
  }

  return {
    closes,
    opens,
    highs,
    lows,
    volumes,
    ma5,
    ma10,
    ma20,
    ma60,
    macd,
    rsi,
    volRatio5,
    consecUpDays,
    consecDownDays,
    bollUpper,
    bollLower,
    bollMid,
  };
}

// ==================== 卖出信号：MA5 下穿 MA20 ====================

function checkMaDeathCross(cache: IndicatorCache, idx: number): boolean {
  if (idx < 1) return false;
  const short = cache.ma5[idx];
  const long = cache.ma20[idx];
  const prevShort = cache.ma5[idx - 1];
  const prevLong = cache.ma20[idx - 1];
  if (short === null || long === null || prevShort === null || prevLong === null) return false;
  return prevShort >= prevLong && short < long;
}

// ==================== 涨跌停检查 ====================

function isPriceLimited(
  bar: KlineBar,
  prevClose: number,
  direction: 'buy' | 'sell',
  limitPct: number,
): boolean {
  const limitPrice = prevClose * (1 + limitPct);
  const downLimitPrice = prevClose * (1 - limitPct);
  if (direction === 'buy') {
    return bar.open >= limitPrice * 0.995;
  }
  return bar.open <= downLimitPrice * 1.005;
}

// ==================== 买入信号预计算（Pyodide Worker）====================

async function computeBuySignals(
  condition: BacktestCondition,
  bars: KlineBar[],
): Promise<boolean[]> {
  if (!condition.formula || typeof condition.formula !== 'string') {
    throw new Error(`自编指标公式为空：${condition.indicatorName}`);
  }

  const runner = getCustomIndicatorRunner();
  if (!runner.isReady()) {
    await runner.init();
  }

  const rawSignals = await runner.executeSingle(
    condition.formula,
    {
      open: bars.map((b) => b.open),
      high: bars.map((b) => b.high),
      low: bars.map((b) => b.low),
      close: bars.map((b) => b.close),
      volume: bars.map((b) => b.volume),
    },
    60_000,
  );

  return rawSignals.map((v) => v !== null && v !== 0 && Number.isFinite(v));
}

// ==================== 主引擎 ====================

export async function runBacktest(
  input: BacktestInput,
  onProgress?: (info: ProgressInfo) => void,
): Promise<BacktestOutput> {
  const { bars: rawBars, buyCondition, config } = input;
  const {
    stockCode,
    capital,
    feeRate,
    slippage,
    riskFreeRate,
    executionPrice,
    maxDeferDays,
    indicatorParams,
  } = config;

  // 缓存涨跌停比例，避免每个交易日重复解析股票代码前缀
  const limitPct = getLimitPctByCode(stockCode);

  // 数据清洗
  const { cleaned: bars, warnings: cleanWarnings } = sanitizeBars(rawBars);
  const warnings: string[] = [...cleanWarnings];

  if (bars.length === 0) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings };
  }
  if (!buyCondition?.indicatorId) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings: [...warnings, '未配置买入条件'] };
  }

  onProgress?.({ stage: 'fetching', percent: 5, message: '数据清洗完成，开始计算指标...' });

  // 1. 计算指标（卖出条件 MA5 下穿 MA20 依赖 ma5/ma20）
  const cache = computeIndicators(bars, indicatorParams);
  onProgress?.({ stage: 'indicators', percent: 20, message: '技术指标计算完成' });

  // 2. 预计算买入信号（Pyodide Worker）
  let buySignals: boolean[];
  try {
    onProgress?.({ stage: 'signals', percent: 30, message: '正在执行自编指标脚本...' });
    buySignals = await computeBuySignals(buyCondition, bars);
    onProgress?.({ stage: 'signals', percent: 50, message: '买入信号预计算完成' });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    warnings.push(`自编指标执行失败：${msg}`);
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings };
  }

  // 校验信号长度
  if (buySignals.length !== bars.length) {
    warnings.push(`买入信号长度 ${buySignals.length} 与 K 线数量 ${bars.length} 不一致`);
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings };
  }

  // 3. 确定预热期
  const warmupDays = Math.max(
    indicatorParams.ma60,
    indicatorParams.bollPeriod,
    indicatorParams.macdSlow + indicatorParams.macdSignal,
    indicatorParams.rsiPeriod,
    5,
  );
  const firstValidIdx = warmupDays;

  // 4. 模拟交易
  let cash = capital;
  let shares = 0;
  let tradeId = 0;
  let state: 'idle' | 'holding' | 'closed' = 'idle';
  let pendingBuySignal: { idx: number; deferCount: number } | null = null;
  let pendingSellSignal: { idx: number; deferCount: number } | null = null;
  let currentEntryIdx = -1;
  let currentEntryPrice = 0;

  // 诊断计数器：用于无交易时向用户暴露原因
  let buySignalCount = 0;
  let buyLimitDeferredCount = 0;
  let buyLimitExpiredCount = 0;
  let insufficientFundCount = 0;
  let unexecutedBuyCount = 0;
  let sellSignalCount = 0;
  let sellLimitDeferredCount = 0;
  let sellLimitExpiredCount = 0;

  const trades: Trade[] = [];
  const equityCurve: EquityPoint[] = [];

  // 回撤 O(1) 优化：维护历史峰值
  let peakEquity = capital;

  onProgress?.({ stage: 'signals', percent: 55, message: '开始信号检测与模拟交易...' });

  const totalBars = bars.length;
  let processed = 0;

  for (let i = firstValidIdx; i < totalBars; i++) {
    const bar = bars[i];
    const isLastBar = i === totalBars - 1;
    const prevClose = i > 0 ? bars[i - 1].close : bar.open;

    // 停牌日：沿用前日净值
    if (bar.volume === 0) {
      const prevEquity = equityCurve.length > 0
        ? equityCurve[equityCurve.length - 1].equity
        : capital;
      equityCurve.push({
        time: bar.time,
        equity: prevEquity,
        drawdown: computeDrawdownO1(prevEquity, peakEquity),
      });
      processed++;
      continue;
    }

    // --- 处理待成交买入信号 ---
    // 信号确认机制已废除：信号日触发后，次日执行时不再要求信号持续为真
    if (state === 'idle' && pendingBuySignal !== null) {
      if (isPriceLimited(bar, prevClose, 'buy', limitPct)) {
        pendingBuySignal.deferCount++;
        buyLimitDeferredCount++;
        if (pendingBuySignal.deferCount > maxDeferDays) {
          buyLimitExpiredCount++;
          warnings.push(`${bar.time} 买入信号顺延超过 ${maxDeferDays} 天，自动失效`);
          pendingBuySignal = null;
        }
      } else {
        const execPrice = executionPrice === 'next_open' ? bar.open : bar.close;
        const availableCash = cash * (1 - feeRate);
        const buyShares = Math.floor(availableCash / (execPrice * LOT_SIZE)) * LOT_SIZE;
        if (buyShares >= LOT_SIZE) {
          const cost = buyShares * execPrice * (1 + feeRate);
          cash -= cost;
          shares = buyShares;
          currentEntryIdx = i;
          currentEntryPrice = execPrice;
          state = 'holding';
          trades.push({
            id: tradeId++,
            direction: 'buy',
            entryTime: bar.time,
            exitTime: '',
            entryPrice: execPrice,
            exitPrice: 0,
            shares: buyShares,
            profit: 0,
            profitPct: 0,
            holdDays: 0,
            isForcedClose: false,
            entryReason: buildEntryReason(buyCondition),
            exitReason: '',
          });
        } else {
          insufficientFundCount++;
          warnings.push(`${bar.time} 资金不足 1 手，无法买入（需 ${execPrice * LOT_SIZE} 元，可用 ${cash} 元）`);
        }
        pendingBuySignal = null;
      }
    }

    // --- 处理待成交卖出信号 ---
    // 同步废除卖出信号确认：死叉触发后，次日执行时不再要求 MA5 持续低于 MA20
    if (state === 'holding' && pendingSellSignal !== null) {
      if (isPriceLimited(bar, prevClose, 'sell', limitPct)) {
        pendingSellSignal.deferCount++;
        sellLimitDeferredCount++;
        if (pendingSellSignal.deferCount > maxDeferDays) {
          sellLimitExpiredCount++;
          warnings.push(`${bar.time} 卖出信号顺延超过 ${maxDeferDays} 天，自动失效`);
          pendingSellSignal = null;
        }
      } else {
        const execPrice = executionPrice === 'next_open' ? bar.open : bar.close;
        const sellProceeds = execPrice * shares * (1 - feeRate);
        const buyCost = currentEntryPrice * shares * (1 + feeRate);
        const actualProfit = sellProceeds - buyCost;
        cash += sellProceeds;

        trades.push({
          id: tradeId++,
          direction: 'sell',
          entryTime: bars[currentEntryIdx].time,
          exitTime: bar.time,
          entryPrice: currentEntryPrice,
          exitPrice: execPrice,
          shares,
          profit: actualProfit,
          profitPct: (actualProfit / capital) * 100,
          holdDays: i - currentEntryIdx - 1,
          isForcedClose: false,
          entryReason: buildEntryReason(buyCondition),
          exitReason: 'MA5下穿MA20',
        });
        shares = 0;
        state = 'idle';
        pendingSellSignal = null;
      }
    }

    // --- 期末清仓（信号执行完毕后，若仍持有仓位则强制清仓）---
    if (isLastBar && state === 'holding') {
      const exitPrice = bar.close;
      const grossProfit = (exitPrice - currentEntryPrice) * shares;
      const fee = (exitPrice * shares) * feeRate;
      const profit = grossProfit - fee;
      cash += exitPrice * shares - fee;
      trades.push({
        id: tradeId++,
        direction: 'close',
        entryTime: bars[currentEntryIdx].time,
        exitTime: bar.time,
        entryPrice: currentEntryPrice,
        exitPrice,
        shares,
        profit,
        profitPct: (profit / capital) * 100,
        holdDays: i - currentEntryIdx - 1,
        isForcedClose: true,
        entryReason: buildEntryReason(buyCondition),
        exitReason: '期末强制清仓',
      });
      shares = 0;
      state = 'closed';
    }

    // --- 信号检测 ---
    if (state === 'idle' && pendingBuySignal === null && buySignals[i]) {
      buySignalCount++;
      pendingBuySignal = { idx: i, deferCount: 0 };
    }

    if (state === 'holding' && pendingSellSignal === null && checkMaDeathCross(cache, i)) {
      sellSignalCount++;
      pendingSellSignal = { idx: i, deferCount: 0 };
    }

    // --- 计算当日净值 ---
    const holdingValue = shares * bar.close;
    const totalEquity = cash + holdingValue;
    if (totalEquity > peakEquity) peakEquity = totalEquity;
    const drawdown = computeDrawdownO1(totalEquity, peakEquity);
    equityCurve.push({
      time: bar.time,
      equity: totalEquity,
      drawdown,
    });

    processed++;
    if (processed % 50 === 0 && onProgress) {
      const pct = Math.round(55 + (processed / (totalBars - firstValidIdx)) * 35);
      onProgress({
        stage: 'simulating',
        percent: Math.min(pct, 90),
        message: `处理到 ${bar.time} (${processed}/${totalBars - firstValidIdx})`,
      });
    }
  }

  // 兜底清仓与期末未执行信号统计
  if (state === 'holding') {
    const lastBar = bars[bars.length - 1];
    const exitPrice = lastBar.close;
    const actualProfit = (exitPrice - currentEntryPrice) * shares;
    cash += exitPrice * shares;
    trades.push({
      id: tradeId++,
      direction: 'close',
      entryTime: bars[currentEntryIdx].time,
      exitTime: lastBar.time,
      entryPrice: currentEntryPrice,
      exitPrice,
      shares,
      profit: actualProfit,
      profitPct: (actualProfit / capital) * 100,
      holdDays: bars.length - 1 - currentEntryIdx - 1,
      isForcedClose: true,
      entryReason: buildEntryReason(buyCondition),
      exitReason: '期末强制清仓',
    });
    shares = 0;
  } else if (pendingBuySignal !== null) {
    // T+1 模型：信号出现在回测最后交易日，无下一交易日可执行
    unexecutedBuyCount++;
    warnings.push(
      `${bars[bars.length - 1].time} 出现买入信号，但已是回测期最后交易日，` +
      `T+1 成交模型无法执行该信号。`,
    );
  }

  onProgress?.({ stage: 'simulating', percent: 95, message: '模拟交易完成，计算汇总指标...' });

  // 5. 诊断汇总：无完整交易时向用户暴露具体原因
  const closedTrades = trades.filter((t) => t.direction === 'sell' || t.isForcedClose);
  if (closedTrades.length === 0) {
    warnings.push(
      `回测期间共检测到 ${buySignalCount} 次买入信号，` +
      `因涨停顺延 ${buyLimitDeferredCount} 次（失效 ${buyLimitExpiredCount} 次），` +
      `因资金不足跳过 ${insufficientFundCount} 次，` +
      `因信号出现在期末无法 T+1 执行 ${unexecutedBuyCount} 次，` +
      `因无后续卖出信号/未命中卖出条件导致 0 笔完整交易。`,
    );
  }

  // 6. 计算汇总指标
  const summary = computeSummary(trades, equityCurve, capital, riskFreeRate, warmupDays, bars.length - firstValidIdx);

  onProgress?.({ stage: 'done', percent: 100, message: '回测完成' });

  return { trades, equityCurve, summary, warnings };
}

// ==================== 辅助函数 ====================

function buildEntryReason(condition: BacktestCondition): string {
  return condition.indicatorName || '自编指标';
}

function buildEmptySummary(): BacktestSummary {
  return {
    totalReturn: 0,
    annualizedReturn: 0,
    winRate: 0,
    profitLossRatio: 0,
    maxDrawdown: 0,
    maxConsecutiveLoss: 0,
    avgHoldDays: 0,
    sharpeRatio: 0,
    totalTrades: 0,
    forcedCloseCount: 0,
    benchmarkReturn: 0,
    tradingDays: 0,
    warmupDays: 0,
  };
}

/** O(1) 回撤计算（依赖当前峰值） */
function computeDrawdownO1(currentEquity: number, peakEquity: number): number {
  if (peakEquity === 0) return 0;
  return Math.max(0, 1 - currentEquity / peakEquity);
}

function computeSummary(
  trades: Trade[],
  equityCurve: EquityPoint[],
  capital: number,
  riskFreeRate: number,
  warmupDays: number,
  tradingDays: number,
): BacktestSummary {
  const finalEquity = equityCurve.length > 0
    ? equityCurve[equityCurve.length - 1].equity
    : capital;
  const totalReturn = (finalEquity - capital) / capital;
  const annualizedReturn = tradingDays > 0
    ? (1 + totalReturn) ** (TRADING_DAYS_PER_YEAR / tradingDays) - 1
    : 0;

  const closedTrades = trades.filter((t) => t.direction === 'sell');
  const forcedCloses = trades.filter((t) => t.isForcedClose);
  const totalClosedTrades = closedTrades.length;

  const winTrades = closedTrades.filter((t) => t.profit > 0);
  const lossTrades = closedTrades.filter((t) => t.profit <= 0);
  const winRate = totalClosedTrades > 0 ? winTrades.length / totalClosedTrades : 0;

  const avgWin = winTrades.length > 0
    ? winTrades.reduce((s, t) => s + t.profit, 0) / winTrades.length
    : 0;
  const avgLoss = lossTrades.length > 0
    ? Math.abs(lossTrades.reduce((s, t) => s + t.profit, 0) / lossTrades.length)
    : 0;
  const profitLossRatio = avgLoss > 0 ? avgWin / avgLoss : 0;

  const maxDrawdown = equityCurve.reduce((max, p) => Math.max(max, p.drawdown), 0);

  let maxConsecutiveLoss = 0;
  let currentConsecutive = 0;
  for (const t of closedTrades) {
    if (t.profit <= 0) {
      currentConsecutive++;
      maxConsecutiveLoss = Math.max(maxConsecutiveLoss, currentConsecutive);
    } else {
      currentConsecutive = 0;
    }
  }

  const avgHoldDays = totalClosedTrades > 0
    ? closedTrades.reduce((s, t) => s + t.holdDays, 0) / totalClosedTrades
    : 0;

  const dailyReturns: number[] = [];
  for (let i = 1; i < equityCurve.length; i++) {
    const prev = equityCurve[i - 1].equity;
    const curr = equityCurve[i].equity;
    if (prev > 0) {
      dailyReturns.push((curr - prev) / prev);
    }
  }
  const avgDailyReturn = dailyReturns.length > 0
    ? dailyReturns.reduce((s, r) => s + r, 0) / dailyReturns.length
    : 0;
  const variance = dailyReturns.length > 0
    ? dailyReturns.reduce((s, r) => s + (r - avgDailyReturn) ** 2, 0) / dailyReturns.length
    : 0;
  const annualizedVol = Math.sqrt(variance) * Math.sqrt(TRADING_DAYS_PER_YEAR);
  const sharpeRatio = annualizedVol > 0
    ? (annualizedReturn - riskFreeRate) / annualizedVol
    : 0;

  const benchmarkReturn = equityCurve.length > 0
    ? (equityCurve[equityCurve.length - 1].equity / capital - 1)
    : 0;

  return {
    totalReturn,
    annualizedReturn,
    winRate,
    profitLossRatio,
    maxDrawdown,
    maxConsecutiveLoss,
    avgHoldDays,
    sharpeRatio,
    totalTrades: totalClosedTrades,
    forcedCloseCount: forcedCloses.length,
    benchmarkReturn,
    tradingDays,
    warmupDays,
  };
}
