import { useState, useEffect, useCallback, useRef } from 'react';
import { searchStocks } from '../stock-detail/api';
import type { StockSearchItem } from '../stock-detail/api';

export interface UseStockSearchResult {
  keyword: string;
  setKeyword: (kw: string) => void;
  options: StockSearchItem[];
  loading: boolean;
  error: string | null;
  triggerSearch: (kw: string) => void;
  clearOptions: () => void;
}

export function useStockSearch(debounceDelay = 300): UseStockSearchResult {
  const [keyword, setKeyword] = useState('');
  const [options, setOptions] = useState<StockSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const doSearch = useCallback(async (kw: string) => {
    if (abortRef.current) abortRef.current.abort();
    if (!kw.trim()) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await searchStocks(kw.trim());
      if (!controller.signal.aborted) {
        setOptions(result.items || []);
      }
    } catch (err: any) {
      if (!controller.signal.aborted) {
        setError(err.message || '搜索失败');
        setOptions([]);
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  // 防抖执行搜索
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doSearch(keyword);
    }, debounceDelay);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [keyword, doSearch, debounceDelay]);

  const triggerSearch = useCallback((kw: string) => {
    setKeyword(kw);
  }, []);

  const clearOptions = useCallback(() => {
    setOptions([]);
  }, []);

  return {
    keyword,
    setKeyword,
    options,
    loading,
    error,
    triggerSearch,
    clearOptions,
  };
}