import { useState, useCallback, useEffect } from 'react';
import type { ScreenerState } from '../context/ScreenerContext';

// ==================== 存储抽象层 ====================

/** 策略存储接口，便于测试时替换为内存存储 */
export interface IStrategyStorage {
  load(): unknown;
  save(data: unknown): void;
}

/** localStorage 实现（Base64 编码存储，防止普通阅读） */
export class LocalStorageStrategyStorage implements IStrategyStorage {
  private readonly key: string;

  constructor(key = 'screener_strategies') {
    this.key = key;
  }

  load(): unknown {
    const raw = localStorage.getItem(this.key);
    if (!raw) return null;
    try {
      // Base64 解码（兼容 Unicode 字符）
      return JSON.parse(decodeURIComponent(atob(raw)));
    } catch {
      // 兼容旧格式（未编码的 JSON）
      try {
        return JSON.parse(raw);
      } catch {
        return null;
      }
    }
  }

  save(data: unknown): void {
    const json = JSON.stringify(data);
    const encoded = btoa(encodeURIComponent(json));
    localStorage.setItem(this.key, encoded);
  }
}

// ==================== 版本管理 ====================

/** 当前策略数据格式版本号 */
const STRATEGY_VERSION = 1;

export interface SavedStrategy {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  /** 数据格式版本号，用于向前兼容 */
  version: number;
  state: Omit<ScreenerState, 'panels'>;
}

// ==================== 操作结果类型 ====================
export type StrategyOperationResult = { ok: true } | { ok: false; error: string };

/**
 * 清洗策略名称：去除 HTML 标签和特殊字符
 * 注：Antd Text 组件默认转义文本，此处双重保险
 */
export function sanitizeName(input: string): string {
  return input
    .replace(/<[^>]*>/g, '')     // 去除 HTML 标签
    .replace(/[<>"']/g, '')      // 去除特殊字符
    .trim()
    .slice(0, 30);               // 限制最大长度
}

// ==================== 序列化 ====================

/**
 * 序列化策略状态（排除 panels 避免保存 UI 偏好）
 */
export function serializeState(state: ScreenerState): Omit<ScreenerState, 'panels'> {
  const { panels, ...rest } = state;
  return rest;
}

// ==================== Hook ====================

/**
 * 本地存储选股策略 Hook — 负责读写 localStorage 中的选股策略
 * @param storage 存储实现，默认使用 localStorage
 * @returns 策略列表和增删改操作
 */
export function useSavedStrategies(storage?: IStrategyStorage) {
  const [strategies, setStrategies] = useState<SavedStrategy[]>([]);
  const store = storage ?? new LocalStorageStrategyStorage();

  /**
   * 校验策略数据完整性
   */
  const validateStrategy = (s: unknown): s is SavedStrategy => {
    if (typeof s !== 'object' || s === null) return false;
    const obj = s as Record<string, unknown>;
    return (
      typeof obj.id === 'string' &&
      typeof obj.name === 'string' &&
      typeof obj.createdAt === 'string' &&
      typeof obj.updatedAt === 'string' &&
      typeof obj.version === 'number' &&
      typeof obj.state === 'object'
    );
  };

  /**
   * 从存储加载所有策略（带版本校验）
   */
  const loadAll = useCallback(() => {
    const raw = store.load();
    if (!raw) {
      setStrategies([]);
      return;
    }
    if (!Array.isArray(raw)) {
      console.warn('[Screener] 策略列表格式错误，清空');
      setStrategies([]);
      return;
    }
    // 过滤：仅加载当前版本兼容的策略，跳过格式异常的
    const valid = raw.filter(s => {
      if (!validateStrategy(s)) return false;
      if (s.version !== STRATEGY_VERSION) {
        console.warn(`[Screener] 策略 "${s.name}" 版本 ${s.version} 不兼容（当前 ${STRATEGY_VERSION}），跳过`);
        return false;
      }
      return true;
    });
    setStrategies(valid);
  }, [store]);

  /**
   * 保存新策略
   */
  const saveStrategy = useCallback((name: string, state: ScreenerState): StrategyOperationResult => {
    const cleanedName = sanitizeName(name);
    if (!cleanedName) {
      return { ok: false as const, error: '策略名称不能为空' };
    }
    const newStrategy: SavedStrategy = {
      id: crypto.randomUUID(),
      name: cleanedName,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      version: STRATEGY_VERSION,
      state: serializeState(state),
    };
    const updated = [...strategies, newStrategy];
    try {
      store.save(updated);
      setStrategies(updated);
      return { ok: true as const };
    } catch (e) {
      console.error('[Screener] 保存策略失败', e);
      return { ok: false as const, error: e instanceof Error ? e.message : '保存失败' };
    }
  }, [strategies, store]);

  /**
   * 重命名策略
   */
  const updateStrategyName = useCallback((id: string, newName: string): StrategyOperationResult => {
    const cleanedName = sanitizeName(newName);
    if (!cleanedName) {
      return { ok: false as const, error: '策略名称不能为空' };
    }
    const updated = strategies.map(s =>
      s.id === id
        ? { ...s, name: cleanedName, updatedAt: new Date().toISOString() }
        : s
    );
    try {
      store.save(updated);
      setStrategies(updated);
      return { ok: true as const };
    } catch (e) {
      console.error('[Screener] 更新策略名称失败', e);
      return { ok: false as const, error: e instanceof Error ? e.message : '更新失败' };
    }
  }, [strategies, store]);

  /**
   * 删除策略
   */
  const deleteStrategy = useCallback((id: string): StrategyOperationResult => {
    const updated = strategies.filter(s => s.id !== id);
    try {
      store.save(updated);
      setStrategies(updated);
      return { ok: true as const };
    } catch (e) {
      console.error('[Screener] 删除策略失败', e);
      return { ok: false as const, error: e instanceof Error ? e.message : '删除失败' };
    }
  }, [strategies, store]);

  /**
   * 刷新列表（在存储变更后调用）
   */
  const reload = useCallback(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return {
    strategies,
    saveStrategy,
    updateStrategyName,
    deleteStrategy,
    reload,
  };
}