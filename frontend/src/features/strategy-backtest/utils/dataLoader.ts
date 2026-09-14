// src/features/strategy-backtest/utils/dataLoader.ts
// 数据加载层：双阶段过滤 + 完整性校验 + 错误分类 + IndexedDB 缓存

import type { FilterNode, StockSnapshot, StrategyBacktestDefaults, SnapshotHistoryRow } from '../types';
import {
  extractPushdownPredicates,
  pushdownToQueryString,
  detectFundamentalFields,
  validateFilterNode,
  type FilterAuditTrail,
} from './filterTreeAdapter';
import { requiredHistoryFields, convertHistoryRow, MARKET_CAP_UNIT } from './historyFieldMap';
import { inferMarketKey, type MarketKey } from '@/features/watchlist/utils/stock-utils';
import { isExcludedStockName } from '@/lib/stocks/exclusion';

// ==================== 类型 ====================

/** 数据加载结果 */
export interface LoadedData {
  allOhlcv: Map<string, number[][]>;
  snapshots: Map<string, StockSnapshot>;
  tradeDates: string[];
  benchmarkOhlcv?: number[][];
  auditTrail: FilterAuditTrail;
  /**
   * 历史逐日快照行（升序）：Map<code, SnapshotHistoryRow[]>。
   * 与选股视图 /api/stocks/ 同源宽表预计算字段，供引擎逐日判定口径统一。
   * 仅当 filterTree 需要 range/pattern 字段时拉取；缺省时引擎回退旧口径（向后兼容）。
   */
  historyRowsByCode?: Map<string, SnapshotHistoryRow[]>;
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
  // v2：整体失效历史缓存（v1 payload 无 historyRowsByCode 字段，字段/Date 键口径已重构）
  return `v2_${Math.abs(hash).toString(16)}`;
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
    console.warn('[DataLoader] 缓存恢复失败');
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
    console.warn('[DataLoader] 缓存保存失败');
  }
}

// ==================== 市场推断（单市场回测） ====================

/**
 * 由基准指数代码推断回测市场（回测默认单市场，市场由基准决定）：
 * - 港股：代码含 `.HK` 或恒生指数（`^HSI` / 恒生）
 * - A股：沪深指数 / 6 位数字代码（`000300.SH` / `999999` 等）
 * - 美股：其余（`^GSPC` / `SPY` / `^IXIC` 等）
 * A股(纯数字)返回 cn；港股特判恒生指数（inferMarketKey 会把 `^HSI` 判为美股）。
 */
export function inferBacktestMarket(benchmarkCode: string): MarketKey {
  const c = benchmarkCode.trim().toUpperCase();
  if (c.includes('.HK') || c.startsWith('^HSI') || c.startsWith('恒生')) return 'hk';
  return inferMarketKey(c) ?? 'cn';
}

// ==================== 汇率折算（跨市场结算） ====================

/** 各市场对应的"当地货币折 CNY"债券对（横拟为债券：HKDCNY=X / USDCNY=X），A股无需折算返回 null。 */
function getFxPairForMarket(market: MarketKey): string | null {
  if (market === 'hk') return 'HKDCNY=X';
  if (market === 'us') return 'USDCNY=X';
  return null;
}

/**
 * 构建跨市场回测的逐交易日汇率折算表：Map<tradeDate, 每单位当地货币折合 CNY 的比率>。
 *
 * 仅供港/美股（hk/us）使用；A股(cn)返回 undefined（引擎默认 rate=1，无换算，保证 A股无回归）。
 *
 * 后端 /api/fx/rate 仅支持"单日期 AS-OF"查询（返回该日及之前最近有效汇率），无法一次拉全区间。
 * 为控制请求量，以【每月首个交易日】为锚点，逐锚点查询 AS-OF 汇率，该月其余交易日沿用，
 * 即"月首汇率按月 forward-fill"的近似（fx_rates 每日 ffill，月首取值可代表当月水平，误差可忽略）。
 *
 * @param market 回测市场（hk/us）
 * @param tradeDates 升序交易日历 YYYY-MM-DD
 * @param signal 中止信号
 * @returns ₹率折算表；cn 或无交易日历返回 undefined
 */
