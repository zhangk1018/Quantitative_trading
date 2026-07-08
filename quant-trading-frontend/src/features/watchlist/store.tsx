/**
 * store.tsx — 自选股 localStorage 存储（零后端依赖）
 *
 * 数据模型：
 * - customGroups: 用户自建的分组名列表
 * - stocks: { groupName: [code, ...] } — 分组 → 股票代码列表
 * - 系统分组（全部/沪深/港股/美股）由代码派生存算，不持久化
 */

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';

// ============================================
// Storage key
// ============================================
const STORAGE_KEY = 'watchlist';

// ============================================
// 系统分组（硬编码，不可删除）
// ============================================
const SYSTEM_GROUPS = ['全部', '沪深', '港股', '美股'] as const;
export type SystemGroup = (typeof SYSTEM_GROUPS)[number];
export const SYSTEM_GROUP_SET: ReadonlySet<string> = new Set(SYSTEM_GROUPS);

/** 根据代码前缀判断所属市场分组 */
export function detectMarketGroup(code: string): string {
  if (!code || code.length < 2) return '沪深';
  const prefix = code.substring(0, 1);
  // 沪深：6xxxx(上海), 0xxxx/3xxxx(深圳)
  if (['6', '0', '3'].includes(prefix)) return '沪深';
  // 港股：暂按代码规则预留
  // 美股：暂按代码规则预留
  return '沪深';
}

// ============================================
// 持久化结构
// ============================================
interface WatchlistStorage {
  customGroups: string[];
  stocks: Record<string, string[]>;
}

function loadStorage(): WatchlistStorage {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        customGroups: Array.isArray(parsed.customGroups) ? parsed.customGroups : [],
        stocks: parsed.stocks && typeof parsed.stocks === 'object' ? parsed.stocks : {},
      };
    }
  } catch { /* ignore */ }
  return { customGroups: [], stocks: {} };
}

function saveStorage(data: WatchlistStorage): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

// ============================================
// Bridge: 同步旧后端数据 → localStorage
// 首次加载时读取旧接口数据，写入 localStorage
// ============================================
async function migrateFromBackend(): Promise<WatchlistStorage | null> {
  try {
    const resp = await fetch('/api/watchlist/?user_id=default');
    const json = await resp.json();
    if (json.code === 200 && Array.isArray(json.data) && json.data.length > 0) {
      const stocks: Record<string, string[]> = {};
      const codes = new Set<string>();
      for (const item of json.data) {
        const group = item.group_name || '默认分组';
        if (!stocks[group]) stocks[group] = [];
        if (!stocks[group].includes(item.code)) {
          stocks[group].push(item.code);
        }
        codes.add(item.code);
      }
      // 为所有股票自动填充"全部"和市场分组
      stocks['全部'] = Array.from(codes);
      for (const code of codes) {
        const market = detectMarketGroup(code);
        if (!stocks[market]) stocks[market] = [];
        if (!stocks[market].includes(code)) stocks[market].push(code);
      }
      const customGroups = Object.keys(stocks).filter((g) => !SYSTEM_GROUP_SET.has(g));
      const data: WatchlistStorage = { customGroups, stocks };
      saveStorage(data);
      return data;
    }
  } catch { /* ignore */ }
  return null;
}

// ============================================
// State & Actions
// ============================================
interface WatchlistState {
  customGroups: string[];
  stocks: Record<string, string[]>;
  loading: boolean;
  migrated: boolean;
}

type WatchlistAction =
  | { type: 'LOAD'; payload: WatchlistStorage }
  | { type: 'ADD_STOCK'; payload: { code: string; groupName: string } }
  | { type: 'REMOVE_FROM_GROUP'; payload: { code: string; groupName: string } }
  | { type: 'CREATE_GROUP'; payload: { name: string } }
  | { type: 'DELETE_GROUP'; payload: { name: string } }
  | { type: 'SET_LOADING'; payload: boolean };

function reducer(state: WatchlistState, action: WatchlistAction): WatchlistState {
  switch (action.type) {
    case 'LOAD':
      return { ...state, ...action.payload, loading: false, migrated: true };

    case 'ADD_STOCK': {
      const { code, groupName } = action.payload;
      const newStocks = { ...state.stocks };
      const newCustomGroups = [...state.customGroups];

      // 添加到目标分组
      if (!newStocks[groupName]) newStocks[groupName] = [];
      if (!newStocks[groupName].includes(code)) {
        newStocks[groupName] = [...newStocks[groupName], code];
      }

      // 自动添加到"全部"
      if (!newStocks['全部']) newStocks['全部'] = [];
      if (!newStocks['全部'].includes(code)) {
        newStocks['全部'] = [...newStocks['全部'], code];
      }

      // 自动添加到市场分组
      const market = detectMarketGroup(code);
      if (!newStocks[market]) newStocks[market] = [];
      if (!newStocks[market].includes(code)) {
        newStocks[market] = [...newStocks[market], code];
      }

      return { ...state, stocks: newStocks, customGroups: newCustomGroups };
    }

    case 'REMOVE_FROM_GROUP': {
      const { code, groupName } = action.payload;
      const newStocks = { ...state.stocks };
      const newCustomGroups = [...state.customGroups];

      if (SYSTEM_GROUP_SET.has(groupName)) {
        // 从系统分组删除 = 从全部分组中移除该股票
        for (const g of Object.keys(newStocks)) {
          newStocks[g] = newStocks[g].filter((c) => c !== code);
          if (newStocks[g].length === 0 && !SYSTEM_GROUP_SET.has(g)) {
            delete newStocks[g];
          }
        }
      } else {
        // 从自建分组删除：仅从该分组移除
        if (newStocks[groupName]) {
          newStocks[groupName] = newStocks[groupName].filter((c) => c !== code);
          if (newStocks[groupName].length === 0) {
            delete newStocks[groupName];
          }
        }
        // 检查该股票是否还在其他自建分组中
        const inOtherCustom = Object.entries(newStocks).some(
          ([g, codes]) => !SYSTEM_GROUP_SET.has(g) && g !== groupName && codes.includes(code),
        );
        if (!inOtherCustom) {
          // 从所有系统分组中移除
          for (const sys of SYSTEM_GROUPS) {
            if (newStocks[sys]) {
              newStocks[sys] = newStocks[sys].filter((c) => c !== code);
            }
          }
        }
      }

      return { ...state, stocks: newStocks, customGroups: newCustomGroups };
    }

    case 'CREATE_GROUP': {
      const { name } = action.payload;
      if (state.customGroups.includes(name)) return state;
      if (SYSTEM_GROUP_SET.has(name)) return state;
      return {
        ...state,
        customGroups: [...state.customGroups, name],
        stocks: { ...state.stocks, [name]: state.stocks[name] || [] },
      };
    }

    case 'DELETE_GROUP': {
      const { name } = action.payload;
      if (SYSTEM_GROUP_SET.has(name)) return state;
      const newStocks = { ...state.stocks };
      delete newStocks[name];
      return {
        ...state,
        customGroups: state.customGroups.filter((g) => g !== name),
        stocks: newStocks,
      };
    }

    case 'SET_LOADING':
      return { ...state, loading: action.payload };

    default:
      return state;
  }
}

