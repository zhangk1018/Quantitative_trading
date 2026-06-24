import {
  OHLCV_OPEN,
  OHLCV_HIGH,
  OHLCV_LOW,
  OHLCV_CLOSE,
  type OHLCVArray,
  type PatternType,
  type PatternDetectionResult,
} from './types';

// --- 默认阈值常量 (作为 fallback) ---
const DEFAULT_MORNING_STAR_PENETRATION = 0.3;
const DEFAULT_EVENING_STAR_PENETRATION = 0.3;
const DEFAULT_DOJI_BODY_RATIO = 0.1;
const DEFAULT_LARGE_BODY_RATIO = 0.6;
const DEFAULT_HAMMER_LOWER_SHADOW_RATIO = 2.0;
const DEFAULT_HAMMER_UPPER_SHADOW_RATIO = 0.1;

export interface DetectionConfig {
  /** 参与检测的K线总数窗口（强制要求整个形态都落入此窗口内） */
  lookbackDays: number;
  morningStarPenetration?: number;
  eveningStarPenetration?: number;
  dojiBodyRatio?: number;
  largeBodyRatio?: number;
  hammerLowerShadowRatio?: number;
  hammerUpperShadowRatio?: number;
  /** 是否要求晨星/夜星的星线必须与前后K线存在跳空缺口 */
  requireGapForStar?: boolean;
}

function getOpen(bar: OHLCVArray): number { return bar[OHLCV_OPEN]; }
function getHigh(bar: OHLCVArray): number { return bar[OHLCV_HIGH]; }
function getLow(bar: OHLCVArray): number { return bar[OHLCV_LOW]; }
function getClose(bar: OHLCVArray): number { return bar[OHLCV_CLOSE]; }

function isValidBar(bar: OHLCVArray): boolean {
  return (
    bar != null &&
    Number.isFinite(getOpen(bar)) &&
    Number.isFinite(getHigh(bar)) &&
    Number.isFinite(getLow(bar)) &&
    Number.isFinite(getClose(bar)) &&
    getHigh(bar) >= getLow(bar) &&
    getHigh(bar) >= Math.max(getOpen(bar), getClose(bar)) &&
    getLow(bar) <= Math.min(getOpen(bar), getClose(bar))
  );
}

function getBodyTop(bar: OHLCVArray): number { return Math.max(getOpen(bar), getClose(bar)); }
function getBodyBottom(bar: OHLCVArray): number { return Math.min(getOpen(bar), getClose(bar)); }
function getBodySize(bar: OHLCVArray): number { return Math.abs(getClose(bar) - getOpen(bar)); }
function getRange(bar: OHLCVArray): number { return getHigh(bar) - getLow(bar); }
function isBullish(bar: OHLCVArray): boolean { return getClose(bar) > getOpen(bar); }
function isBearish(bar: OHLCVArray): boolean { return getClose(bar) < getOpen(bar); }
function getUpperShadow(bar: OHLCVArray): number { return getHigh(bar) - getBodyTop(bar); }
function getLowerShadow(bar: OHLCVArray): number { return getBodyBottom(bar) - getLow(bar); }

function isDoji(bar: OHLCVArray, ratio: number = DEFAULT_DOJI_BODY_RATIO): boolean {
  const range = getRange(bar);
  if (range === 0) return true;
  return getBodySize(bar) / range <= ratio;
}

function isLargeBody(bar: OHLCVArray, ratio: number = DEFAULT_LARGE_BODY_RATIO): boolean {
  const range = getRange(bar);
  if (range === 0) return false;
  return getBodySize(bar) / range >= ratio;
}

export function isHammer(
  bar: OHLCVArray, 
  lowerRatio: number = DEFAULT_HAMMER_LOWER_SHADOW_RATIO, 
  upperRatio: number = DEFAULT_HAMMER_UPPER_SHADOW_RATIO
): boolean {
  if (!isValidBar(bar)) return false;
  const range = getRange(bar);
  if (range === 0) return false;
  
  const body = getBodySize(bar);
  const lowerShadow = getLowerShadow(bar);
  const upperShadow = getUpperShadow(bar);
  const upperTolerance = range * 0.01; // 允许 1% 振幅的上影线容差
  
  return (
    lowerShadow >= body * lowerRatio &&
    upperShadow <= body * upperRatio + upperTolerance
  );
}

export function isBullishEngulfing(prevBar: OHLCVArray, currBar: OHLCVArray): boolean {
  if (!isValidBar(prevBar) || !isValidBar(currBar)) return false;
  if (!isBearish(prevBar) || !isBullish(currBar)) return false;
  return (
    getOpen(currBar) <= getBodyBottom(prevBar) && 
    getClose(currBar) >= getBodyTop(prevBar) &&
    getBodySize(currBar) > getBodySize(prevBar) 
  );
}

export function isBearishEngulfing(prevBar: OHLCVArray, currBar: OHLCVArray): boolean {
  if (!isValidBar(prevBar) || !isValidBar(currBar)) return false;
  if (!isBullish(prevBar) || !isBearish(currBar)) return false;
  return (
    getOpen(currBar) >= getBodyTop(prevBar) && 
    getClose(currBar) <= getBodyBottom(prevBar) &&
    getBodySize(currBar) > getBodySize(prevBar) 
  );
}

