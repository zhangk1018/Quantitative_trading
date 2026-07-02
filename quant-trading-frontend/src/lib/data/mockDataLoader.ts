/**
 * Mock 数据加载层
 *
 * 通过 VITE_USE_MOCK 环境变量控制数据源：
 * - true: 从 mock_snapshot.json 加载本地 Mock 数据
 * - false: 请求真实后端 API 端点
 *
 * 核心原则：业务代码零侵入 —— 组件层无感知数据源切换。
 * 改造说明：
 * 1. 统一 Result 结构体返回，上层可区分空数据/接口异常
 * 2. 增加 pendingPromise 解决并发重复请求，异常时重置pending状态避免永久阻塞
 * 3. 统一 Mock/真实API 数据契约，强制标准 { data: {...} } 格式
 * 4. 日期对比使用时间戳，前置校验日期合法性，拦截NaN时间戳
 * 5. OHLCV 支持字符串数字转数值，NaN兜底0
 * 6. 所有接口统一返回 FetchResult<T>，异常不会静默吞噬
 * 7. 移除业务清洗工具函数，解耦至独立工具模块
 * 8. 增量参数url编码，请求统一超时+abort控制，区分超时错误
 * 9. 强化类型守卫，同时校验属性存在+字段类型，过滤脏数据
 * 10. 真实API增加运行时结构校验，避免类型断言掩盖数据异常
 */
import type { StockSnapshot, OHLCVArray } from '../indicators/types';

// ==================== 统一返回结果类型（解决异常静默吞噬） ====================
export interface FetchResult<T> {
  data: T | null;
  error: string | null;
}

// ==================== 业务响应类型 ====================
export interface SnapshotAllResponse {
  latest_trade_date: string;
  total: number;
  stocks: StockSnapshot[];
}
export interface SnapshotIncrementalResponse {
  latest_trade_date: string;
  stocks: StockSnapshot[];
}

// ==================== 环境常量 ====================
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
const REQUEST_TIMEOUT = 10000;

// ==================== 缓存状态（解决并发重复请求） ====================
let mockCache: SnapshotAllResponse | null = null;
let pendingAllPromise: Promise<SnapshotAllResponse> | null = null;

