/**
 * utils/klineCache.ts - K线数据 + 技术指标本地缓存
 *
 * 策略：
 * - LRU 缓存，最多 200 只股票（约 1.5-2MB，可控）
 * - 每只股票保留最近 100 个交易日的 K线 + 一次计算的指标
 * - 增量更新：下次请求时只取 lastDate 之后的数据
 * - 持久化到 localStorage（页面刷新仍生效）
 *
 * 收益：
 * - 第一次看 K线：全量拉 100 天
 * - 同日再次查看：纯本地读取，0 网络请求
 * - 隔日查看：只拉 1-2 天增量 + 合并
 * - 形态识别批量：优先复用单股缓存
 */

import type { KLineItem } from '../types'
import { computeAllIndicators, type IndicatorSeries } from './indicators'

const KLINE_STORAGE_KEY = 'quant.kline_cache.v1'
/** 最多缓存的股票数量（LRU 上限） */
const MAX_KLINE_ENTRIES = 200
/** 每只股票保留的天数 */
const KEEP_DAYS = 100

/** 单只股票的缓存条目 */
interface KLineEntry {
  /** 数据中最新一日（YYYY-MM-DD） */
  lastDate: string
  /** 数据中最旧一日（YYYY-MM-DD） */
  firstDate: string
  /** 最后访问时间（毫秒） */
  lastAccess: number
  /** K线数据（按日期从新到旧排序） */
  items: KLineItem[]
  /** 计算好的技术指标（基于 items） */
  indicators: IndicatorSeries
}

/** 缓存结构 */
interface CacheShape {
  entries: Record<string, KLineEntry>
}

function loadCache(): CacheShape {
  try {
    const raw = localStorage.getItem(KLINE_STORAGE_KEY)
    if (!raw) return { entries: {} }
    const parsed = JSON.parse(raw) as CacheShape
    if (!parsed.entries) return { entries: {} }
    return parsed
  } catch {
    return { entries: {} }
  }
}

function saveCache(cache: CacheShape): void {
  try {
    localStorage.setItem(KLINE_STORAGE_KEY, JSON.stringify(cache))
  } catch {
    // localStorage 满：丢弃最旧一半的条目后重试
    try {
      const codes = Object.keys(cache.entries)
      const half = Math.floor(codes.length / 2)
      const toRemove = codes
        .map(c => ({ code: c, t: cache.entries[c].lastAccess }))
        .sort((a, b) => a.t - b.t)
        .slice(0, half)
      toRemove.forEach(({ code }) => delete cache.entries[code])
      localStorage.setItem(KLINE_STORAGE_KEY, JSON.stringify(cache))
    } catch {
      // 仍然失败：清空缓存
      try {
        localStorage.removeItem(KLINE_STORAGE_KEY)
      } catch {
        /* ignore */
      }
    }
  }
}

/**
 * LRU 淘汰：当 entries 超过 MAX_KLINE_ENTRIES 时，删除最久未访问的
 */
function evictIfNeeded(cache: CacheShape): void {
  const codes = Object.keys(cache.entries)
  if (codes.length <= MAX_KLINE_ENTRIES) return

  const toRemove = codes
    .map(c => ({ code: c, t: cache.entries[c].lastAccess }))
    .sort((a, b) => a.t - b.t)
    .slice(0, codes.length - MAX_KLINE_ENTRIES)
  toRemove.forEach(({ code }) => delete cache.entries[code])
}

/**
 * 读取某只股票的缓存
 * @returns 缓存条目（并更新 lastAccess），无缓存返回 null
 */
export function getCachedKLine(code: string): KLineEntry | null {
  const cache = loadCache()
  const entry = cache.entries[code]
  if (!entry) return null
  // 更新访问时间（异步写回，不阻塞）
  entry.lastAccess = Date.now()
  // 静默持久化（高频操作时不打扰）
  scheduleSave(cache)
  return entry
}

/** 节流写：避免每次 get 都写 localStorage */
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave(cache: CacheShape): void {
  if (saveTimer) return
  saveTimer = setTimeout(() => {
    saveTimer = null
    saveCache(cache)
  }, 1000)
}

/**
 * 合并并保存 K线数据
 * @param code 股票代码
 * @param newItems 新拉取的 K线（从新到旧）
 * @returns 合并后的 K线 + 计算好的指标
 */
export function mergeAndCacheKLine(
  code: string,
  newItems: KLineItem[]
): { items: KLineItem[]; indicators: IndicatorSeries; lastDate: string } {
  const cache = loadCache()
  const existing = cache.entries[code]

  // 合并：按日期去重（保留较新数据，因为 newItems 是最新拉的）
  const map = new Map<string, KLineItem>()
  if (existing) {
    existing.items.forEach(it => map.set(it.trade_date, it))
  }
  newItems.forEach(it => map.set(it.trade_date, it))

  // 按日期从新到旧排序
  const merged = Array.from(map.values()).sort((a, b) =>
    b.trade_date.localeCompare(a.trade_date)
  )

  // 截取最近 KEEP_DAYS 天
  const trimmed = merged.slice(0, KEEP_DAYS)

  // 计算指标
  const indicators = computeAllIndicators(trimmed)

  // 写回缓存
  const lastDate = trimmed[0]?.trade_date ?? ''
  const firstDate = trimmed[trimmed.length - 1]?.trade_date ?? ''
  cache.entries[code] = {
    lastDate,
    firstDate,
    lastAccess: Date.now(),
    items: trimmed,
    indicators,
  }
  evictIfNeeded(cache)
  saveCache(cache)

  return { items: trimmed, indicators, lastDate }
}

/**
 * 检查某只股票是否已缓存（仅查不更新 lastAccess）
 */
export function hasCachedKLine(code: string): boolean {
  try {
    const raw = localStorage.getItem(KLINE_STORAGE_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw) as CacheShape
    return !!parsed.entries?.[code]
  } catch {
    return false
  }
}

/**
 * 清除某只股票的缓存
 */
export function clearKLineCache(code: string): void {
  const cache = loadCache()
  if (cache.entries[code]) {
    delete cache.entries[code]
    saveCache(cache)
  }
}

/**
 * 清除所有 K线缓存（调试用）
 */
export function clearAllKLineCache(): void {
  try {
    localStorage.removeItem(KLINE_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
