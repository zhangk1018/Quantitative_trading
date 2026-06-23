/**
 * watchlist store - 自选股模块状态管理（V1.0）
 *
 * 设计要点：
 * - 不引入 Redux/Zustand，沿用项目其它 feature 的 React Context + useReducer 模式
 * - 提供 4 个 actions：LOAD/ADD/REMOVE/REFRESH，供 watchlist 页面与 stock-picker 共享
 * - 错误状态独立保留（lastError），避免单次失败把整个列表清空
 * - 添加自选时去重：若已在列表中 → 跳过（不抛错，调用方可选择性提示）
 */
import { createContext, useContext, useReducer, ReactNode, useCallback } from 'react';
import {
  WatchlistItem,
  fetchWatchlist,
  addWatchlist as apiAddWatchlist,
  removeWatchlist as apiRemoveWatchlist,
} from './api';

export interface WatchlistState {
  items: WatchlistItem[];
  loading: boolean;
  lastError: string | null;
  /** 最近一次批量操作的结果摘要（成功/跳过/失败数） */
  lastBatchSummary: { added: number; skipped: number; failed: number } | null;
}

type Action =
  | { type: 'LOAD_START' }
  | { type: 'LOAD_SUCCESS'; payload: WatchlistItem[] }
  | { type: 'LOAD_ERROR'; payload: string }
  | { type: 'ADD_ITEM'; payload: WatchlistItem }
  | { type: 'REMOVE_ITEM'; payload: string /* code */ }
  // K 2026-06-22 反馈 #4：补 SET_BATCH_SUMMARY action，让 addMany 完成后
  // 把统计写入 state.lastBatchSummary，供调用方 UI 展示（不只是返回）
  | { type: 'SET_BATCH_SUMMARY'; payload: { added: number; skipped: number; failed: number } }
  | { type: 'CLEAR_BATCH_SUMMARY' }
  | { type: 'CLEAR_ERROR' };

export const initialState: WatchlistState = {
  items: [],
  loading: false,
  lastError: null,
  lastBatchSummary: null,
};

/** @internal 导出供单测验证 */
export function watchlistReducer(state: WatchlistState, action: Action): WatchlistState {
  switch (action.type) {
    case 'LOAD_START':
      return { ...state, loading: true, lastError: null };
    case 'LOAD_SUCCESS':
      return { ...state, loading: false, items: action.payload, lastError: null };
    case 'LOAD_ERROR':
      return { ...state, loading: false, lastError: action.payload };
    case 'ADD_ITEM': {
      // 防御：重复 code 不重复加入
      if (state.items.some((i) => i.code === action.payload.code)) {
        return state;
      }
      return { ...state, items: [...state.items, action.payload] };
    }
    case 'REMOVE_ITEM':
      return {
        ...state,
        items: state.items.filter((i) => i.code !== action.payload),
      };
    case 'SET_BATCH_SUMMARY':
      return { ...state, lastBatchSummary: action.payload };
    case 'CLEAR_BATCH_SUMMARY':
      return { ...state, lastBatchSummary: null };
    case 'CLEAR_ERROR':
      return { ...state, lastError: null };
    default:
      return state;
  }
}

interface WatchlistContextValue {
  state: WatchlistState;
  refresh: () => Promise<void>;
  addOne: (code: string, groupName?: string) => Promise<WatchlistItem | 'duplicate' | null>;
  removeOne: (code: string) => Promise<boolean>;
  /** 批量添加（用于选股结果批量加入自选） */
  addMany: (
    codes: string[],
    groupName?: string,
  ) => Promise<{ added: number; skipped: number; failed: number; errors: string[] }>;
  clearBatchSummary: () => void;
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(watchlistReducer, initialState);

  const refresh = useCallback(async () => {
    dispatch({ type: 'LOAD_START' });
    try {
      const items = await fetchWatchlist();
      dispatch({ type: 'LOAD_SUCCESS', payload: items });
    } catch (e) {
      dispatch({ type: 'LOAD_ERROR', payload: (e as Error).message });
    }
  }, []);

  /**
   * 添加单只：
   * - 已在列表 → 返回 'duplicate'，不调后端
   * - 后端 409 冲突 → 同样视作 duplicate（防御）
   * - 其它错误 → 返回 null，错误信息通过 lastError 暴露
   */
  const addOne = useCallback(
    async (code: string, groupName?: string): Promise<WatchlistItem | 'duplicate' | null> => {
      if (state.items.some((i) => i.code === code)) {
        return 'duplicate';
      }
      try {
        const item = await apiAddWatchlist({ code, group_name: groupName });
        dispatch({ type: 'ADD_ITEM', payload: item });
        return item;
      } catch (e: any) {
        // 409 业务冲突：后端已存在 → 视作 duplicate
        const msg = (e?.response?.data?.message || e?.message || '') as string;
        if (e?.response?.status === 409 || msg.includes('已在自选股中')) {
          return 'duplicate';
        }
        dispatch({ type: 'LOAD_ERROR', payload: msg || '添加自选失败' });
        return null;
      }
    },
    [state.items],
  );

  const removeOne = useCallback(async (code: string): Promise<boolean> => {
    try {
      await apiRemoveWatchlist(code);
      dispatch({ type: 'REMOVE_ITEM', payload: code });
      return true;
    } catch (e) {
      dispatch({ type: 'LOAD_ERROR', payload: (e as Error).message });
      return false;
    }
  }, []);

  /**
   * 批量添加（用于选股结果）：
   * - 串行执行避免触发后端连接池过载
   * - 失败不影响其它股票继续添加
   * - 返回分类统计供 UI 提示
   */
  const addMany = useCallback(
    async (
      codes: string[],
      groupName?: string,
    ): Promise<{ added: number; skipped: number; failed: number; errors: string[] }> => {
      let added = 0;
      let skipped = 0;
      let failed = 0;
      const errors: string[] = [];
      for (const code of codes) {
        const result = await addOne(code, groupName);
        if (result === null) {
          failed += 1;
          errors.push(code);
        } else if (result === 'duplicate') {
          skipped += 1;
        } else {
          added += 1;
        }
      }
      // K 2026-06-22 反馈 #4：把统计写回 state.lastBatchSummary，便于其它页面消费
      dispatch({
        type: 'SET_BATCH_SUMMARY',
        payload: { added, skipped, failed },
      });
      return { added, skipped, failed, errors };
    },
    [addOne],
  );

  const clearBatchSummary = useCallback(() => {
    dispatch({ type: 'CLEAR_BATCH_SUMMARY' });
  }, []);

  return (
    <WatchlistContext.Provider
      value={{ state, refresh, addOne, removeOne, addMany, clearBatchSummary }}
    >
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist() {
  const ctx = useContext(WatchlistContext);
  if (!ctx) {
    throw new Error('useWatchlist must be used within a WatchlistProvider');
  }
  return ctx;
}
