/**
 * 股票快照数据工具函数
 *
 * 从 mockDataLoader.ts 剥离，与 Mock/真实数据加载层解耦。
 */

import type { StockSnapshot, OHLCVArray } from '../lib/indicators/types';

/** 按股票代码提取 OHLCV 行情数据 */
export function getStockOHLCV(
  stocks: StockSnapshot[],
  code: string,
): OHLCVArray[] {
  if (!Array.isArray(stocks) || typeof code !== 'string' || !code) return [];
  return stocks.find((item) => item.code === code)?.ohlcv ?? [];
}

/** 生成表格专用精简股票列表（剥离大容量 ohlcv） */
export function getStockList(stocks: StockSnapshot[]): StockSnapshot[] {
  if (!Array.isArray(stocks)) return [];
  return stocks.map(({ ohlcv, ...rest }) => ({
    ...rest,
    ohlcv: [],
  }));
}