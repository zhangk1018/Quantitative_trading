import { useState, useCallback, useRef, useEffect } from 'react';
import { App } from 'antd';
import { useScreenerSelector } from '../context/ScreenerContext';
import { fetchStocks } from '../../stock-detail/api';
import { buildScreeningParams, CONFIG, ScreenerFilterPayload } from '../utils/screener';
import { applyCustomIndicatorFilter, extractCustomConditions, getCustomIndicatorService } from '../utils/applyCustomIndicatorFilter';
import { isExcludedStockName } from '../../../lib/stocks/exclusion';
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
  } catch {
    console.warn('[Screener] localStorage 读取自选股数据失败');
  }
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
export function getRangeConditionHash(state: ScreenerFilterPayload & { filterGroup?: FilterGroup | null }): string {
  return JSON.stringify({
    // 市场必须参与缓存键：切换市场会改变候选集（后端 market 参数 + 板块规则），
    // 漏掉它会导致 hk→us 时命中旧缓存，仍旧返回上一市场的股票（K 2026-10-06）。
    selectedMarket: state.selectedMarket,
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

/** 分批拉取最大轮次保护（200只/批 × 50批 = 10000只上限） */
const MAX_BATCH_LOOPS = 50;
/** 候选股分页并发度（港股/美股候选集大，并发可显著缩短加载时间） */
const CANDIDATE_FETCH_CONCURRENCY = 5;
/** 单批请求最大重试次数 */
const BATCH_MAX_RETRIES = 2;
/** 首次重试延迟（毫秒），后续指数退避 */
const BATCH_RETRY_BASE_DELAY = 500;

/** 重置缓存状态的工厂函数 */
function createEmptyCache() {
  return {
    rangeHash: null as string | null,
    customHash: null as string | null,
    candidates: null as StockItem[] | null,
    candidateTotal: 0,
    _lastPassedCodes: null as Set<string> | null,
  };
}

export function useScreenerData(messageApi: ReturnType<typeof App.useApp>['message']) {
  const selectedMarket = useScreenerSelector((s) => s.market.selectedMarket);
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
    selectedMarket, selectedBoards, stockRange, marketIndicatorRanges,
    financialIndicatorRanges, selectedTechnicalIndicators, filterGroup,
    customIndicators,
  });
  useEffect(() => {
    stateRef.current = {
      selectedMarket, selectedBoards, stockRange, marketIndicatorRanges,
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
  /**
   * 结果集「整批替换」计数器（fetchFirstPage 每次成功返回 +1）。
   * 用于让表格在结果替换后把滚动位置复位到顶部——滚动容器 DOM 节点会被 React
   * 复用，旧滚动位置会残留，导致新结果的前几行被跳过（K 2026-10-09）。
   * 「加载更多」(fetchNextPage) 为追加，不在此列。
   */
  const [resultsResetToken, setResultsResetToken] = useState(0);

  const cacheRef = useRef(createEmptyCache());

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

        // 排除名称含 ST/*ST/退 的股票（自编指标公式层拿不到名称，必须在候选阶段剔除）
        let filteredItems = result.items.filter((item) => !isExcludedStockName(item.stock_name));
        let filteredTotal = Math.max(
          Math.round((result.total || 0) * (filteredItems.length / Math.max(result.items.length, 1))),
          filteredItems.length,
        );
        const currentFilterGroup = stateRef.current.filterGroup;
        const currentCustomIndicators = stateRef.current.customIndicators;
        if (currentFilterGroup?.conditions && currentCustomIndicators && !append) {
          const customConditions = extractCustomConditions(currentFilterGroup.conditions, currentCustomIndicators);
          if (customConditions.length > 0) {
            const stockCodes = result.items.map((item) => item.stock_code).filter(Boolean);
            const filterResult = await applyCustomIndicatorFilter(stockCodes, customConditions);
            if (filterResult.executed) {
              const passedSet = filterResult.passedCodes;
              filteredItems = result.items.filter(
                (item) => passedSet.has(item.stock_code) && !isExcludedStockName(item.stock_name),
              );
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
      let totalCount = Infinity;

      const isCancelled = (): boolean => {
        if (cancelledRef.current) return true;
        if (signal?.aborted) return true;
        return false;
      };

      /** 拉取单页（带重试与取消），返回该页 items/total */
      const fetchPage = async (
        offset: number,
      ): Promise<{ items: StockItem[]; total: number }> => {
        let lastErr: Error | null = null;
        for (let attempt = 0; attempt <= BATCH_MAX_RETRIES; attempt++) {
          if (isCancelled()) throw new Error('已取消');
          if (attempt > 0) {
            const delay = BATCH_RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
            await sleep(delay);
          }
          try {
            const requestParams = buildScreeningParams(
              state, sortByParam, sortAscParam, BATCH, offset, watchlistCodes,
            );
            const result = (await fetchStocks(requestParams, signal)) as FetchStocksResponse;
            return { items: (result.items as StockItem[]) || [], total: result.total || 0 };
          } catch (err) {
            if (isCancelled()) throw new Error('已取消');
            if (isApiErrorLike(err) && (err.name === 'CanceledError' || err.code === 'ERR_CANCELED')) {
              throw new Error('已取消');
            }
            lastErr = err instanceof Error ? err : new Error(String(err));
            console.warn(`[loadAllCandidates] offset=${offset} 第${attempt + 1}次拉取失败: ${lastErr.message}`);
          }
        }
        throw new Error(`候选股拉取失败: ${lastErr?.message || '未知错误'}`);
      };

      // 第一页拿 total，再对其余分页并发拉取（顺序按 offset 复原）。
      // 港股/美股候选集大（港股约 2.7k 只 ≈ 14 页），串行拉取约需 80s，
      // 并发后显著缩短（K 2026-10-10）。
      const first = await fetchPage(0);
      totalCount = first.total;
      const pages: StockItem[][] = [first.items];
      let loaded = first.items.length;
      const report = () => {
        const pct = Math.min(100, Math.round((loaded / Math.max(totalCount, 1)) * 100 * CONFIG.CANDIDATE_FETCH_WEIGHT));
        setProgress(pct);
        setProgressText(`正在拉取候选股 ${loaded.toLocaleString()}/${totalCount.toLocaleString()} 只`);
      };
      report();

      const maxPages = Math.min(Math.ceil(totalCount / BATCH), MAX_BATCH_LOOPS);
      if (maxPages > MAX_BATCH_LOOPS) {
        throw new Error(`候选股数量超过上限（${BATCH * MAX_BATCH_LOOPS}只），请缩小筛选范围`);
      }

      const offsets: number[] = [];
      for (let p = 1; p < maxPages; p++) offsets.push(p * BATCH);

      for (let i = 0; i < offsets.length; i += CANDIDATE_FETCH_CONCURRENCY) {
        if (isCancelled()) throw new Error('已取消');
        const group = offsets.slice(i, i + CANDIDATE_FETCH_CONCURRENCY);
        const results = await Promise.all(group.map((off) => fetchPage(off)));
        results.forEach((r, gi) => {
          const pageIndex = (i + gi) + 1;
          pages[pageIndex] = r.items;
          loaded += r.items.length;
        });
        report();
      }

      for (const page of pages) {
        if (page) all.push(...page);
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
    async (sortByParam: string, sortAscParam: boolean): Promise<{ items: StockItem[]; total: number } | null> => {
      const state = stateRef.current;
      const cache = cacheRef.current;

      // 【P0 修复】声明的自编条件必须都能解析出「可运行」的指标，否则不允许静默放行。
      // 历史缺陷：filterGroup 里存在自定义条件（hasCustomIndicator=true → 走全量管道），
      // 但引用的指标已被删除/未加载/公式为空时 extractCustomConditions 返回 []，
      // computeAndFilter 走 "conditions 为空 → 全部通过" 的 fail-open 分支，
      // 结果 = 候选股全量（K 2026-10-10：港股/美股「自编指标没起作用，100% 通过」）。
      const declaredCustom = (state.filterGroup?.conditions || []).filter(
        (c: FilterCondition) => c.source === 'custom' && c.sourceId,
      );
      if (declaredCustom.length > 0) {
        const resolved = extractCustomConditions(state.filterGroup?.conditions || [], state.customIndicators);
        const runnable = resolved.filter((c) => c.formula && c.formula.trim());
        if (runnable.length === 0) {
          throw new Error('所选自编指标不可用（指标可能已被删除，或公式为空），请重新选择后再选股');
        }
      }

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
          // 注意：不在此处 clearCache()。OHLCV 只与股票代码有关、与筛选范围无关，
          // 每次范围变化都清空会导致重复下载全市场 K 线（港股全量约 136s）。
          const [loadedCandidates] = await loadAllCandidates(sortByParam, sortAscParam, signal);
          candidates = loadedCandidates.filter((c) => !isExcludedStockName(c.stock_name));
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
          return { items: [], total: 0 };
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
          return { items: resultItems, total: resultItems.length };
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

        const ohlcvMap = await service.loadOhlcv(codes, signal, (done, totalCount) => {
          const pct = Math.round(
            baseProgress + (done / Math.max(totalCount, 1)) * CONFIG.OHLCV_LOAD_WEIGHT * 100,
          );
          setProgress(pct);
          setProgressText(`正在加载K线数据 ${done.toLocaleString()}/${totalCount.toLocaleString()} 只`);
        });

        // 覆盖度可见化：无 K 线的候选股会被 computeAndFilter 静默剔除，
        // 若占比可观必须提示，否则用户会误判为「指标没起作用」（K 2026-10-10）。
        const missingBars = codes.filter((c) => (ohlcvMap.get(c)?.length ?? 0) === 0).length;
        if (missingBars > 0) {
          messageApi.warning(`${missingBars.toLocaleString()} 只候选股缺少K线数据，已从结果中剔除`);
        }

        setPhase('computing-custom');
        const computeBaseProgress = (CONFIG.CANDIDATE_FETCH_WEIGHT + CONFIG.OHLCV_LOAD_WEIGHT) * 100;
        setProgress(Math.round(computeBaseProgress));
        setProgressText('正在计算自编指标...');

        // 各指标在 computeAndFilter 内部按「自身」窗口切片（不再全局统一切片），
        // 保证单指标结果与组合选时一致，组合结果 = 各指标单独结果的交集。
        const { passedCodes, scores } = await service.computeAndFilter(
          customConditions,
          codes,
          ohlcvMap,
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
          candidates
            .filter((c) => passedCodes.has(c.stock_code))
            .map((c) => ({
              ...c,
              custom_score: scores.get(c.stock_code),
            })),
          sortByParam,
          sortAscParam,
        );

        setItems(resultItems);
        setTotal(resultItems.length);
        setSortBy(sortByParam);
        setSortAsc(sortAscParam);
        setPhase('ready');
        setProgress(100);
        return { items: resultItems, total: resultItems.length };
      } catch (err) {
        if ((err as Error).message === '已取消' || signal.aborted) {
          setPhase('idle');
          setProgress(0);
          return null;
        }
        const msg = getErrorMessage(err, '选股失败，请稍后重试');
        setError(msg);
        setPhase('idle');
        messageApi.error(msg);
        return null;
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
        cacheRef.current = createEmptyCache();
        getCustomIndicatorService().clearCache();
        setPhase('idle');
        setProgress(0);
        const page = await fetchScreeningData({
          sortBy: sortByParam,
          sortAsc: sortAscParam,
          offset: 0,
          append: false,
        });
        setResultsResetToken((t) => t + 1);
        return page;
      }

      cancelledRef.current = false;
      setLoading(true);
      setPhase('fetching-candidates');

      const result = await runFullScreening(sortByParam, sortAscParam);
      setLoading(false);

      if (result) {
        setResultsResetToken((t) => t + 1);
        return result as FetchStocksResponse;
      }
      return null;
    },
    [fetchScreeningData, runFullScreening, sortBy, sortAsc],
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

  /**
   * 本地排序：仅对当前已加载的 items 排序，不重新触发后端选股查询。
   * 排序是纯展示交互，改变顺序不应导致 loading / 进度条 / 重新请求。
   */
  const applyLocalSort = useCallback(
    (column: string) => {
      const defaultAsc = CONFIG.DEFAULT_SORT_DIR[column] ?? false;
      const newAsc = sortBy === column ? !sortAsc : defaultAsc;
      setItems((prev) => sortItems(prev, column, newAsc));
      setSortBy(column);
      setSortAsc(newAsc);
    },
    [sortBy, sortAsc],
  );

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
    cacheRef.current = createEmptyCache();
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
    applyLocalSort,
    resultsResetToken,
    candidateTotal: cacheRef.current?.candidateTotal ?? 0,
  };
}
