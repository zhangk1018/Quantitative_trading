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
  type BacktestCustomSellCondition,
  type BacktestIndicatorOperator,
  type BacktestIndicatorThreshold,
  PRESET_CONDITIONS,
  type IndicatorParams,
  type ProgressInfo,
  type DiagnosticEntry,
  type SellStrategy,
  DEFAULT_LAYERED_TP_PARAMS,
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

  return rawSignals.map((v) => applyIndicatorThreshold(v, condition.operator, condition.threshold));
}

/**
 * 预计算自编卖出策略信号（纯信号协议）
 *
 * 复用自编指标 Pyodide 执行管线：脚本对整段 K 线全量输出每日「是否触发卖出」信号，
 * 引擎在持仓状态下消费。持仓上下文（entry/peak/顺延）由引擎管理，脚本不可见。
 */
async function computeSellSignals(
  condition: BacktestCustomSellCondition,
  bars: KlineBar[],
  volRatio5?: (number | null)[],
): Promise<boolean[]> {
  if (!condition.formula || typeof condition.formula !== 'string') {
    throw new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      `自编卖出策略公式为空：${condition.strategyName}`,
      { indicatorName: condition.strategyName },
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
    if (volRatio5) {
      data.volRatio5 = volRatio5.map((v) => (v !== null && Number.isFinite(v) ? v : 0));
    }
    rawSignals = await runner.executeSingle(condition.formula, data, 60_000);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new SignalError(
      BacktestErrorCode.SIGNAL_SCRIPT_ERROR,
      `自编卖出策略执行失败：${msg}`,
      { indicatorName: condition.strategyName, originalError: msg },
    );
  }

  return rawSignals.map((v) => applyIndicatorThreshold(v, condition.operator, condition.threshold));
}

/**
 * 按选股视图口径对自编指标逐日得分做算子+阈值判定。
 *
 * 兼容规则（对齐 CustomIndicator.filter 语义）：
 * - 数值非有限值（null/NaN）→ 恒 false
 * - operator 缺省，或 operator 非 range 且 threshold 缺省 → 退化为 score !== 0
 * - range → v 在 [low, high] 内（含边界）
 * - cross_up / cross_down → 需 prev 得分，本函数单日无法判定，退化为非 0（由调用方在需要时另行处理）
 */
