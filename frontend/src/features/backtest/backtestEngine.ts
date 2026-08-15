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
  type BacktestPresetCondition,
  PRESET_CONDITIONS,
  type IndicatorParams,
  type ProgressInfo,
  type DiagnosticEntry,
  type SellStrategy,
} from './backtestTypes';
import { getCustomIndicatorRunner } from '../strategy-backtest/utils/customIndicatorRunner';
import { detectConditions } from '../../lib/indicators/condition-detector';
import {
  TRADING_DAYS_PER_YEAR,
  LOT_SIZE,
  MIN_WARMUP_DAYS,
  PROGRESS_REPORT_INTERVAL,
  LIMIT_UP_TOLERANCE,
  LIMIT_DOWN_TOLERANCE,
  MIN_CAPITAL,
  MAX_CAPITAL,
  MIN_FEE_RATE,
  MAX_FEE_RATE,
  MIN_SLIPPAGE,
  MAX_SLIPPAGE,
  MIN_MAX_DEFER_DAYS,
  MAX_MAX_DEFER_DAYS,
} from './constants';
import {
  ParamError,
  SignalError,
  BacktestErrorCode,
} from './errors';

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
  /** ATR(14) — 用于吊灯止损策略 */
  atr14: (number | null)[];
  /** EMA(10) — 用于双均线死叉策略 */
  ema10: (number | null)[];
  /** EMA(30) — 用于双均线死叉策略 */
  ema30: (number | null)[];
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

  // ATR(14) — 使用 Wilder's smoothing：首值简单平均，后续 EMA 平滑
  const atrPeriod = 14;
  const atr14: (number | null)[] = new Array(n).fill(null);
  if (n >= atrPeriod + 1) {
    // True Range 数组
    const tr: number[] = new Array(n).fill(0);
    for (let i = 0; i < n; i++) {
      const prevClose = i > 0 ? closes[i - 1] : opens[i];
      tr[i] = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - prevClose),
        Math.abs(lows[i] - prevClose),
      );
    }
    // 初始 ATR = 前14根 TR 的简单平均
    let atrSum = 0;
    for (let i = 0; i < atrPeriod; i++) {
      atrSum += tr[i];
    }
    atr14[atrPeriod - 1] = atrSum / atrPeriod;
    // Wilder's EMA: ATR_t = (ATR_{t-1} * (period-1) + TR_t) / period
    for (let i = atrPeriod; i < n; i++) {
      atr14[i] = (atr14[i - 1]! * (atrPeriod - 1) + tr[i]) / atrPeriod;
    }
  }

  // EMA(10) 和 EMA(30) — 用于双均线死叉策略
  const ema10 = ema(closes as (number | null)[], 10);
  const ema30 = ema(closes as (number | null)[], 30);

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
    atr14,
    ema10,
    ema30,
  };
}

// ==================== 卖出信号检测（策略可配置）====================

interface SellSignalParams {
  strategy: SellStrategy;
  /** 高点回落比例（trailing_stop），如 0.08 = 8% */
  trailingStopPct: number;
  /** ATR周期（atr_chandelier），默认14 */
  atrPeriod: number;
  /** ATR倍数（atr_chandelier），默认3 */
  atrMultiplier: number;
  /** 短期EMA周期（ema_cross），默认10 */
  emaShort: number;
  /** 长期EMA周期（ema_cross），默认30 */
  emaLong: number;
}

interface SellSignalContext {
  bar: KlineBar;
  idx: number;
  entryPrice: number;
  entryIdx: number;
  peakPriceSinceEntry: number;
  cache: IndicatorCache;
}

/**
 * 检测当前 K 线是否触发卖出信号。
 * 返回 { triggered: boolean, reason: string, newPeak: number }
 *
 * 策略一（trailing_stop）：从持仓最高价回撤 trailingStopPct 即卖出
 * 策略二（atr_chandelier）：收盘价 < 最高价 - atrMultiplier × ATR 即卖出
 * 策略三（ema_cross）：短期EMA下穿长期EMA即卖出
 */
