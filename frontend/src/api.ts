/**
 * api.ts - API 调用函数封装
 * 
 * 统一接口请求封装，支持 AbortController 取消请求
 * 所有 API 返回 ApiResponse<T> 格式
 * 
 * 注意：所有路径必须带尾部斜杠，否则 FastAPI 会返回 307 重定向
 */

import type {
  ApiResponse,
  MetaResponseData,
  StockResponse,
  StocksRequest,
  KLineResponse,
  SignalResponse
} from './types'

const BASE = '/api'

/**
 * 通用请求配置
 */
interface RequestConfig {
  signal?: AbortSignal
}

/**
 * 获取元数据（行业/地区选项）
 * 
 * @returns 元数据响应
 */
export async function fetchMeta(signal?: AbortSignal): Promise<ApiResponse<MetaResponseData>> {
  const res = await fetch(`${BASE}/meta/`, { signal })
  if (!res.ok) throw new Error(`/api/meta/ failed: ${res.status}`)
  return res.json()
}

/**
 * 获取股票列表（支持筛选、排序、分页）
 * 
 * @param params 查询参数
 * @param params.signal 可选的取消信号
 * @returns 股票列表响应（包含分页信息）
 */
export interface StockListResponse {
  items: StockResponse[]
  total: number
  offset: number
  limit: number
}

export async function fetchStocks(
  params: Omit<StocksRequest, 'sort_asc' | 'filters'> & { sort_asc?: boolean; filters?: string },
  config?: RequestConfig
): Promise<ApiResponse<StockListResponse>> {
  const p = new URLSearchParams()
  
  // 可选参数
  if (params.listed_board) p.set('listed_board', params.listed_board)
  if (params.industry) p.set('industry', params.industry)
  if (params.area) p.set('area', params.area)
  if (params.filters) p.set('filters', params.filters)
  
  // 必填参数
  p.set('sort_by', params.sort_by)
  p.set('sort_asc', String(params.sort_asc ?? false))
  p.set('offset', String(params.offset ?? 0))
  p.set('limit', String(params.limit ?? 100))
  p.set('as_of_date', params.as_of_date)

  const res = await fetch(`${BASE}/stocks/?${p}`, { signal: config?.signal })
  if (!res.ok) throw new Error(`/api/stocks/ failed: ${res.status}`)
  return res.json()
}

/**
 * 获取K线数据
 *
 * 注意：后端 kline API 返回的是裸 KLineResponse（无 ApiResponse 信封包装）
 *
 * @param code 股票代码
 * @param period K线周期（默认: daily）
 * @param startDate 开始日期（可选）
 * @param endDate 结束日期（可选）
 * @param limit 数据条数限制（默认: 150，与后端 kline 接口对齐）
 * @param signal 可选的取消信号
 * @returns K线数据响应（请求被中止时返回 null）
 */
export async function fetchKline(
  code: string,
  period: string = 'daily',
  startDate?: string,
  endDate?: string,
  limit: number = 150,
  signal?: AbortSignal
): Promise<KLineResponse | null> {
  const params = new URLSearchParams()
  params.set('period', period)
  params.set('limit', String(limit))
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)

  try {
    const res = await fetch(`${BASE}/kline/${code}?${params}`, { signal })
    if (!res.ok) throw new Error(`/api/kline failed: ${res.status}`)
    return res.json()
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') return null
    throw e
  }
}

/**
 * 获取买卖信号
 *
 * @param code 股票代码
 * @param signalType 信号类型（可选）
 * @param startDate 开始日期（可选）
 * @param endDate 结束日期（可选）
 * @param limit 数据条数限制（默认: 100）
 * @param signal 可选的取消信号
 * @returns 买卖信号响应
 */
export async function fetchSignals(
  code: string,
  signalType?: string,
  startDate?: string,
  endDate?: string,
  limit: number = 100,
  signal?: AbortSignal
): Promise<SignalResponse> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (signalType) params.set('signal_type', signalType)
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)

  const res = await fetch(`${BASE}/signals/${code}?${params}`, { signal })
  if (!res.ok) throw new Error(`/api/signals failed: ${res.status}`)
  return res.json()
}

/**
 * 获取单只股票详情（基本面 + 行情 + 估值 + 指标 + 形态）
 *
 * 对应后端: GET /api/stocks/{stock_code}
 *
 * @param stockCode 股票代码（支持纯数字 000001 或带前缀 SH600000）
 * @param signal 可选的取消信号
 * @returns 股票详情响应（请求被中止时返回 null）
 */
export async function fetchStockByCode(
  stockCode: string,
  signal?: AbortSignal
): Promise<ApiResponse<StockResponse> | null> {
  if (!stockCode) {
    throw new Error('fetchStockByCode: stockCode is required')
  }

  try {
    const res = await fetch(`${BASE}/stocks/${encodeURIComponent(stockCode)}/`, { signal })
    if (!res.ok) throw new Error(`/api/stocks/${stockCode}/ failed: ${res.status}`)
    return res.json()
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') return null
    throw e
  }
}

// ============================================
// 自选股 CRUD（对应后端 /api/watchlist/）
// ============================================

/** 自选股项（与后端 WatchlistItem 对齐） */
export interface WatchlistItem {
  id: number
  code: string
  group_name: string
  sort_order: number
  created_at?: string | null
}

/**
 * 获取自选股列表
 * 对应后端: GET /api/watchlist/?user_id=xxx
 */
export async function fetchWatchlist(
  userId: string = 'default',
  signal?: AbortSignal
): Promise<ApiResponse<WatchlistItem[]>> {
  const res = await fetch(`${BASE}/watchlist/?user_id=${encodeURIComponent(userId)}`, { signal })
  if (!res.ok) throw new Error(`/api/watchlist/ failed: ${res.status}`)
  return res.json()
}

/**
 * 添加自选股
 * 对应后端: POST /api/watchlist/
 */
export async function addWatchlist(
  code: string,
  groupName?: string,
  userId: string = 'default'
): Promise<ApiResponse<WatchlistItem>> {
  const res = await fetch(`${BASE}/watchlist/?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, group_name: groupName }),
  })
  const data = await res.json()
  if (!res.ok) {
    // 业务错误：404/409/500 也返回 ApiResponse
    return data
  }
  return data
}

/**
 * 移除自选股
 * 对应后端: DELETE /api/watchlist/{code}?user_id=xxx
 */
export async function deleteWatchlist(
  code: string,
  userId: string = 'default'
): Promise<ApiResponse<null>> {
  const res = await fetch(
    `${BASE}/watchlist/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`,
    { method: 'DELETE' }
  )
  if (!res.ok) throw new Error(`/api/watchlist/${code} DELETE failed: ${res.status}`)
  return res.json()
}

/**
 * 更新自选股（分组/排序）
 * 对应后端: PATCH /api/watchlist/{code}
 */
export async function updateWatchlist(
  code: string,
  updates: { group_name?: string; sort_order?: number },
  userId: string = 'default'
): Promise<ApiResponse<WatchlistItem>> {
  const res = await fetch(
    `${BASE}/watchlist/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }
  )
  if (!res.ok) throw new Error(`/api/watchlist/${code} PATCH failed: ${res.status}`)
  return res.json()
}