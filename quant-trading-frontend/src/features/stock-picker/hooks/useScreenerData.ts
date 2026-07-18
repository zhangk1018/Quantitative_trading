import { useState, useCallback, useRef, useEffect } from 'react';
import { App } from 'antd';
import { useScreenerSelector } from '../context/ScreenerContext';
import { fetchStocks } from '../../stock-detail/api';
import { buildScreeningParams, CONFIG, ScreenerFilterPayload } from '../utils/screener';
import { applyCustomIndicatorFilter, extractCustomConditions, getCustomIndicatorService } from '../utils/applyCustomIndicatorFilter';
import { CustomIndicatorService } from '../services/CustomIndicatorService';
import type { StockItem, FetchStocksResponse } from '../types';
import type { FilterCondition, FilterGroup } from '../types/filterTree';

type ScreeningPhase =
  | 'idle'
  | 'fetching-candidates'
  | 'loading-ohlcv'
  | 'computing-custom'
  | 'ready';

function getWatchlistCodes(): string[] {
  try {
    const raw = localStorage.getItem('watchlist');
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed.stocks?.['全部'] || [];
    }
  } catch { /* ignore */ }
  return [];
}

interface ApiErrorLike {
  message?: string;
  name?: string;
  code?: string;
  response?: { status: number };
  request?: unknown;
}

function isApiErrorLike(err: unknown): err is ApiErrorLike {
  return typeof err === 'object' && err !== null;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (isApiErrorLike(err)) {
    if (err.message) return err.message;
  }
  if (typeof err === 'string') return err;
  return fallback;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 生成影响候选集范围的缓存键（不含排序）
 * 排序变化不影响数据集合，仅影响展示顺序，不需要重新拉取
 */
function getRangeConditionHash(state: ScreenerFilterPayload & { filterGroup?: FilterGroup | null }): string {
  return JSON.stringify({
    selectedBoards: state.selectedBoards,
    stockRange: state.stockRange,
    marketIndicatorRanges: state.marketIndicatorRanges,
    financialIndicatorRanges: state.financialIndicatorRanges,
    selectedTechnicalIndicators: state.selectedTechnicalIndicators,
    filterGroup: state.filterGroup
      ? {
          conditions: state.filterGroup.conditions
            ?.filter((c: FilterCondition) => c.source !== 'custom')
            .map((c: FilterCondition) => ({ fieldKey: c.fieldKey, op: c.op, lookbackDays: c.lookbackDays })),
        }
      : null,
  });
}

function getCustomConditionHash(
  filterGroup: FilterGroup | null | undefined,
  customIndicators: { id: string; formula?: string; operator?: string; defaultThreshold?: number | [number, number] }[],
): string {
  if (!filterGroup?.conditions) return '';
  const customConds = filterGroup.conditions.filter((c: FilterCondition) => c.source === 'custom' && c.sourceId);
  if (customConds.length === 0) return '';
  const details = customConds.map((c: FilterCondition) => {
    const ind = customIndicators.find((i) => i.id === c.sourceId);
    return {
      id: c.sourceId,
      formula: ind?.formula,
      operator: ind?.operator,
      threshold: ind?.defaultThreshold,
    };
  });
  return JSON.stringify(details);
}

function hasCustomIndicator(
  filterGroup: FilterGroup | null | undefined,
): boolean {
  return !!filterGroup?.conditions?.some((c: FilterCondition) => c.source === 'custom' && c.sourceId);
}

function sortItems(items: StockItem[], sortBy: string, sortAsc: boolean): StockItem[] {
  const sorted = [...items];
  sorted.sort((a, b) => {
    const av = (a as unknown as Record<string, unknown>)[sortBy];
    const bv = (b as unknown as Record<string, unknown>)[sortBy];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') {
      return sortAsc ? av - bv : bv - av;
    }
    const as = String(av);
    const bs = String(bv);
    return sortAsc ? as.localeCompare(bs) : bs.localeCompare(as);
  });
  return sorted;
}

const CUSTOM_CONDITION_TYPE = 'custom';

interface LookbackCondition {
  lookbackDays?: number | string;
  formula?: string;
}

/**
 * 从条件中解析最大回溯天数
 *
 * 优先级：
 *   1. 显式 `lookbackDays` 字段（数字类型，且在 1~1000 之间）
 *   2. 从 `formula` 中正则提取数字（1~3 位的独立数字，排除大数字如成交量单位）
 *   3. 默认 30 天
 */
