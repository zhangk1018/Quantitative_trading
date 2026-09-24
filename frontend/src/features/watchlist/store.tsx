/**
 * store.tsx — 自选股 localStorage 存储（零后端依赖）
 *
 * 数据模型：
 * - customGroups: 用户自建的分组名列表
 * - stocks: { groupName: [code, ...] } — 分组 → 股票代码列表
 * - 系统分组（全部/沪深/港股/美股）由代码派生存算，不持久化
 *
 * 多账号（协作单 42.0）：存储键按登录账号命名空间隔离（`watchlist:<username>`），
 * A/B 账号互不可见；多账号改造前的全局键 `watchlist` 由管理员首次登录承接一次。
 */

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';
import { SYSTEM_GROUPS, SYSTEM_GROUP_SET, detectMarketGroup, isValidStockCode } from './utils/stock-utils';
import { useOptionalAuth } from '@/features/auth/AuthContext';

export { SYSTEM_GROUP_SET, detectMarketGroup };
export type { SystemGroup } from './utils/stock-utils';

// ============================================
// Storage key & schema version
// ============================================
/** 多账号改造前的全局键（无账号维度），仅管理员首次登录承接一次 */
const LEGACY_STORAGE_KEY = 'watchlist';
const STORAGE_KEY_PREFIX = 'watchlist:';
const STORAGE_VERSION = 1;

/** 按账号取存储键（未启用认证门禁时回退老全局键） */
export function storageKeyFor(username: string): string {
  return username ? `${STORAGE_KEY_PREFIX}${username}` : LEGACY_STORAGE_KEY;
}

/** 空数据结构 */
function emptyStorage(): WatchlistStorage {
  return { version: STORAGE_VERSION, customGroups: [], stocks: {} };
}

// ============================================
// 持久化结构
// ============================================
interface WatchlistStorage {
  version: number;
  customGroups: string[];
  stocks: Record<string, string[]>;
}

function loadStorage(storageKey: string): WatchlistStorage {
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Schema 校验：版本号不匹配或结构无效时降级为空
      if (!parsed || typeof parsed.version !== 'number' || parsed.version !== STORAGE_VERSION) {
        return emptyStorage();
      }
      return {
        version: STORAGE_VERSION,
        customGroups: Array.isArray(parsed.customGroups) ? parsed.customGroups : [],
        stocks: parsed.stocks && typeof parsed.stocks === 'object' ? parsed.stocks : {},
      };
    }
  } catch {
    console.warn('[Watchlist] localStorage 读取自选股数据失败，使用空数据');
  }
  return emptyStorage();
}

function saveStorage(storageKey: string, data: WatchlistStorage): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify(data));
  } catch (e) {
    console.warn('Failed to save watchlist to localStorage', e);
  }
}

/**
 * 承接多账号改造前的全局键数据（仅管理员首次登录调用一次）。
 * 承接后删除老键，避免其它账号读到管理员的自选股。
 */
function takeLegacyStorage(): WatchlistStorage | null {
  const legacy = loadStorage(LEGACY_STORAGE_KEY);
  if (legacy.customGroups.length === 0 && Object.keys(legacy.stocks).length === 0) {
    return null;
  }
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    console.warn('[Watchlist] 清理旧全局自选股键失败');
  }
  return legacy;
}

// ============================================
// Bridge: 同步旧后端数据 → localStorage
// 某账号首次加载且本地无数据时读取该账号的后端自选股
// （后端按会话身份隔离，故只取当前登录账号的数据）
// ============================================
async function migrateFromBackend(): Promise<WatchlistStorage | null> {
  try {
    const resp = await fetch('/api/watchlist/');
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
      // 持久化由 Provider 统一按账号键写入
      return { version: STORAGE_VERSION, customGroups, stocks };
    }
  } catch {
    console.warn('[Watchlist] 后端数据迁移失败，使用本地数据');
  }
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
  /** 当前 state 对应的账号存储键（切账号时用于阻止串写） */
  loadedFor: string | null;
}

type WatchlistAction =
  | { type: 'LOAD'; payload: WatchlistStorage; loadedFor: string }
  | { type: 'RESET' }
  | { type: 'ADD_STOCK'; payload: { code: string; groupName: string } }
  | { type: 'BATCH_ADD_STOCKS'; payload: { codes: string[]; groupName: string } }
  | { type: 'REMOVE_FROM_GROUP'; payload: { code: string; groupName: string } }
  | { type: 'BATCH_REMOVE'; payload: { codes: string[]; groupName: string } }
  | { type: 'CREATE_GROUP'; payload: { name: string } }
  | { type: 'DELETE_GROUP'; payload: { name: string } }
  | { type: 'SET_LOADING'; payload: boolean };

export const INITIAL_STATE: WatchlistState = {
  customGroups: [],
  stocks: {},
  loading: true,
  migrated: false,
  loadedFor: null,
};