// ============================================
// Context
// ============================================
interface WatchlistContextValue {
  state: WatchlistState;
  /** 所有可用分组（系统 + 自建） */
  allGroups: string[];
  /** 添加股票到指定分组 */
  addOne: (code: string, groupName: string) => void;
  /** 批量添加股票到指定分组 */
  addMany: (codes: string[], groupName: string) => { added: number; skipped: number; failed: number; errors: string[] };
  /** 从指定分组移除股票 */
  removeOne: (code: string, groupName: string) => void;
  /** 创建自建分组 */
  createGroup: (name: string) => boolean;
  /** 删除自建分组 */
  deleteGroup: (name: string) => void;
  /** 刷新（重新加载 localStorage） */
  refresh: () => void;
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export function useWatchlist(): WatchlistContextValue {
  const ctx = useContext(WatchlistContext);
  if (!ctx) throw new Error('useWatchlist must be used within WatchlistProvider');
  return ctx;
}

// ============================================
// Provider
// ============================================
export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, {
    customGroups: [],
    stocks: {},
    loading: true,
    migrated: false,
  });
  const migratedRef = useRef(false);

  const persist = useCallback((s: WatchlistState) => {
    saveStorage({ customGroups: s.customGroups, stocks: s.stocks });
  }, []);

  // 初始化：从 localStorage 加载，或从后端迁移
  useEffect(() => {
    if (migratedRef.current) return;
    migratedRef.current = true;
    (async () => {
      const local = loadStorage();
      if (local.customGroups.length > 0 || Object.keys(local.stocks).length > 0) {
        dispatch({ type: 'LOAD', payload: local });
      } else {
        const migrated = await migrateFromBackend();
        if (migrated) {
          dispatch({ type: 'LOAD', payload: migrated });
        } else {
          dispatch({ type: 'LOAD', payload: { customGroups: [], stocks: {} } });
        }
      }
    })();
  }, []);

  // 状态变化时持久化
  useEffect(() => {
    if (state.migrated) {
      persist(state);
    }
  }, [state.customGroups, state.stocks, state.migrated, persist]);

  const allGroups = [
    ...SYSTEM_GROUPS.filter((g) => state.stocks[g] && state.stocks[g].length > 0),
    ...state.customGroups.filter((g) => state.stocks[g] && state.stocks[g].length > 0),
  ];

  const addOne = useCallback(
    (code: string, groupName: string) => {
      dispatch({ type: 'ADD_STOCK', payload: { code, groupName } });
    },
    [],
  );

  const removeOne = useCallback(
    (code: string, groupName: string) => {
      dispatch({ type: 'REMOVE_FROM_GROUP', payload: { code, groupName } });
    },
    [],
  );

  const createGroup = useCallback(
    (name: string): boolean => {
      const trimmed = name.trim();
      if (!trimmed) return false;
      if (SYSTEM_GROUP_SET.has(trimmed)) return false;
      if (state.customGroups.includes(trimmed)) return false;
      dispatch({ type: 'CREATE_GROUP', payload: { name: trimmed } });
      return true;
    },
    [state.customGroups],
  );

  const deleteGroup = useCallback(
    (name: string) => {
      dispatch({ type: 'DELETE_GROUP', payload: { name } });
    },
    [],
  );

  const addMany = useCallback(
    (codes: string[], groupName: string): { added: number; skipped: number; failed: number; errors: string[] } => {
      const targetGroup = groupName.trim() || '全部';
      let added = 0;
      let skipped = 0;
      for (const code of codes) {
        if (!code || code.trim() === '') {
          skipped++;
          continue;
        }
        const existing = state.stocks[targetGroup] || [];
        if (existing.includes(code)) {
          skipped++;
        } else {
          dispatch({ type: 'ADD_STOCK', payload: { code, groupName: targetGroup } });
          added++;
        }
      }
      return { added, skipped, failed: 0, errors: [] };
    },
    [state.stocks],
  );

  const refresh = useCallback(() => {
    const local = loadStorage();
    dispatch({ type: 'LOAD', payload: local });
  }, []);

  return (
    <WatchlistContext.Provider value={{ state, allGroups, addOne, addMany, removeOne, createGroup, deleteGroup, refresh }}>
      {children}
    </WatchlistContext.Provider>
  );
}