function computeMaxLookback(
  allConditions: (FilterCondition | FilterGroup)[],
  customConditions: LookbackCondition[],
): number {
  const values: number[] = [];

  for (const cond of customConditions) {
    if (cond.lookbackDays != null) {
      const n = typeof cond.lookbackDays === 'number'
        ? cond.lookbackDays
        : parseInt(String(cond.lookbackDays), 10);
      if (!Number.isNaN(n) && n >= 1 && n <= 1000) {
        values.push(n);
        continue;
      }
    }

    if (cond.formula) {
      const matches = cond.formula.match(/\b(\d{1,3})\b/g);
      if (matches) {
        const nums = matches
          .map((m) => parseInt(m, 10))
          .filter((n) => !Number.isNaN(n) && n >= 1 && n <= 500);
        if (nums.length > 0) {
          values.push(Math.max(...nums));
        }
      }
    }
  }

  return values.length > 0 ? Math.max(...values) : 30;
}

/** 分批拉取最大轮次保护（200只/批 × 50批 = 10000只上限） */
const MAX_BATCH_LOOPS = 50;
/** 单批请求最大重试次数 */
const BATCH_MAX_RETRIES = 2;
/** 首次重试延迟（毫秒），后续指数退避 */
const BATCH_RETRY_BASE_DELAY = 500;