export function watchlistReducer(state: WatchlistState, action: WatchlistAction): WatchlistState {
  switch (action.type) {
    case 'LOAD':
      return {
        ...state,
        ...action.payload,
        loading: false,
        migrated: true,
        loadedFor: action.loadedFor,
      };

    // 切换账号：清空内存态，避免上一账号数据被短暂展示/串写
    case 'RESET':
      return { ...INITIAL_STATE };

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

    case 'BATCH_REMOVE': {
      const { codes, groupName } = action.payload;
      const codeSet = new Set(codes);
      const newStocks = { ...state.stocks };

      if (SYSTEM_GROUP_SET.has(groupName)) {
        // 从系统分组删除 = 从全部分组中移除这些股票
        for (const g of Object.keys(newStocks)) {
          newStocks[g] = newStocks[g].filter((c) => !codeSet.has(c));
          if (newStocks[g].length === 0 && !SYSTEM_GROUP_SET.has(g)) {
            delete newStocks[g];
          }
        }
      } else {
        // 从自建分组删除：仅从该分组移除
        if (newStocks[groupName]) {
          newStocks[groupName] = newStocks[groupName].filter((c) => !codeSet.has(c));
          if (newStocks[groupName].length === 0) {
            delete newStocks[groupName];
          }
        }
        // 检查每只股票是否还在其他自建分组中
        for (const code of codes) {
          const inOtherCustom = Object.entries(newStocks).some(
            ([g, cs]) => !SYSTEM_GROUP_SET.has(g) && g !== groupName && cs.includes(code),
          );
          if (!inOtherCustom) {
            for (const sys of SYSTEM_GROUPS) {
              if (newStocks[sys]) {
                newStocks[sys] = newStocks[sys].filter((c) => c !== code);
              }
            }
          }
        }
      }

      return { ...state, stocks: newStocks, customGroups: state.customGroups };
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
  /** 从指定分组批量移除股票 */
  removeMany: (codes: string[], groupName: string) => void;
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
  // 账号隔离：按当前登录用户名取存储键
  // - 无 AuthProvider（纯本地/单测）与未启用认证门禁 → 老全局键
  // - 登录态未解析/未登录 → 空键（先不加载不持久化，避免暂用老全局键造成串号）
  const auth = useOptionalAuth();
  const isAdmin = auth?.user?.role === 'admin';
  const username = auth?.user?.username ?? '';
  const storageKey = !auth
    ? LEGACY_STORAGE_KEY
    : auth.authDisabled
      ? LEGACY_STORAGE_KEY
      : username
        ? storageKeyFor(username)
        : '';

  const [state, dispatch] = useReducer(watchlistReducer, INITIAL_STATE);
  const loadedKeyRef = useRef<string | null>(null);

  // 初始化/切换账号：加载该账号本地数据；无数据时先承接管理员的老全局键，再回落到后端迁移
  useEffect(() => {
    if (!storageKey || loadedKeyRef.current === storageKey) return;
    loadedKeyRef.current = storageKey;
    dispatch({ type: 'RESET' });

    const deliver = (data: WatchlistStorage) => {
      // 只在仍停留在该账号键时派发，避免切换账号过程中的旧请求串号
      if (loadedKeyRef.current === storageKey) {
        dispatch({ type: 'LOAD', payload: data, loadedFor: storageKey });
      }
    };

    (async () => {
      const local = loadStorage(storageKey);
      if (local.customGroups.length > 0 || Object.keys(local.stocks).length > 0) {
        deliver(local);
        return;
      }
      // 多账号改造前的老全局数据：仅管理员首次承接（方案 §6.1 老数据归首个 admin）
      const legacy = username && isAdmin ? takeLegacyStorage() : null;
      if (legacy) {
        deliver(legacy);
        return;
      }
      deliver((await migrateFromBackend()) ?? emptyStorage());
    })();
  }, [storageKey, username, isAdmin]);

  // 状态变化时持久化（仅当 state 对应当前账号键，避免切号瞬间串写）
  useEffect(() => {
    if (storageKey && state.migrated && state.loadedFor === storageKey) {
      saveStorage(storageKey, {
        version: STORAGE_VERSION,
        customGroups: state.customGroups,
        stocks: state.stocks,
      });
    }
  }, [state.customGroups, state.stocks, state.migrated, state.loadedFor, storageKey]);

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

  const removeMany = useCallback(
    (codes: string[], groupName: string) => {
      if (codes.length === 0) return;
      dispatch({ type: 'BATCH_REMOVE', payload: { codes, groupName } });
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
        if (!isValidStockCode(trimmed)) {
          errors.push(`${trimmed}: 格式无效（需6位数字 / 港股 .HK / 美股字母代码）`);
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
    const local = loadStorage(storageKey);
    dispatch({ type: 'LOAD', payload: local, loadedFor: storageKey });
  }, [storageKey]);

  return (
    <WatchlistContext.Provider value={{ state, allGroups, addOne, addMany, removeOne, removeMany, createGroup, deleteGroup, refresh }}>
      {children}
    </WatchlistContext.Provider>
  );
}