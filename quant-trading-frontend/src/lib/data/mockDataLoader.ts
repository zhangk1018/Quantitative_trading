/**
 * Mock 数据加载层
 *
 * 通过 VITE_USE_MOCK 环境变量控制数据源：
 * - true: 从 mock_snapshot.json 加载本地 Mock 数据
 * - false: 请求真实后端 API 端点
 *
 * 核心原则：业务代码零侵入 —— 组件层无感知数据源切换。
 */

import type { StockSnapshot, OHLCVArray, PatternType } from '../indicators/types';

// ==================== 类型定义 ====================

export interface SnapshotAllResponse {
  latest_trade_date: string;
  total: number;
  stocks: StockSnapshot[];
}

export interface SnapshotIncrementalResponse {
  latest_trade_date: string;
  stocks: StockSnapshot[];
}

// ==================== 环境开关 ====================

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

// ==================== Mock 实现 ====================

let mockCache: SnapshotAllResponse | null = null;

async function loadMockAll(): Promise<SnapshotAllResponse> {
  if (mockCache) return mockCache;
  const resp = await fetch('/mock_snapshot.json');
  const raw = await resp.json();

  // 格式适配：mock_snapshot.json 当前是 { stocks: [...] } 格式
  const stocks: StockSnapshot[] = (raw.stocks || raw.data?.stocks || []).map((s: any) => ({
    code: s.code,
    name: s.name,
    listed_board: s.listed_board || '',
    industry: s.industry || '',
    trade_date: s.trade_date || raw.latest_trade_date || '',
    close: Number(s.close ?? 0),
    change_pct: Number(s.change_pct ?? 0),
    market_cap: Number(s.market_cap ?? 0),
    turnover_rate: Number(s.turnover_rate ?? 0),
    pe_ttm: Number(s.pe_ttm ?? 0),
    pb: Number(s.pb ?? 0),
    indicators: s.indicators || {
      ma5: 0, ma10: 0, ma20: 0, ma60: null,
      rsi_6: 0, rsi_12: 0, rsi_24: 0,
      macd_dif: 0, macd_dea: 0, macd: 0,
      boll_upper: 0, boll_mid: 0, boll_lower: 0,
      is_macd_golden_cross: 0, is_macd_dead_cross: 0,
    },
    ohlcv: (s.ohlcv || []).map((row: number[]) =>
      row.length >= 6
        ? ([row[0], row[1], row[2], row[3], row[4], row[5]] as OHLCVArray)
        : ([0, 0, 0, 0, 0, 0] as OHLCVArray),
    ),
  }));

  const result: SnapshotAllResponse = {
    latest_trade_date: raw.latest_trade_date || stocks[0]?.trade_date || '',
    total: stocks.length,
    stocks,
  };

  mockCache = result;
  return result;
}

async function loadMockIncremental(since: string): Promise<SnapshotIncrementalResponse> {
  const all = await loadMockAll();
  const filtered = all.stocks.filter((s) => s.trade_date >= since);
  return {
    latest_trade_date: all.latest_trade_date,
    stocks: filtered,
  };
}

// ==================== 真实 API 实现 ====================

async function fetchRealAll(): Promise<SnapshotAllResponse> {
  const resp = await fetch('/api/snapshot/all');
  const json = await resp.json();
  return json.data;
}

async function fetchRealIncremental(since: string): Promise<SnapshotIncrementalResponse> {
  const resp = await fetch(`/api/snapshot/incremental?since=${since}`);
  const json = await resp.json();
  return json.data;
}

// ==================== 统一导出（调用方无感知） ====================

export async function fetchSnapshotAll(): Promise<SnapshotAllResponse> {
  return USE_MOCK ? loadMockAll() : fetchRealAll();
}

export async function fetchSnapshotIncremental(since: string): Promise<SnapshotIncrementalResponse> {
  return USE_MOCK ? loadMockIncremental(since) : fetchRealIncremental(since);
}

/** 从全量快照中筛选指定股票的 OHLCV 数据 */
export function getStockOHLCV(
  stocks: StockSnapshot[],
  code: string,
): OHLCVArray[] {
  return stocks.find((s) => s.code === code)?.ohlcv ?? [];
}

/** 从全量快照获取股票列表（不含 OHLCV，用于表格展示） */
export function getStockList(stocks: StockSnapshot[]): StockSnapshot[] {
  return stocks.map(({ ohlcv, ...rest }) => ({
    ...rest,
    ohlcv: [],
  }));
}