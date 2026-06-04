/**
 * utils/patternCache.ts - 形态识别结果缓存
 *
 * 缓存策略：
 * - 按 trade_date 隔离（每天的 K线不同，缓存按天失效）
 * - 存到 localStorage（页面刷新后仍生效）
 * - 容量控制：最多保留 7 个交易日数据
 * - 单只股票命中任一形态才缓存（不缓存"全部不命中"的负结果）
 *
 * 收益：
 * - 首次计算后，第二次进入秒开
 * - 跨页面/跨会话复用
 * - 后端无需感知
 */

import type { PatternKey } from './patternDetector'

/** 缓存 key 前缀 */
const STORAGE_KEY = 'quant.pattern_cache.v1'
/** 最多保留的交易日期数（防止 localStorage 无限增长） */
const MAX_TRADE_DATES = 7

/**
 * 缓存数据结构：
 * {
 *   dates: ['20260604', '20260603', ...]   // 按时间倒序
 *   data: {
 *     '20260604': {
 *       '000001': ['pattern_morning_star', ...],
 *       '000002': ['pattern_hammer'],
 *     },
 *     ...
 *   }
 * }
 */
interface CacheShape {
  dates: string[]
  data: Record<string, Record<string, PatternKey[]>>
}

function loadCache(): CacheShape {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { dates: [], data: {} }
    const parsed = JSON.parse(raw) as CacheShape
    if (!parsed.dates || !parsed.data) return { dates: [], data: {} }
    return parsed
  } catch {
    return { dates: [], data: {} }
  }
}

function saveCache(cache: CacheShape): void {
  try {
    // 超过容量时丢弃最旧的
    while (cache.dates.length > MAX_TRADE_DATES) {
      const old = cache.dates.pop()
      if (old) delete cache.data[old]
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cache))
  } catch {
    // localStorage 满（QuotaExceededError），丢弃所有缓存
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }
}

/**
 * 读取某交易日下某只股票的形态缓存
 * @returns 形态数组，无缓存返回 null
 */
export function getCachedPatterns(
  tradeDate: string,
  stockCode: string
): PatternKey[] | null {
  const cache = loadCache()
  return cache.data[tradeDate]?.[stockCode] ?? null
}

/**
 * 批量读取某交易日下多只股票的缓存
 * @returns Map<code, PatternKey[]>（仅包含有缓存的股票）
 */
export function getCachedPatternsBatch(
  tradeDate: string,
  stockCodes: string[]
): Map<string, PatternKey[]> {
  const cache = loadCache()
  const dateCache = cache.data[tradeDate]
  const result = new Map<string, PatternKey[]>()
  if (!dateCache) return result
  for (const code of stockCodes) {
    const patterns = dateCache[code]
    if (patterns) result.set(code, patterns)
  }
  return result
}

/**
 * 保存某只股票的形态结果
 * @param stockCode 股票代码
 * @param patterns 形态列表（空数组表示已计算但无命中，不缓存）
 */
export function setCachedPatterns(
  tradeDate: string,
  stockCode: string,
  patterns: PatternKey[]
): void {
  // 命中为空时不缓存，下次还需重新计算（避免永远错失新命中）
  if (patterns.length === 0) return

  const cache = loadCache()
  if (!cache.data[tradeDate]) {
    cache.data[tradeDate] = {}
    if (!cache.dates.includes(tradeDate)) {
      cache.dates.unshift(tradeDate)
    }
  }
  cache.data[tradeDate][stockCode] = patterns
  saveCache(cache)
}

/**
 * 清除某交易日下的所有缓存（用于切换交易日时强制刷新）
 */
export function clearTradeDateCache(tradeDate: string): void {
  const cache = loadCache()
  delete cache.data[tradeDate]
  cache.dates = cache.dates.filter(d => d !== tradeDate)
  saveCache(cache)
}

/**
 * 清除所有缓存（调试用）
 */
export function clearAllPatternCache(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