function checkSellSignal(
  params: SellSignalParams,
  ctx: SellSignalContext,
): { triggered: boolean; reason: string; newPeak: number } {
  const { strategy, trailingStopPct, atrMultiplier, emaShort, emaLong } = params;
  const { bar, idx, peakPriceSinceEntry, cache } = ctx;
  let newPeak = peakPriceSinceEntry;

  switch (strategy) {
    // ==================== 策略一：高点回落移动止损 ====================
    case 'trailing_stop': {
      // 更新持仓期间最高价
      if (bar.high > peakPriceSinceEntry) {
        newPeak = bar.high;
      }
      // 从最高价回撤超过阈值即卖出
      const drawdown = (bar.close - newPeak) / newPeak;
      if (drawdown <= -trailingStopPct) {
        return {
          triggered: true,
          reason: `高点回落${(trailingStopPct * 100).toFixed(0)}%止损（峰值${newPeak.toFixed(2)}，当前${bar.close.toFixed(2)}，回撤${Math.abs(drawdown * 100).toFixed(1)}%）`,
          newPeak,
        };
      }
      return { triggered: false, reason: '', newPeak };
    }

    // ==================== 策略二：ATR吊灯止损 ====================
    case 'atr_chandelier': {
      // 更新持仓期间最高价
      if (bar.high > peakPriceSinceEntry) {
        newPeak = bar.high;
      }
      // 需要 ATR 值有效
      const atr = cache.atr14[idx];
      if (atr === null || atr <= 0) return { triggered: false, reason: '', newPeak };
      // 吊灯止损线 = 最高价 - atrMultiplier × ATR
      const stopPrice = newPeak - atrMultiplier * atr;
      if (bar.close < stopPrice) {
        return {
          triggered: true,
          reason: `ATR吊灯止损（峰值${newPeak.toFixed(2)}，ATR=${atr.toFixed(2)}，止损线=${stopPrice.toFixed(2)}，收盘${bar.close.toFixed(2)}）`,
          newPeak,
        };
      }
      return { triggered: false, reason: '', newPeak };
    }

    // ==================== 策略三：双均线死叉 ====================
    case 'ema_cross': {
      if (idx < 1) return { triggered: false, reason: '', newPeak };
      const shortNow = cache.ema10[idx];
      const longNow = cache.ema30[idx];
      const shortPrev = cache.ema10[idx - 1];
      const longPrev = cache.ema30[idx - 1];
      if (shortNow === null || longNow === null || shortPrev === null || longPrev === null) {
        return { triggered: false, reason: '', newPeak };
      }
      // 前一日短均 >= 长均，当日短均 < 长均 → 死叉
      if (shortPrev >= longPrev && shortNow < longNow) {
        return {
          triggered: true,
          reason: `双均线死叉（EMA${emaShort}=${shortNow.toFixed(2)} < EMA${emaLong}=${longNow.toFixed(2)}）`,
          newPeak,
        };
      }
      return { triggered: false, reason: '', newPeak };
    }

    default:
      return { triggered: false, reason: '', newPeak };
  }
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
    return bar.open >= limitPrice * LIMIT_UP_TOLERANCE;
  }
  return bar.open <= downLimitPrice * LIMIT_DOWN_TOLERANCE;
}

// ==================== 买入信号预计算（Pyodide Worker / 系统预设）====================

