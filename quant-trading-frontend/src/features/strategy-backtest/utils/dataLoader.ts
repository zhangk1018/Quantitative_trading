// src/features/strategy-backtest/utils/dataLoader.ts
// 数据加载层：双阶段过滤 + 完整性校验 + 错误分类 + IndexedDB 缓存

import type { FilterNode, StockSnapshot, StrategyBacktestDefaults } from '../types';
import {
  extractPushdownPredicates,
  pushdownToQueryString,
  detectFundamentalFields,
  validateFilterNode,
  type FilterAuditTrail,
} from './filterTreeAdapter';

// ==================== 类型 ====================

/** 数据加载结果 */
export interface LoadedData {
  allOhlcv: Map<string, number[][]>;
  snapshots: Map<string, StockSnapshot>;
  tradeDates: string[];
  benchmarkOhlcv?: number[][];
  auditTrail: FilterAuditTrail;
}

/** 数据完整性校验结果 */
export interface ValidationResult {
  hardErrors: string[];    // 硬阻断
  softErrors: string[];    // 警告+可继续
  warnings: string[];
}

/** 配置迁移器接口（与 storage.ts 配合） */
export interface MigrationResult {
  migrated: boolean;
  from?: string;
  to?: string;
}

// ==================== IndexedDB 缓存（断点续传） ====================

const DB_NAME = 'strategy-backtest-cache';
const DB_VERSION = 1;
const CACHE_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 小时