function applyIndicatorThreshold(
  v: number | null,
  operator: BacktestIndicatorOperator | undefined,
  threshold: BacktestIndicatorThreshold | undefined,
): boolean {
  if (v === null || !Number.isFinite(v)) return false;

  // 区间算子
  if (operator === 'range') {
    if (Array.isArray(threshold) && threshold.length === 2) {
      const [lo, hi] = threshold;
      return v >= lo && v <= hi;
    }
    // 无有效区间 → 退化 score !== 0
    return v !== 0;
  }

  // 上穿/下穿需前后日对比，单日判定无上下文 → 退化为非 0 信号（调用方有 prev 时按日判定）
  if (operator === 'cross_up' || operator === 'cross_down') {
    return v !== 0;
  }

  // 单值算子
  switch (operator) {
    case '>':
      return typeof threshold === 'number' ? v > threshold : v !== 0;
    case '>=':
      return typeof threshold === 'number' ? v >= threshold : v !== 0;
    case '<':
      return typeof threshold === 'number' ? v < threshold : v !== 0;
    case '<=':
      return typeof threshold === 'number' ? v <= threshold : v !== 0;
    case '==':
      return typeof threshold === 'number' ? v === threshold : v !== 0;
    default:
      // operator 缺省
      return v !== 0;
  }
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
    customSellStrategy,
    layeredTPParams,
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

  // 卖出策略参数（自编卖出策略失败时回退内置 trailing_stop）
  const sellParams: SellSignalParams = {
    strategy: sellStrategy === 'custom' ? 'trailing_stop' : sellStrategy,
    trailingStopPct,
    atrPeriod,
    atrMultiplier,
    emaShort,
    emaLong,
  };
  /** 自编卖出策略是否启用且成功预计算（false 时主循环走内置 checkSellSignal） */
  const useCustomSell = sellStrategy === 'custom' && !!customSellStrategy;

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

  // 2.5 预计算自编卖出策略信号（纯信号协议；失败 → 回退内置 + 警告，非阻断）
  let customSellSignals: boolean[] | null = null;
  let customSellFailed = false;
  if (useCustomSell && customSellStrategy) {
    try {
      safeProgress(onProgress, { stage: 'signals', percent: 52, message: '正在计算自编卖出策略信号...' });
      customSellSignals = await computeSellSignals(customSellStrategy, bars, cache.volRatio5);
      if (customSellSignals.length !== bars.length) {
        customSellFailed = true;
        warnings.push(`自编卖出策略信号长度 ${customSellSignals.length} 与 K 线数量 ${bars.length} 不一致，已回退内置策略「高点回落移动止损（8%回撤）」`);
      } else {
        safeProgress(onProgress, { stage: 'signals', percent: 58, message: '自编卖出策略信号预计算完成' });
      }
    } catch (err) {
      customSellFailed = true;
      const msg = err instanceof Error ? err.message : String(err);
      warnings.push(`自编卖出策略执行失败，已回退内置策略「高点回落移动止损（8%回撤）」：${msg}`);
      diagnostics.push({
        time: new Date().toISOString().slice(0, 10),
        event: 'script_error',
        reason: `自编卖出策略执行失败：${msg}`,
        data: { strategyName: customSellStrategy.strategyName },
      });
    }
    if (customSellFailed) customSellSignals = null;
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

  // 预热段信号显式化（协作单 36.0）：用户起始日之前取数段（[firstValidIdx, startIdx)）的信号
  // 不进入交易区间、保持静默。该段信号本身合法（尤其当预热窗口偏短、EMA/ADX 未收敛时，
  // 得分可能与全历史口径不一致），显式记录而非静默丢弃，便于排查近起始日信号漏报问题。
  let leadingSignalCount = 0;
  let leadingEarliestTime = '';
  for (let j = firstValidIdx; j < startIdx && j < buySignals.length; j++) {
    if (buySignals[j]) {
      if (leadingSignalCount === 0) leadingEarliestTime = bars[j].time;
      leadingSignalCount++;
    }
  }
  if (leadingSignalCount > 0) {
    diagnostics.push({
      time: bars[Math.min(startIdx, bars.length - 1)].time,
      event: 'signal_before_range',
      reason: `"${getConditionName(buyCondition)}" 在用户起始日之前（预热段）命中 ${leadingSignalCount} 次，不参与成交`,
      data: { count: leadingSignalCount, earliest: leadingEarliestTime },
    });
    warnings.push(
      `${getConditionName(buyCondition)} 在起始日之前（预热段）命中 ${leadingSignalCount} 次（最早 ${leadingEarliestTime}），预热段信号不成交，仅提示。`,
    );
  }

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
  /**
   * 分层止盈状态机（仅 sellStrategy==='layered_take_profit' 时维护）。
   * 单仓模型：一次只持一个价位分组，分批卖出通过 shares 递减 + 状态 phase 推进实现。
   */
  let layeredTP: {
    phase: 'initial' | 'tp1_done' | 'tp2_done' | 'closed';
    groupId: number;         // 买入发生时的 bar index（用于聚合多次分批卖出）
    entryPrice: number;      // 原始买入价（成本，前复权）
    totalBuyShares: number;  // 原始买入总股数（分批比例基准）
    peakPrice: number;       // 持仓期间最高价（含当日）
    maBreakDays: number;     // 连续收盘跌破均线天数
    committedSellShares: number; // 当日已承诺卖出股数（同日 TP1+TP2 股数计算用）
  } | null = null;

  // 诊断计数器 + 结构化日志
  let buySignalCount = 0;
  let buyLimitDeferredCount = 0;
  let buyLimitExpiredCount = 0;
  let insufficientFundCount = 0;
  let unexecutedBuyCount = 0;
  let sellSignalCount = 0;
  let sellLimitDeferredCount = 0;
  let sellLimitExpiredCount = 0;
  /** 单仓持有期再触发买入信号（卖出后才重新进场），原先静默丢弃，现计数并写入诊断 */
  let holdingBuySkipCount = 0;

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
            // 分层止盈：初始化状态（groupId=买入 bar index，用于分批聚合）
            if (sellStrategy === 'layered_take_profit') {
              layeredTP = {
                phase: 'initial',
                groupId: i,
                entryPrice: execPrice,
                totalBuyShares: buyShares,
                peakPrice: execPrice,
                maBreakDays: 0,
                committedSellShares: 0,
              };
            }
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
              groupId: sellStrategy === 'layered_take_profit' ? i : undefined,
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
          groupId: sellStrategy === 'layered_take_profit' && layeredTP ? layeredTP.groupId : undefined,
        });
        shares = 0;
        state = 'closed';
        if (sellStrategy === 'layered_take_profit') layeredTP = null;
      }

      // ==================== 分层止盈：当日即时分批卖出（单仓，逐笔成交） ====================
      if (sellStrategy === 'layered_take_profit' && state === 'holding' && layeredTP) {

        const lp = layeredTPParams ?? DEFAULT_LAYERED_TP_PARAMS;
        const t = layeredTP;
        const holdDays = i - currentEntryIdx;

        // 更新持仓峰值（用当日最高价）
        if (bar.high > t.peakPrice) t.peakPrice = bar.high;
        // 当日已承诺卖出清零（同 bar 内 TP1+TP2 累加）
        t.committedSellShares = 0;

        // 收集当日卖出动作（支持同日 TP1+TP2 两笔部分卖出）
        const todayActions: { shares: number; price: number; reason: string }[] = [];
        // 当日已累计卖出股数（同 bar 内多次部分卖出累加，用于裁剪不超可卖）
        let todaySold = 0;
        // 统一入账：将卖出动作推入 todayActions，并用当日剩余可卖裁剪，推进今日累计卖出
        // 返回是否真的推入（requested>0 且剩余可卖>0）
        const pushSell = (requested: number, price: number, exitReason: string): boolean => {
          const cap = shares - todaySold;
          const n = Math.floor(Math.min(Math.max(requested, 0), cap) / LOT_SIZE) * LOT_SIZE;
          if (n <= 0) return false;
          todayActions.push({ shares: n, price, reason: exitReason });
          todaySold += n;
          return true;
        };

        // ---- 建仓期（initial）：初始止损 / 时间止损 ----
        // 注意：已废除「买入失效止损(不涨即走)」。突破策略常见回踩洗盘，早期微亏是健康信号，
        // 不应在第 3-5 天就把仓位震出局；纯以初始止损（跌破 entry×(1+initialStopLossPct)）逻辑证伪。
        if (t.phase === 'initial') {
          const stopPrice = t.entryPrice * (1 + lp.initialStopLossPct);
          // 1a 开盘跳空保护：开盘已破止损，以开盘价扣滑点成交
          if (bar.open <= stopPrice) {
            pushSell(shares, bar.open * (1 - lp.stopSlippagePct), '初始止损(开盘跳空)');
            t.phase = 'closed';
          }
          // 1b 盘中触及止损：以止损价扣滑点成交（最低不高于当日 low）
          else if (bar.low <= stopPrice) {
            pushSell(shares, Math.max(stopPrice * (1 - lp.stopSlippagePct), bar.low), '初始止损');
            t.phase = 'closed';
          }
          // 时间止损：建仓期持有天数达上限且未触发止盈（仅作为防死扛兜底）
          else if (holdDays >= lp.maxHoldDays) {
            pushSell(shares, bar.close, `时间止损(${lp.maxHoldDays}日)`);
            t.phase = 'closed';
          }
        }

        // ---- 第一止盈（TP1，仅 initial）：高价触及后卖 firstSellPct 比例 → tp1_done ----
        if (t.phase === 'initial') {
          const tp1Price = t.entryPrice * (1 + lp.firstProfitPct);
          if (bar.high >= tp1Price) {
            const sellShares = Math.floor((t.totalBuyShares * lp.firstSellPct) / LOT_SIZE) * LOT_SIZE;
            if (pushSell(sellShares, tp1Price, '第一止盈TP1(卖25%)')) {
              t.phase = 'tp1_done';
              t.committedSellShares = todaySold;
            }
          }
        }

        // ---- TP1 后：保本止损 + 第二止盈（TP2）+ 底仓主动离场保护 ----
        // 修复痛点：TP1 卖 25% 后，若价格既不涨到 TP2 又不跌破保本价、长期横盘，原逻辑会让
        // 剩余底仓无限期死扛到期末强制清仓。保护原则：TP2 优先分批卖出，仅在当日未触及 TP2
        // 时启用均线兜底离场，防止底仓死扛，同时不抢跑、不破坏正常分批流程。
        if (t.phase === 'tp1_done') {
          const bePrice = t.entryPrice * (1 + lp.breakevenStopPct);
          // 保本止损始终优先（防亏）：跌破成本即清剩余底仓
          if (bar.low <= bePrice) {
            pushSell(shares, Math.max(bePrice * (1 - lp.stopSlippagePct), bar.low), 'TP1后保本止损');
            t.phase = 'closed';
          } else if (todaySold < shares) {
            // 第二止盈（TP2）：优先推进分批。合计卖出 firstSellPct+secondSellPct，卖到目标比例
            const tp2Price = t.entryPrice * (1 + lp.secondProfitPct);
            if (bar.high >= tp2Price) {
              const targetTotal = Math.floor((t.totalBuyShares * (lp.firstSellPct + lp.secondSellPct)) / LOT_SIZE) * LOT_SIZE;
              // 全程已累计卖出 = 原始买入 - 当前剩余（跨 bar 也正确）
              const soldSoFar = t.totalBuyShares - shares;
              // TP2 本次应卖 = 目标累计量扣去已卖，再裁剪到当日可卖剩余
              const rounded = Math.min(Math.max(targetTotal - soldSoFar, 0), shares - todaySold);
              if (pushSell(rounded, tp2Price, '第二止盈TP2(卖30%)')) {
                t.phase = 'tp2_done';
                t.committedSellShares = soldSoFar + rounded;
              }
            } else {
              // 未触及 TP2：底仓主动离场保护。
              // 主导：从持仓期最高点回撤 baseTrailingPct（默认 8%）追踪止盈——给足爆发空间，
              //      又比 MA 等迟钝指标更能及时锁利，契合右侧突破策略。
              // 底线：跌回成本即走（用 breakeven 而非 tp2 后的 lockProfit，避免 TP1 当日振幅误清）。
              // 辅助：均线兜底（跌破 maPeriod 均线）作兜底。
              const trailingBase = Math.max(
                t.peakPrice * (1 - lp.baseTrailingPct),
                t.entryPrice * (1 + lp.breakevenStopPct),
              );
              const ma =
                lp.maPeriod === 5 ? cache.ma5[i] :
                lp.maPeriod === 10 ? cache.ma10[i] :
                lp.maPeriod === 60 ? cache.ma60[i] :
                cache.ma20[i];
              const canUseMa = ma !== null && Number.isFinite(ma);
              const dayDrop = canUseMa ? (bar.close - prevClose) / prevClose : 0;
              const isBelowMa = canUseMa ? bar.close < ma : false;
              const maBreakNow = canUseMa &&
                (dayDrop <= -lp.maExceptionDropPct
                  ? true
                  : (isBelowMa ? t.maBreakDays + 1 : 0) >= lp.maConfirmDays);

              if (bar.low <= trailingBase) {
                pushSell(shares, Math.max(trailingBase * (1 - lp.stopSlippagePct), bar.low), `TP1后回撤追踪(峰值${t.peakPrice.toFixed(2)})`);
                t.phase = 'closed';
              } else if (maBreakNow) {
                pushSell(shares, bar.close, dayDrop <= -lp.maExceptionDropPct ? 'TP1后单日暴跌清仓' : `TP1后跌破MA${lp.maPeriod}清仓`);
                t.phase = 'closed';
              } else if (canUseMa) {
                // 未触发离场：更新均线连续跌破计数（供下一日判定）
                if (isBelowMa || dayDrop <= -lp.maExceptionDropPct) t.maBreakDays += 1;
                else t.maBreakDays = 0;
              }
            }
          }
        }

        // ---- TP2 后三重保护（锁定利润+峰值回撤 / 硬底线 / 均线兜底）----
        if (t.phase === 'tp2_done') {
          const lockPrice = t.entryPrice * (1 + lp.lockProfitPct);
          const trailingPrice = t.peakPrice * (1 - lp.trailingDrawdownPct);
          const dynamicStop = Math.max(lockPrice, trailingPrice);
          if (bar.low <= dynamicStop) {
            pushSell(shares, Math.max(dynamicStop * (1 - lp.stopSlippagePct), bar.low), `跟踪止盈(峰值${t.peakPrice.toFixed(2)})`);
            t.phase = 'closed';
          } else {
            const hardFloor = t.entryPrice * (1 + lp.hardFloorPct);
            if (bar.low <= hardFloor) {
              pushSell(shares, Math.max(hardFloor * (1 - lp.stopSlippagePct), bar.low), '硬底线止损');
              t.phase = 'closed';
            } else {
              // 均线兜底（连续跌破确认 / 单日暴跌例外）
              const ma =
                lp.maPeriod === 5 ? cache.ma5[i] :
                lp.maPeriod === 10 ? cache.ma10[i] :
                lp.maPeriod === 60 ? cache.ma60[i] :
                cache.ma20[i];
              if (ma !== null && Number.isFinite(ma)) {
                const dayDrop = (bar.close - prevClose) / prevClose;
                if (dayDrop <= -lp.maExceptionDropPct) {
                  pushSell(shares, bar.close, '单日暴跌例外清仓');
                  t.phase = 'closed';
                } else {
                  if (bar.close < ma) t.maBreakDays += 1;
                  else t.maBreakDays = 0;
                  if (t.maBreakDays >= lp.maConfirmDays) {
                    pushSell(shares, bar.close, `跌破MA${lp.maPeriod}清仓`);
                    t.phase = 'closed';
                  }
                }
              }
            }
          }
        }

        // ---- 执行当日卖出动作（逐笔成交，支持部分递减）----
        for (const a of todayActions) {
          if (a.shares <= 0 || shares < a.shares) continue;
          const execPrice = a.price;
          const sellProceeds = execPrice * a.shares * (1 - feeRate);
          const buyCost = currentEntryPrice * a.shares * (1 + feeRate);
          const actualProfit = sellProceeds - buyCost;
          cash += sellProceeds;
          diagnostics.push({
            time: bar.time,
            event: 'sell_executed',
            reason: `${a.reason}，卖出 ${a.shares} 股 @ ${execPrice}`,
            data: { shares: a.shares, price: execPrice, profit: actualProfit },
          });
          trades.push({
            id: tradeId++,
            direction: 'sell',
            entryTime: bars[currentEntryIdx].time,
            exitTime: bar.time,
            entryPrice: currentEntryPrice,
            exitPrice: execPrice,
            shares: a.shares,
            profit: actualProfit,
            profitPct: (actualProfit / capital) * 100,
            holdDays: i - currentEntryIdx - 1,
            isForcedClose: false,
            entryReason: buildEntryReason(buyCondition),
            exitReason: a.reason,
            groupId: t.groupId,
          });
          shares -= a.shares;
          if (shares === 0) {
            state = 'idle';
            layeredTP = null;
          }
        }
      }

      // --- 信号检测 ---
      if (buySignals[i]) {
        if (state === 'idle' && pendingBuySignal === null) {
          buySignalCount++;
          diagnostics.push({
            time: bar.time,
            event: 'buy_signal',
            reason: `"${getConditionName(buyCondition)}" 发出买入信号`,
            data: { indicatorName: getConditionName(buyCondition) },
          });
          pendingBuySignal = { idx: i, deferCount: 0 };
        } else if (state === 'holding') {
          // 单仓持有期：卖出后才重新进场，命中信号不静默丢弃 → 写入诊断
          holdingBuySkipCount++;
          diagnostics.push({
            time: bar.time,
            event: 'buy_signal_holding_skip',
            reason: `单仓持有期 "${getConditionName(buyCondition)}" 再触发买入信号，卖出后才重新进场，本次跳过`,
            data: { indicatorName: getConditionName(buyCondition) },
          });
        }
      }

      if (sellStrategy !== 'layered_take_profit' && state === 'holding' && pendingSellSignal === null) {
        if (customSellSignals !== null && !customSellFailed && i < customSellSignals.length) {
          // 自编卖出策略（纯信号协议）：持仓状态下消费预计算信号，不依赖 peak/entry 上下文
          if (customSellSignals[i]) {
            sellSignalCount++;
            diagnostics.push({
              time: bar.time,
              event: 'sell_signal',
              reason: `"${customSellStrategy?.strategyName}" 发出卖出信号`,
            });
            pendingSellSignal = { idx: i, deferCount: 0 };
          }
        } else {
          // 内置卖出策略（或自编失败回退内置）
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
      groupId: sellStrategy === 'layered_take_profit' && layeredTP ? layeredTP.groupId : undefined,
    });
    shares = 0;
    if (sellStrategy === 'layered_take_profit') layeredTP = null;
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
      `因买入条件确认/阈值判定共触发 ${buySignalCount} 次买入信号，` +
      `其中持有期跳过（卖出后重新进场）${holdingBuySkipCount} 次，` +
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

