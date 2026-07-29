import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSelection } from '@/features/stock-picker/hooks/useSelection';
import type { StockItem } from '@/features/stock-picker/types';

const makeStock = (code: string, name: string): StockItem => ({
  stock_code: code,
  stock_name: name,
  close: 10,
  change_pct: 0,
  turnover_rate: 0,
  pe: 10,
  pb: 1,
  market_cap: 100000000,
  amount: 1000000,
  listed_board: '上海主板',
});

const items: StockItem[] = [
  makeStock('600036', '招商银行'),
  makeStock('000001', '平安银行'),
  makeStock('300750', '宁德时代'),
];

describe('useSelection', () => {
  it('初始状态 selectedCount 为 0', () => {
    const { result } = renderHook(() => useSelection([]));
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.allSelected).toBe(false);
    expect(result.current.indeterminate).toBe(false);
  });

  it('toggleOne 添加选中', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleOne('600036');
    });
    expect(result.current.selectedCodes.has('600036')).toBe(true);
    expect(result.current.selectedCount).toBe(1);
  });

  it('toggleOne 再次点击取消选中', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleOne('600036');
    });
    act(() => {
      result.current.toggleOne('600036');
    });
    expect(result.current.selectedCodes.has('600036')).toBe(false);
    expect(result.current.selectedCount).toBe(0);
  });

  it('toggleOne 多个独立选中', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleOne('600036');
      result.current.toggleOne('000001');
    });
    expect(result.current.selectedCount).toBe(2);
    expect(result.current.selectedCodes.has('600036')).toBe(true);
    expect(result.current.selectedCodes.has('000001')).toBe(true);
  });

  it('toggleAll 全选所有', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleAll();
    });
    expect(result.current.selectedCount).toBe(3);
    expect(result.current.allSelected).toBe(true);
    expect(result.current.indeterminate).toBe(false);
  });

  it('toggleAll 再次点击取消全选', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleAll();
    });
    act(() => {
      result.current.toggleAll();
    });
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.allSelected).toBe(false);
  });

  it('partial selection 时 indeterminate 为 true', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.toggleOne('600036');
    });
    expect(result.current.selectedCount).toBe(1);
    expect(result.current.allSelected).toBe(false);
    expect(result.current.indeterminate).toBe(true);
  });

  it('空列表时 allSelected 为 false', () => {
    const { result } = renderHook(() => useSelection([]));
    expect(result.current.allSelected).toBe(false);
  });

  it('setSelectedCodes 直接设置选中集合', () => {
    const { result } = renderHook(() => useSelection(items));
    act(() => {
      result.current.setSelectedCodes(new Set(['600036', '000001']));
    });
    expect(result.current.selectedCount).toBe(2);
    expect(result.current.selectedCodes.has('600036')).toBe(true);
    expect(result.current.selectedCodes.has('000001')).toBe(true);
  });
});