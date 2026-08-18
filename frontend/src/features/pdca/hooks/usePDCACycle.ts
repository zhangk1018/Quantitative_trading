/**
 * usePDCACycle.ts — 周期列表加载 Hook
 *
 * 封装周期列表加载、排序、选中周期管理逻辑，
 * 消除 CheckModule / ActModule 中的重复代码。
 *
 * 变更历史：
 * - 2026-08-18: 使用解包后的 fetchCycles 直接返回 PDCACycle[]，
 *   移除手动 res.code 检查；loadCycles 响应 statusOrder 依赖变化。
 */
import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import type { PDCACycle } from '../types';
import { fetchCycles } from '../services/cycle';

interface UsePDCACycleOptions {
  /** 排序权重：key=状态名, value=排序值，越小越靠前。默认 CHECK/ACT 优先 */
  statusOrder?: Record<string, number>;
}

interface UsePDCACycleReturn {
  cycles: PDCACycle[];
  loading: boolean;
  selectedCycleId: number | null;
  selectedCycle: PDCACycle | undefined;
  setSelectedCycleId: (id: number | null) => void;
  refresh: () => Promise<void>;
}

export function usePDCACycle(options?: UsePDCACycleOptions): UsePDCACycleReturn {
  const [cycles, setCycles] = useState<PDCACycle[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCycleId, setSelectedCycleId] = useState<number | null>(null);

  // 使用 useCallback 包裹，声明 statusOrder 依赖
  const loadCycles = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchCycles();
      const orderMap = options?.statusOrder ?? { CHECK: 0, ACT: 1, DO: 2, PLAN: 3 };
      items.sort((a, b) => (orderMap[a.status] ?? 99) - (orderMap[b.status] ?? 99));
      setCycles(items);
    } catch (err: unknown) {
      message.error('加载周期列表失败: ' + (err instanceof Error ? err.message : ''));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options?.statusOrder?.CHECK, options?.statusOrder?.ACT, options?.statusOrder?.DO, options?.statusOrder?.PLAN]);

  useEffect(() => {
    loadCycles();
  }, [loadCycles]);

  const selectedCycle = cycles.find((c) => c.id === selectedCycleId);

  return {
    cycles,
    loading,
    selectedCycleId,
    selectedCycle,
    setSelectedCycleId,
    refresh: loadCycles,
  };
}