/**
 * hooks/useKLineData.ts - 单只股票 K线数据（含本地缓存 + 增量更新 + 指标）
 *
 * 数据流：
 * 1. 立即从 localStorage 读取（如有），秒级首屏
 * 2. 后台拉取增量数据（仅 lastDate 之后）
 * 3. 合并 + 计算技术指标 + 回写缓存
 *
 * 返回的 data 为最终合并后的 K线，可直接用于图表。
 * 计算好的 indicators 也会随 data 一起返回（可选用）。
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchKline } from '../api'
import type { KLineItem } from '../types'
import {
  getCachedKLine,
  mergeAndCacheKLine,
} from '../utils/klineCache'
import type { IndicatorSeries } from '../utils/indicators'

interface UseKLineDataOptions {
  limit?: number
  period?: string
}

interface UseKLineDataReturn {
  data: KLineItem[]
  indicators: IndicatorSeries | null
  loading: boolean
  error: string | null
  stockCode: string | null
  /** true 表示当前是从本地缓存秒级返回，false 表示已发网络请求 */
  fromCache: boolean
  fetchData: (code: string) => Promise<void>
  clearData: () => void
}

export function useKLineData(
  options: UseKLineDataOptions = {}
): UseKLineDataReturn {
  const { limit = 120, period = 'daily' } = options

  const [data, setData] = useState<KLineItem[]>([])
  const [indicators, setIndicators] = useState<IndicatorSeries | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stockCode, setStockCode] = useState<string | null>(null)
  const [fromCache, setFromCache] = useState(false)

  const abortControllerRef = useRef<AbortController | null>(null)

  const fetchData = useCallback(
    async (code: string) => {
      if (!code) return

      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      const controller = new AbortController()
      abortControllerRef.current = controller

      setStockCode(code)
      setError(null)
      setFromCache(false)

      // ========== 第 1 步：先读本地缓存（秒级首屏） ==========
      const cached = getCachedKLine(code)
      if (cached && cached.items.length > 0) {
        setData(cached.items)
        setIndicators(cached.indicators)
        setFromCache(true)
        setLoading(false)

        // 如果缓存最新日期就是今天（或最近），无需网络请求
        const today = new Date().toISOString().slice(0, 10)
        if (cached.lastDate >= today) return
      } else {
        setLoading(true)
      }

      // ========== 第 2 步：拉取缺失数据 ==========
      try {
        // 增量：start_date 取缓存次新日（不是最新，因为最新可能更新了收盘价）
        // 简单起见：取 lastDate 后一天开始
        const startDate = cached?.lastDate
          ? nextTradeDate(cached.lastDate)
          : undefined
        // 如果缓存已有 limit 条，理论上增量只有几条；但为了保险仍用 limit
        const fetchLimit = cached ? Math.max(limit, 30) : limit

        const apiResponse = await fetchKline(
          code,
          period,
          startDate,
          undefined,
          fetchLimit,
          controller.signal
        )

        if (!apiResponse) return // 已中止

        console.log('useKLineData: API 响应:', apiResponse)

        // 解析 ApiResponse 信封
        const response = apiResponse?.data

        if (!response) {
          console.warn('useKLineData: API 响应中无 data')
          if (!cached) {
            setData([])
            setIndicators(null)
          }
          return
        }

        console.log('useKLineData: K线数据:', response)

        // 拉到了才需要合并并显示 loading
        if (response.data && response.data.length > 0) {
          // 合并 + 写回缓存
          const merged = mergeAndCacheKLine(code, response.data)
          console.log('useKLineData: 合并后数据:', merged)
          setData(merged.items)
          setIndicators(merged.indicators)
        } else if (!cached) {
          // 缓存空 + 接口空 → 无数据
          setData([])
          setIndicators(null)
        }
        setFromCache(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        // 网络失败但有缓存 → 静默使用缓存
        if (!cached) {
          setError(err instanceof Error ? err.message : '获取K线数据失败')
        }
      } finally {
        if (abortControllerRef.current === controller) {
          setLoading(false)
          abortControllerRef.current = null
        }
      }
    },
    [limit, period]
  )

  const clearData = useCallback(() => {
    setData([])
    setIndicators(null)
    setError(null)
    setStockCode(null)
    setFromCache(false)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }, [])

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return {
    data,
    indicators,
    loading,
    error,
    stockCode,
    fromCache,
    fetchData,
    clearData,
  }
}

/**
 * 计算下一交易日（简化：直接 +1 天）
 * 后端若是非交易日返回空，所以不需要严格判断
 */
function nextTradeDate(date: string): string {
  const d = new Date(date + 'T00:00:00')
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}