export function useScreenerData(messageApi: ReturnType<typeof App.useApp>['message']) {
  const selectedBoards = useScreenerSelector((s) => s.market.selectedBoards);
  const stockRange = useScreenerSelector((s) => s.market.stockRange);
  const marketIndicatorRanges = useScreenerSelector((s) => s.marketIndicators.ranges);
  const financialIndicatorRanges = useScreenerSelector((s) => s.financialIndicators.ranges);
  const selectedTechnicalIndicators = useScreenerSelector((s) => s.technical.selected);
  const filterGroup = useScreenerSelector((s) => s.condition.filterGroup);
  const customIndicators = useScreenerSelector((s) => s.custom.indicators);

  const stateRef = useRef<ScreenerFilterPayload & {
    filterGroup?: FilterGroup | null;
    customIndicators: typeof customIndicators;
  }>({
    selectedBoards, stockRange, marketIndicatorRanges,
    financialIndicatorRanges, selectedTechnicalIndicators, filterGroup,
    customIndicators,
  });
  useEffect(() => {
    stateRef.current = {
      selectedBoards, stockRange, marketIndicatorRanges,
      financialIndicatorRanges, selectedTechnicalIndicators, filterGroup,
      customIndicators,
    };
  });

  const [items, setItems] = useState<StockItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState('change_pct');
  const [sortAsc, setSortAsc] = useState(false);
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = CONFIG.PAGE_SIZE;

  const [phase, setPhase] = useState<ScreeningPhase>('idle');
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState('');

  const cacheRef = useRef<{
    rangeHash: string | null;
    customHash: string | null;
    candidates: StockItem[] | null;
    candidateTotal: number;
    _lastPassedCodes: Set<string> | null;
  }>({
    rangeHash: null,
    customHash: null,
    candidates: null,
    candidateTotal: 0,
    _lastPassedCodes: null,
  });

  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timedOutRef = useRef(false);
  const cancelledRef = useRef(false);

  const fetchScreeningData = useCallback(
    async (params: {
      sortBy: string;
      sortAsc: boolean;
      offset: number;
      append?: boolean;
      signal?: AbortSignal;
    }): Promise<FetchStocksResponse | null> => {
      const { sortBy: sortByParam, sortAsc: sortAscParam, offset: offsetParam, append = false, signal } = params;

      if (abortRef.current) abortRef.current.abort();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);

      const controller = new AbortController();
      abortRef.current = controller;
      const finalSignal = signal || controller.signal;

      timedOutRef.current = false;
      const timeoutId = setTimeout(() => {
        timedOutRef.current = true;
        controller.abort();
      }, CONFIG.REQUEST_TIMEOUT);
      timeoutRef.current = timeoutId;

      if (!append) {
        setLoading(true);
        setError(null);
      } else {
        setLoadingMore(true);
        setLoadMoreError(null);
      }

      try {
        const state = stateRef.current;
        const watchlistCodes = state.stockRange === 'watchlist' ? getWatchlistCodes() : undefined;
        const requestParams = buildScreeningParams(state, sortByParam, sortAscParam, PAGE_SIZE, offsetParam, watchlistCodes);
        const result = (await fetchStocks(requestParams, finalSignal)) as FetchStocksResponse;

        let filteredItems = result.items;
        let filteredTotal = result.total || 0;
        const currentFilterGroup = stateRef.current.filterGroup;
        const currentCustomIndicators = stateRef.current.customIndicators;
        if (currentFilterGroup?.conditions && currentCustomIndicators && !append) {
          const customConditions = extractCustomConditions(currentFilterGroup.conditions, currentCustomIndicators);
          if (customConditions.length > 0) {
            const stockCodes = result.items.map((item) => item.stock_code).filter(Boolean);
            const filterResult = await applyCustomIndicatorFilter(stockCodes, customConditions);
            if (filterResult.executed) {
              const passedSet = filterResult.passedCodes;
              filteredItems = result.items.filter((item) => passedSet.has(item.stock_code));
              filteredTotal = Math.max(
                Math.round((result.total || 0) * (filteredItems.length / Math.max(result.items.length, 1))),
                filteredItems.length,
              );
            } else if (filterResult.error) {
              console.warn('自编指标筛选警告:', filterResult.error);
            }
          }
        }

        setItems((prev) => (append ? [...prev, ...filteredItems] : filteredItems));
        if (!append) {
          setTotal(filteredTotal);
        }
        setSortBy(sortByParam);
        setSortAsc(sortAscParam);
        setOffset(offsetParam);
        return result;
      } catch (err: unknown) {
        if (timedOutRef.current) {
          const timeoutMsg = '请求超时，请重试';
          if (!append) {
            setError(timeoutMsg);
          } else {
            setLoadMoreError(timeoutMsg);
          }
          messageApi.warning(timeoutMsg);
          return null;
        }
        if (finalSignal.aborted) return null;
        if (isApiErrorLike(err) && (err.name === 'CanceledError' || err.code === 'ERR_CANCELED')) return null;

        const isNetworkError = isApiErrorLike(err) && !err.response && !!err.request;
        const statusCode = isApiErrorLike(err) ? err.response?.status : undefined;
        let errorMsg = '选股失败，请稍后重试';
        if (isNetworkError) errorMsg = '网络连接异常，请检查网络';
        else if (statusCode === 400) errorMsg = '请求参数错误，请检查筛选条件';
        else if (statusCode === 422) errorMsg = '请求参数校验失败，请检查筛选条件';
        else if (statusCode != null && statusCode >= 500) errorMsg = '服务器异常，请稍后重试';
        else errorMsg = getErrorMessage(err, errorMsg);

        console.error('选股失败:', err);
        if (!append) {
          setError(errorMsg);
        } else {
          setLoadMoreError(errorMsg);
        }
        messageApi.error(errorMsg);
        return null;
      } finally {
        if (timeoutRef.current === timeoutId) {
          clearTimeout(timeoutId);
          timeoutRef.current = null;
        }
        if (!append) setLoading(false);
        else setLoadingMore(false);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [PAGE_SIZE],
  );

  /**
   * 分批拉取所有候选股（带断路器 + 指数退避重试 + 取消信号）
   *
   * @param signal 取消信号（可选），同时也会检查 cancelledRef
   * @returns [候选股列表, 总数量]
   */
  const loadAllCandidates = useCallback(
    async (sortByParam: string, sortAscParam: boolean, signal?: AbortSignal): Promise<[StockItem[], number]> => {
      const state = stateRef.current;
      const watchlistCodes = state.stockRange === 'watchlist' ? getWatchlistCodes() : undefined;
      const BATCH = CONFIG.CANDIDATE_BATCH_SIZE;
      const all: StockItem[] = [];
      let curOffset = 0;
      let totalCount = Infinity;
      let batchCount = 0;

      const isCancelled = (): boolean => {
        if (cancelledRef.current) return true;
        if (signal?.aborted) return true;
        return false;
      };

      while (curOffset < totalCount) {
        if (isCancelled()) throw new Error('已取消');
        batchCount++;
        if (batchCount > MAX_BATCH_LOOPS) {
          throw new Error(`候选股数量超过上限（${BATCH * MAX_BATCH_LOOPS}只），请缩小筛选范围`);
        }

        let lastErr: Error | null = null;
        let result: FetchStocksResponse | null = null;

        for (let attempt = 0; attempt <= BATCH_MAX_RETRIES; attempt++) {
          if (isCancelled()) throw new Error('已取消');
          if (attempt > 0) {
            const delay = BATCH_RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
            await sleep(delay);
          }
          try {
            const requestParams = buildScreeningParams(
              state, sortByParam, sortAscParam, BATCH, curOffset, watchlistCodes,
            );
            result = (await fetchStocks(requestParams, signal)) as FetchStocksResponse;
            lastErr = null;
            break;
          } catch (err) {
            if (isCancelled()) throw new Error('已取消');
            if (isApiErrorLike(err) && (err.name === 'CanceledError' || err.code === 'ERR_CANCELED')) {
              throw new Error('已取消');
            }
            lastErr = err instanceof Error ? err : new Error(String(err));
            console.warn(`[loadAllCandidates] 第${attempt + 1}次拉取失败: ${lastErr.message}`);
          }
        }

        if (lastErr || !result) {
          throw new Error(`候选股拉取失败: ${lastErr?.message || '未知错误'}`);
        }

        if (totalCount === Infinity) {
          totalCount = result.total || 0;
        }
        all.push(...(result.items as StockItem[]));
        curOffset += BATCH;

        const pct = Math.min(100, Math.round((all.length / Math.max(totalCount, 1)) * 100 * CONFIG.CANDIDATE_FETCH_WEIGHT));
        setProgress(pct);
        setProgressText(`正在拉取候选股 ${all.length.toLocaleString()}/${totalCount.toLocaleString()} 只`);
      }

      cacheRef.current.candidateTotal = totalCount;
      return [all, totalCount];
    },
    [],
  );

  /**
   * 运行全量筛选（有自编指标时）
   *
   * 缓存策略：
   *   - 范围条件变化 → 重新拉取候选股 + 重新加载OHLCV
   *   - 自编条件变化 → 仅重新计算，复用候选股 + OHLCV
   *   - 排序变化 → 仅本地重排，不重新拉取或计算
   */
  const runFullScreening = useCallback(
    async (sortByParam: string, sortAscParam: boolean): Promise<boolean> => {
      const state = stateRef.current;
      const cache = cacheRef.current;
      const rangeHash = getRangeConditionHash(state);
      const customHash = getCustomConditionHash(state.filterGroup, state.customIndicators);

      const rangeChanged = cache.rangeHash !== rangeHash;
      const customChanged = cache.customHash !== customHash;

      const service = getCustomIndicatorService();
      const abortController = new AbortController();
      abortRef.current = abortController;
      const signal = abortController.signal;

      let candidates: StockItem[];

      try {
        if (rangeChanged || !cache.candidates) {
          setPhase('fetching-candidates');
          setProgress(0);
          setProgressText('正在拉取候选股...');
          service.clearCache();
          const [loadedCandidates] = await loadAllCandidates(sortByParam, sortAscParam, signal);
          candidates = loadedCandidates;
          cache.candidates = candidates;
          cache.rangeHash = rangeHash;
          cache._lastPassedCodes = null;
        } else {
          candidates = cache.candidates!;
          setProgress(Math.round(CONFIG.CANDIDATE_FETCH_WEIGHT * 100));
        }

        if (candidates.length === 0) {
          setItems([]);
          setTotal(0);
          setSortBy(sortByParam);
          setSortAsc(sortAscParam);
          setPhase('ready');
          setProgress(100);
          return true;
        }

        if (!customChanged && !rangeChanged && cache._lastPassedCodes && cache.customHash !== null) {
          const resultItems = sortItems(
            candidates.filter((c) => cache._lastPassedCodes!.has(c.stock_code)),
            sortByParam,
            sortAscParam,
          );
          setItems(resultItems);
          setTotal(resultItems.length);
          setSortBy(sortByParam);
          setSortAsc(sortAscParam);
          setPhase('ready');
          setProgress(100);
          return true;
        }

        setPhase('loading-ohlcv');
        const baseProgress = CONFIG.CANDIDATE_FETCH_WEIGHT * 100;
        setProgress(Math.round(baseProgress));
        setProgressText('正在加载K线数据...');

        const codes = candidates.map((c) => c.stock_code);
        const customConditions = extractCustomConditions(
          state.filterGroup?.conditions || [],
          state.customIndicators,
        );

        const maxLookback = computeMaxLookback(
          state.filterGroup?.conditions || [],
          customConditions,
        );

        const ohlcvMap = await service.loadOhlcv(codes, signal, (done, totalCount) => {
          const pct = Math.round(
            baseProgress + (done / Math.max(totalCount, 1)) * CONFIG.OHLCV_LOAD_WEIGHT * 100,
          );
          setProgress(pct);
          setProgressText(`正在加载K线数据 ${done.toLocaleString()}/${totalCount.toLocaleString()} 只`);
        });

        const slicedOhlcv = service.sliceOhlcv(ohlcvMap, maxLookback);

        setPhase('computing-custom');
        const computeBaseProgress = (CONFIG.CANDIDATE_FETCH_WEIGHT + CONFIG.OHLCV_LOAD_WEIGHT) * 100;
        setProgress(Math.round(computeBaseProgress));
        setProgressText('正在计算自编指标...');

        const passedCodes = await service.computeAndFilter(
          customConditions,
          codes,
          slicedOhlcv,
          signal,
          (p) => {
            const ratio = customConditions.length > 0 ? p.done / customConditions.length : 1;
            const pct = Math.round(
              computeBaseProgress + ratio * CONFIG.CUSTOM_COMPUTE_WEIGHT * 100,
            );
            setProgress(pct);
            setProgressText(p.message);
          },
        );

        cache._lastPassedCodes = passedCodes;
        cache.customHash = customHash;

        const resultItems = sortItems(
          candidates.filter((c) => passedCodes.has(c.stock_code)),
          sortByParam,
          sortAscParam,
        );

        setItems(resultItems);
        setTotal(resultItems.length);
        setSortBy(sortByParam);
        setSortAsc(sortAscParam);
        setPhase('ready');
        setProgress(100);
        return true;
      } catch (err) {
        if ((err as Error).message === '已取消' || signal.aborted) {
          setPhase('idle');
          setProgress(0);
          return false;
        }
        const msg = getErrorMessage(err, '选股失败，请稍后重试');
        setError(msg);
        setPhase('idle');
        messageApi.error(msg);
        return false;
      } finally {
        if (abortRef.current === abortController) {
          abortRef.current = null;
        }
      }
    },
    [loadAllCandidates],
  );

  const fetchFirstPage = useCallback(
    async (newSortBy?: string, newSortAsc?: boolean): Promise<FetchStocksResponse | null> => {
      const sortByParam = newSortBy ?? sortBy;
      const sortAscParam = newSortAsc ?? sortAsc;

      setError(null);
      setLoadMoreError(null);

      const state = stateRef.current;
      const useFullScreening = hasCustomIndicator(state.filterGroup);

      if (!useFullScreening) {
        cacheRef.current = {
          rangeHash: null,
          customHash: null,
          candidates: null,
          candidateTotal: 0,
          _lastPassedCodes: null,
        };
        getCustomIndicatorService().clearCache();
        setPhase('idle');
        setProgress(0);
        return fetchScreeningData({
          sortBy: sortByParam,
          sortAsc: sortAscParam,
          offset: 0,
          append: false,
        });
      }

      cancelledRef.current = false;
      setLoading(true);
      setPhase('fetching-candidates');

      const success = await runFullScreening(sortByParam, sortAscParam);
      setLoading(false);

      if (success) {
        return { items, total } as FetchStocksResponse;
      }
      return null;
    },
    [fetchScreeningData, runFullScreening, sortBy, sortAsc, items, total],
  );

  const fetchNextPage = useCallback(() => {
    const state = stateRef.current;
    const useFullScreening = hasCustomIndicator(state.filterGroup);
    if (useFullScreening) return;

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      const nextOffset = offset + PAGE_SIZE;
      fetchScreeningData({ sortBy, sortAsc, offset: nextOffset, append: true });
      debounceTimerRef.current = null;
    }, CONFIG.DEBOUNCE_DELAY);
  }, [fetchScreeningData, sortBy, sortAsc, offset, PAGE_SIZE]);

  const cancelScreening = useCallback(() => {
    cancelledRef.current = true;
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setPhase('idle');
    setProgress(0);
    setProgressText('');
    setLoading(false);
  }, []);

  const clearResults = useCallback(() => {
    cancelledRef.current = true;
    if (abortRef.current) abortRef.current.abort();
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    setItems([]);
    setTotal(0);
    setError(null);
    setLoadMoreError(null);
    setSortBy('change_pct');
    setSortAsc(false);
    setOffset(0);
    setPhase('idle');
    setProgress(0);
    setProgressText('');
    cacheRef.current = {
      rangeHash: null,
      customHash: null,
      candidates: null,
      candidateTotal: 0,
      _lastPassedCodes: null,
    };
    getCustomIndicatorService().clearCache();
  }, []);

  const retry = useCallback(() => {
    return fetchFirstPage();
  }, [fetchFirstPage]);

  const retryLoadMore = useCallback(() => {
    fetchNextPage();
  }, [fetchNextPage]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (abortRef.current) abortRef.current.abort();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, []);

  return {
    items, total, loading, loadingMore, error, loadMoreError,
    sortBy, sortAsc, offset, PAGE_SIZE,
    phase, progress, progressText,
    fetchFirstPage, fetchNextPage, clearResults, retry, retryLoadMore,
    cancelScreening,
    candidateTotal: cacheRef.current?.candidateTotal ?? 0,
  };
}
