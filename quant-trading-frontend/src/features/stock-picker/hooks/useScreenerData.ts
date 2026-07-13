import { useState, useCallback, useRef, useEffect } from 'react';
import { App } from 'antd';
import { useScreenerSelector } from '../context/ScreenerContext';
import { fetchStocks } from '../../stock-detail/api';
import { buildScreeningParams, CONFIG, ScreenerFilterPayload } from '../utils/screener';
import type { StockItem, FetchStocksResponse } from '../types';

// ==================== 自选股代码读取 ====================
/** 从 localStorage 读取用户自选股代码列表（与 watchlist/store.tsx 共用 STORAGE_KEY） */
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

// ==================== 错误类型守卫 ====================
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

/**
 * 选股器数据管理 Hook
 *
 * 职责：
 * - 从 Context 读取筛选条件，同步到 useRef 保证最新值
 * - 封装 fetchScreeningData 请求逻辑（排序、分页、超时、取消）
 * - 提供 fetchFirstPage / fetchNextPage / clearResults
 * - 管理 loading / error / loadMoreError 状态，区分超时错误
 * - 页面可见性变化时取消请求，组件卸载时清理资源
 */
export function useScreenerData(messageApi: ReturnType<typeof App.useApp>['message']) {
  // ========== 筛选条件同步（ref 保证 fetchScreeningData 中始终读到最新值） ==========
  const selectedBoards = useScreenerSelector((s) => s.market.selectedBoards);
  const stockRange = useScreenerSelector((s) => s.market.stockRange);
  const marketIndicatorRanges = useScreenerSelector((s) => s.marketIndicators.ranges);
  const financialIndicatorRanges = useScreenerSelector((s) => s.financialIndicators.ranges);
  const selectedTechnicalIndicators = useScreenerSelector((s) => s.technical.selected);
  const filterGroup = useScreenerSelector((s) => s.condition.filterGroup);

  const stateRef = useRef<ScreenerFilterPayload>({
    selectedBoards, stockRange, marketIndicatorRanges,
    financialIndicatorRanges, selectedTechnicalIndicators, filterGroup,
  });
  // ref 更新不涉及 UI，使用 useEffect 即可，避免同步渲染阻塞
  useEffect(() => {
    stateRef.current = {
      selectedBoards, stockRange, marketIndicatorRanges,
      financialIndicatorRanges, selectedTechnicalIndicators, filterGroup,
    };
  });

  // ========== 数据状态 ==========
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

  // ========== 请求控制资源 ==========
  const abortRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timedOutRef = useRef(false); // 区分超时 vs 用户取消

  // ========== 核心请求 ==========
  const fetchScreeningData = useCallback(
    async (params: {
      sortBy: string;
      sortAsc: boolean;
      offset: number;
      append?: boolean;
      signal?: AbortSignal;
    }): Promise<FetchStocksResponse | null> => {
      const { sortBy: sortByParam, sortAsc: sortAscParam, offset: offsetParam, append = false, signal } = params;

      // 取消上一次请求
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

        setItems((prev) => (append ? [...prev, ...result.items] : result.items));
        setTotal(result.total || 0);
        setSortBy(sortByParam);
        setSortAsc(sortAscParam);
        setOffset(offsetParam);
        return result;
      } catch (err: unknown) {
        // 超时 → 抛出明确消息
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
        // 用户取消或页面切换 → 静默
        if (finalSignal.aborted) return null;
        if (isApiErrorLike(err) && (err.name === 'CanceledError' || err.code === 'ERR_CANCELED')) return null;

        // 网络/服务器错误
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

  // ========== 公开方法 ==========
  /** 获取第一页数据 */
  const fetchFirstPage = useCallback(
    async (newSortBy?: string, newSortAsc?: boolean): Promise<FetchStocksResponse | null> => {
      const sortByParam = newSortBy ?? sortBy;
      const sortAscParam = newSortAsc ?? sortAsc;
      return fetchScreeningData({
        sortBy: sortByParam,
        sortAsc: sortAscParam,
        offset: 0,
        append: false,
      });
    },
    [fetchScreeningData, sortBy, sortAsc],
  );

  /** 加载下一页 */
  const fetchNextPage = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      const nextOffset = offset + PAGE_SIZE;
      fetchScreeningData({ sortBy, sortAsc, offset: nextOffset, append: true });
      debounceTimerRef.current = null;
    }, CONFIG.DEBOUNCE_DELAY);
  }, [fetchScreeningData, sortBy, sortAsc, offset, PAGE_SIZE]);

  /** 清空结果 */
  const clearResults = useCallback(() => {
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
  }, []);

  /** 重试第一页 */
  const retry = useCallback(() => {
    return fetchFirstPage();
  }, [fetchFirstPage]);

  /** 重试加载更多 */
  const retryLoadMore = useCallback(() => {
    fetchNextPage();
  }, [fetchNextPage]);

  // ========== 生命周期 ==========
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
      if (abortRef.current) abortRef.current.abort();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, []);

  return {
    items, total, loading, loadingMore, error, loadMoreError,
    sortBy, sortAsc, offset, PAGE_SIZE,
    fetchFirstPage, fetchNextPage, clearResults, retry, retryLoadMore,
  };
}