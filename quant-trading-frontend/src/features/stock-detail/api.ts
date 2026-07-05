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
  amount?: string | number;
  ma5?: string | number;
  ma10?: string | number;
  ma20?: string | number;
  rsi_6?: string | number;
  macd?: string | number;
  boll_upper?: string | number | null;
  boll_mid?: string | number | null;
  boll_lower?: string | number | null;
}

export interface KLineItem {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
}

export const fetchKLineData = async (
  code: string,
  options?: KLineFetchOptions | string,
  signal?: AbortSignal,
): Promise<KLineItem[]> => {
  let params: Record<string, any> = {};
  if (typeof options === 'string') {
    params = { period: options };
  } else if (options) {
    if (options.period) params.period = options.period;
    if (options.limit) params.limit = options.limit;
    if (options.adj) params.adj = options.adj;
  }
  const { data } = await api.get<ApiResponse<RawKLineItem[]>>(`/kline/${code}`, {
    params,
    ...(signal ? { signal } : {}),
  });
  const rawList = unwrap(data);
  if (!Array.isArray(rawList)) return [];

  return rawList
    .map(item => ({
      time: item.trade_date,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
      volume: Number(item.volume),
    }))
    .filter(item => !isNaN(item.open));
};

export const fetchSignals = async (code: string): Promise<SignalItem[]> => {
  const { data } = await api.get<ApiResponse<SignalItem[]>>(`/signals/${code}`);
  const list = unwrap(data);
  return Array.isArray(list) ? list : [];
};