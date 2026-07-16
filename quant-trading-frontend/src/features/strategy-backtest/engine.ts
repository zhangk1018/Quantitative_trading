// src/features/strategy-backtest/engine.ts
// 策略回测引擎核心 | 迁移自 features/backtest/strategyBacktestEngine.ts

import {
  sma,
  ema,
  calcRSI,
  sampleStdDev,
} from '../../lib/indicators/indicators';
import type {
  StrategyBacktestDefaults,
  FilterNode,
  OhlcvBar,
  StockSnapshot,
  Position,
  Trade,
  EquityPoint,
  StrategyBacktestResult,
  StrategyMetrics,
  SellReason,
  RangeField,
  TechPattern,
} from './types';
import { IndicatorCache } from './types';
import { runTonghuashun6Strategy } from '../backtest/strategies/tonghuashun6Strategy';

// ==================== 常量定义 ====================

const TRADING_DAYS_PER_YEAR = 252;
const LOT_SIZE = 100; // A股最小交易单位
/** P1-2: 兜底交易日历构建时的市值阈值（亿元），仅用于无后端交易日历时的降级方案 */
const FALLBACK_MARKET_CAP_THRESHOLD = 100;

/** OHLCV 数组索引常量（后端返回 number[]） */
const OHLCV_TS = 0;
const OHLCV_OPEN = 1;
const OHLCV_HIGH = 2;
const OHLCV_LOW = 3;
const OHLCV_CLOSE = 4;
const OHLCV_VOLUME = 5;
const OHLCV_PRE_CLOSE = 6;

// ==================== 进度回调类型 ====================

export interface ProgressInfo {
  stage: 'data' | 'indicators' | 'simulation' | 'done';
  percent: number;
  message: string;
}

// ==================== 交易指令队列（T+1 执行） ====================

interface PendingOrder {
  code: string;
  action: 'buy' | 'sell';
  signalDate: string;       // 信号生成日（T日）
  executionDate: string;    // 执行日（T+1日）
  /** 买入权重比例（0~1），执行时按当天现金 × weight 计算目标金额 */
  weight?: number;
  shares?: number;          // 卖出股数（可选，执行时确定）
  sellReason?: SellReason;  // 卖出原因（仅卖出指令）
  deferCount: number;       // 顺延次数
}

// ==================== 输入数据结构 ====================

export interface StrategyBacktestInput {
  /** 全市场 OHLCV 数据：Map<股票代码, number[][]> */
  allOhlcv: Map<string, number[][]>;
  /** 股票快照（含 is_st, listed_board 等） */
  snapshots: Map<string, StockSnapshot>;
  /** 选股条件 AST（仅 filterTree 策略使用） */
  filterTree?: FilterNode;
  /** 策略类型 */
  strategyType?: 'filterTree' | 'tonghuashun6' | 'filterTreeLayeredTP';
  /** 退出模式（仅 filterTree 策略使用） */
  exitMode?: 'standard' | 'layeredTakeProfit';
  /** 分层止盈参数（仅 exitMode='layeredTakeProfit' 时使用） */
  layeredTPParams?: {
    minHoldDays: number;
    maxDrawdown: number;
    firstProfitTarget: number;
    secondProfitTarget: number;
    fullProfitTarget: number;
    rsiHigh: number;
  };
  /** 同花顺6重买入策略参数（仅 tonghuashun6 策略使用） */
  tonghuashun6Params?: import('../backtest/strategies/tonghuashun6Strategy').Tonghuashun6Params;
  /** 回测配置 */
  config: StrategyBacktestDefaults;
  /** 回测起止日期 YYYY-MM-DD */
  startDate: string;
  endDate: string;
  /** 基准指数 OHLCV（可选，用于 Alpha/Beta 计算） */
  benchmarkOhlcv?: number[][];
  /** 交易日历（可选，后端提供则直接使用） */
  tradeDates?: string[];
  /** 进度回调 */
  onProgress?: (info: ProgressInfo) => void;
  /** 选股条件中剥离的非标准字段名列表（用于审计日志） */
  strippedFields?: string[];
  /** 自编指标预计算值: Map<scriptId, Map<stockCode, values[]>> */
  customIndicatorValues?: Map<string, Map<string, (number | null)[]>>;
}

// ==================== 辅助函数 ====================

/**
 * 获取涨跌停幅度（基于板块和 ST 状态）
 * @param listedBoard 板块：'main', 'gem'(创业板), 'star'(科创板), 'beijing'(北交所)
 * @param isSt 是否 ST 股
 */
export function getLimitPct(listedBoard: string, isSt: boolean): number {
  if (isSt) return 0.05;
  if (listedBoard === 'gem' || listedBoard === 'star') return 0.20;
  if (listedBoard === 'beijing') return 0.30;
  return 0.10;
}

/**
 * 停牌判定（修正版，排除一字涨跌停）
 * @param bar OHLCV 数组
 * @param preClose 昨收价（前复权）
 * @param limitPct 涨跌停幅度
 */
/**
 * 检查是否停牌（含一字板判定）
 * 使用整数分比较避免浮点误差
 */
export function isSuspended(bar: number[], preClose: number, limitPct: number): boolean {
  const volume = bar[OHLCV_VOLUME];
  const open = bar[OHLCV_OPEN];
  const high = bar[OHLCV_HIGH];
  const low = bar[OHLCV_LOW];
  const close = bar[OHLCV_CLOSE];

  // 条件1：成交量必须为0
  if (volume !== 0) return false;
  // 条件2：价格区间为0（开盘=最高=最低=收盘）
  if (open !== high || high !== low || low !== close) return false;
  // 条件3：检查是否一字板（无量涨停/跌停），使用整数分比较
  const preCloseCents = Math.round(preClose * 100);
  const closeCents = Math.round(close * 100);
  // P2-2.2: 优化浮点乘法精度，先计算 limitPct 部分再与 preCloseCents 相加
  const upLimitCents = preCloseCents + Math.round(preCloseCents * limitPct);
  const downLimitCents = preCloseCents - Math.round(preCloseCents * limitPct);
  if (closeCents >= upLimitCents) return false;   // 一字涨停
  if (closeCents <= downLimitCents) return false;  // 一字跌停
  return true;
}

/**
 * 检查是否涨停封板（买入方向）
 * 一字板检测：open=high=low=close 全部达到涨停价，表示全天封死无法买入
 * 若盘中打开涨停（如 open < upLimit 但 close == upLimit），存在成交机会，判定为可买入
 * 使用整数分比较避免浮点误差，引入 1 分钱容差消除浮点取整误差
 */
export function isLimitUp(bar: number[], preClose: number, limitPct: number): boolean {
  const open = bar[OHLCV_OPEN];
  const high = bar[OHLCV_HIGH];
  const low = bar[OHLCV_LOW];
  const close = bar[OHLCV_CLOSE];
  const preCloseCents = Math.round(preClose * 100);
  const upLimitCents = preCloseCents + Math.round(preCloseCents * limitPct);
  // 一字板：所有价格均达到涨停价，全天无成交机会
  // 容差 1 分钱：消除浮点取整误差（如 9.995 元取整后为 999 分，实际应为 1000 分）
  const openCents = Math.round(open * 100);
  const highCents = Math.round(high * 100);
  const lowCents = Math.round(low * 100);
  const closeCents = Math.round(close * 100);
  return (openCents + 1) >= upLimitCents
    && (highCents + 1) >= upLimitCents
    && (lowCents + 1) >= upLimitCents
    && (closeCents + 1) >= upLimitCents;
}

