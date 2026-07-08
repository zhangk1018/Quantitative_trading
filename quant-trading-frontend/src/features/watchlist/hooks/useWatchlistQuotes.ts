/**
 * hooks/useWatchlistQuotes.ts — 自选股行情数据获取 Hook
 *
 * 职责：
 * 1. 根据自选股代码列表拉取行情数据（含 AbortController 竞态防护）
 * 2. 维护行情数据缓存（Map<stock_code, StockItem>）
 * 3. 区分首次加载与刷新失败的错误处理策略
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { App } from 'antd';
import { fetchStocks, type StockItem } from '@/features/stock-detail/api';

/** 获取行情数据的最大条数 */
const MAX_WATCHLIST_SIZE = 200;

interface UseWatchlistQuotesResult {
  /** 行情数据映射表 */
  quotesMap: Map<string, StockItem>;
  /** 是否正在加载（首次加载） */
  loading: boolean;
  /** 是否正在刷新（非首次） */
  refreshing: boolean;
  /** 错误信息，null 表示无错误 */
  error: string | null;
  /** 手动刷新行情 */
  refresh: () => void;
}

export function useWatchlistQuotes(codes: string[]): UseWatchlistQuotesResult {
  const { message } = App.useApp();
  const [quotesMap, setQuotesMap] = useState<Map<string, StockItem>>(new Map());
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasLoaded = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const codesRef = useRef(codes);
  codesRef.current = codes;

  const fetchQuotes = useCallback(
    (isRefresh: boolean) => {
      const currentCodes = codesRef.current;
      if (currentCodes.length === 0) return;

      // 中止上一次未完成的请求
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);

      fetchStocks({ stock_codes: currentCodes.join(','), limit: MAX_WATCHLIST_SIZE }, controller.signal)
        .then((result) => {
          // 忽略已中止的请求
          if (controller.signal.aborted) return;
          const map = new Map<string, StockItem>();
          if (result.items) {
            result.items.forEach((item) => map.set(item.stock_code, item));
          }
          setQuotesMap(map);
          hasLoaded.current = true;
          setError(null);
        })
        .catch((e: any) => {
          if (controller.signal.aborted) return;
          const msg = e?.message || '获取行情失败';
          setError(msg);
          // 首次加载失败：清空数据，避免展示过时缓存
          if (!hasLoaded.current) {
            setQuotesMap(new Map());
          }
          message.error(msg);
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setLoading(false);
            setRefreshing(false);
          }
        });
    },
    [message],
  );

  // 代码列表变化时自动拉取行情
  const codesKey = codes.join(',');
  useEffect(() => {
    if (codes.length === 0) {
      setQuotesMap(new Map());
      setError(null);
      hasLoaded.current = false;
      return;
    }
    fetchQuotes(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codesKey]);

  // 组件卸载时中止请求
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const refresh = useCallback(() => {
    if (codes.length === 0) return;
    fetchQuotes(true);
  }, [codes.length, fetchQuotes]);

  return { quotesMap, loading, refreshing, error, refresh };
}