/** 打开 IndexedDB 连接 */
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains('batches')) {
        db.createObjectStore('batches', { keyPath: 'cacheKey' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** 缓存键参数 Hash 计算 */
export function computeCacheHash(
  filterTree: FilterNode,
  startDate: string,
  endDate: string,
  rebalanceInterval: number,
  maxPositions: number,
  riskControlEnabled: boolean,
): string {
  const raw = JSON.stringify({
    filterTree,
    startDate,
    endDate,
    rebalanceInterval,
    maxPositions,
    riskControlEnabled,
  });
  // 使用简单的字符串哈希（非加密，仅用于缓存键）
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    const char = raw.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32bit integer
  }
  return `v1_${Math.abs(hash).toString(16)}`;
}

/** 尝试从缓存恢复 */
export async function tryRestoreFromCache(
  cacheKey: string,
): Promise<LoadedData | null> {
  try {
    const db = await openDB();
    const tx = db.transaction('batches', 'readonly');
    const store = tx.objectStore('batches');
    const request = store.get(cacheKey);

    return new Promise((resolve) => {
      request.onsuccess = () => {
        const data = request.result;
        if (!data) {
          resolve(null);
          return;
        }
        // 校验时间戳
        if (Date.now() - data.timestamp > CACHE_EXPIRY_MS) {
          resolve(null);
          return;
        }
        resolve(data.payload as LoadedData);
      };
      request.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/** 保存缓存 */
export async function saveToCache(
  cacheKey: string,
  payload: LoadedData,
): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction('batches', 'readwrite');
    const store = tx.objectStore('batches');
    store.put({
      cacheKey,
      timestamp: Date.now(),
      payload,
    });
  } catch {
    // 缓存失败不阻塞主流程
    console.warn('[Cache] 保存缓存失败');
  }
}

// ==================== 数据完整性校验 ====================

/**
 * 数据完整性校验
 * 硬错误 → 阻断，软错误 → 警告+可继续
 */
export function validateDataIntegrity(
  allOhlcv: Map<string, number[][]>,
  snapshots: Map<string, StockSnapshot>,
  tradeDates: string[],
): ValidationResult {
  const hardErrors: string[] = [];
  const softErrors: string[] = [];
  const warnings: string[] = [];

  // 1. 交易日历不得为空
  if (!tradeDates || tradeDates.length === 0) {
    hardErrors.push('交易日历为空，无法确定回测区间');
  }

  // 2. OHLCV 必须包含 pre_close 列
  let missingPreClose = false;
  const missingPreCloseCodes: string[] = [];
  for (const [code, bars] of allOhlcv) {
    if (bars.length > 0 && bars[0].length < 7) {
      if (!missingPreClose) {
        missingPreClose = true;
        missingPreCloseCodes.push(code);
      } else if (missingPreCloseCodes.length < 5) {
        missingPreCloseCodes.push(code);
      }
    }
  }
  if (missingPreClose) {
    hardErrors.push(
      `OHLCV 缺少 pre_close 列（影响除权除息计算），示例股票：${missingPreCloseCodes.join(', ')}`,
    );
  }

  // 3. snapshot 必须包含 is_st 字段
  let missingIsSt = false;
  const missingIsStCodes: string[] = [];
  for (const [code, snap] of snapshots) {
    if (snap.isSt === undefined) {
      if (!missingIsSt) {
        missingIsSt = true;
        missingIsStCodes.push(code);
      } else if (missingIsStCodes.length < 5) {
        missingIsStCodes.push(code);
      }
    }
  }
  if (missingIsSt) {
    softErrors.push(
      `部分股票缺少 is_st 字段（涨跌停判定可能不准确），示例：${missingIsStCodes.join(', ')}`,
    );
  }

  // 4. 检查空数据
  let emptyOhlcvCount = 0;
  for (const [, bars] of allOhlcv) {
    if (bars.length === 0) emptyOhlcvCount++;
  }
  if (emptyOhlcvCount > 0) {
    warnings.push(`有 ${emptyOhlcvCount} 只股票无 OHLCV 数据，已在回测中排除`);
  }

  return { hardErrors, softErrors, warnings };
}

// ==================== 数据加载主流程 ====================

/**
 * 加载回测数据（双阶段过滤）
 *
 * 阶段一：后端粗筛 — 提取无歧义条件传给后端 API
 * 阶段二：引擎预过滤 — 用完整 AST 在引擎侧再次精准过滤
 */
export async function loadBacktestData(
  filterTree: FilterNode,
  config: StrategyBacktestDefaults,
  signal?: AbortSignal,
): Promise<{ data: LoadedData; validation: ValidationResult }> {
  // 0. 校验 FilterNode 结构
  validateFilterNode(filterTree, 0);

  // 1. 检测基本面字段
  const fundamentalFields = detectFundamentalFields(filterTree);
  if (fundamentalFields.length > 0) {
    throw new Error(
      `选股条件包含高风险基本面字段（${fundamentalFields.join(', ')}），` +
      '回测引擎无法获取历史时点的基本面数据。请移除这些条件后重试，' +
      '仅保留技术指标（MA/MACD/RSI/BOLL）和行情数据等可基于OHLCV计算的指标。',
    );
  }

  // 2. 提取可下推条件
  const { pushdown, engineSideOnly } = extractPushdownPredicates(filterTree);
  const pushdownQuery = pushdownToQueryString(pushdown);

  // 3. 调用后端 API 获取候选股票池
  let candidateCodes: string[] = [];
  try {
    const response = await fetch(
      `/api/stocks/?${pushdownQuery}`,
      { signal },
    );
    const result = await response.json();
    // API 返回 {code, data: {items: [{stock_code, ...}], total: N}}，提取 stock_code 列表
    const items = result.data?.items ?? [];
    if (Array.isArray(items)) {
      candidateCodes = items.map((i: any) => i.stock_code).filter(Boolean);
    } else {
      candidateCodes = [];
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    console.warn('[DataLoader] 后端粗筛失败，降级为全量加载', err);
  }

  // 4. 拉取候选池的 OHLCV + 快照
  let allOhlcv: Map<string, number[][]>;
  let snapshots: Map<string, StockSnapshot>;
  let tradeDates: string[];

  /**
   * 将后端 SnapshotStock 数组转换为前端需要的 Map 格式
   * 后端返回结构：{ code, name, ohlcv, market_cap, pe_ttm, pb, turnover_rate, listed_board, ... }
   * 前端需要：allOhlcv = Map<code, ohlcv[][]>, snapshots = Map<code, StockSnapshot>
   */
  function extractFromStocks(stocks: any[]): {
    ohlcvMap: Map<string, number[][]>;
    snapMap: Map<string, StockSnapshot>;
  } {
    const ohlcvMap = new Map<string, number[][]>();
    const snapMap = new Map<string, StockSnapshot>();
    const BOARD_MAP: Record<string, string> = {
      '主板': 'main', '上海主板': 'main', '深圳主板': 'main',
      '创业板': 'gem', '科创板': 'star', '北交所': 'beijing',
    };
    for (const s of stocks) {
      if (s.ohlcv && Array.isArray(s.ohlcv)) {
        ohlcvMap.set(s.code, s.ohlcv);
      }
      snapMap.set(s.code, {
        code: s.code,
        name: s.name ?? '',
        listedBoard: BOARD_MAP[s.listed_board] ?? 'main',
        isSt: s.is_st ?? false,
        marketCap: s.market_cap ? s.market_cap / 10000 : 0, // 万元→亿元
        pe: s.pe_ttm ?? 0,
        peTtm: s.pe_ttm ?? 0,
        pb: s.pb ?? 0,
        turnoverRate: s.turnover_rate ?? 0,
      });
    }
    return { ohlcvMap, snapMap };
  }

  if (candidateCodes.length > 0) {
    const codesParam = candidateCodes.join(',');
    const ohlcvResp = await fetch(`/api/snapshot/all?codes=${codesParam}`, { signal });

    const ohlcvData = await ohlcvResp.json();

    // 从 ohlcvData 中提取 OHLCV 和快照数据（snapshot 已包含在响应中）
    const stocks = ohlcvData.data?.stocks ?? [];
    const extracted = extractFromStocks(stocks);
    allOhlcv = extracted.ohlcvMap;
    snapshots = extracted.snapMap;
    tradeDates = ohlcvData.data?.trade_dates ?? [];
  } else {
    // 兜底：全量加载
    const resp = await fetch('/api/snapshot/all', { signal });
    const data = await resp.json();
    const stocks = data.data?.stocks ?? [];
    const extracted = extractFromStocks(stocks);
    allOhlcv = extracted.ohlcvMap;
    snapshots = extracted.snapMap;
    tradeDates = data.data?.trade_dates ?? [];
  }

  // 5. 数据完整性校验
  const validation = validateDataIntegrity(allOhlcv, snapshots, tradeDates);

  // 6. 构建审计报告
  const auditTrail: FilterAuditTrail = {
    pushdownQuery,
    beforeEngineFilter: allOhlcv.size,
    afterEngineFilter: allOhlcv.size, // 引擎侧过滤在 engine 中完成
    removedExamples: [],
    hasEngineSideFilter: engineSideOnly,
  };

  // 7. 加载基准数据
  let benchmarkOhlcv: number[][] | undefined;
  try {
    const resp = await fetch(`/api/kline/${config.benchmarkCode}`, { signal });
    const data = await resp.json();
    benchmarkOhlcv = data.data ?? [];
  } catch {
    // 基准数据可选，加载失败不阻塞
  }

  return {
    data: {
      allOhlcv,
      snapshots,
      tradeDates,
      benchmarkOhlcv,
      auditTrail,
    },
    validation,
  };
}