/**
 * 检查是否跌停封板（卖出方向）
 * 一字板检测：open=high=low=close 全部达到跌停价，表示全天封死无法卖出
 * 若盘中打开跌停（如 open > downLimit 但 close == downLimit），存在成交机会，判定为可卖出
 * 使用整数分比较避免浮点误差，引入 1 分钱容差消除浮点取整误差
 */
export function isLimitDown(bar: number[], preClose: number, limitPct: number): boolean {
  const open = bar[OHLCV_OPEN];
  const high = bar[OHLCV_HIGH];
  const low = bar[OHLCV_LOW];
  const close = bar[OHLCV_CLOSE];
  const preCloseCents = Math.round(preClose * 100);
  const downLimitCents = preCloseCents - Math.round(preCloseCents * limitPct);
  // 一字板：所有价格均达到跌停价，全天无成交机会
  // 容差 1 分钱：消除浮点取整误差
  const openCents = Math.round(open * 100);
  const highCents = Math.round(high * 100);
  const lowCents = Math.round(low * 100);
  const closeCents = Math.round(close * 100);
  return (openCents - 1) <= downLimitCents
    && (highCents - 1) <= downLimitCents
    && (lowCents - 1) <= downLimitCents
    && (closeCents - 1) <= downLimitCents;
}

/**
 * 解析时间戳为 YYYY-MM-DD 格式字符串
 * 支持三种格式（按优先级判定）：
 * 1. 毫秒级 Unix 时间戳（> 1e11，对应 1973-03-03+，覆盖 1990 年上交所开市以来的全部数据）
 * 2. 秒级 Unix 时间戳（1e9 ~ 1e10，对应 2001-09-09 到 2286-11-20）
 * 3. YYYYMMDD 数字格式（1990-01-01 ~ 2099-12-31，兜底解析）
 *
 * 判定顺序：毫秒级 > 秒级 > YYYYMMDD，避免误判
 * 注意：阈值 1e11 意味着 2000-01-01 的毫秒级时间戳（9.47e11）被正确识别为毫秒级，
 * 而非被误判为秒级（9.47e11 秒 ≈ 30000 年，超出合理范围）。
 *
 * @param ts 时间戳
 * @returns YYYY-MM-DD 格式字符串
 */
