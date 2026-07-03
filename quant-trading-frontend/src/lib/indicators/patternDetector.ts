// lib/indicators/patternDetector.ts

import {
  precomputeBars,
  type PrecomputedBar,
  getBodySize,
  getRange,
  getBodyTop,
  getBodyBottom,
  getOpen,
  getClose,
  getHigh,
  getLow,
} from './barUtils';
import { DETECTION_CONFIG, validateConfig, ChartError, ChartErrorType } from './chartConstants';
import { type PatternType, type PatternDetectionResult, type OHLCVArray, OHLCV_TIME } from './types';

// ---------- 单K线形态（基于 PrecomputedBar） ----------
/**
 * 判断是否为十字星
 * @param bar - 预计算K线数据
 * @param ratio - 实体占振幅的最大比例
 */
function isDojiFromPrecomputed(bar: PrecomputedBar, ratio: number): boolean {
  if (bar.range === 0) return true;
  return bar.bodySize / bar.range <= ratio;
}

/**
 * 判断是否为大实体
 */
function isLargeBodyFromPrecomputed(bar: PrecomputedBar, ratio: number): boolean {
  if (bar.range === 0) return false;
  return bar.bodySize / bar.range >= ratio;
}

/**
 * 判断是否为锤子线（含上影线容差）
 */
function isHammerFromPrecomputed(
  bar: PrecomputedBar,
  lowerRatio: number,
  upperRatio: number,
  tolerance: number,
): boolean {
  if (bar.range === 0) return false;
  const upperTolerance = bar.range * tolerance;
  return (
    bar.lowerShadow >= bar.bodySize * lowerRatio &&
    bar.upperShadow <= bar.bodySize * upperRatio + upperTolerance
  );
}

// ---------- 双K线形态 ----------
function isBullishEngulfingFromPrecomputed(prev: PrecomputedBar, curr: PrecomputedBar): boolean {
  if (!prev.bearish || !curr.bullish) return false;
  return (
    curr.open <= prev.bodyBottom &&
    curr.close >= prev.bodyTop &&
    curr.bodySize > prev.bodySize
  );
}

function isBearishEngulfingFromPrecomputed(prev: PrecomputedBar, curr: PrecomputedBar): boolean {
  if (!prev.bullish || !curr.bearish) return false;
  return (
    curr.open >= prev.bodyTop &&
    curr.close <= prev.bodyBottom &&
    curr.bodySize > prev.bodySize
  );
}

// ---------- 星形态（晨星/夜星） ----------
function isStarPatternFromPrecomputed(
  bar1: PrecomputedBar,
  bar2: PrecomputedBar,
  bar3: PrecomputedBar,
  firstBullish: boolean,   // true: 夜星（第一根阳线）, false: 晨星（第一根阴线）
  penetration: number,
  dojiRatio: number,
  largeBodyRatio: number,
  requireGap: boolean,
): boolean {
  // 第一根
  if (firstBullish) {
    if (!bar1.bullish || !isLargeBodyFromPrecomputed(bar1, largeBodyRatio)) return false;
  } else {
    if (!bar1.bearish || !isLargeBodyFromPrecomputed(bar1, largeBodyRatio)) return false;
  }
  // 第二根（星线）
  if (!isDojiFromPrecomputed(bar2, dojiRatio)) return false;
  // 第三根
  if (firstBullish) {
    if (!bar3.bearish || !isLargeBodyFromPrecomputed(bar3, largeBodyRatio)) return false;
  } else {
    if (!bar3.bullish || !isLargeBodyFromPrecomputed(bar3, largeBodyRatio)) return false;
  }

  if (requireGap) {
    if (firstBullish) {
      // 夜星：第二根高开，第三根低开
      if (bar2.high >= bar1.close) return false;
      if (bar3.open >= bar2.close) return false;
    } else {
      // 晨星：第二根低开，第三根高开
      if (bar2.low <= bar1.close) return false;
      if (bar3.open <= bar2.close) return false;
    }
  }

  const bodySize = bar1.bodySize;
  if (firstBullish) {
    const penetrationPrice = bar1.bodyTop - bodySize * penetration;
    return bar3.close <= penetrationPrice;
  } else {
    const penetrationPrice = bar1.bodyBottom + bodySize * penetration;
    return bar3.close >= penetrationPrice;
  }
}

function isMorningStarFromPrecomputed(
  b1: PrecomputedBar,
  b2: PrecomputedBar,
  b3: PrecomputedBar,
  config: typeof DETECTION_CONFIG,
): boolean {
  return isStarPatternFromPrecomputed(
    b1, b2, b3,
    false,
    config.morningStarPenetration,
    config.dojiBodyRatio,
    config.largeBodyRatio,
    config.requireGapForStar,
  );
}

function isEveningStarFromPrecomputed(
  b1: PrecomputedBar,
  b2: PrecomputedBar,
  b3: PrecomputedBar,
  config: typeof DETECTION_CONFIG,
): boolean {
  return isStarPatternFromPrecomputed(
    b1, b2, b3,
    true,
    config.eveningStarPenetration,
    config.dojiBodyRatio,
    config.largeBodyRatio,
    config.requireGapForStar,
  );
}

// ---------- 辅助：检查时间有序性 ----------
/**
 * 检查 OHLCV 数组是否按时间升序排列
 * @param ohlcv - 数据数组
 * @param strict - 若为 false，检测到乱序则自动排序并警告；若为 true 则抛出错误
 * @returns 排序后的数组（若原有序则返回原数组引用）
 */
