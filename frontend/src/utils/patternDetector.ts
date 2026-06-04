/**
 * utils/patternDetector.ts - K线形态识别工具
 *
 * 保留 5 个胜率最高的形态（按胜率排序）：
 * 1. 早晨之星 (morning_star)    - 87% 底部反转
 * 2. 黄昏之星 (evening_star)    - 顶部反转
 * 3. 看涨吞没 (bullish_engulfing) - 2K 强势反转
 * 4. 看跌吞没 (bearish_engulfing) - 高位见顶
 * 5. 锤子线 (hammer)             - 单K 看涨
 */

import type { KLineItem } from '../types'

/** K线基础计算字段 */
interface Candle {
  open: number
  high: number
  low: number
  close: number
}

/** 形态识别结果 */
export type PatternKey =
  | 'pattern_morning_star'
  | 'pattern_evening_star'
  | 'pattern_bullish_engulfing'
  | 'pattern_bearish_engulfing'
  | 'pattern_hammer'

/** 单根 K线的几何特征 */
function candleParts(c: Candle) {
  const body = Math.abs(c.close - c.open)
  const upper = c.high - Math.max(c.open, c.close)
  const lower = Math.min(c.open, c.close) - c.low
  const range = c.high - c.low
  return { body, upper, lower, range }
}

/** 是否阳线 */
function isBullish(c: Candle) {
  return c.close > c.open
}

/** 是否阴线 */
function isBearish(c: Candle) {
  return c.close < c.open
}

/**
 * 早晨之星：K1 大阴 + K2 小实体/十字星 + K0 大阳
 * 判定：K0 阳线且实体 >= 2 * K2 实体，K1 阴线且实体 > K2 实体
 */
export function detectMorningStar(k1: KLineItem, k2: KLineItem, k0: KLineItem): boolean {
  const c1 = candleParts(k1)
  const c2 = candleParts(k2)
  const c0 = candleParts(k0)
  return isBearish(k1) && isBullish(k0) && c0.body >= 2 * c2.body && c1.body > c2.body
}

/**
 * 黄昏之星：K1 大阳 + K2 小实体/十字星 + K0 大阴
 */
export function detectEveningStar(k1: KLineItem, k2: KLineItem, k0: KLineItem): boolean {
  const c1 = candleParts(k1)
  const c2 = candleParts(k2)
  const c0 = candleParts(k0)
  return isBullish(k1) && isBearish(k0) && c0.body >= 2 * c2.body && c1.body > c2.body
}

/**
 * 看涨吞没：K1 阴 + K0 阳，K0 实体完全包住 K1 实体
 */
export function detectBullishEngulfing(k1: KLineItem, k0: KLineItem): boolean {
  return isBearish(k1) && isBullish(k0) && k0.open < k1.close && k0.close > k1.open
}

/**
 * 看跌吞没：K1 阳 + K0 阴，K0 实体完全包住 K1 实体
 */
export function detectBearishEngulfing(k1: KLineItem, k0: KLineItem): boolean {
  return isBullish(k1) && isBearish(k0) && k0.open > k1.close && k0.close < k1.open
}

/**
 * 锤子线：下影 > 实体 2 倍，上影很短
 */
export function detectHammer(c: KLineItem): boolean {
  const p = candleParts(c)
  return p.lower >= 2 * p.body && p.upper <= 0.1 * p.range
}

/**
 * 识别单只股票最新 K线命中的所有形态
 *
 * @param klines K线数据（按日期从新到旧），至少 3 根
 * @returns 命中的形态 key 数组
 */
export function detectPatterns(klines: KLineItem[]): PatternKey[] {
  if (!klines || klines.length === 0) return []

  const result: PatternKey[] = []
  const k0 = klines[0] // 最新
  const k1 = klines[1] // 前一根
  const k2 = klines[2] // 前两根

  // 1. 早晨之星
  if (k1 && k2 && detectMorningStar(k1, k2, k0)) {
    result.push('pattern_morning_star')
  }

  // 2. 黄昏之星
  if (k1 && k2 && detectEveningStar(k1, k2, k0)) {
    result.push('pattern_evening_star')
  }

  // 3. 看涨吞没
  if (k1 && detectBullishEngulfing(k1, k0)) {
    result.push('pattern_bullish_engulfing')
  }

  // 4. 看跌吞没
  if (k1 && detectBearishEngulfing(k1, k0)) {
    result.push('pattern_bearish_engulfing')
  }

  // 5. 锤子线
  if (detectHammer(k0)) {
    result.push('pattern_hammer')
  }

  return result
}

/**
 * 形态 key 列表（按胜率排序）
 */
export const PATTERN_KEYS: PatternKey[] = [
  'pattern_morning_star',
  'pattern_evening_star',
  'pattern_bullish_engulfing',
  'pattern_bearish_engulfing',
  'pattern_hammer',
]