async function computeBuySignals(
  condition: BacktestCondition,
  bars: KlineBar[],
  /** 预计算量比（5日均量比），由后台数据提供，脚本可直接使用 */
  volRatio5?: (number | null)[],
): Promise<boolean[]> {
  if (condition.type === 'preset') {
    return computePresetBuySignals(condition, bars);
  }

  // 自编指标：Pyodide Worker 执行
  if (!condition.formula || typeof condition.formula !== 'string') {
    throw new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      `自编指标公式为空：${condition.indicatorName}`,
      { indicatorName: condition.indicatorName },
    );
  }

  const runner = getCustomIndicatorRunner();
  if (!runner.isReady()) {
    await runner.init();
  }

  let rawSignals: (number | null)[];
  try {
    const data: {
      open: number[];
      high: number[];
      low: number[];
      close: number[];
      volume: number[];
      volRatio5?: number[];
    } = {
      open: bars.map((b) => b.open),
      high: bars.map((b) => b.high),
      low: bars.map((b) => b.low),
      close: bars.map((b) => b.close),
      volume: bars.map((b) => b.volume),
    };
    // 传入预计算量比（后台已有，脚本可直接使用 CUSTOM_VOL_RATIO）
    if (volRatio5) {
      data.volRatio5 = volRatio5.map((v) => (v !== null && Number.isFinite(v) ? v : 0));
    }
    rawSignals = await runner.executeSingle(
      condition.formula,
      data,
      60_000,
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      `自编指标执行失败：${msg}`,
      { indicatorName: condition.indicatorName, originalError: msg },
    );
  }

  return rawSignals.map((v) => v !== null && v !== 0 && Number.isFinite(v));
}

/**
 * 系统预设条件买入信号计算。
 * 使用 condition-detector.ts 的 detectConditions 函数，
 * 与选股视图条件构建器的检测逻辑保持一致。
 */
function computePresetBuySignals(
  condition: BacktestPresetCondition,
  bars: KlineBar[],
): boolean[] {
  const n = bars.length;
  const signals = new Array(n).fill(false);

  const presetDef = PRESET_CONDITIONS.find((p) => p.id === condition.presetId);
  if (!presetDef) {
    throw new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      `未知的系统预设条件：${condition.presetName}（${condition.presetId}）`,
      { presetId: condition.presetId },
    );
  }

  // 使用 detectConditions 检测所有条件
  const conditions = presetDef.conditionKeys.map((k) => ({ fieldKey: k }));
  const result = detectConditions(bars, conditions);

  // 构建日期→索引映射，避免重复 findIndex
  const dateToIdx = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    dateToIdx.set(bars[i].time, i);
  }

  // 将事件列表按 fieldKey 分组为 Set<dayIndex>
  const eventDays = new Map<string, Set<number>>();
  for (const event of result.events) {
    const idx = dateToIdx.get(event.time);
    if (idx === undefined) continue;
    if (!eventDays.has(event.fieldKey)) {
      eventDays.set(event.fieldKey, new Set());
    }
    eventDays.get(event.fieldKey)!.add(idx);
  }

  /**
   * 窗口内先后出现逻辑（如"晨星放量"的3日窗口）：
   * - 最后一个 conditionKey 是"触发条件"，信号日设为触发日
   * - 其他条件必须在 [触发日 - windowDays, 触发日] 范围内出现过
   */
  if (presetDef.windowDays && presetDef.conditionKeys.length >= 2) {
    const triggerKey = presetDef.conditionKeys[presetDef.conditionKeys.length - 1];
    const otherKeys = presetDef.conditionKeys.slice(0, -1);
    const triggerDays = eventDays.get(triggerKey);

    if (triggerDays) {
      for (const triggerDay of triggerDays) {
        let allMet = true;
        for (const key of otherKeys) {
          const days = eventDays.get(key);
          if (!days) {
            allMet = false;
            break;
          }
          // 检查 key 是否在 [triggerDay - windowDays, triggerDay] 范围内出现过
          let found = false;
          const windowStart = Math.max(0, triggerDay - presetDef.windowDays);
          for (let d = windowStart; d <= triggerDay; d++) {
            if (days.has(d)) {
              found = true;
              break;
            }
          }
          if (!found) {
            allMet = false;
            break;
          }
        }
        if (allMet) {
          signals[triggerDay] = true;
        }
      }
    }
    return signals;
  }

  // 默认逻辑：所有条件在同一天同时满足（AND 逻辑）
  // 例如"晨星放量"需要 pattern_morning_star 和 volume_breakout 同时成立
  for (let i = 0; i < n; i++) {
    let allMet = true;
    for (const key of presetDef.conditionKeys) {
      const days = eventDays.get(key);
      if (!days || !days.has(i)) {
        allMet = false;
        break;
      }
    }
    signals[i] = allMet;
  }

  return signals;
}

