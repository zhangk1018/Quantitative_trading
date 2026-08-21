/**
 * stock.ts — 股票搜索 & 券商适配器 API
 */
import { apiGet } from './client';
import { API_PREFIX } from '@/config/constants';
import type { StockSearchResult, BrokerAdapter, ListData } from '../types';

const BASE = API_PREFIX;

/** 搜索股票代码 */
export async function searchStocks(q: string): Promise<StockSearchResult[]> {
  // 后端返回 data=纯数组（非 {items: [...]}），Axios 拦截器已自动解包 body.data
  return apiGet<StockSearchResult[]>(`${BASE}/stocks/search`, { params: { q } });
}

/** 获取可用券商适配器列表 */
export async function fetchBrokerAdapters(): Promise<BrokerAdapter[]> {
  const result = await apiGet<ListData<BrokerAdapter>>(`${BASE}/import/brokers`);
  return result.items;
}