// ==================== 通用工具 ====================
/** 带超时中断的统一请求封装 */
async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
  try {
    const response = await fetch(input, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * 强化类型守卫：校验单条股票快照合法性
 * 同时校验：属性存在 + 字段基础类型，避免脏数字/空值流入计算逻辑
 */
function isValidStockSnapshot(data: unknown): data is StockSnapshot {
  if (typeof data !== 'object' || data === null) return false;
  const item = data as Record<string, unknown>;
  return (
    typeof item.code === 'string' &&
    typeof item.name === 'string' &&
    typeof item.trade_date === 'string' &&
    !Number.isNaN(Number(item.close)) &&
    Array.isArray(item.ohlcv)
  );
}

/** 标准化OHLCV单条行数据，兼容字符串数字、补齐6位 */
function normalizeOHLCVRow(rawRow: unknown[]): OHLCVArray {
  const sliceRow = rawRow.slice(0, 6);
  const normalized = sliceRow.map((item) => {
    const num = Number(item);
    return Number.isNaN(num) ? 0 : num;
  });
  // 不足6位补0
  while (normalized.length < 6) normalized.push(0);
  return normalized as OHLCVArray;
}

// ==================== Mock 数据源实现 ====================
async function loadMockAll(): Promise<SnapshotAllResponse> {
  // 命中内存缓存直接返回
  if (mockCache) return mockCache;
  // 正在请求中，复用pending Promise，防止并发重复请求
  if (pendingAllPromise) return pendingAllPromise;

  pendingAllPromise = (async () => {
    try {
      const resp = await fetchWithTimeout('/mock_snapshot.json');
      const raw = await resp.json();
      // 统一契约：强制 mock 文件格式 { data: { stocks: [], latest_trade_date } }
      const source = raw.data ?? {};
      const rawStocks = Array.isArray(source.stocks) ? source.stocks : [];

      const stocks: StockSnapshot[] = [];
      for (const item of rawStocks) {
        if (!isValidStockSnapshot(item)) {
          console.warn('非法股票快照数据已跳过', item);
          continue;
        }
        stocks.push({
          code: item.code,
          name: item.name,
          listed_board: (item.listed_board as string) || '',
          industry: (item.industry as string) || '',
          trade_date: item.trade_date || source.latest_trade_date || '',
          close: Number(item.close ?? 0),
          change_pct: Number(item.change_pct ?? 0),
          market_cap: Number(item.market_cap ?? 0),
          turnover_rate: Number(item.turnover_rate ?? 0),
          pe_ttm: Number(item.pe_ttm ?? 0),
          pb: Number(item.pb ?? 0),
          indicators: (item.indicators as StockSnapshot['indicators']) || {
            ma5: 0, ma10: 0, ma20: 0, ma60: null,
            rsi_6: 0, rsi_12: 0, rsi_24: 0,
            macd_dif: 0, macd_dea: 0, macd: 0,
            boll_upper: 0, boll_mid: 0, boll_lower: 0,
            is_macd_golden_cross: 0, is_macd_dead_cross: 0,
          },
          ohlcv: Array.isArray(item.ohlcv)
            ? item.ohlcv.map(normalizeOHLCVRow)
            : [],
        });
      }

      const result: SnapshotAllResponse = {
        latest_trade_date: source.latest_trade_date || stocks[0]?.trade_date || '',
        total: stocks.length,
        stocks,
      };
      mockCache = result;
      pendingAllPromise = null;
      return result;
    } catch (e) {
      // 请求异常重置pending，允许后续重试
      pendingAllPromise = null;
      throw e;
    }
  })();

  return pendingAllPromise;
}

async function loadMockIncremental(since: string): Promise<SnapshotIncrementalResponse> {
  // 前置校验日期合法性，拦截NaN时间戳
  const sinceTs = new Date(since).getTime();
  if (Number.isNaN(sinceTs)) {
    throw new Error(`无效的增量起始日期参数: ${since}`);
  }

  const allData = await loadMockAll();
  const filteredStocks = allData.stocks.filter((stock) => {
    const stockTs = new Date(stock.trade_date).getTime();
    // 单条股票日期非法则过滤丢弃并打印警告
    if (Number.isNaN(stockTs)) {
      console.warn(`股票${stock.code}交易日期格式非法，已过滤`, stock.trade_date);
      return false;
    }
    return stockTs >= sinceTs;
  });
  return {
    latest_trade_date: allData.latest_trade_date,
    stocks: filteredStocks,
  };
}

// ==================== 真实后端API实现 ====================
async function fetchRealAll(): Promise<SnapshotAllResponse> {
  const resp = await fetchWithTimeout('/api/snapshot/all');
  const json = await resp.json();
  // 运行时强校验，阻断残缺数据流入
  if (!json?.data) throw new Error('后端全量接口返回格式不符合标准，缺失data节点');
  if (!json.data.stocks || !Array.isArray(json.data.stocks)) {
    throw new Error('后端全量接口返回的 stocks 字段缺失或非数组');
  }
  return json.data as SnapshotAllResponse;
}

async function fetchRealIncremental(since: string): Promise<SnapshotIncrementalResponse> {
  // 前置校验日期合法性
  const sinceTs = new Date(since).getTime();
  if (Number.isNaN(sinceTs)) {
    throw new Error(`无效的增量起始日期参数: ${since}`);
  }

  const safeSince = encodeURIComponent(since);
  const resp = await fetchWithTimeout(`/api/snapshot/incremental?since=${safeSince}`);
  const json = await resp.json();
  // 运行时强校验
  if (!json?.data) throw new Error('后端增量接口返回格式不符合标准，缺失data节点');
  if (!json.data.stocks || !Array.isArray(json.data.stocks)) {
    throw new Error('后端增量接口返回的 stocks 字段缺失或非数组');
  }
  return json.data as SnapshotIncrementalResponse;
}

// ==================== 对外统一接口（返回Result结构，上层可感知异常） ====================
/**
 * 获取全量股票快照
 * @returns FetchResult：包含data/error，上层区分空数据与报错
 */
export async function fetchSnapshotAll(): Promise<FetchResult<SnapshotAllResponse>> {
  try {
    const data = USE_MOCK ? await loadMockAll() : await fetchRealAll();
    return { data, error: null };
  } catch (err) {
    // 区分超时Abort错误，给出专属提示
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { data: null, error: '请求超时，请稍后重试' };
    }
    const msg = err instanceof Error ? err.message : '获取全量快照未知异常';
    console.error('[fetchSnapshotAll]', msg, err);
    return { data: null, error: msg };
  }
}

/**
 * 获取增量股票快照
 * @param since 起始日期字符串 YYYY-MM-DD
 * @returns FetchResult
 */
export async function fetchSnapshotIncremental(since: string): Promise<FetchResult<SnapshotIncrementalResponse>> {
  try {
    if (!since || typeof since !== 'string') throw new Error('参数since必须为合法日期字符串');
    const data = USE_MOCK ? await loadMockIncremental(since) : await fetchRealIncremental(since);
    return { data, error: null };
  } catch (err) {
    // 区分超时Abort错误
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { data: null, error: '请求超时，请稍后重试' };
    }
    const msg = err instanceof Error ? err.message : '获取增量快照未知异常';
    console.error('[fetchSnapshotIncremental]', msg, err);
    return { data: null, error: msg };
  }
}