/** 从数组末尾查找第一个满足条件的元素索引（兼容 ES2023 之前的 findLastIndex） */
function findLastIndex<T>(arr: T[], predicate: (val: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i;
  }
  return -1;
}

/** 安全调用 onProgress 回调，异常时仅记录日志不中断回测 */
function safeProgress(
  onProgress: ((info: ProgressInfo) => void) | undefined,
  info: ProgressInfo,
): void {
  if (!onProgress) return;
  try {
    onProgress(info);
  } catch {
    console.warn('[Backtest] onProgress 回调异常');
  }
}

// ==================== 主引擎 ====================

/** 校验回测配置参数合法性，失败时抛出 ParamError */
function validateConfig(config: {
  capital: number;
  feeRate: number;
  slippage: number;
  riskFreeRate: number;
  maxDeferDays: number;
  stockCode: string;
}): void {
  if (!Number.isFinite(config.capital) || config.capital < MIN_CAPITAL) {
    throw new ParamError(BacktestErrorCode.PARAM_OUT_OF_RANGE, `资金必须 >= ${MIN_CAPITAL}，当前=${config.capital}`, { field: 'capital', value: config.capital });
  }
  if (config.capital > MAX_CAPITAL) {
    throw new ParamError(BacktestErrorCode.PARAM_OUT_OF_RANGE, `资金不能超过 ${MAX_CAPITAL}，当前=${config.capital}`, { field: 'capital', value: config.capital });
  }
  if (!Number.isFinite(config.feeRate) || config.feeRate < MIN_FEE_RATE || config.feeRate > MAX_FEE_RATE) {
    throw new ParamError(BacktestErrorCode.PARAM_OUT_OF_RANGE, `费率必须在 ${MIN_FEE_RATE}~${MAX_FEE_RATE} 之间，当前=${config.feeRate}`, { field: 'feeRate', value: config.feeRate });
  }
  if (!Number.isFinite(config.slippage) || config.slippage < MIN_SLIPPAGE || config.slippage > MAX_SLIPPAGE) {
    throw new ParamError(BacktestErrorCode.PARAM_OUT_OF_RANGE, `滑点必须在 ${MIN_SLIPPAGE}~${MAX_SLIPPAGE} 之间，当前=${config.slippage}`, { field: 'slippage', value: config.slippage });
  }
  if (!Number.isFinite(config.maxDeferDays) || config.maxDeferDays < MIN_MAX_DEFER_DAYS || config.maxDeferDays > MAX_MAX_DEFER_DAYS) {
    throw new ParamError(BacktestErrorCode.PARAM_OUT_OF_RANGE, `最大顺延天数必须在 ${MIN_MAX_DEFER_DAYS}~${MAX_MAX_DEFER_DAYS} 之间，当前=${config.maxDeferDays}`, { field: 'maxDeferDays', value: config.maxDeferDays });
  }
  if (!config.stockCode || typeof config.stockCode !== 'string') {
    throw new ParamError(BacktestErrorCode.PARAM_INVALID, '股票代码不能为空', { field: 'stockCode' });
  }
}

