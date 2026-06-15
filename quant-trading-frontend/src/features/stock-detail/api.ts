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