export async function buildFxRateMap(
  market: MarketKey,
  tradeDates: string[],
  signal?: AbortSignal,
): Promise<Record<string, number> | undefined> {
  const pair = getFxPairForMarket(market);
  if (!pair || tradeDates.length === 0) return undefined;

  // 每月首个交易日作为锚点（保证任意交易日都能命中一个 ≤ 其自身的锚点，覆盖完整区间）
  const firstByMonth = new Map<string, string>();
  for (const d of tradeDates) {
    const month = d.slice(0, 7);
    if (!firstByMonth.has(month)) firstByMonth.set(month, d);
  }
  const anchors = Array.from(firstByMonth.values()).sort();

  // 逐步拉取锚点 AS-OF 汇率（后端仅支持单日期），失败或异常沿用前一有效值
  const anchorRates: Array<{ date: string; rate: number }> = [];
  let prevRate = 1;
  for (const asOf of anchors) {
    let rate = prevRate;
    try {
      const resp = await fetch(
        `/api/fx/rate?pair=${encodeURIComponent(pair)}&date=${encodeURIComponent(asOf)}`,
        { signal },
      );
      if (resp.ok) {
        const js = await resp.json();
        if (typeof js?.rate === 'number' && js.rate > 0) rate = js.rate;
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') throw e;
      // 网络/认证异常：沿用前一有效汇率，不阻断回测
    }
    anchorRates.push({ date: asOf, rate });
    prevRate = rate;
  }

  // 逐交易日回填"最近一个 ≤ 该日的锚点汇率"
  const rateByDate: Record<string, number> = {};
  let ai = 0;
  for (const d of tradeDates) {
    while (ai < anchorRates.length - 1 && anchorRates[ai + 1].date <= d) ai++;
    rateByDate[d] = anchorRates[ai].date <= d ? anchorRates[ai].rate : 1;
  }
  return rateByDate;
}

// ==================== 历史逐日快照拉取（回测逐日判定，与选股视图同口径） ====================

const HISTORY_MAX_ROWS = 60000;        // 行数上限（与后端 snapshot_service.HISTORY_MAX_ROWS 一致）
const HISTORY_MAX_CODE_COUNT = 2000;   // 单请求 codes 上限（后端 HISTORY_MAX_CODES）
const HISTORY_MAX_CONCURRENCY = 4;     // 并发批次数上限

/** 将 /history 响应 payload 解析为 Map<code, SnapshotHistoryRow[]>（rows 升序，字段已裁剪+market_cap 转亿元） */
export function parseHistoryPayload(
  result: any,
  fields: ReadonlySet<string>,
): Map<string, SnapshotHistoryRow[]> {
  const out = new Map<string, SnapshotHistoryRow[]>();
  const stocks = result?.data?.stocks ?? [];
  for (const s of stocks) {
    if (!s?.code || !Array.isArray(s.rows)) continue;
    const rows = s.rows
      .filter((r: any) => r && typeof r === 'object')
      .map((r: any) => convertHistoryRow(r, fields));
    out.set(s.code, rows);
  }
  return out;
}

/** 构造 /history 查询串（fields 为不含 trade_date 的字段白名单） */
function historyQuery(
  codes: string[],
  startDate: string,
  endDate: string,
  fields: string[],
  market: string | undefined,
): string {
  const params = new URLSearchParams();
  params.set('codes', codes.join(','));
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  if (fields.length > 0) params.set('fields', fields.join(','));
  if (market && market !== 'cn') params.set('market', market);
  return params.toString();
}

/** 判断 /history 非 2xx 响应是否为「行数超限」（仅此需二分重试，其余直接抛错） */
async function isRowLimitError(resp: Response): Promise<boolean> {
  if (resp.status !== 400) return false;
  let msg = '';
  try {
    const body = await resp.json();
    msg = String(body?.message ?? body?.detail ?? '');
  } catch {
    return false;
  }
  return msg.includes('上限');
}

/**
 * 拉取一批 codes 的 /history。若该片返回行数超限 → 对 codes 二分递归重试（单 code 仍超限则抛错）。
 */
async function fetchHistoryChunk(
  codes: string[],
  startDate: string,
  endDate: string,
  fields: string[],
  market: string | undefined,
  signal?: AbortSignal,
): Promise<Map<string, SnapshotHistoryRow[]>> {
  const fieldsSet = new Set<string>(['trade_date', ...fields]);
  const params = historyQuery(codes, startDate, endDate, fields, market);

  const resp = await fetch(`/api/snapshot/history?${params}`, { signal });
  if (resp.ok) {
    return parseHistoryPayload(await resp.json(), fieldsSet);
  }
  if (!(await isRowLimitError(resp))) {
    let msg = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      msg = String(body?.message ?? body?.detail ?? msg);
    } catch { /* ignore */ }
    throw new Error(`历史快照拉取失败(${msg}) codes=${codes.join(',')}`);
  }

  // 行数超限 → 二分重试（单 code 仍超限则报错提示缩小区间/裁剪 fields）
  if (codes.length <= 1) {
    throw new Error(
      `历史快照拉取失败：单票 ${codes[0]} 行数仍超上限 ${HISTORY_MAX_ROWS}，请缩小日期区间或用 fields 裁剪`,
    );
  }
  const mid = Math.floor(codes.length / 2);
  const left = codes.slice(0, mid);
  const right = codes.slice(mid);
  const [lm, rm] = await Promise.all([
    fetchHistoryChunk(left, startDate, endDate, fields, market, signal),
    fetchHistoryChunk(right, startDate, endDate, fields, market, signal),
  ]);
  const merged = new Map<string, SnapshotHistoryRow[]>(lm);
  for (const [k, v] of rm) merged.set(k, v);
  return merged;
}