export async function runBacktest(
  input: BacktestInput,
  onProgress?: (info: ProgressInfo) => void,
): Promise<BacktestOutput> {
  const { bars: rawBars, buyCondition, config } = input;
  const {
    stockCode,
    startDate,
    endDate,
    capital,
    sellStrategy,
    trailingStopPct,
    atrPeriod,
    atrMultiplier,
    emaShort,
    emaLong,
    feeRate,
    slippage,
    riskFreeRate,
    executionPrice,
    maxDeferDays,
    indicatorParams,
  } = config;

  // 卖出策略参数
  const sellParams: SellSignalParams = {
    strategy: sellStrategy,
    trailingStopPct,
    atrPeriod,
    atrMultiplier,
    emaShort,
    emaLong,
  };

  // P0-1: 参数合法性校验（致命错误：Worker 层捕获后向 UI 报告错误码）
  try {
    validateConfig({ capital, feeRate, slippage, riskFreeRate, maxDeferDays, stockCode });
  } catch (err) {
    if (err instanceof ParamError) {
      // 重抛时附带错误码，便于 Worker 层精确展示
      throw new ParamError(err.code, err.message, err.context);
    }
    throw err;
  }

  // 缓存涨跌停比例，避免每个交易日重复解析股票代码前缀
  const limitPct = getLimitPctByCode(stockCode);

  // 数据清洗
  const { cleaned: bars, warnings: cleanWarnings } = sanitizeBars(rawBars);
  const warnings: string[] = [...cleanWarnings];
  const diagnostics: DiagnosticEntry[] = [];

  if (bars.length === 0) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings, diagnostics };
  }
  if (!buyCondition || (buyCondition.type === 'custom' ? !buyCondition.indicatorId : !buyCondition.presetId)) {
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings: [...warnings, '未配置买入条件'], diagnostics };
  }

  safeProgress(onProgress, { stage: 'fetching', percent: 5, message: '数据清洗完成，开始计算指标...' });

  // 1. 计算指标（含 ATR、EMA10/30，供卖出策略使用）
  const cache = computeIndicators(bars, indicatorParams);
  safeProgress(onProgress, { stage: 'indicators', percent: 20, message: '技术指标计算完成' });

  // 2. 预计算买入信号（Pyodide Worker）
  let buySignals: boolean[];
  try {
    safeProgress(onProgress, { stage: 'signals', percent: 30, message: '正在计算买入条件信号...' });
    buySignals = await computeBuySignals(buyCondition, bars, cache.volRatio5);
    safeProgress(onProgress, { stage: 'signals', percent: 50, message: '买入信号预计算完成' });
  } catch (err) {
    if (err instanceof SignalError) {
      warnings.push(err.message);
      diagnostics.push({
        time: new Date().toISOString().slice(0, 10),
        event: 'script_error',
        reason: err.message,
        data: { code: err.code, indicatorName: err.context.indicatorName as string },
      });
      return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings, diagnostics };
    }
    const msg = err instanceof Error ? err.message : String(err);
    warnings.push(`买入条件计算失败：${msg}`);
    diagnostics.push({
      time: new Date().toISOString().slice(0, 10),
      event: 'script_error',
      reason: `买入条件计算失败：${msg}`,
      data: { indicatorName: getConditionName(buyCondition) },
    });
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings, diagnostics };
  }

  // 校验信号长度
  if (buySignals.length !== bars.length) {
    warnings.push(`买入信号长度 ${buySignals.length} 与 K 线数量 ${bars.length} 不一致`);
    return { trades: [], equityCurve: [], summary: buildEmptySummary(), warnings, diagnostics };
  }

  // 3. 确定预热期和日期范围
  const warmupDays = Math.max(
    indicatorParams.ma60,
    indicatorParams.bollPeriod,
    indicatorParams.macdSlow + indicatorParams.macdSignal,
    indicatorParams.rsiPeriod,
    atrPeriod + 1,   // ATR 需要 period+1 根 K 线
    emaLong + 1,     // 长周期 EMA 需要 period+1 根 K 线
    MIN_WARMUP_DAYS,
  );
  const firstValidIdx = warmupDays;

  // 计算 startDate 和 endDate 对应的 bar 索引
  const startIdx = startDate ? bars.findIndex((b) => b.time >= startDate) : firstValidIdx;
  const endIdx = endDate ? findLastIndex(bars, (b) => b.time <= endDate) : bars.length - 1;

  // 4. 模拟交易
  let cash = capital;
  let shares = 0;
  let tradeId = 0;
  let state: 'idle' | 'holding' | 'closed' = 'idle';
  let pendingBuySignal: { idx: number; deferCount: number } | null = null;
  let pendingSellSignal: { idx: number; deferCount: number } | null = null;
  let currentEntryIdx = -1;
  let currentEntryPrice = 0;
  /** 持仓期间的最高价（用于移动止盈策略） */
  let peakPriceSinceEntry = 0;

  // 诊断计数器 + 结构化日志
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

  safeProgress(onProgress, { stage: 'signals', percent: 55, message: '开始信号检测与模拟交易...' });

  const totalBars = bars.length;
  let processed = 0;

  for (let i = firstValidIdx; i < totalBars; i++) {
    const bar = bars[i];
    const prevClose = i > 0 ? bars[i - 1].close : bar.open;

    // 判断当前 bar 是否在用户选择的日期范围内
    const inDateRange = i >= startIdx && i <= endIdx;
    // 回测期结束日：到达 endDate 对应的 bar 时视为期末
    const isBacktestEnd = i === endIdx;

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

    // --- 仅在日期范围内执行交易逻辑 ---
    if (inDateRange) {
      // --- 处理待成交买入信号 ---
      if (state === 'idle' && pendingBuySignal !== null) {
        if (isPriceLimited(bar, prevClose, 'buy', limitPct)) {
          pendingBuySignal.deferCount++;
          buyLimitDeferredCount++;
          diagnostics.push({
            time: bar.time,
            event: 'buy_deferred',
            reason: `涨停限制，已顺延 ${pendingBuySignal.deferCount} 天`,
            data: { deferCount: pendingBuySignal.deferCount, maxDeferDays },
          });
          if (pendingBuySignal.deferCount > maxDeferDays) {
            buyLimitExpiredCount++;
            diagnostics.push({
              time: bar.time,
              event: 'buy_expired',
              reason: `买入信号顺延超过 ${maxDeferDays} 天，自动失效`,
            });
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
            peakPriceSinceEntry = execPrice;
            state = 'holding';
            diagnostics.push({
              time: bar.time,
              event: 'buy_executed',
              reason: `执行买入 ${buyShares} 股 @ ${execPrice}`,
              data: { shares: buyShares, price: execPrice, cost },
            });
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
            diagnostics.push({
              time: bar.time,
              event: 'insufficient_funds',
              reason: `资金不足 1 手（需 ${execPrice * LOT_SIZE} 元，可用 ${cash} 元）`,
              data: { required: execPrice * LOT_SIZE, available: cash },
            });
            warnings.push(`${bar.time} 资金不足 1 手，无法买入（需 ${execPrice * LOT_SIZE} 元，可用 ${cash} 元）`);
          }
          pendingBuySignal = null;
        }
      }

      // --- 处理待成交卖出信号 ---
      if (state === 'holding' && pendingSellSignal !== null) {
        if (isPriceLimited(bar, prevClose, 'sell', limitPct)) {
          pendingSellSignal.deferCount++;
          sellLimitDeferredCount++;
          diagnostics.push({
            time: bar.time,
            event: 'sell_deferred',
            reason: `跌停限制，已顺延 ${pendingSellSignal.deferCount} 天`,
            data: { deferCount: pendingSellSignal.deferCount, maxDeferDays },
          });
          if (pendingSellSignal.deferCount > maxDeferDays) {
            sellLimitExpiredCount++;
            diagnostics.push({
              time: bar.time,
              event: 'sell_expired',
              reason: `卖出信号顺延超过 ${maxDeferDays} 天，自动失效`,
            });
            warnings.push(`${bar.time} 卖出信号顺延超过 ${maxDeferDays} 天，自动失效`);
            pendingSellSignal = null;
          }
        } else {
          const execPrice = executionPrice === 'next_open' ? bar.open : bar.close;
          const sellProceeds = execPrice * shares * (1 - feeRate);
          const buyCost = currentEntryPrice * shares * (1 + feeRate);
          const actualProfit = sellProceeds - buyCost;
          cash += sellProceeds;

          // 从最近一次卖出信号诊断中获取原因
          const sellReason = diagnostics
            .filter((d) => d.event === 'sell_signal')
            .slice(-1)[0]?.reason?.replace(' 发出卖出信号', '') || '卖出信号';

          diagnostics.push({
            time: bar.time,
            event: 'sell_executed',
            reason: `${sellReason}，卖出 ${shares} 股 @ ${execPrice}`,
            data: { shares, price: execPrice, profit: actualProfit },
          });
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
            exitReason: sellReason,
          });
          shares = 0;
          state = 'idle';
          pendingSellSignal = null;
        }
      }

      // --- 期末清仓（到达 endDate 时，若仍持有仓位则强制清仓）---
      if (isBacktestEnd && state === 'holding') {
        const exitPrice = bar.close;
        const grossProfit = (exitPrice - currentEntryPrice) * shares;
        const fee = (exitPrice * shares) * feeRate;
        const profit = grossProfit - fee;
        cash += exitPrice * shares - fee;
        diagnostics.push({
          time: bar.time,
          event: 'forced_close',
          reason: '期末强制清仓',
          data: { shares, price: exitPrice, profit },
        });
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
        diagnostics.push({
          time: bar.time,
          event: 'buy_signal',
          reason: `"${getConditionName(buyCondition)}" 发出买入信号`,
          data: { indicatorName: getConditionName(buyCondition) },
        });
        pendingBuySignal = { idx: i, deferCount: 0 };
      }

      if (state === 'holding' && pendingSellSignal === null) {
        const sellResult = checkSellSignal(sellParams, {
          bar,
          idx: i,
          entryPrice: currentEntryPrice,
          entryIdx: currentEntryIdx,
          peakPriceSinceEntry,
          cache,
        });
        // 更新峰值（trailing_stop 策略会更新）
        peakPriceSinceEntry = sellResult.newPeak;
        if (sellResult.triggered) {
          sellSignalCount++;
          diagnostics.push({
            time: bar.time,
            event: 'sell_signal',
            reason: `${sellResult.reason} 发出卖出信号`,
          });
          pendingSellSignal = { idx: i, deferCount: 0 };
        }
      }
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
    if (processed % PROGRESS_REPORT_INTERVAL === 0) {
      const pct = Math.round(55 + (processed / (totalBars - firstValidIdx)) * 35);
      safeProgress(onProgress, {
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
    diagnostics.push({
      time: lastBar.time,
      event: 'forced_close',
      reason: '兜底清仓（回测结束时仍持有仓位）',
      data: { shares, price: exitPrice, profit: actualProfit },
    });
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
    unexecutedBuyCount++;
    diagnostics.push({
      time: bars[bars.length - 1].time,
      event: 'unexecuted_buy',
      reason: '买入信号出现在回测期最后交易日，T+1 模型无法执行',
    });
    warnings.push(
      `${bars[bars.length - 1].time} 出现买入信号，但已是回测期最后交易日，` +
      `T+1 成交模型无法执行该信号。`,
    );
  }

  safeProgress(onProgress, { stage: 'simulating', percent: 95, message: '模拟交易完成，计算汇总指标...' });

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

  safeProgress(onProgress, { stage: 'done', percent: 100, message: '回测完成' });

  return { trades, equityCurve, summary, warnings, diagnostics };
}

// ==================== 辅助函数 ====================

/** 获取条件显示名称 */
function getConditionName(condition: BacktestCondition): string {
  if (condition.type === 'preset') {
    return condition.presetName;
  }
  return condition.indicatorName || '自编指标';
}

function buildEntryReason(condition: BacktestCondition): string {
  return getConditionName(condition) || '买入条件';
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
