// backtestEngine.ts — 回测引擎纯函数（支持进度回调）

import {
  calcRSI,
  sma,
  ema,
  type KlineBar,
} from '../../lib/indicators/indicators';
import {
  REVERSE_CONDITION_MAP,
  CONDITION_LABEL_MAP,
  getLimitPctByCode,
  type BacktestInput,
  type BacktestOutput,
  type Trade,
  type EquityPoint,
  type BacktestSummary,
  type BacktestCondition,
  type ConditionFieldKey,
  type IndicatorParams,
  type ProgressInfo,
} from './backtestTypes';

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

// ==================== 信号检测 ====================

function checkCondition(
  c: BacktestCondition,
  cache: IndicatorCache,
  idx: number,
): boolean {
  const { fieldKey } = c;
  const params = c.params ?? {};

  switch (fieldKey) {
    case 'macd_golden_cross': {
      if (idx < 1) return false;
      const prev = cache.macd.dif[idx - 1] !== null && cache.macd.dea[idx - 1] !== null
        ? cache.macd.dif[idx - 1]! - cache.macd.dea[idx - 1]!
        : null;
      const curr = cache.macd.dif[idx] !== null && cache.macd.dea[idx] !== null
        ? cache.macd.dif[idx]! - cache.macd.dea[idx]!
        : null;
      return prev !== null && curr !== null && prev <= 0 && curr > 0;
    }
    case 'macd_death_cross': {
      if (idx < 1) return false;
      const prev = cache.macd.dif[idx - 1] !== null && cache.macd.dea[idx - 1] !== null
        ? cache.macd.dif[idx - 1]! - cache.macd.dea[idx - 1]!
        : null;
      const curr = cache.macd.dif[idx] !== null && cache.macd.dea[idx] !== null
        ? cache.macd.dif[idx]! - cache.macd.dea[idx]!
        : null;
      return prev !== null && curr !== null && prev >= 0 && curr < 0;
    }
    case 'rsi_oversold': {
      const threshold = params.threshold ?? 30;
      return cache.rsi[idx] !== null && cache.rsi[idx]! < threshold;
    }
    case 'rsi_overbought': {
      const threshold = params.threshold ?? 70;
      return cache.rsi[idx] !== null && cache.rsi[idx]! > threshold;
    }
    case 'volume_breakout': {
      const threshold = params.threshold ?? 1.5;
      return cache.volRatio5[idx] !== null && cache.volRatio5[idx]! >= threshold;
    }
    case 'volume_shrink': {
      const threshold = params.threshold ?? 0.5;
      return cache.volRatio5[idx] !== null && cache.volRatio5[idx]! <= threshold;
    }
    case 'consecutive_up': {
      const days = params.days ?? 3;
      return (cache.consecUpDays[idx] ?? 0) >= days;
    }
    case 'consecutive_down': {
      const days = params.days ?? 3;
      return (cache.consecDownDays[idx] ?? 0) >= days;
    }
    case 'ma_golden_cross': {
      if (idx < 1) return false;
      const short = cache.ma5[idx];
      const long = cache.ma20[idx];
      const prevShort = cache.ma5[idx - 1];
      const prevLong = cache.ma20[idx - 1];
      if (short === null || long === null || prevShort === null || prevLong === null) return false;
      return prevShort <= prevLong && short > long;
    }
    case 'ma_death_cross': {
      if (idx < 1) return false;
      const short = cache.ma5[idx];
      const long = cache.ma20[idx];
      const prevShort = cache.ma5[idx - 1];
      const prevLong = cache.ma20[idx - 1];
      if (short === null || long === null || prevShort === null || prevLong === null) return false;
      return prevShort >= prevLong && short < long;
    }
    default:
      return false;
  }
}

// ==================== 涨跌停检查 ====================

function isPriceLimited(
  bar: KlineBar,
  prevClose: number,
  direction: 'buy' | 'sell',
  stockCode: string,
): boolean {
  const limitPct = getLimitPctByCode(stockCode);
  const limitPrice = prevClose * (1 + limitPct);
  const downLimitPrice = prevClose * (1 - limitPct);
  if (direction === 'buy') {
    return bar.open >= limitPrice * 0.995;
  }
  return bar.open <= downLimitPrice * 1.005;
}