function ensureTimeOrder(ohlcv: OHLCVArray[], strict = false): OHLCVArray[] {
  if (ohlcv.length < 2) return ohlcv;
  let sorted = true;
  for (let i = 1; i < ohlcv.length; i++) {
    if (ohlcv[i][OHLCV_TIME] < ohlcv[i - 1][OHLCV_TIME]) {
      sorted = false;
      break;
    }
  }
  if (sorted) return ohlcv;
  const msg = 'OHLCV data is not in ascending time order, auto-sorting.';
  console.warn(`[ensureTimeOrder] ${msg}`);
  if (strict) {
    throw new ChartError(ChartErrorType.DATA_INVALID, 'OHLCV data must be time-ascending');
  }
  // 复制并排序（按时间升序）
  const copy = [...ohlcv];
  copy.sort((a, b) => a[OHLCV_TIME] - b[OHLCV_TIME]);
  return copy;
}

// ---------- 批量检测入口（核心） ----------
/**
 * 检测所有形态（纯函数）
 * @param ohlcv - OHLCV 数组（建议按时间升序，若非升序则会自动排序并警告）
 * @param config - 检测配置（覆盖默认值，非法值将自动修正）
 * @param targetPatterns - 仅检测指定形态（可选，用于提前终止）
 * @returns 包含命中形态和对应索引的结果
 * @throws {ChartError} 当入参严重无效时（如非数组、元素不足）
 */
export function detectAllPatterns(
  ohlcv: OHLCVArray[],
  config: Partial<typeof DETECTION_CONFIG> = {},
  targetPatterns?: PatternType[],
): PatternDetectionResult {
  // 1. 入参基础校验
  if (!Array.isArray(ohlcv) || ohlcv.length < 2) {
    throw new ChartError(
      ChartErrorType.DATA_INVALID,
      'ohlcv must be an array with at least 2 elements'
    );
  }
  // 2. 时间有序性检查 & 自动排序
  const sortedData = ensureTimeOrder(ohlcv, false);

  // 3. 配置校验与合并
  const validatedConfig = validateConfig(config);

  // 4. 预计算
  const precomputed = precomputeBars(sortedData);
  if (precomputed.length < 2) {
    return {
      hits: [],
      hitDays: {
        hammer: [],
        morning_star: [],
        evening_star: [],
        bullish_engulfing: [],
        bearish_engulfing: [],
      },
    };
  }

  // 5. 初始化结果
  const result: PatternDetectionResult = {
    hits: [],
    hitDays: {
      hammer: [],
      morning_star: [],
      evening_star: [],
      bullish_engulfing: [],
      bearish_engulfing: [],
    },
  };

  const targetSet = targetPatterns ? new Set(targetPatterns) : null;
  const hitSet = new Set<PatternType>();

  // 6. 遍历预计算数组
  for (let idx = 0; idx < precomputed.length; idx++) {
    const bar = precomputed[idx];
    const originalIndex = bar.index;

    // ---- 锤子线 ----
    if (isHammerFromPrecomputed(
      bar,
      validatedConfig.hammerLowerShadowRatio,
      validatedConfig.hammerUpperShadowRatio,
      validatedConfig.hammerUpperTolerance
    )) {
      result.hitDays.hammer.push(originalIndex);
      hitSet.add('hammer');
    }

    // ---- 吞没（需要连续两根原始K线相邻） ----
    if (idx > 0 && precomputed[idx - 1].index === originalIndex - 1) {
      const prev = precomputed[idx - 1];
      if (isBullishEngulfingFromPrecomputed(prev, bar)) {
        result.hitDays.bullish_engulfing.push(originalIndex);
        hitSet.add('bullish_engulfing');
      }
      if (isBearishEngulfingFromPrecomputed(prev, bar)) {
        result.hitDays.bearish_engulfing.push(originalIndex);
        hitSet.add('bearish_engulfing');
      }
    }

    // ---- 星形态（需要连续三根原始K线相邻） ----
    if (idx > 1 &&
        precomputed[idx - 1].index === originalIndex - 1 &&
        precomputed[idx - 2].index === originalIndex - 2) {
      const b1 = precomputed[idx - 2],
            b2 = precomputed[idx - 1],
            b3 = bar;
      if (isMorningStarFromPrecomputed(b1, b2, b3, validatedConfig)) {
        result.hitDays.morning_star.push(originalIndex);
        hitSet.add('morning_star');
      }
      if (isEveningStarFromPrecomputed(b1, b2, b3, validatedConfig)) {
        result.hitDays.evening_star.push(originalIndex);
        hitSet.add('evening_star');
      }
    }

    // 提前终止（若已找到所有目标形态）
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

/**
 * 快速检测是否存在指定形态（基于 `detectAllPatterns`）
 */
export function hasAnyPattern(
  ohlcv: OHLCVArray[],
  patterns: PatternType[],
  config: Partial<typeof DETECTION_CONFIG> = {},
): boolean {
  if (!patterns || patterns.length === 0) return false;
  try {
    const result = detectAllPatterns(ohlcv, config, patterns);
    return patterns.some((p) => result.hits.includes(p));
  } catch (err) {
    console.error('[hasAnyPattern] detection failed:', err);
    return false;
  }
}