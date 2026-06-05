/**
 * hooks/useBatchKLine.ts - 批量识别 K线形态
 *
 * 三级缓存策略：
 * 1. patternCache（按 trade_date）→ 形态结果（最上层）
 * 2. klineCache（按 stock_code，100 天）→ K线数据 + 指标（中间层）
 * 3. fetchKline API（兜底）→ 网络请求
 *
 * 流程：
 * 1. 查 patternCache：命中直接用
 * 2. 未命中：查 klineCache：有 5+ 条 K线则直接计算形态
 * 3. klineCache 没有：fetchKline → 写 klineCache → 计算形态
 * 4. 形态结果回写 patternCache
 *
 * tradeDate 由调用方传入（用于按天隔离形态缓存）
 */

import { useState, useCallback, useRef } from 'react'
import { fetchKline } from '../api'
import type { KLineItem } from '../types'
import {
  getCachedPatternsBatch,
  setCachedPatterns,
} from '../utils/patternCache'
import {
  getCachedKLine,
  mergeAndCacheKLine,
} from '../utils/klineCache'
import { detectPatterns, type PatternKey } from '../utils/patternDetector'

interface UseBatchKLineReturn {
  /** key: stock_code, value: 命中的形态列表（已合并 cache + 新计算） */
  patterns: Record<string, PatternKey[]>
  loading: boolean
  error: string | null
  progress: { current: number; total: number }
  /** 形态缓存命中数 */
  patternCacheHits: number
  /** K线缓存命中数（形态未命中但 K线已缓存） */
  klineCacheHits: number
  fetchBatch: (codes: string[], tradeDate: string, limit?: number) => Promise<void>
  clear: () => void
}

const MAX_CONCURRENCY = 6 // 最大并发数

export function useBatchKLine(): UseBatchKLineReturn {
  const [patterns, setPatterns] = useState<Record<string, PatternKey[]>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [patternCacheHits, setPatternCacheHits] = useState(0)
  const [klineCacheHits, setKlineCacheHits] = useState(0)
  const abortRef = useRef<AbortController | null>(null)

  const fetchBatch = useCallback(
    async (codes: string[], tradeDate: string, limit = 5) => {
      if (codes.length === 0) return

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setLoading(true)
      setError(null)
      setProgress({ current: 0, total: codes.length })

      // ========== 第 1 步：查 patternCache ==========
      const patternCached = getCachedPatternsBatch(tradeDate, codes)
      const patternHitCodes = new Set(patternCached.keys())
      const patternMissCodes = codes.filter(c => !patternHitCodes.has(c))
      setPatternCacheHits(patternHitCodes.size)

      const merged: Record<string, PatternKey[]> = {}
      patternCached.forEach((p, code) => {
        merged[code] = p
      })
      setPatterns(merged)
      setProgress({ current: patternHitCodes.size, total: codes.length })

      if (patternMissCodes.length === 0) {
        setLoading(false)
        return
      }

      // ========== 第 2 步：查 klineCache ==========
      const klineReady: string[] = []
      const needFetch: string[] = []
      patternMissCodes.forEach(code => {
        const cached = getCachedKLine(code)
        if (cached && cached.items.length >= limit) {
          // 直接用 K线缓存计算形态
          const patterns = detectPatterns(cached.items)
          if (patterns.length > 0) {
            setCachedPatterns(tradeDate, code, patterns)
            merged[code] = patterns
            setPatterns({ ...merged })
          } else {
            // 不缓存空结果，但仍计入完成
            merged[code] = []
          }
          klineReady.push(code)
        } else {
          needFetch.push(code)
        }
      })
      setKlineCacheHits(klineReady.length)
      setProgress({
        current: patternHitCodes.size + klineReady.length,
        total: codes.length,
      })

      if (needFetch.length === 0) {
        setLoading(false)
        return
      }

      // ========== 第 3 步：网络拉取 ==========
      const queue = [...needFetch]
      let completed = 0
      let failed = 0
      let aborted = false

      const worker = async () => {
        while (queue.length > 0) {
          if (controller.signal.aborted) {
            aborted = true
            return
          }
          const code = queue.shift()
          if (!code) return

          try {
            // 已缓存的会传 startDate 增量；未缓存的不传
            const cached = getCachedKLine(code)
            const startDate = cached?.lastDate
              ? nextTradeDate(cached.lastDate)
              : undefined
            const fetchLimit = cached ? Math.max(limit, 30) : limit

            const apiRes = await fetchKline(
              code,
              'daily',
              startDate,
              undefined,
              fetchLimit,
              controller.signal
            )
            const res = apiRes?.data
            console.log('useBatchKLine:', code, 'API 响应:', apiRes)
            if (res?.data && res.data.length > 0) {
              // 写 klineCache（同时计算并缓存 indicators）
              const mergedK = mergeAndCacheKLine(code, res.data)
              // 用合并后的 K线计算形态（确保有完整 5 根）
              const klinesForPattern: KLineItem[] = mergedK.items.slice(0, limit)
              const patterns = detectPatterns(klinesForPattern)
              if (patterns.length > 0) {
                setCachedPatterns(tradeDate, code, patterns)
                merged[code] = patterns
              } else {
                merged[code] = []
              }
              setPatterns({ ...merged })
            }
          } catch (e) {
            if (e instanceof Error && e.name === 'AbortError') {
              aborted = true
              return
            }
            failed++
          } finally {
            completed++
            setProgress({
              current:
                patternHitCodes.size + klineReady.length + completed,
              total: codes.length,
            })
          }
        }
      }

      const workers = Array.from(
        { length: Math.min(MAX_CONCURRENCY, needFetch.length) },
        () => worker()
      )
      await Promise.all(workers)

      if (!aborted) {
        if (failed > 0 && needFetch.length === failed) {
          setError(`批量获取 K线失败 (${failed}/${needFetch.length})`)
        }
        setLoading(false)
      }
    },
    []
  )

  const clear = useCallback(() => {
    abortRef.current?.abort()
    setPatterns({})
    setError(null)
    setProgress({ current: 0, total: 0 })
    setPatternCacheHits(0)
    setKlineCacheHits(0)
  }, [])

  return {
    patterns,
    loading,
    error,
    progress,
    patternCacheHits,
    klineCacheHits,
    fetchBatch,
    clear,
  }
}

/** 计算下一日期（YYYY-MM-DD + 1 天） */
function nextTradeDate(date: string): string {
  const d = new Date(date + 'T00:00:00')
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}