/**
 * 按 codes 分批拉取 /history（并发 ≤ HISTORY_MAX_CONCURRENCY），行数超限自动二分重试。
 * @param chunkSize 每批 codes 数量（≈floor(60000/daysInRange)，保证不触发行数超限）
 */
async function fetchHistoryInChunks(
  codes: string[],
  startDate: string,
  endDate: string,
  fields: string[],
  daysInRange: number,
  market: string | undefined,
  signal?: AbortSignal,
): Promise<Map<string, SnapshotHistoryRow[]>> {
  const chunkSize = Math.max(1, Math.min(HISTORY_MAX_CODE_COUNT, Math.floor(HISTORY_MAX_ROWS / Math.max(1, daysInRange))));
  const batches: string[][] = [];
  for (let i = 0; i < codes.length; i += chunkSize) {
    batches.push(codes.slice(i, i + chunkSize));
  }

  const result = new Map<string, SnapshotHistoryRow[]>();
  for (let i = 0; i < batches.length; i += HISTORY_MAX_CONCURRENCY) {
    const slot = batches.slice(i, i + HISTORY_MAX_CONCURRENCY);
    const resolved = await Promise.all(
      slot.map((b) => fetchHistoryChunk(b, startDate, endDate, fields, market, signal)),
    );
    for (const m of resolved) {
      for (const [k, v] of m) result.set(k, v);
    }
  }
  return result;
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
  startDate: string,
  endDate: string,
  signal?: AbortSignal,
): Promise<{ data: LoadedData; validation: ValidationResult }> {
  // 0. 校验 FilterNode 结构
  validateFilterNode(filterTree, 0);

  // 回测市场（由基准推断，单市场）；A股默认 cn 不显式传 market
  const mkt = inferBacktestMarket(config.benchmarkCode);
  const marketParam = mkt !== 'cn' ? `market=${mkt}` : '';
  const buildStocksQuery = (q: string) => {
    if (mkt === 'cn' || /[?&]market=/.test(q)) return q;
    return q ? `${q}&market=${mkt}` : `market=${mkt}`;
  };

  const warnings: string[] = [];
  const softErrors: string[] = [];
  const hardErrors: string[] = [];

  // 1. 检测基本面字段（不再硬阻断、不再剥离；逐日判定已改用 /history 历史日值口径）
  const fundamentalFields = detectFundamentalFields(filterTree);
  if (fundamentalFields.length > 0) {
    // 已改用历史日值口径（宽表预计算字段），与选股视图一致。
    warnings.push('基本面/行情字段已改用历史日值口径（宽表预计算字段），与选股视图一致。');
  }

  // 2. 提取可下推条件
  const { pushdown, engineSideOnly } = extractPushdownPredicates(filterTree);
  // market_cap 单位修复：FilterNode 阈值为「亿元」，而下推给 /api/stocks/ 的 market_cap 语义为「万元」，
  // 此处把亿元阈值 ×10000 转万元再下推，保证候选池缩池口径正确（引擎逐日判定仍用已转亿元的 /history 行）。
  const pushdownWidget = { ...pushdown };
  if (pushdownWidget.marketCapMin !== undefined) pushdownWidget.marketCapMin = pushdownWidget.marketCapMin * MARKET_CAP_UNIT;
  if (pushdownWidget.marketCapMax !== undefined) pushdownWidget.marketCapMax = pushdownWidget.marketCapMax * MARKET_CAP_UNIT;
  const pushdownQuery = pushdownToQueryString(pushdownWidget);

  // 3. 调用后端 API 获取候选股票池
  let candidateCodes: string[] = [];
  try {
    const response = await fetch(
      `/api/stocks/?${buildStocksQuery(pushdownQuery)}`,
      { signal },
    );
    const result = await response.json();
    // API 返回 {code, data: {items: [{stock_code, ...}], total: N}}，提取 stock_code 列表
    const items = result.data?.items ?? [];
    if (Array.isArray(items)) {
      // 排除名称含 ST/*ST/退 的股票（自编指标公式层拿不到名称，须在候选池阶段剔除）
      candidateCodes = items
        .filter((i: any) => i && !isExcludedStockName(i.name ?? i.stock_name))
        .map((i: any) => i.stock_code)
        .filter(Boolean);
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
   * 为OHLCV数据补全pre_close列（第7列，index=6）
   * 后端返回6列：[ts, open, high, low, close, volume]
   * 补全为7列：[ts, open, high, low, close, volume, pre_close]
   * pre_close规则：第0根K线用open替代，后续用前一根K线的close
   */
  function fillPreClose(bars: number[][]): number[][] {
    if (!bars || bars.length === 0) return bars;
    if (bars[0].length >= 7) return bars;
    const filled: number[][] = [];
    for (let i = 0; i < bars.length; i++) {
      const bar = bars[i];
      const preClose = i === 0 ? bar[1] : bars[i - 1][4];
      filled.push([...bar.slice(0, 6), preClose]);
    }
    return filled;
  }

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
        ohlcvMap.set(s.code, fillPreClose(s.ohlcv));
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
    const params = new URLSearchParams();
    params.set('codes', codesParam);
    if (marketParam) params.set('market', mkt);
    const ohlcvResp = await fetch(`/api/snapshot/all?${params.toString()}`, { signal });

    const ohlcvData = await ohlcvResp.json();

    // 从 ohlcvData 中提取 OHLCV 和快照数据（snapshot 已包含在响应中）
    const stocks = (ohlcvData.data?.stocks ?? []).filter((s: any) => !isExcludedStockName(s.name));
    const extracted = extractFromStocks(stocks);
    allOhlcv = extracted.ohlcvMap;
    snapshots = extracted.snapMap;
    tradeDates = ohlcvData.data?.trade_dates ?? [];
  } else {
    // 兜底：全量加载
    const resp = await fetch(`/api/snapshot/all${marketParam ? `?${marketParam}` : ''}`, { signal });
    const data = await resp.json();
    const stocks = (data.data?.stocks ?? []).filter((s: any) => !isExcludedStockName(s.name));
    const extracted = extractFromStocks(stocks);
    allOhlcv = extracted.ohlcvMap;
    snapshots = extracted.snapMap;
    tradeDates = data.data?.trade_dates ?? [];
  }

  // 4.5 拉取历史逐日快照（逐日判定口径与选股视图统一）。
  // 仅当 filterTree 需要 range/pattern 字段时拉取；区间用 config 起止，无需 warmup（预计算字段每日独立）。
  let historyRowsByCode: Map<string, SnapshotHistoryRow[]> | undefined;
  const requiredFields = requiredHistoryFields(filterTree);
  if (requiredFields.length > 0 && candidateCodes.length > 0 && tradeDates.length > 0) {
    const daysInRange = tradeDates.filter((d) => d >= startDate && d <= endDate).length;
    try {
      historyRowsByCode = await fetchHistoryInChunks(
        candidateCodes,
        startDate,
        endDate,
        requiredFields,
        daysInRange,
        mkt === 'cn' ? undefined : mkt,
        signal,
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err;
      console.warn('[DataLoader] 历史快照拉取失败，回退旧口径（snapshot 最新值+重算指标）', err);
      historyRowsByCode = undefined;
    }
  }

  // 5. 数据完整性校验
  const integrityValidation = validateDataIntegrity(allOhlcv, snapshots, tradeDates);

  // 合并校验结果
  const validation: ValidationResult = {
    hardErrors: [...hardErrors, ...integrityValidation.hardErrors],
    softErrors: [...softErrors, ...integrityValidation.softErrors],
    warnings: [...warnings, ...integrityValidation.warnings],
  };

  // 6. 构建审计报告
  const auditTrail: FilterAuditTrail = {
    pushdownQuery,
    beforeEngineFilter: allOhlcv.size,
    afterEngineFilter: allOhlcv.size, // 引擎侧过滤在 engine 中完成
    removedExamples: [],
    hasEngineSideFilter: engineSideOnly,
    historyFields: requiredFields,
  };

  // 7. 加载基准数据
  let benchmarkOhlcv: number[][] | undefined;
  try {
    const resp = await fetch(`/api/kline/${config.benchmarkCode}`, { signal });
    const data = await resp.json();
    const kline: Array<{ trade_date: string; open?: string | number; high?: string | number; low?: string | number; close?: string | number; volume?: string | number }> = data.data ?? [];
    // /api/kline 返回对象数组 [{trade_date, open, high, low, close, volume}, ...]，
    // 而引擎 calcMetrics 按 number[][]（[ts,o,h,l,c,v]）读取。
    // 此处归一化为与个股 ohlcv 一致的数组格式，否则 ts/close 取到 undefined，
    // 日期键退化为 "NaN-NaN-NaN"，基准收益/Alpha/Beta 计算失败。
    benchmarkOhlcv = kline.map((b) => [
      Date.parse(b.trade_date),
      Number(b.open),
      Number(b.high),
      Number(b.low),
      Number(b.close),
      Number(b.volume),
    ]);
  } catch {
    console.warn('[DataLoader] 基准数据加载失败，使用空数据');
  }

  return {
    data: {
      allOhlcv,
      snapshots,
      tradeDates,
      benchmarkOhlcv,
      auditTrail,
      historyRowsByCode,
    },
    validation,
  };
}