/**
 * 把卖出交易聚合法为若干"完整交易（Round Trip）"。
 * - 分层止盈等一次建仓分多批卖出的（同 groupId）合并为一条：总盈亏 = Σ各笔profit，持有天数 = 末次卖出最长，股数 = Σ
 * - 无 groupId 的普通交易各自独立为一条
 * 返回数组用于计算 winRate / 连亏 / 平均持有等全局指标（不破坏底层 Trade 明细展示）。
 */
export function aggregateTradesByGroupId(trades: Trade[]): { profit: number; holdDays: number; shares: number }[] {
  const byGroup = new Map<string | number, { profit: number; holdDays: number; shares: number }>();
  const order: (string | number)[] = [];
  for (const t of trades) {
    const key = t.groupId !== undefined ? t.groupId : `__ind_${t.id}`;
    if (!byGroup.has(key)) {
      byGroup.set(key, { profit: 0, holdDays: 0, shares: 0 });
      order.push(key);
    }
    const g = byGroup.get(key)!;
    g.profit += t.profit;
    g.shares += t.shares;
    if (t.holdDays > g.holdDays) g.holdDays = t.holdDays;
  }
  return order.map((k) => byGroup.get(k)!);
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

  // 聚合同一建仓（groupId）的多次分批卖出为一次完整交易，避免拆散胜负/连亏/持有统计
  const closedTrades = aggregateTradesByGroupId(trades.filter((t) => t.direction === 'sell'));
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
