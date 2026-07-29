// src/features/stock-detail/api.ts
import axios from 'axios';

// ==================== 1. 通用响应结构 ====================
interface ApiResponse<T> {
  code?: number;
  message?: string;
  data: T;
  stock_code?: string;
}

// 成功状态码（后端实际返回 200，约定 0 或缺失 code 字段也视为成功）
const SUCCESS_CODES = [0, 200];

const unwrap = <T>(response: ApiResponse<T>): T => {
  // 检查业务状态码
  if (response.code !== undefined && !SUCCESS_CODES.includes(response.code)) {
    throw new Error(response.message || `业务错误 (code: ${response.code})`);
  }
  if (response.data !== undefined) return response.data;
  throw new Error(response.message || 'API Request Failed');
};

// ==================== 1b. 错误友好映射 ====================
const FRIENDLY_ERRORS: Record<string, string> = {
  'Request failed with status code 404': '数据接口不存在，请联系管理员',
  'Request failed with status code 500': '服务器繁忙，请稍后重试',
  'Request failed with status code 502': '网关超时，请稍后重试',
  'timeout of 0ms exceeded': '网络连接超时，请检查网络后重试',
  'Network Error': '网络连接失败，请检查网络后重试',
};

/**
 * 将 API 抛出的错误转换为用户友好的提示文本
 */
export function toFriendlyMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  for (const [key, val] of Object.entries(FRIENDLY_ERRORS)) {
    if (msg.includes(key)) return val;
  }
  return msg.length > 80 ? msg.substring(0, 80) + '...' : msg;
}

// ==================== 2. 类型定义 ====================
export interface StockListParams {
  listed_board?: string;
  industry?: string;
  area?: string;
  filters?: string;
  sort_by?: string;
  sort_asc?: boolean;
  offset?: number;
  limit?: number;
  as_of_date?: string;
  watchlist_only?: boolean;
  stock_codes?: string;
  [key: string]: any;
}

export interface StockItem {
  stock_code: string;
  stock_name: string;
  close: number;
  change_pct: number;
  market_cap?: number;
  pe?: number;
  pe_ttm?: number;
  pb?: number;
  volume?: number;
  amount?: number;
  turnover_rate?: number;
  listed_board?: string;
  industry?: string;
  area?: string;
  trade_date?: string;
  [key: string]: any;
}

export interface StockListResponse {
  items: StockItem[];
  total: number;
}

interface RawKLineItem {
  trade_date: string;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume: string | number;
  amount?: string | number | null;
  ma5?: string | number;
  ma10?: string | number;
  ma20?: string | number;
  rsi_6?: string | number;
  macd?: string | number;
  boll_upper?: string | number | null;
  boll_mid?: string | number | null;
  boll_lower?: string | number | null;
  pe_ttm?: string | number | null;
  turnover_rate?: string | number | null;
}

/** KLineResponse 的原始 JSON 结构（后端直接返回，非 ApiResponse 信封） */
interface KLineApiResponse {
  stock_code: string;
  data: RawKLineItem[];
  count: number;
  adj_method: string;
  pattern_markers?: PatternMarker[];
  warning?: string | null;
  latest_factor?: number | null;
}

export interface KLineItem {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  pe_ttm: number | null;
  turnover_rate: number | null;
}

/** 后端 TA-Lib 返回的单日形态标记 */
export interface PatternMarker {
  trade_date: string;
  patterns: string[];
}

/** K 线数据 + 形态标记的完整返回 */
export interface KLineDataResult {
  items: KLineItem[];
  patternMarkers: PatternMarker[];
}

export interface SignalItem {
  time: string;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  color: string;
  text?: string;
}

export interface StockDetailInfo {
  stock_code: string;
  stock_name: string;
  listed_board?: string;
  industry?: string;
  pe?: number;
  pb?: number;
  circ_mv?: number;
  market_cap?: number;
  change_pct?: number;
  close?: number;
}

// ==================== 3. API 封装 ====================
const api = axios.create({ baseURL: '/api' });

export const fetchStocks = async (
  params: StockListParams = {},
  signal?: AbortSignal,
): Promise<StockListResponse> => {
  const { data } = await api.get<ApiResponse<StockListResponse>>('/stocks/', {
    params,
    ...(signal ? { signal } : {}),
  });
  return unwrap(data);
};

export const fetchStockDetail = async (code: string): Promise<StockDetailInfo> => {
  const { data } = await api.get<ApiResponse<StockDetailInfo>>(`/stocks/${code}`);
  return unwrap(data);
};

export interface KLineFetchOptions {
  period?: string;
  limit?: number;
  adj?: 'none' | 'forward' | 'backward';
  start_date?: string;
  end_date?: string;
}

export const fetchKLineData = async (
  code: string,
  options?: KLineFetchOptions | string,
  signal?: AbortSignal,
): Promise<KLineDataResult> => {
  let params: Record<string, any> = {};
  if (typeof options === 'string') {
    params = { period: options };
  } else if (options) {
    if (options.period) params.period = options.period;
    if (options.limit) params.limit = options.limit;
    if (options.adj) params.adj = options.adj;
    if (options.start_date) params.start_date = options.start_date;
    if (options.end_date) params.end_date = options.end_date;
  }
  const { data } = await api.get<KLineApiResponse>(`/kline/${code}`, {
    params,
    ...(signal ? { signal } : {}),
  });

  // 提取 pattern_markers（KLineResponse 顶层字段）
  const patternMarkers: PatternMarker[] = Array.isArray(data?.pattern_markers)
    ? data.pattern_markers
    : [];

  // 提取 K 线数据数组（KLineResponse.data）
  const rawItems = data?.data ?? [];
  if (!Array.isArray(rawItems)) {
    return { items: [], patternMarkers };
  }

  const items: KLineItem[] = rawItems
    .map(item => ({
      time: item.trade_date,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
      volume: Number(item.volume),
      amount: item.amount != null ? Number(item.amount) : 0,
      pe_ttm: item.pe_ttm != null ? Number(item.pe_ttm) : null,
      turnover_rate: item.turnover_rate != null ? Number(item.turnover_rate) : null,
    }))
    .filter(item => !isNaN(item.open));

  return { items, patternMarkers };
};

export const fetchSignals = async (code: string): Promise<SignalItem[]> => {
  const { data } = await api.get<ApiResponse<SignalItem[]>>(`/signals/${code}`);
  const list = unwrap(data);
  return Array.isArray(list) ? list : [];
};

// ==================== 4. 股票搜索（代码/名称模糊匹配） ====================
export interface StockSearchItem {
  stock_code: string;  // e.g., "000001" (不含后缀)
  stock_name: string;  // e.g., "平安银行"
  close?: number;
  change_pct?: number;
  [key: string]: any;
}

export interface StockSearchResponse {
  items: StockSearchItem[];
  total: number;
}

export const searchStocks = async (
  keyword: string,
  page = 1,
  pageSize = 20,
): Promise<StockSearchResponse> => {
  const { data } = await api.get<ApiResponse<StockSearchResponse>>('/stocks/search', {
    params: { keyword, page, page_size: pageSize },
  });
  return unwrap(data);
};
