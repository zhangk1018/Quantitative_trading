import { useState, useCallback, useMemo } from 'react';
import type { StockItem } from '../types';

/**
 * 表格选中状态管理 Hook
 *
 * 职责：单选/全选/计数逻辑，与 UI 无关
 * 可用于任何列表选中场景
 */
export function useSelection(items: StockItem[]) {
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  const allCodes = useMemo(
    () => items.map((s) => s.stock_code).filter((code) => code != null),
    [items],
  );
  const selectedCount = selectedCodes.size;
  const allSelected = allCodes.length > 0 && selectedCount === allCodes.length;
  const indeterminate = selectedCount > 0 && !allSelected;

  const toggleOne = useCallback((code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (allSelected) setSelectedCodes(new Set());
    else setSelectedCodes(new Set(allCodes));
  }, [allCodes, allSelected]);

  return {
    selectedCodes, selectedCount, allSelected, indeterminate,
    toggleOne, toggleAll, setSelectedCodes,
  } as const;
}