// ==================== 信号确认 ====================

/** 检查条件是否处于"已触发状态"（而非交叉事件），用于信号确认 */
function checkConditionState(
  c: BacktestCondition,
  cache: IndicatorCache,
  idx: number,
): boolean {
  const { fieldKey } = c;
  const params = c.params ?? {};

  switch (fieldKey) {
    case 'macd_golden_cross':
      return (cache.macd.dif[idx] ?? 0) > (cache.macd.dea[idx] ?? 0);
    case 'macd_death_cross':
      return (cache.macd.dif[idx] ?? 0) < (cache.macd.dea[idx] ?? 0);
    case 'rsi_oversold': {
      const threshold = params.threshold ?? 30;
      return cache.rsi[idx] !== null && cache.rsi[idx]! < threshold;
    }
    case 'rsi_overbought': {
      const threshold = params.threshold ?? 70;
      return cache.rsi[idx] !== null && cache.rsi[idx]! > threshold;
    }
    case 'volume_breakout': {
      const threshold = params.threshold ?? 1.5;
      return cache.volRatio5[idx] !== null && cache.volRatio5[idx]! >= threshold;
    }
    case 'volume_shrink': {
      const threshold = params.threshold ?? 0.5;
      return cache.volRatio5[idx] !== null && cache.volRatio5[idx]! <= threshold;
    }
    case 'consecutive_up': {
      const days = params.days ?? 3;
      return (cache.consecUpDays[idx] ?? 0) >= days;
    }
    case 'consecutive_down': {
      const days = params.days ?? 3;
      return (cache.consecDownDays[idx] ?? 0) >= days;
    }
    case 'ma_golden_cross':
      return (cache.ma5[idx] ?? 0) > (cache.ma20[idx] ?? 0);
    case 'ma_death_cross':
      return (cache.ma5[idx] ?? 0) < (cache.ma20[idx] ?? 0);
    default:
      return false;
  }
}

function isSignalConfirmed(
  condition: BacktestCondition,
  cache: IndicatorCache,
  bars: KlineBar[],
  crossIdx: number,
  confirmBars: number,
): boolean {
  // 交叉事件必须发生在 crossIdx
  if (!checkCondition(condition, cache, crossIdx)) return false;
  // 确认：交叉之后的状态必须持续 confirmBars 根 K 线
  for (let i = 1; i < confirmBars; i++) {
    const idx = crossIdx + i;
    if (idx >= bars.length) return false;
    if (bars[idx].volume === 0) continue;
    if (!checkConditionState(condition, cache, idx)) return false;
  }
  return true;
}

function isSignalStillValid(
  condition: BacktestCondition,
  cache: IndicatorCache,
  bars: KlineBar[],
  signalIdx: number,
  currentIdx: number,
): boolean {
  // 使用 checkConditionState 而非 checkCondition，因为交叉事件是一次性的
  // 信号有效性的判定标准是"状态是否持续"（如 DIF > DEA），而非"交叉事件是否重复发生"
  for (let i = signalIdx + 1; i <= currentIdx; i++) {
    if (bars[i].volume === 0) continue;
    if (!checkConditionState(condition, cache, i) && !checkConditionState(condition, cache, i - 1)) {
      return false;
    }
  }
  return true;
}

// ==================== 主引擎 ====================