export function isMorningStar(
  bar1: OHLCVArray, bar2: OHLCVArray, bar3: OHLCVArray,
  penetration: number = DEFAULT_MORNING_STAR_PENETRATION,
  dojiRatio: number = DEFAULT_DOJI_BODY_RATIO,
  largeBodyRatio: number = DEFAULT_LARGE_BODY_RATIO,
  requireGap: boolean = false,
): boolean {
  if (!isValidBar(bar1) || !isValidBar(bar2) || !isValidBar(bar3)) return false;
  if (!isBearish(bar1) || !isLargeBody(bar1, largeBodyRatio)) return false;
  if (!isDoji(bar2, dojiRatio)) return false;
  if (!isBullish(bar3) || !isLargeBody(bar3, largeBodyRatio)) return false;
  
  if (requireGap) {
    if (getLow(bar2) <= getClose(bar1)) return false;
    if (getOpen(bar3) <= getClose(bar2)) return false;
  }
  
  const penetrationPrice = getBodyBottom(bar1) + getBodySize(bar1) * penetration;
  return getClose(bar3) >= penetrationPrice;
}

export function isEveningStar(
  bar1: OHLCVArray, bar2: OHLCVArray, bar3: OHLCVArray,
  penetration: number = DEFAULT_EVENING_STAR_PENETRATION,
  dojiRatio: number = DEFAULT_DOJI_BODY_RATIO,
  largeBodyRatio: number = DEFAULT_LARGE_BODY_RATIO,
  requireGap: boolean = false,
): boolean {
  if (!isValidBar(bar1) || !isValidBar(bar2) || !isValidBar(bar3)) return false;
  if (!isBullish(bar1) || !isLargeBody(bar1, largeBodyRatio)) return false;
  if (!isDoji(bar2, dojiRatio)) return false;
  if (!isBearish(bar3) || !isLargeBody(bar3, largeBodyRatio)) return false;
  
  if (requireGap) {
    if (getHigh(bar2) >= getClose(bar1)) return false;
    if (getOpen(bar3) >= getClose(bar2)) return false;
  }
  
  const penetrationPrice = getBodyTop(bar1) - getBodySize(bar1) * penetration;
  return getClose(bar3) <= penetrationPrice;
}

export function detectAllPatterns(
  code: string,
  ohlcv: OHLCVArray[],
  config: DetectionConfig = { lookbackDays: 3 },
  targetPatterns?: PatternType[], 
): PatternDetectionResult {
  const result: PatternDetectionResult = {
    code,
    hits: [],
    hitDays: {
      hammer: [], morning_star: [], evening_star: [],
      bullish_engulfing: [], bearish_engulfing: [],
    },
  };

  const n = ohlcv.length;
  if (n === 0) return result;

  const windowStart = Math.max(0, n - config.lookbackDays);
  
  const dojiRatio = config.dojiBodyRatio ?? DEFAULT_DOJI_BODY_RATIO;
  const largeBodyRatio = config.largeBodyRatio ?? DEFAULT_LARGE_BODY_RATIO;
  const hammerLower = config.hammerLowerShadowRatio ?? DEFAULT_HAMMER_LOWER_SHADOW_RATIO;
  const hammerUpper = config.hammerUpperShadowRatio ?? DEFAULT_HAMMER_UPPER_SHADOW_RATIO;
  const morningPen = config.morningStarPenetration ?? DEFAULT_MORNING_STAR_PENETRATION;
  const eveningPen = config.eveningStarPenetration ?? DEFAULT_EVENING_STAR_PENETRATION;
  const requireGap = config.requireGapForStar ?? false;

  const hitSet = new Set<PatternType>();
  const targetSet = targetPatterns ? new Set(targetPatterns) : null;

  for (let i = windowStart; i < n; i++) {
    const bar = ohlcv[i];
    if (!isValidBar(bar)) continue;

    if (isHammer(bar, hammerLower, hammerUpper)) {
      result.hitDays.hammer.push(i);
      hitSet.add('hammer');
    }

    if (i >= windowStart + 1) {
      const prev = ohlcv[i - 1];
      if (isBullishEngulfing(prev, bar)) {
        result.hitDays.bullish_engulfing.push(i);
        hitSet.add('bullish_engulfing');
      }
      if (isBearishEngulfing(prev, bar)) {
        result.hitDays.bearish_engulfing.push(i);
        hitSet.add('bearish_engulfing');
      }
    }

    if (i >= windowStart + 2) {
      const b1 = ohlcv[i - 2];
      const b2 = ohlcv[i - 1];
      const b3 = bar;
      if (isMorningStar(b1, b2, b3, morningPen, dojiRatio, largeBodyRatio, requireGap)) {
        result.hitDays.morning_star.push(i);
        hitSet.add('morning_star');
      }
      if (isEveningStar(b1, b2, b3, eveningPen, dojiRatio, largeBodyRatio, requireGap)) {
        result.hitDays.evening_star.push(i);
        hitSet.add('evening_star');
      }
    }

    if (targetSet && targetSet.size > 0) {
      let allFound = true;
      for (const p of targetSet) {
        if (!hitSet.has(p)) { allFound = false; break; }
      }
      if (allFound) break;
    }
  }

  result.hits = Array.from(hitSet);
  return result;
}

export function hasAnyPattern(
  code: string,
  ohlcv: OHLCVArray[],
  patterns: PatternType[],
  lookbackDays: number = 3,
): boolean {
  if (!patterns || patterns.length === 0) return false;
  const result = detectAllPatterns(code, ohlcv, { lookbackDays }, patterns);
  return patterns.some((p) => result.hits.includes(p));
}