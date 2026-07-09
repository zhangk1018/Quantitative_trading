/**
 * store.tsx — 自选股 localStorage 存储（零后端依赖）
 *
 * 数据模型：
 * - customGroups: 用户自建的分组名列表
 * - stocks: { groupName: [code, ...] } — 分组 → 股票代码列表
 * - 系统分组（全部/沪深/港股/美股）由代码派生存算，不持久化
 */

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';
import { SYSTEM_GROUPS, SYSTEM_GROUP_SET, detectMarketGroup } from './utils/stock-utils';

export { SYSTEM_GROUP_SET, detectMarketGroup };
export type { SystemGroup } from './utils/stock-utils';

// ============================================
// Storage key & schema version
// ============================================
const STORAGE_KEY = 'watchlist';
const STORAGE_VERSION = 1;

// ============================================
// 持久化结构
// ============================================
interface WatchlistStorage {
  version: number;
  customGroups: string[];
  stocks: Record<string, string[]>;
}

function loadStorage(): WatchlistStorage {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Schema 校验：版本号不匹配或结构无效时降级为空
      if (!parsed || typeof parsed.version !== 'number' || parsed.version !== STORAGE_VERSION) {
        return { version: STORAGE_VERSION, customGroups: [], stocks: {} };
      }
      return {
        version: STORAGE_VERSION,
        customGroups: Array.isArray(parsed.customGroups) ? parsed.customGroups : [],
        stocks: parsed.stocks && typeof parsed.stocks === 'object' ? parsed.stocks : {},
      };
    }
  } catch { /* ignore */ }
  return { version: STORAGE_VERSION, customGroups: [], stocks: {} };
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
      const data: WatchlistStorage = { version: STORAGE_VERSION, customGroups, stocks };
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
  | { type: 'BATCH_ADD_STOCKS'; payload: { codes: string[]; groupName: string } }
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
      return addStockToState(state, code, groupName);
    }

    case 'BATCH_ADD_STOCKS': {
      const { codes, groupName } = action.payload;
      const newStocks = { ...state.stocks };

      // 使用 Set 一次性收集所有去重代码，避免循环内重复拷贝
      const targetSet = new Set(newStocks[groupName] || []);
      const allSet = new Set(newStocks['全部'] || []);
      const marketSets: Record<string, Set<string>> = {};

      for (const code of codes) {
        targetSet.add(code);
        allSet.add(code);
        const market = detectMarketGroup(code);
        if (!marketSets[market]) {
          marketSets[market] = new Set(newStocks[market] || []);
        }
        marketSets[market].add(code);
      }

      newStocks[groupName] = Array.from(targetSet);
      newStocks['全部'] = Array.from(allSet);
      for (const [market, codeSet] of Object.entries(marketSets)) {
        newStocks[market] = Array.from(codeSet);
      }

      return { ...state, stocks: newStocks };
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

/** 纯函数：向 state 添加一只股票到目标分组（同时自动加入"全部"和市场分组） */
function addStockToState(state: WatchlistState, code: string, groupName: string): WatchlistState {
  const newStocks = { ...state.stocks };
  const newCustomGroups = [...state.customGroups];

  if (!newStocks[groupName]) newStocks[groupName] = [];
  if (!newStocks[groupName].includes(code)) {
    newStocks[groupName] = [...newStocks[groupName], code];
  }

  if (!newStocks['全部']) newStocks['全部'] = [];
  if (!newStocks['全部'].includes(code)) {
    newStocks['全部'] = [...newStocks['全部'], code];
  }

  const market = detectMarketGroup(code);
  if (!newStocks[market]) newStocks[market] = [];
  if (!newStocks[market].includes(code)) {
    newStocks[market] = [...newStocks[market], code];
  }

  return { ...state, stocks: newStocks, customGroups: newCustomGroups };
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
    saveStorage({ version: STORAGE_VERSION, customGroups: s.customGroups, stocks: s.stocks });
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
          dispatch({ type: 'LOAD', payload: { version: STORAGE_VERSION, customGroups: [], stocks: {} } });
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
      const trimmedGroup = groupName.trim() || '全部';
      dispatch({ type: 'ADD_STOCK', payload: { code: code.trim(), groupName: trimmedGroup } });
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
      const validCodes: string[] = [];
      let skipped = 0;
      const errors: string[] = [];
      const batchSeen = new Set<string>();

      const existing = state.stocks[targetGroup] || [];
      for (const code of codes) {
        const trimmed = code.trim();
        if (!trimmed) {
          errors.push('空代码已跳过');
          skipped++;
          continue;
        }
        if (!/^\d{6}$/.test(trimmed)) {
          errors.push(`${trimmed}: 格式无效（需6位数字）`);
          skipped++;
          continue;
        }
        if (batchSeen.has(trimmed)) {
          errors.push(`${trimmed}: 批次内重复`);
          skipped++;
          continue;
        }
        batchSeen.add(trimmed);
        if (existing.includes(trimmed)) {
          errors.push(`${trimmed}: 已在目标分组中`);
          skipped++;
          continue;
        }
        validCodes.push(trimmed);
      }

      if (validCodes.length > 0) {
        dispatch({ type: 'BATCH_ADD_STOCKS', payload: { codes: validCodes, groupName: targetGroup } });
      }

      return { added: validCodes.length, skipped, failed: 0, errors };
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