export function runBacktest(
  input: BacktestInput,
  onProgress?: (info: ProgressInfo) => void,
): BacktestOutput {
  const { bars: rawBars, buyConditions, config } = input;
  const {
    stockCode,
    capital,
    feeRate,
    slippage,
    riskFreeRate,
    executionPrice,
    signalConfirmBars,
    maxDeferDays,
    indicatorParams,
  } = config;

  // 数据清洗
  const { cleaned: bars, warnings: cleanWarnings } = sanitizeBars(rawBars);
  const warnings: string[] = [...cleanWarnings];

  if (bars.length === 0) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings };
  }
  if (buyConditions.length === 0) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings: [...warnings, '未配置买入条件'] };
  }

  onProgress?.({ stage: 'fetching', percent: 5, message: '数据清洗完成，开始计算指标...' });

  // 1. 计算指标
  const cache = computeIndicators(bars, indicatorParams);
  onProgress?.({ stage: 'indicators', percent: 30, message: '技术指标计算完成' });

  // 2. 确定预热期
  const warmupDays = Math.max(
    indicatorParams.ma60,
    indicatorParams.bollPeriod,
    indicatorParams.macdSlow + indicatorParams.macdSignal,
    indicatorParams.rsiPeriod,
    5,
  );
  const firstValidIdx = warmupDays;

  // 3. 模拟交易
  let cash = capital;
  let shares = 0;
  let tradeId = 0;
  let state: 'idle' | 'holding' | 'closed' = 'idle';
  let pendingBuySignal: { idx: number; deferCount: number } | null = null;
  let pendingSellSignal: { idx: number; deferCount: number } | null = null;
  let potentialBuyCrossIdx: number | null = null; // 潜在的买入交叉索引，等待确认
  let potentialSellCrossIdx: number | null = null;
  let currentEntryIdx = -1;
  let currentEntryPrice = 0;

  const trades: Trade[] = [];
  const equityCurve: EquityPoint[] = [];

  // 回撤 O(1) 优化：维护历史峰值
  let peakEquity = capital;

  onProgress?.({ stage: 'signals', percent: 50, message: '开始信号检测与模拟交易...' });

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
      // 峰值不更新（停牌日不改变）
      processed++;
      continue;
    }

    // --- 期末清仓（必须在待成交信号执行之后，确保信号优先执行）---
    // 注意：期末清仓放在信号执行之前会导致最后一天的卖出信号被跳过
    // 正确顺序：先执行待成交信号，若仍持有仓位再清仓

    // --- 处理待成交信号 ---
    if (state === 'idle' && pendingBuySignal !== null) {
      if (!isSignalStillValid(buyConditions[0], cache, bars, pendingBuySignal.idx, i)) {
        pendingBuySignal = null;
        warnings.push(`${bar.time} 买入信号失效，条件已消失`);
      } else {
        if (isPriceLimited(bar, prevClose, 'buy', stockCode)) {
          pendingBuySignal.deferCount++;
          if (pendingBuySignal.deferCount > maxDeferDays) {
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
              entryReason: buildEntryReason(buyConditions),
              exitReason: '',
            });
          } else {
            warnings.push(`${bar.time} 资金不足 1 手，无法买入（需 ${execPrice * LOT_SIZE} 元，可用 ${cash} 元）`);
          }
          pendingBuySignal = null;
        }
      }
    }

    if (state === 'holding' && pendingSellSignal !== null) {
      const reverseKey = getReverseConditionKey(buyConditions[0]);
      const reverseCond: BacktestCondition = {
        fieldKey: reverseKey,
        label: getReverseConditionLabel(buyConditions[0]),
        params: buyConditions[0].params,
      };
      if (!isSignalStillValid(reverseCond, cache, bars, pendingSellSignal.idx, i)) {
        pendingSellSignal = null;
        warnings.push(`${bar.time} 卖出信号失效，条件已消失`);
      } else {
        if (isPriceLimited(bar, prevClose, 'sell', stockCode)) {
          pendingSellSignal.deferCount++;
          if (pendingSellSignal.deferCount > maxDeferDays) {
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
            entryReason: buildEntryReason(buyConditions),
            exitReason: getReverseConditionLabel(buyConditions[0]),
          });
          shares = 0;
          state = 'idle';
          pendingSellSignal = null;
        }
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
        entryReason: buildEntryReason(buyConditions),
        exitReason: '期末强制清仓',
      });
      shares = 0;
      state = 'closed';
    }

    // --- 信号检测（两阶段：交叉事件检测 → 状态持续确认）---
    // 交叉事件是一次性的（如 MACD 金叉），检测到后需等待 confirmBars 根 K 线确认状态持续
    if (state === 'idle' && pendingBuySignal === null) {
      if (potentialBuyCrossIdx === null) {
        // 第一阶段：检测交叉事件
        const allBuyMet = buyConditions.every((c) => checkCondition(c, cache, i));
        if (allBuyMet) {
          potentialBuyCrossIdx = i;
        }
      } else {
        // 第二阶段：等待确认窗口，期间用 checkConditionState 验证状态持续
        const stateValid = buyConditions.every((c) => checkConditionState(c, cache, i));
        if (!stateValid) {
          potentialBuyCrossIdx = null;
        } else if (i - potentialBuyCrossIdx >= signalConfirmBars - 1) {
          const confirmed = buyConditions.every((c) =>
            isSignalConfirmed(c, cache, bars, potentialBuyCrossIdx!, signalConfirmBars),
          );
          if (confirmed) {
            pendingBuySignal = { idx: potentialBuyCrossIdx, deferCount: 0 };
          }
          potentialBuyCrossIdx = null;
        }
      }
    }

    if (state === 'holding' && pendingSellSignal === null) {
      const reverseKey = getReverseConditionKey(buyConditions[0]);
      const reverseCond: BacktestCondition = {
        fieldKey: reverseKey,
        label: getReverseConditionLabel(buyConditions[0]),
        params: buyConditions[0].params,
      };
      if (potentialSellCrossIdx === null) {
        // 第一阶段：检测卖出交叉事件
        const sellTriggered = checkCondition(reverseCond, cache, i);
        if (sellTriggered) {
          potentialSellCrossIdx = i;
        }
      } else {
        // 第二阶段：等待确认窗口
        const stateValid = checkConditionState(reverseCond, cache, i);
        if (!stateValid) {
          potentialSellCrossIdx = null;
        } else if (i - potentialSellCrossIdx >= signalConfirmBars - 1) {
          const confirmed = isSignalConfirmed(reverseCond, cache, bars, potentialSellCrossIdx, signalConfirmBars);
          if (confirmed) {
            pendingSellSignal = { idx: potentialSellCrossIdx, deferCount: 0 };
          }
          potentialSellCrossIdx = null;
        }
      }
    }

    // --- 计算当日净值 ---
    const holdingValue = shares * bar.close;
    const totalEquity = cash + holdingValue;
    // 更新峰值
    if (totalEquity > peakEquity) peakEquity = totalEquity;
    const drawdown = computeDrawdownO1(totalEquity, peakEquity);
    equityCurve.push({
      time: bar.time,
      equity: totalEquity,
      drawdown,
    });

    processed++;
    // 每处理 50 根 K 线报告一次进度
    if (processed % 50 === 0 && onProgress) {
      const pct = Math.round(50 + (processed / (totalBars - firstValidIdx)) * 40);
      onProgress({
        stage: 'simulating',
        percent: Math.min(pct, 90),
        message: `处理到 ${bar.time} (${processed}/${totalBars - firstValidIdx})`,
      });
    }
  }

  // 兜底清仓
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
      entryReason: buildEntryReason(buyConditions),
      exitReason: '期末强制清仓',
    });
    shares = 0;
  }

  onProgress?.({ stage: 'simulating', percent: 95, message: '模拟交易完成，计算汇总指标...' });

  // 4. 计算汇总指标
  const summary = computeSummary(trades, equityCurve, capital, riskFreeRate, warmupDays, bars.length - firstValidIdx);

  onProgress?.({ stage: 'done', percent: 100, message: '回测完成' });

  return { trades, equityCurve, summary, warnings };
}

// ==================== 辅助函数 ====================

function getReverseConditionKey(c: BacktestCondition): ConditionFieldKey {
  return REVERSE_CONDITION_MAP[c.fieldKey] ?? c.fieldKey;
}

function getReverseConditionLabel(c: BacktestCondition): string {
  const reverseKey = getReverseConditionKey(c);
  return CONDITION_LABEL_MAP[reverseKey] ?? reverseKey;
}

function buildEntryReason(conditions: BacktestCondition[]): string {
  return conditions.map((c) => c.label).join(' + ');
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