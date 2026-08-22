import { useState, useCallback, useMemo } from 'react';
import { App } from 'antd';
import { useScreenerDispatch, useScreenerSelector } from '../context/ScreenerContext';
import { exportToCsv, exportToTxt } from '../utils/screener';
import { useSelection } from './useSelection';
import { useWatchlistAdd } from './useWatchlistAdd';
import { useStrategyUI } from './useStrategyUI';
import type { StockItem, FetchStocksResponse } from '../types';

/**
 * 选股器操作逻辑聚合 Hook
 *
 * 组合 useSelection / useWatchlistAdd / useStrategyUI 三个子 Hook，
 * 加上排序、导出、重置、开始选股、双击分析、筛选计数等剩余逻辑。
 *
 * 依赖：useScreenerData 返回的 fetchFirstPage / clearResults
 */
export function useStockPickerActions(
  items: StockItem[],
  _total: number,
  _sortBy: string,
  _sortAsc: boolean,
  _loading: boolean,
  fetchFirstPage: (newSortBy?: string, newSortAsc?: boolean) => Promise<FetchStocksResponse | null>,
  clearResults: () => void,
  tableContainerRef: React.RefObject<HTMLDivElement | null>,
  onSortLocal: (column: string) => void,
) {
  const { message } = App.useApp();
  const dispatch = useScreenerDispatch();

  // ========== 子 Hook ==========
  const selection = useSelection(items);
  const watchlistAdd = useWatchlistAdd(
    selection.selectedCodes, selection.selectedCount, selection.setSelectedCodes,
  );
  const strategyUI = useStrategyUI();

  // ========== 排序 ==========
  const handleSort = useCallback(
    (column: string) => {
      onSortLocal(column);
      if (tableContainerRef.current) {
        tableContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },
    [onSortLocal, tableContainerRef],
  );

  // ========== 导出 ==========
  const handleExport = useCallback((format: 'csv' | 'txt') => {
    if (items.length === 0) {
      message.warning('暂无可导出的数据，请先选股');
      return;
    }
    if (format === 'csv') {
      exportToCsv(items);
    } else {
      exportToTxt(items);
    }
    message.success(`已导出 ${items.length} 只股票（${format.toUpperCase()}）`);
  }, [items]);

  // ========== 重置 ==========
  const handleReset = useCallback(() => {
    dispatch({ type: 'RESET_ALL' });
    clearResults();
    selection.setSelectedCodes(new Set());
  }, [dispatch, clearResults, selection.setSelectedCodes]);

  // ========== 开始选股 ==========
  const handleStartScreening = useCallback(async () => {
    const result = await fetchFirstPage();
    if (result && result.items.length > 0) {
      // 滚动到顶部，确保展示完整列表
      if (tableContainerRef.current) {
        tableContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
      }
      message.success(`选股成功，共 ${result.total} 只`);
    }
  }, [fetchFirstPage, tableContainerRef]);

  // ========== 双击查看分析 ==========
  const [analysisStock, setAnalysisStock] = useState<StockItem | null>(null);
  const handleDoubleClick = useCallback((stock: StockItem) => {
    setAnalysisStock(stock);
  }, []);

  // ========== 筛选条件计数 ==========
  const marketCount = useScreenerSelector((s) => s.marketIndicators.selected.length);
  const financialCount = useScreenerSelector((s) => s.financialIndicators.selected.length);
  const techCount = useScreenerSelector((s) => Object.keys(s.technical.selected).length);
  const conditionCount = useScreenerSelector((s) => s.condition.filterGroup?.conditions?.length || 0);
  const totalFiltersCount = useMemo(
    () => marketCount + financialCount + techCount + conditionCount,
    [marketCount, financialCount, techCount, conditionCount],
  );

  return {
    // 选中
    ...selection,
    // 操作
    handleSort, handleExport, handleReset, handleStartScreening,
    handleDoubleClick,
    // 分析
    analysisStock, setAnalysisStock,
    // 添加自选
    ...watchlistAdd,
    // 策略
    ...strategyUI,
    // 计数
    totalFiltersCount,
    // 原始 selector
    filterGroup: useScreenerSelector((s) => s.condition.filterGroup),
  } as const;
}