function parseTimestamp(ts: number): string {
  // 毫秒级时间戳（> 1e11，对应 1973-03-03+，覆盖 1990 年上交所开市以来的全部数据）
  if (ts > 1e11) {
    const date = new Date(ts);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
  // 秒级时间戳（1e9 ~ 1e10，对应 2001-09-09 ~ 2286-11-20）
  if (ts > 1e9 && ts < 1e10) {
    const date = new Date(ts * 1000);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
  // YYYYMMDD 格式（1990-01-01 ~ 2099-12-31，兜底解析）
  const year = Math.floor(ts / 10000);
  const month = Math.floor((ts % 10000) / 100);
  const day = ts % 100;
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * 构建交易日历
 * 优先使用后端提供的 tradeDates，否则取大市值股票的日期并集
 */
export function buildTradeDates(
  allOhlcv: Map<string, number[][]>,
  snapshots: Map<string, StockSnapshot>,
  providedTradeDates?: string[]
): string[] {
  // 优先：后端提供的交易日历
  if (providedTradeDates && providedTradeDates.length > 0) {
    return providedTradeDates.sort();
  }

  // 兜底：取沪深主板大市值股票的 OHLCV 日期并集
  const dateSet = new Set<string>();
  for (const [code, bars] of allOhlcv) {
    const snapshot = snapshots.get(code);
    if (!snapshot) continue;
    // 只取沪深主板（60/00开头）且市值 > FALLBACK_MARKET_CAP_THRESHOLD 的股票
    if (snapshot.listedBoard !== 'main') continue;
    if (snapshot.marketCap < FALLBACK_MARKET_CAP_THRESHOLD) continue;

    for (const bar of bars) {
      const ts = bar[OHLCV_TS];
      const dateStr = parseTimestamp(ts);
      dateSet.add(dateStr);
    }
  }

  return Array.from(dateSet).sort();
}

/**
 * 计算单只股票的技术指标缓存
 */
export function computeIndicatorCache(bars: number[][], warmupDays: number): IndicatorCache {
  const n = bars.length;
  const cache = new IndicatorCache(n);

  if (n === 0) return cache;

  // 提取价格序列
  const closes = bars.map(b => b[OHLCV_CLOSE]);
  const volumes = bars.map(b => b[OHLCV_VOLUME]);

  // MA 系列
  const ma5 = sma(closes, 5);
  const ma10 = sma(closes, 10);
  const ma20 = sma(closes, 20);
  const ma60 = sma(closes, 60);

  for (let i = 0; i < n; i++) {
    if (ma5[i] !== null) { cache.ma5[i] = ma5[i]!; cache.setReady('ma5', i); }
    if (ma10[i] !== null) { cache.ma10[i] = ma10[i]!; cache.setReady('ma10', i); }
    if (ma20[i] !== null) { cache.ma20[i] = ma20[i]!; cache.setReady('ma20', i); }
    if (ma60[i] !== null) { cache.ma60[i] = ma60[i]!; cache.setReady('ma60', i); }
  }

  // MACD (12, 26, 9)
  const ema12 = ema(closes as (number | null)[], 12);
  const ema26 = ema(closes as (number | null)[], 26);
  const difRaw: (number | null)[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (ema12[i] !== null && ema26[i] !== null) {
      difRaw[i] = ema12[i]! - ema26[i]!;
    }
  }
  const dea = ema(difRaw, 9);
  for (let i = 0; i < n; i++) {
    if (difRaw[i] !== null) { cache.macdDif[i] = difRaw[i]!; cache.setReady('macdDif', i); }
    if (dea[i] !== null) { cache.macdDea[i] = dea[i]!; cache.setReady('macdDea', i); }
    if (difRaw[i] !== null && dea[i] !== null) {
      cache.macdHist[i] = 2 * (difRaw[i]! - dea[i]!);
      cache.setReady('macdHist', i);
    }
  }

  // RSI (6, 12, 24)
  const rsi6 = calcRSI(closes, 6);
  const rsi12 = calcRSI(closes, 12);
  const rsi24 = calcRSI(closes, 24);
  for (let i = 0; i < n; i++) {
    if (rsi6[i] !== null) { cache.rsi6[i] = rsi6[i]!; cache.setReady('rsi6', i); }
    if (rsi12[i] !== null) { cache.rsi12[i] = rsi12[i]!; cache.setReady('rsi12', i); }
    if (rsi24[i] !== null) { cache.rsi24[i] = rsi24[i]!; cache.setReady('rsi24', i); }
  }

  // BOLL (20, 2)
  const ma20Boll = sma(closes, 20);
  const std20 = sampleStdDev(closes, 20);
  for (let i = 0; i < n; i++) {
    if (ma20Boll[i] !== null && std20[i] !== null) {
      cache.bollMid[i] = ma20Boll[i]!;
      cache.bollUpper[i] = ma20Boll[i]! + 2 * std20[i]!;
      cache.bollLower[i] = ma20Boll[i]! - 2 * std20[i]!;
      cache.setReady('bollMid', i);
      cache.setReady('bollUpper', i);
      cache.setReady('bollLower', i);
    }
  }

  // 量比（5日）
  const volMa5 = sma(volumes, 5);
  for (let i = 0; i < n; i++) {
    if (volMa5[i] !== null && volMa5[i]! > 0) {
      cache.volRatio5[i] = volumes[i] / volMa5[i]!;
      cache.setReady('volRatio5', i);
    }
  }

  return cache;
}

// ==================== AST 条件评估器（含 NaN 阻断） ====================

/**
 * 获取字段值（用于 range 类型过滤器）
 * NaN/undefined 直接返回 null，触发阻断
 */
function getFieldValue(
  field: RangeField,
  snapshot: StockSnapshot,
  bars: number[][],
  cache: IndicatorCache,
  idx: number
): number | null {
  switch (field) {
    case 'market_cap':
      return snapshot.marketCap;
    case 'close':
      return bars[idx]?.[OHLCV_CLOSE] ?? null;
    case 'change_pct': {
      if (idx < 1) return null;
      const prevClose = bars[idx - 1]?.[OHLCV_CLOSE];
      const currClose = bars[idx]?.[OHLCV_CLOSE];
      if (!prevClose || !currClose) return null;
      return (currClose / prevClose - 1) * 100;
    }
    case 'pe':
      return snapshot.pe;
    case 'pe_ttm':
      return snapshot.peTtm;
    case 'pb':
      return snapshot.pb;
    case 'turnover_rate':
      return snapshot.turnoverRate;
    case 'vol_ratio_5':
      return cache.getVolRatio5(idx);
    default:
      return null;
  }
}

/**
 * 检查技术形态（Phase 1 支持 4 种基础形态）
 * @param bars OHLCV 数组，用于获取 close 等价格数据
 */
function checkThs6BuySignal(
  bars: number[][],
  idx: number,
): boolean {
  if (idx < 1 || idx >= bars.length) return false;

  const closes = bars.map(b => b[OHLCV_CLOSE]);
  const highs = bars.map(b => b[OHLCV_HIGH]);
  const volumes = bars.map(b => b[OHLCV_VOLUME]);

  // 计算 EMA5、EMA48
  const ema5Arr = ema(closes, 5);
  const ema48Arr = ema(closes, 48);
  if (ema5Arr[idx] === null || ema48Arr[idx] === null) return false;

  // 计算 MACD (12, 26, 9)
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdDif: (number | null)[] = new Array(bars.length).fill(null);
  for (let i = 0; i < bars.length; i++) {
    if (ema12[i] !== null && ema26[i] !== null) {
      macdDif[i] = ema12[i]! - ema26[i]!;
    }
  }
  const macdDea = ema(macdDif, 9);
  const macdHist: (number | null)[] = new Array(bars.length).fill(null);
  for (let i = 0; i < bars.length; i++) {
    if (macdDif[i] !== null && macdDea[i] !== null) {
      macdHist[i] = (macdDif[i]! - macdDea[i]!) * 2;
    }
  }
  if (macdDif[idx] === null || macdDea[idx] === null || macdHist[idx] === null) return false;

  // 计算 RSI14
  const rsi14 = calcRSI(closes, 14);
  if (rsi14[idx] === null) return false;

  // 计算 SMA(volume, 15)
  const volAvg15 = sma(volumes, 15);
  if (volAvg15[idx] === null || volAvg15[idx]! <= 0) return false;

  // 计算 HHV20（20 日最高价）
  let hhv20 = highs[idx];
  for (let j = Math.max(0, idx - 19); j <= idx; j++) {
    if (highs[j] > hhv20) hhv20 = highs[j];
  }

  const close = bars[idx][OHLCV_CLOSE];
  const volume = bars[idx][OHLCV_VOLUME];

  // 6 重条件判断
  const trendUp = ema5Arr[idx]! > ema48Arr[idx]!;
  const macdGold = macdDif[idx]! > macdDea[idx]! && macdHist[idx]! > 0;
  const rsiValid = rsi14[idx]! > 25 && rsi14[idx]! < 70;
  const volUp = volume > 1.05 * volAvg15[idx]!;
  const priceBreak = close >= hhv20 * 0.98;

  const buyCond = trendUp && macdGold && rsiValid && volUp && priceBreak;
  if (!buyCond) return false;

  // CROSS 检查：前一日不满足
  if (idx - 1 < 0) return true;
  const prevClose = bars[idx - 1][OHLCV_CLOSE];
  const prevVol = bars[idx - 1][OHLCV_VOLUME];
  const prevEma5 = ema5Arr[idx - 1];
  const prevEma48 = ema48Arr[idx - 1];
  const prevMacdDif = macdDif[idx - 1];
  const prevMacdDea = macdDea[idx - 1];
  const prevMacdHist = macdHist[idx - 1];
  const prevRsi14 = rsi14[idx - 1];
  const prevVolAvg15 = volAvg15[idx - 1];

  // 计算前一日 HHV20
  let prevHhv20 = highs[idx - 1];
  for (let j = Math.max(0, idx - 20); j <= idx - 1; j++) {
    if (highs[j] > prevHhv20) prevHhv20 = highs[j];
  }

  const prevTrendUp = prevEma5 !== null && prevEma48 !== null && prevEma5! > prevEma48!;
  const prevMacdGold = prevMacdDif !== null && prevMacdDea !== null && prevMacdHist !== null
    && prevMacdDif! > prevMacdDea! && prevMacdHist! > 0;
  const prevRsiValid = prevRsi14 !== null && prevRsi14! > 25 && prevRsi14! < 70;
  const prevVolUp = prevVolAvg15 !== null && prevVolAvg15! > 0
    && prevVol > 1.05 * prevVolAvg15!;
  const prevPriceBreak = prevClose >= prevHhv20 * 0.98;
  const prevBuyCond = prevTrendUp && prevMacdGold && prevRsiValid && prevVolUp && prevPriceBreak;

  return !prevBuyCond; // CROSS: 从 false 到 true
}

function checkTechPattern(
  pattern: TechPattern,
  cache: IndicatorCache,
  bars: number[][],
  idx: number
): boolean {
  if (idx < 1 || idx >= bars.length) return false;

  switch (pattern) {
    case 'ma_bullish': {
      // MA5 > MA10 > MA20 多头排列
      const ma5 = cache.getMA(5, idx);
      const ma10 = cache.getMA(10, idx);
      const ma20 = cache.getMA(20, idx);
      if (ma5 === null || ma10 === null || ma20 === null) return false;
      return ma5 > ma10 && ma10 > ma20;
    }
    case 'macd_golden_cross': {
      // MACD 金叉：DIF 上穿 DEA
      const prevDif = cache.getMACD('dif', idx - 1);
      const prevDea = cache.getMACD('dea', idx - 1);
      const currDif = cache.getMACD('dif', idx);
      const currDea = cache.getMACD('dea', idx);
      if (prevDif === null || prevDea === null || currDif === null || currDea === null) return false;
      return prevDif <= prevDea && currDif > currDea;
    }
    case 'rsi_golden_cross': {
      // RSI6 上穿 RSI12
      const prevRsi6 = cache.getRSI(6, idx - 1);
      const prevRsi12 = cache.getRSI(12, idx - 1);
      const currRsi6 = cache.getRSI(6, idx);
      const currRsi12 = cache.getRSI(12, idx);
      if (prevRsi6 === null || prevRsi12 === null || currRsi6 === null || currRsi12 === null) return false;
      return prevRsi6 <= prevRsi12 && currRsi6 > currRsi12;
    }
    case 'boll_break_upper': {
      // 收盘价突破布林上轨：close > bollUpper 且前一日 close <= bollUpper
      const close = bars[idx][OHLCV_CLOSE];
      const prevClose = bars[idx - 1][OHLCV_CLOSE];
      const upper = cache.getBOLL('upper', idx);
      const prevUpper = cache.getBOLL('upper', idx - 1);
      if (upper === null || prevUpper === null) return false;
      if (Number.isNaN(close) || Number.isNaN(prevClose)) return false;
      return prevClose <= prevUpper && close > upper;
    }
    case 'ths_6_buy_signal':
      return checkThs6BuySignal(bars, idx);
    default:
      return false;
  }
}

/**
 * AST 过滤器评估（含 NaN 硬阻断）
 */
export function evaluateFilter(
  node: FilterNode,
  snapshot: StockSnapshot,
  bars: number[][],
  cache: IndicatorCache,
  idx: number,
  /** 自编指标预计算值: Map<scriptId, Map<stockCode, values[]>> */
  customIndicatorValues?: Map<string, Map<string, (number | null)[]>>,
): boolean {
  switch (node.type) {
    case 'and':
      return node.children.every(c => evaluateFilter(c, snapshot, bars, cache, idx, customIndicatorValues));
    case 'or':
      return node.children.some(c => evaluateFilter(c, snapshot, bars, cache, idx, customIndicatorValues));
    case 'not': {
      const childResult = evaluateFilter(node.child, snapshot, bars, cache, idx, customIndicatorValues);
      if (childResult === null || childResult === undefined) {
        return false;
      }
      return !childResult;
    }
    case 'range': {
      const val = getFieldValue(node.field, snapshot, bars, cache, idx);
      if (val === null || val === undefined || Number.isNaN(val)) return false;
      const meetsMin = node.min === undefined || val >= node.min;
      const meetsMax = node.max === undefined || val <= node.max;
      return meetsMin && meetsMax;
    }
    case 'pattern': {
      return checkTechPattern(node.pattern, cache, bars, idx);
    }
    case 'kline': {
      return false;
    }
    case 'market': {
      const boards = node.boards ?? [];
      if (node.watchlistOnly) return false;
      if (boards.length === 0) return true;
      return boards.includes(snapshot.listedBoard);
    }
    case 'custom_indicator': {
      if (!customIndicatorValues) return false;
      const scriptValues = customIndicatorValues.get(node.scriptId);
      if (!scriptValues) return false;
      const stockValues = scriptValues.get(snapshot.code);
      if (!stockValues || idx >= stockValues.length) return false;
      const val = stockValues[idx];
      if (val === null || val === undefined || Number.isNaN(val)) return false;
      const meetsMin = node.min === undefined || val >= node.min;
      const meetsMax = node.max === undefined || val <= node.max;
      return meetsMin && meetsMax;
    }
    default:
      return false;
  }
}

// ==================== 仓位计算 ====================

/**
 * 计算等权分配下的目标持仓
 * @param totalEquityFen 总资产（分）
 * @param maxPositions 最大持仓数
 * @param singleStockMaxPct 单股最大仓位比例（1.0=不限制）
 * @returns 每只股票的目标权重（0~1）
 */
export function calcEqualWeight(
  maxPositions: number,
  singleStockMaxPct: number
): { weight: number; cashDragWarning: boolean } {
  const equalWeight = 1 / maxPositions;
  const targetWeight = Math.min(equalWeight, singleStockMaxPct);
  const cashDragWarning = equalWeight > singleStockMaxPct;
  return { weight: targetWeight, cashDragWarning };
}

/**
 * 计算买入股数（100股整数倍，纳入手续费计算）
 * @param targetAmountFen 目标金额（分）
 * @param priceYuan 股价（元/股，复权）
 * @param feeRate 手续费率
 * @param slippage 滑点率
 * @param minCommissionFen 最低佣金（分）
 * @returns 买入股数
 */
export function calcSharesToBuy(
  targetAmountFen: number,
  priceYuan: number,
  feeRate: number,
  slippage: number,
  minCommissionFen: number
): number {
  // 估算总成本比例（手续费 + 滑点）
  const costRate = feeRate + slippage;

  // 可用金额 = 目标金额 / (1 + costRate)，预留手续费空间
  const availableAmountFen = targetAmountFen / (1 + costRate);
  const availableAmountYuan = availableAmountFen / 100;

  // 计算最大可买股数（100股整数倍）
  const maxShares = Math.floor(availableAmountYuan / priceYuan / LOT_SIZE) * LOT_SIZE;
  if (maxShares <= 0) return 0;

  // P0-2.4: 循环递减验证，确保实际买入金额 + 手续费 <= 预算
  // 从 maxShares 开始递减，每次减少 LOT_SIZE，直到预算满足或股数为 0
  const maxIterations = Math.min(Math.floor(maxShares / LOT_SIZE), 50); // 最多 50 次迭代保护
  let shares = maxShares;
  for (let iter = 0; iter < maxIterations; iter++) {
    const buyAmountFen = shares * priceYuan * 100;
    const commission = calcBuyCommission(buyAmountFen, feeRate, slippage, minCommissionFen);
    if (buyAmountFen + commission <= targetAmountFen) {
      return shares;
    }
    shares -= LOT_SIZE;
  }
  return 0;
}

// ==================== 交易成本计算 ====================

/**
 * 计算买入交易成本（分）
 */
export function calcBuyCommission(
  amountFen: number,
  feeRate: number,
  slippage: number,
  minCommissionFen: number
): number {
  const commission = Math.max(amountFen * feeRate, minCommissionFen);
  const slippageCost = amountFen * slippage;
  return Math.round(commission + slippageCost);
}

/**
 * 计算卖出交易成本（分）
 */
export function calcSellCommission(
  amountFen: number,
  feeRate: number,
  slippage: number,
  stampDuty: number,
  minCommissionFen: number
): number {
  const commission = Math.max(amountFen * feeRate, minCommissionFen);
  const slippageCost = amountFen * slippage;
  const stampDutyCost = amountFen * stampDuty;
  return Math.round(commission + slippageCost + stampDutyCost);
}

// ==================== 主引擎（骨架） ====================

/**
 * 运行策略回测
 * 主循环：预计算指标 → 逐日模拟交易
 */
export function runStrategyBacktest(input: StrategyBacktestInput): StrategyBacktestResult {
  // 策略类型分发
  if (input.strategyType === 'tonghuashun6') {
    return runTonghuashun6Strategy({
      allOhlcv: input.allOhlcv,
      snapshots: input.snapshots,
      config: input.config,
      startDate: input.startDate,
      endDate: input.endDate,
      benchmarkOhlcv: input.benchmarkOhlcv,
      tradeDates: input.tradeDates,
      onProgress: input.onProgress,
      params: input.tonghuashun6Params,
    });
  }

  const startTime = performance.now();
  const { allOhlcv, snapshots, filterTree, config, startDate, endDate, benchmarkOhlcv, tradeDates, strippedFields, exitMode, layeredTPParams, customIndicatorValues } = input;
  const warnings: string[] = [];

  // P1-1.1: 将剥离的非标准字段名写入回测警告，提升用户透明度
  if (strippedFields && strippedFields.length > 0) {
    warnings.push(`选股条件中包含 ${strippedFields.length} 个非标准字段（系统设置参数），已自动忽略: ${strippedFields.join(', ')}`);
  }

  // P0-2: onProgress 空值保护，提供安全的默认实现
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
  const indicatorCaches = new Map<string, IndicatorCache>();
  const stockBars = new Map<string, number[][]>();
  // P1-4: 构建日期→索引映射表，消除 findIndex O(n) 查找
  const stockDateIndexMap = new Map<string, Map<string, number>>();

  let processed = 0;
  const totalStocks = allOhlcv.size;
  for (const [code, bars] of allOhlcv) {
    // 过滤出回测区间前的数据（含预热期）
    const warmupStart = Math.max(0, startIdx - config.warmupDays);
    const filteredBars = bars.filter(bar => {
      const ts = bar[OHLCV_TS];
      const dateStr = parseTimestamp(ts);
      const idx = allTradeDates.indexOf(dateStr);
      return idx >= warmupStart && idx <= actualEndIdx;
    });

    if (filteredBars.length > 0) {
      stockBars.set(code, filteredBars);
      const cache = computeIndicatorCache(filteredBars, config.warmupDays);
      indicatorCaches.set(code, cache);

      // P1-4: 构建日期→索引映射
      const dateIndexMap = new Map<string, number>();
      for (let i = 0; i < filteredBars.length; i++) {
        const dateStr = parseTimestamp(filteredBars[i][OHLCV_TS]);
        dateIndexMap.set(dateStr, i);
      }
      stockDateIndexMap.set(code, dateIndexMap);
    }

    processed++;
    if (processed % 100 === 0) {
      const pct = 10 + (processed / totalStocks) * 60; // 10% -> 70%
      safeOnProgress({ stage: 'indicators', percent: pct, message: `预计算指标 ${processed}/${totalStocks}` });
    }
  }

  const indicatorCalcTime = performance.now() - indicatorCalcStart;
  safeOnProgress({ stage: 'indicators', percent: 70, message: '指标预计算完成' });

  // 3. 模拟交易主循环（阶段2：70-100%）
  safeOnProgress({ stage: 'simulation', percent: 75, message: '开始模拟交易...' });
  const simulationStart = performance.now();

  // 初始化状态
  let cashFen = config.initialCapital; // 初始资金（分）
  const positions = new Map<string, Position>(); // 当前持仓
  const trades: Trade[] = [];
  const equityCurve: EquityPoint[] = [];
  const holdings: Array<{ date: string; positions: Position[] }> = [];
  // P1-3: T+1 执行指令队列（改为 let 声明，使用数组替换避免内存碎片）
  let pendingOrders: PendingOrder[] = [];

  let peakEquityFen = config.initialCapital;
  let forceLiquidate = false; // 组合级风控触发
  let forceStop = false; // 最大回撤止损触发

  // 分层止盈状态（仅 exitMode='layeredTakeProfit' 使用）
  const layeredTPState = new Map<string, {
    hasForceStopped: boolean;
    hasFirstProfit: boolean;
    hasSecondProfit: boolean;
    hasFullProfit: boolean;
    hasStopLoss: boolean;
    peakPrice: number;
  }>();

  // P2-6: 调仓日计算（转为 Set 优化查找为 O(1)）
  const rebalanceDaysSet = new Set<number>();
  for (let i = startIdx; i <= actualEndIdx; i += config.rebalanceInterval) {
    rebalanceDaysSet.add(i);
  }

  // P2-9: 仅记录调仓日持仓快照
  const isRebalanceDay = (idx: number) => rebalanceDaysSet.has(idx);

  // 逐日模拟
  for (let i = startIdx; i <= actualEndIdx; i++) {
    const currentDate = allTradeDates[i];
    const prevDate = i > 0 ? allTradeDates[i - 1] : currentDate;

    // P1-3: 执行待执行指令队列（T+1 执行）
    const ordersToExecute = pendingOrders.filter(o => o.executionDate === currentDate);
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
        // 当日无数据，顺延
        order.deferCount++;
        if (order.deferCount > config.maxDeferDays) {
          if (config.deferFailAction === 'abandon') {
            warnings.push(`${currentDate}: ${order.code} 顺延超时，放弃执行`);
            continue;
          } else {
            // atClose: 以收盘价执行
            order.executionDate = currentDate;
          }
        } else {
          // 顺延到下一交易日
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
        // 检查是否停牌（无法卖出）
        if (isSuspended(bar, preClose, limitPct)) {
          order.deferCount++;
          if (order.deferCount > config.maxDeferDays) {
            if (config.deferFailAction === 'abandon') {
              warnings.push(`${currentDate}: ${order.code} 停牌顺延超时，放弃卖出`);
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

        // 检查是否跌停（无法卖出）
        if (isLimitDown(bar, preClose, limitPct)) {
          order.deferCount++;
          if (order.deferCount > config.maxDeferDays) {
            if (config.deferFailAction === 'abandon') {
              warnings.push(`${currentDate}: ${order.code} 跌停顺延超时，放弃卖出`);
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

        const sellPrice = bar[OHLCV_OPEN]; // T+1 开盘价执行
        const sellAmountFen = pos.shares * sellPrice * 100;
        const commission = calcSellCommission(
          sellAmountFen,
          config.feeRate,
          config.slippage,
          config.stampDuty,
          config.minCommission
        );
        const pnlFen = sellAmountFen - pos.shares * pos.avgCost * 100 - commission;
        cashFen += sellAmountFen - commission;
        trades.push({
          code: order.code,
          name: snapshot.name,
          entryDate: allTradeDates[pos.entryDateIdx],
          exitDate: currentDate,
          entryPrice: pos.avgCost,
          exitPrice: sellPrice,
          shares: pos.shares,
          pnl: pnlFen / 100,
          pnlPct: pnlFen / (pos.shares * pos.avgCost * 100),
          holdDays: pos.holdDays,
          sellReason: order.sellReason ?? 'rebalance',
        });
        positions.delete(order.code);
      } else if (order.action === 'buy') {
        // 检查是否涨停（无法买入）
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

        const buyPrice = bar[OHLCV_OPEN]; // T+1 开盘价执行
        // P1-1: 使用执行日当天的现金 × 权重计算目标金额
        const targetAmountFen = cashFen * (order.weight ?? 0);
        const shares = calcSharesToBuy(
          targetAmountFen,
          buyPrice,
          config.feeRate,
          config.slippage,
          config.minCommission
        );
        // P1-2: 买入失败时记录警告
        if (shares <= 0) {
          warnings.push(`${currentDate}: ${order.code} 买入失败，计算股数为0（目标金额: ${targetAmountFen.toFixed(0)}分，价格: ${buyPrice}元）`);
          continue;
        }

        const buyAmountFen = shares * buyPrice * 100;
        const commission = calcBuyCommission(buyAmountFen, config.feeRate, config.slippage, config.minCommission);
        if (buyAmountFen + commission > cashFen) continue;

        cashFen -= (buyAmountFen + commission);
        positions.set(order.code, {
          code: order.code,
          shares,
          avgCost: buyPrice,
          entryDateIdx: i,
          holdDays: 0,
        });
        // 初始化分层止盈状态
        if (exitMode === 'layeredTakeProfit') {
          layeredTPState.set(order.code, {
            hasForceStopped: false,
            hasFirstProfit: false,
            hasSecondProfit: false,
            hasFullProfit: false,
            hasStopLoss: false,
            peakPrice: buyPrice,
          });
        }
      }
    }

    // P1-3: 更新待执行队列（使用数组替换避免内存碎片）
    pendingOrders = ordersToKeep;

    // a) 更新持仓市值
    let marketValueFen = 0;
    for (const [code, pos] of positions) {
      const dateIndexMap = stockDateIndexMap.get(code);
      if (!dateIndexMap) continue;
      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined) continue;

      const bars = stockBars.get(code);
      if (!bars) continue;
      const closePrice = bars[barIdx][OHLCV_CLOSE];
      marketValueFen += pos.shares * closePrice * 100;
    }

    const totalEquityFen = cashFen + marketValueFen;
    const totalEquityYuan = totalEquityFen / 100;

    // b) 计算日收益率（已扣费）
    const prevEquityFen = i > startIdx
      ? (equityCurve[equityCurve.length - 1]?.totalEquity ?? config.initialCapital) * 100
      : config.initialCapital;
    const dayReturn = (totalEquityFen - prevEquityFen) / prevEquityFen;

    // c) 更新峰值和回撤
    if (totalEquityFen > peakEquityFen) {
      peakEquityFen = totalEquityFen;
    }
    const drawdown = (totalEquityFen - peakEquityFen) / peakEquityFen;

    // d) 记录净值点
    equityCurve.push({
      date: currentDate,
      totalEquity: totalEquityYuan,
      cash: cashFen / 100,
      marketValue: marketValueFen / 100,
      returnPct: dayReturn,
      drawdownPct: drawdown,
    });

    // P2-9: 仅记录调仓日持仓快照
    if (isRebalanceDay(i)) {
      holdings.push({
        date: currentDate,
        positions: Array.from(positions.values()).map(p => ({ ...p })),
      });
    }

    // P2-8: 个股风控检查（止损/止盈/超时）
    const riskControlSells: Array<{ code: string; reason: SellReason }> = [];
    for (const [code, pos] of positions) {
      const dateIndexMap = stockDateIndexMap.get(code);
      if (!dateIndexMap) continue;
      const barIdx = dateIndexMap.get(currentDate);
      if (barIdx === undefined) continue;

      const bars = stockBars.get(code);
      if (!bars) continue;

      const snapshot = snapshots.get(code);
      if (!snapshot) continue;

      const bar = bars[barIdx];
      const preClose = barIdx > 0 ? bars[barIdx - 1][OHLCV_CLOSE] : bar[OHLCV_CLOSE];
      const limitPct = getLimitPct(snapshot.listedBoard, snapshot.isSt);

      // 停牌中跳过风控检查
      if (isSuspended(bar, preClose, limitPct)) continue;

      const currentPrice = bar[OHLCV_CLOSE];
      const pnlPct = (currentPrice - pos.avgCost) / pos.avgCost;

      if (exitMode === 'layeredTakeProfit') {
        // 分层止盈/止损退出逻辑
        const tpState = layeredTPState.get(code);
        if (!tpState) continue;

        // 更新持仓峰值
        if (currentPrice > tpState.peakPrice) {
          tpState.peakPrice = currentPrice;
        }

        const drawdown = (currentPrice - tpState.peakPrice) / tpState.peakPrice;
        const lp = layeredTPParams ?? { minHoldDays: 3, maxDrawdown: 0.05, firstProfitTarget: 0.04, secondProfitTarget: 0.08, fullProfitTarget: 0.10, rsiHigh: 80 };

        // 1. 强制止损（持仓 < minHoldDays 且回撤超过阈值）
        if (!tpState.hasForceStopped && pos.holdDays < lp.minHoldDays && drawdown < -lp.maxDrawdown) {
          riskControlSells.push({ code, reason: 'stop_loss' });
          continue;
        }

        // 2. 全止盈
        if (!tpState.hasFullProfit && pos.holdDays >= lp.minHoldDays && pnlPct >= lp.fullProfitTarget) {
          riskControlSells.push({ code, reason: 'take_profit' });
          continue;
        }

        // 3. 第二止盈（需第一止盈已触发）
        if (!tpState.hasSecondProfit && tpState.hasFirstProfit
          && pos.holdDays >= lp.minHoldDays && pnlPct >= lp.secondProfitTarget) {
          riskControlSells.push({ code, reason: 'take_profit' });
          continue;
        }

        // 4. 第一止盈
        if (!tpState.hasFirstProfit && pos.holdDays >= lp.minHoldDays && pnlPct >= lp.firstProfitTarget) {
          riskControlSells.push({ code, reason: 'take_profit' });
          continue;
        }

        // 5. 常规止损（持仓 >= minHoldDays 且回撤超阈值 或 RSI > rsiHigh）
        if (!tpState.hasStopLoss && pos.holdDays >= lp.minHoldDays) {
          const cache = indicatorCaches.get(code);
          const rsiVal = cache ? cache.getRSI(12, barIdx) : null;
          const rsiTrigger = rsiVal !== null && rsiVal > lp.rsiHigh;
          if (drawdown < -lp.maxDrawdown || rsiTrigger) {
            riskControlSells.push({ code, reason: 'stop_loss' });
            continue;
          }
        }

        // 超时检查
        if (pos.holdDays >= config.maxHoldDays) {
          riskControlSells.push({ code, reason: 'timeout' });
          continue;
        }
      } else {
        // 标准退出逻辑（止损/止盈/超时）
        if (pnlPct <= config.stopLossPct) {
          riskControlSells.push({ code, reason: 'stop_loss' });
          continue;
        }
        if (pnlPct >= config.takeProfitPct) {
          riskControlSells.push({ code, reason: 'take_profit' });
          continue;
        }
        if (pos.holdDays >= config.maxHoldDays) {
          riskControlSells.push({ code, reason: 'timeout' });
          continue;
        }
      }
    }

    // 生成个股风控卖出指令（T+1 执行）
    for (const { code, reason } of riskControlSells) {
      const pos = positions.get(code);
      if (!pos) continue;
      pendingOrders.push({
        code,
        action: 'sell',
        signalDate: currentDate,
        executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
        shares: pos.shares,
        sellReason: reason,
        deferCount: 0,
      });
    }

    // f) 组合级风控检查
    if (config.dailyLossLimitEnabled && dayReturn <= config.dailyLossLimitPct) {
      forceLiquidate = true;
      warnings.push(`${currentDate}: 单日亏损 ${(dayReturn * 100).toFixed(2)}%，触发清仓`);
      // P1-5: 立即生成清仓卖出指令
      for (const [code, pos] of positions) {
        pendingOrders.push({
          code,
          action: 'sell',
          signalDate: currentDate,
          executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
          shares: pos.shares,
          sellReason: 'portfolio_risk',
          deferCount: 0,
        });
      }
    }
    if (config.maxDrawdownStopEnabled && drawdown <= config.maxDrawdownStopPct) {
      forceStop = true;
      forceLiquidate = true;
      warnings.push(`${currentDate}: 回撤 ${(drawdown * 100).toFixed(2)}%，触发最大回撤止损`);
      // P1-5: 立即生成清仓卖出指令（避免重复添加）
      if (!config.dailyLossLimitEnabled || dayReturn > config.dailyLossLimitPct) {
        for (const [code, pos] of positions) {
          pendingOrders.push({
            code,
            action: 'sell',
            signalDate: currentDate,
            executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
            shares: pos.shares,
            sellReason: 'portfolio_risk',
            deferCount: 0,
          });
        }
      }
    }

    // g) 调仓日逻辑
    // forceLiquidate 生命周期：
    //   1. 在风控阶段（f 段）被设置为 true，同时生成清仓卖出指令（T+1 执行）
    //   2. 在非调仓日，forceLiquidate 保持 true，跳过调仓日逻辑（无调仓日则无事发生）
    //   3. 在调仓日，forceLiquidate 被重置为 false，允许后续调仓日正常选股
    //   4. 若在非调仓日触发多次风控，第二次风控触发时 forceLiquidate 再次置为 true，逻辑正确
    if (isRebalanceDay(i) && !forceStop) {
      // P0-2.4: 若组合风控已触发清仓，跳过调仓日逻辑（已在风控阶段生成卖出指令，避免重复）
      // 重置风控标记，允许后续调仓日正常选股
      if (forceLiquidate) {
        forceLiquidate = false;
      } else {
        // 选股：遍历所有股票，评估 AST 过滤器
        const targetPool = new Set<string>();
        for (const [code, bars] of stockBars) {
          const snapshot = snapshots.get(code);
          const cache = indicatorCaches.get(code);
          const dateIndexMap = stockDateIndexMap.get(code);
          if (!snapshot || !cache || !dateIndexMap) continue;

          const barIdx = dateIndexMap.get(currentDate);
          if (barIdx === undefined) continue;

          // 排除停牌、涨停（无法买入）
          const bar = bars[barIdx];
          const preClose = barIdx > 0 ? bars[barIdx - 1][OHLCV_CLOSE] : bar[OHLCV_CLOSE];
          const limitPct = getLimitPct(snapshot.listedBoard, snapshot.isSt);
          if (isSuspended(bar, preClose, limitPct)) continue;
          if (isLimitUp(bar, preClose, limitPct)) continue;

          // AST 评估
          if (evaluateFilter(filterTree!, snapshot, bars, cache, barIdx, customIndicatorValues)) {
            targetPool.add(code);
          }
        }

        // 卖出：持仓不在目标池（生成 T+1 卖出指令）
        for (const [code, pos] of positions) {
          if (!targetPool.has(code)) {
            pendingOrders.push({
              code,
              action: 'sell',
              signalDate: currentDate,
              executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
              shares: pos.shares,
              sellReason: 'rebalance',
              deferCount: 0,
            });
          }
        }

        // 买入：目标池中的股票，等权分配（生成 T+1 买入指令）
        const { weight, cashDragWarning } = calcEqualWeight(config.maxPositions, config.singleStockMaxPct);
        if (cashDragWarning) {
          warnings.push(`${currentDate}: 单股仓位上限 ${(config.singleStockMaxPct * 100).toFixed(1)}% < 等权 ${(100 / config.maxPositions).toFixed(1)}%，产生现金拖累`);
        }

        for (const code of targetPool) {
          if (positions.has(code)) continue;
          if (positions.size >= config.maxPositions) break;

          pendingOrders.push({
            code,
            action: 'buy',
            signalDate: currentDate,
            executionDate: i + 1 < allTradeDates.length ? allTradeDates[i + 1] : currentDate,
            weight, // P1-1: 存储权重而非固定金额
            deferCount: 0,
          });
        }
      }
    }

    // h) 更新持仓天数
    for (const pos of positions.values()) {
      pos.holdDays++;
    }

    // 进度报告
    if ((i - startIdx) % 10 === 0) {
      const pct = 75 + ((i - startIdx) / (actualEndIdx - startIdx)) * 25;
      safeOnProgress({ stage: 'simulation', percent: pct, message: `模拟交易 ${i - startIdx}/${actualEndIdx - startIdx}` });
    }
  }

  // 4. 期末清仓
  const lastDate = allTradeDates[actualEndIdx];
  for (const [code, pos] of positions) {
    const bars = stockBars.get(code);
    if (bars) {
      const lastBar = bars[bars.length - 1];
      const sellPrice = lastBar[OHLCV_CLOSE];
      const sellAmountFen = pos.shares * sellPrice * 100;
      const commission = calcSellCommission(
        sellAmountFen,
        config.feeRate,
        config.slippage,
        config.stampDuty,
        config.minCommission
      );
      const pnlFen = sellAmountFen - pos.shares * pos.avgCost * 100 - commission;
      cashFen += sellAmountFen - commission;
      trades.push({
        code,
        name: snapshots.get(code)?.name ?? code,
        entryDate: allTradeDates[pos.entryDateIdx],
        exitDate: lastDate,
        entryPrice: pos.avgCost,
        exitPrice: sellPrice,
        shares: pos.shares,
        pnl: pnlFen / 100,
        pnlPct: pnlFen / (pos.shares * pos.avgCost * 100),
        holdDays: pos.holdDays,
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

// ==================== 绩效指标计算 ====================

function calcMetrics(
  equityCurve: EquityPoint[],
  trades: Trade[],
  config: StrategyBacktestDefaults,
  benchmarkOhlcv?: number[][]
): StrategyMetrics {
  if (equityCurve.length === 0) {
    return buildEmptyMetrics();
  }

  const initialEquity = config.initialCapital / 100; // 元
  const finalEquity = equityCurve[equityCurve.length - 1].totalEquity;
  const totalReturn = (finalEquity - initialEquity) / initialEquity;
  const days = equityCurve.length;
  const annualReturn = Math.pow(1 + totalReturn, TRADING_DAYS_PER_YEAR / days) - 1;

  // 夏普比率
  const dailyReturns = equityCurve.map(e => e.returnPct);
  const avgDailyReturn = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
  const dailyStdDev = Math.sqrt(
    dailyReturns.reduce((sum, r) => sum + Math.pow(r - avgDailyReturn, 2), 0) / dailyReturns.length
  );
  const sharpeRatio = dailyStdDev > 0
    ? (avgDailyReturn - config.riskFreeRate / TRADING_DAYS_PER_YEAR) / dailyStdDev * Math.sqrt(TRADING_DAYS_PER_YEAR)
    : 0;

  // 最大回撤
  const maxDrawdown = Math.min(...equityCurve.map(e => e.drawdownPct));

  // 胜率和盈亏比
  const winningTrades = trades.filter(t => t.pnl > 0);
  const losingTrades = trades.filter(t => t.pnl < 0);
  const winRate = trades.length > 0 ? winningTrades.length / trades.length : 0;
  const avgWin = winningTrades.length > 0 ? winningTrades.reduce((s, t) => s + t.pnlPct, 0) / winningTrades.length : 0;
  const avgLoss = losingTrades.length > 0 ? Math.abs(losingTrades.reduce((s, t) => s + t.pnlPct, 0) / losingTrades.length) : 1;
  const profitLossRatio = avgLoss > 0 ? avgWin / avgLoss : 0;

  // 最大连亏
  let maxConsecutiveLosses = 0;
  let currentLosses = 0;
  for (const trade of trades) {
    if (trade.pnl < 0) {
      currentLosses++;
      maxConsecutiveLosses = Math.max(maxConsecutiveLosses, currentLosses);
    } else {
      currentLosses = 0;
    }
  }

  // 平均持仓天数
  const avgHoldDays = trades.length > 0 ? trades.reduce((s, t) => s + t.holdDays, 0) / trades.length : 0;

  // 月度胜率
  const monthlyReturns = calcMonthlyReturns(equityCurve);
  const positiveMonths = monthlyReturns.filter(r => r > 0).length;
  const monthlyWinRate = monthlyReturns.length > 0 ? positiveMonths / monthlyReturns.length : 0;

  // 卡玛比率
  const calmarRatio = maxDrawdown !== 0 ? annualReturn / Math.abs(maxDrawdown) : 0;

  // 基准相关指标
  let benchmarkReturn: number | null = null;
  let alpha: number | null = null;
  let beta: number | null = null;
  let informationRatio: number | null = null;

  if (benchmarkOhlcv && benchmarkOhlcv.length > 0) {
    // 基准总收益率
    const initialBenchmark = benchmarkOhlcv[0][OHLCV_CLOSE];
    const finalBenchmark = benchmarkOhlcv[benchmarkOhlcv.length - 1][OHLCV_CLOSE];
    benchmarkReturn = (finalBenchmark - initialBenchmark) / initialBenchmark;

    // Alpha = 策略收益 - 基准收益
    alpha = totalReturn - benchmarkReturn;

    // P1-4: 计算 Beta 和 Information Ratio（按日期对齐）
    // 构建基准日收益率 Map<date, return>
    const benchmarkReturnMap = new Map<string, number>();
    for (let i = 1; i < benchmarkOhlcv.length; i++) {
      const prevClose = benchmarkOhlcv[i - 1][OHLCV_CLOSE];
      const currClose = benchmarkOhlcv[i][OHLCV_CLOSE];
      if (prevClose > 0) {
        const date = parseTimestamp(benchmarkOhlcv[i][OHLCV_TS]);
        benchmarkReturnMap.set(date, (currClose - prevClose) / prevClose);
      }
    }

    // 构建策略日收益率 Map<date, return>
    const strategyReturnMap = new Map<string, number>();
    for (let i = 0; i < equityCurve.length; i++) {
      strategyReturnMap.set(equityCurve[i].date, equityCurve[i].returnPct);
    }

    // 按日期对齐（取交集）
    const alignedDates = Array.from(strategyReturnMap.keys()).filter(d => benchmarkReturnMap.has(d));
    if (alignedDates.length > 1) {
      const strategyAligned = alignedDates.map(d => strategyReturnMap.get(d)!);
      const benchmarkAligned = alignedDates.map(d => benchmarkReturnMap.get(d)!);

      // Beta = Cov(Rp, Rb) / Var(Rb)
      const avgRp = strategyAligned.reduce((a, b) => a + b, 0) / alignedDates.length;
      const avgRb = benchmarkAligned.reduce((a, b) => a + b, 0) / alignedDates.length;
      let covariance = 0;
      let varianceB = 0;
      for (let i = 0; i < alignedDates.length; i++) {
        const dRp = strategyAligned[i] - avgRp;
        const dRb = benchmarkAligned[i] - avgRb;
        covariance += dRp * dRb;
        varianceB += dRb * dRb;
      }
      beta = varianceB > 0 ? covariance / varianceB : null;

      // Information Ratio = mean(Rp - Rb) / std(Rp - Rb)
      const excessReturns: number[] = [];
      for (let i = 0; i < alignedDates.length; i++) {
        excessReturns.push(strategyAligned[i] - benchmarkAligned[i]);
      }
      const meanExcess = excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length;
      const stdExcess = Math.sqrt(
        excessReturns.reduce((sum, r) => sum + Math.pow(r - meanExcess, 2), 0) / excessReturns.length
      );
      informationRatio = stdExcess > 0
        ? (meanExcess / stdExcess) * Math.sqrt(TRADING_DAYS_PER_YEAR)
        : null;
    }
  }

  return {
    totalReturn,
    annualReturn,
    sharpeRatio,
    maxDrawdown,
    winRate,
    profitLossRatio,
    maxConsecutiveLosses,
    avgHoldDays,
    totalTrades: trades.length,
    monthlyWinRate,
    calmarRatio,
    benchmarkReturn,
    alpha,
    beta,
    informationRatio,
  };
}

function calcMonthlyReturns(equityCurve: EquityPoint[]): number[] {
  const monthlyMap = new Map<string, number>();
  for (const point of equityCurve) {
    const month = point.date.slice(0, 7); // YYYY-MM
    // 利用 Map.set 覆盖特性：同月多个净值点，最终保留最后一个（即月终值）
    monthlyMap.set(month, point.totalEquity);
  }
  const months = Array.from(monthlyMap.keys()).sort();
  const returns: number[] = [];
  for (let i = 1; i < months.length; i++) {
    const prev = monthlyMap.get(months[i - 1])!;
    const curr = monthlyMap.get(months[i])!;
    returns.push((curr - prev) / prev);
  }
  return returns;
}

// ==================== 空结果构建 ====================

function buildEmptyResult(config: StrategyBacktestDefaults, warning: string): StrategyBacktestResult {
  return {
    config,
    equityCurve: [],
    trades: [],
    holdings: [],
    metrics: buildEmptyMetrics(),
    warnings: [warning],
    timings: { dataLoad: 0, indicatorCalc: 0, simulation: 0, total: 0 },
  };
}

function buildEmptyMetrics(): StrategyMetrics {
  return {
    totalReturn: 0,
    annualReturn: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    winRate: 0,
    profitLossRatio: 0,
    maxConsecutiveLosses: 0,
    avgHoldDays: 0,
    totalTrades: 0,
    monthlyWinRate: 0,
    calmarRatio: 0,
    benchmarkReturn: null,
    alpha: null,
    beta: null,
    informationRatio: null,
  };
}
