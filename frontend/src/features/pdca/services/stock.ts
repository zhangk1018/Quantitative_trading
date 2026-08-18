/**
 * stock.ts — 股票搜索 & 券商适配器 API
 */
import client from './client';
import { API_PREFIX } from '@/config/constants';
import type { StockSearchResult, BrokerAdapter, ListData } from '../types';

const BASE = API_PREFIX;

/** 搜索股票代码 */
export async function searchStocks(q: string): Promise<StockSearchResult[]> {
  const { data } = await client.get<ListData<StockSearchResult>>(`${BASE}/stocks/search`, { params: { q } });
  return data.items;
}

/** 获取可用券商适配器列表 */
export async function fetchBrokerAdapters(): Promise<BrokerAdapter[]> {
  const { data } = await client.get<ListData<BrokerAdapter>>(`${BASE}/import/brokers`);
  return data.items;
}