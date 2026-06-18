import axios from 'axios';

// ==================== 1. 通用响应结构 (适配 Swagger ApiResponse) ====================
interface ApiResponse<T> {
  code?: number;
  message?: string;
  data: T;
  stock_code?: string; // 兼容 K线接口的特殊包装
}

const unwrap = <T>(response: ApiResponse<T>): T => {
  if (response.data !== undefined) return response.data;
  throw new Error(response.message || 'API Request Failed');
};

// ==================== 2. 类型定义 ====================

// 股票列表筛选参数
export interface StockListParams {
  listed_board?: string;        // 上市板块（逗号分隔）
  industry?: string;            // 行业（逗号分隔）
  area?: string;                // 地区（逗号分隔）
  filters?: string;             // 形态筛选（逗号分隔）
  sort_by?: string;             // 排序字段
  sort_asc?: boolean;           // 是否升序
  offset?: number;              // 分页偏移量
  limit?: number;               // 每页数量
  as_of_date?: string;          // 数据截止日期
  watchlist_only?: boolean;     // 仅看自选
  // 范围参数（动态）
  [key: string]: any;
}

// 单只股票（来自后端 StockResponse）
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

// 股票列表响应
export interface StockListResponse {
  items: StockItem[];
  total: number;
}

// 后端原始 K 线数据 (Swagger: KLineItem)
interface RawKLineItem {
  trade_date: string;   // 注意：后端用 trade_date
  open: string | number; // 注意：后端可能是字符串
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

// 前端图表标准数据 (Lightweight Charts 要求)
export interface KLineItem {
  time: string;       // 必须是 time
  open: number;       // 必须是 number
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

/**
 * 获取股票列表（选股接口）
 * 响应路径：json.data.items + json.data.total
 *
 * K 2026-06-18 任务 #11：可选 signal 参数用于取消上次未完成的请求，
 * 防止用户快速多次点击"开始选股"时旧数据覆盖新数据。
 */
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

/**
 * 获取股票详情
 */
export const fetchStockDetail = async (code: string): Promise<StockDetailInfo> => {
  const { data } = await api.get<ApiResponse<StockDetailInfo>>(`/stocks/${code}`);
  return unwrap(data);
};

/**
 * 获取K线数据 (核心修复：解包 + 字段映射 + 类型转换)
 */
export const fetchKLineData = async (code: string): Promise<KLineItem[]> => {
  const { data } = await api.get<ApiResponse<RawKLineItem[]>>(`/kline/${code}`);
  const rawList = unwrap(data);
  
  if (!Array.isArray(rawList)) return [];

  // ✅ 关键转换逻辑
  return rawList.map(item => ({
    time: item.trade_date,                    // trade_date -> time
    open: Number(item.open),                  // string -> number
    high: Number(item.high),
    low: Number(item.low),
    close: Number(item.close),
    volume: Number(item.volume),
  })).filter(item => !isNaN(item.open));      // 过滤脏数据
};

/**
 * 获取买卖信号
 */
export const fetchSignals = async (code: string): Promise<SignalItem[]> => {
  const { data } = await api.get<ApiResponse<SignalItem[]>>(`/signals/${code}`);
  const list = unwrap(data);
  return Array.isArray(list) ? list : [];
};