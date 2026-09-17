import { useState, useCallback, useEffect, useMemo } from 'react';
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
      console.warn('[Screener] 策略数据 Base64 解码失败，尝试兼容旧格式');
      // 兼容旧格式（未编码的 JSON）
      try {
        return JSON.parse(raw);
      } catch {
        console.warn('[Screener] 策略数据 JSON 解析失败');
        return null;
      }
    }
  }

  save(data: unknown): void {
    const json = JSON.stringify(data);
    const encoded = btoa(encodeURIComponent(json));
    try {
      localStorage.setItem(this.key, encoded);
    } catch (e) {
      console.warn('Failed to save strategies to localStorage', e);
    }
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
 * 生成唯一 ID
 * 优先使用 crypto.randomUUID（仅在 HTTPS/localhost 安全上下文可用），
 * 否则回退到时间戳+随机串，避免局域网 http://IP 访问时抛错。
 */
export function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

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

// ==================== 导出 ====================

/** 策略导出文件格式版本号 */
export const STRATEGY_EXPORT_VERSION = 1;

/** 策略导出文件（对齐自编指标/卖出策略导出格式） */
export interface StrategyExportFile {
  version: number;
  exportedAt: string;
  strategies: SavedStrategy[];
}

/**
 * 构造策略导出文件；传入 ids 则只导出指定策略，不传导出全部
 */
export function buildStrategyExportFile(
  strategies: SavedStrategy[],
  ids?: string[],
): StrategyExportFile {
  const filtered =
    ids && ids.length > 0
      ? strategies.filter((s) => ids.includes(s.id))
      : strategies;
  return {
    version: STRATEGY_EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    strategies: filtered,
  };
}

// ==================== 导入 ====================

/** 导入过程中的错误类型 */
export type StrategyImportErrorType = 'name_duplicate' | 'field_invalid' | 'parse_error';

/** 单条导入错误明细 */
export interface StrategyImportErrorDetail {
  index: number;
  name?: string;
  type: StrategyImportErrorType;
  message: string;
}

/** 导入预览 / 结果 */
export interface StrategyImportResult {
  added: number;
  skipped: number;
  errors: StrategyImportErrorDetail[];
}

/** 解析导入 JSON 文本，返回 StrategyExportFile 或抛错 */
export function parseStrategyImportFile(jsonText: string): StrategyExportFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch (e) {
    throw new Error(`JSON 解析失败：${(e as Error).message}`);
  }
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('文件根节点不是对象');
  }
  const root = parsed as Record<string, unknown>;
  const version = typeof root.version === 'number' ? root.version : 0;
  if (version !== STRATEGY_EXPORT_VERSION) {
    throw new Error(`不支持的导出格式版本 v${version}（当前支持 v${STRATEGY_EXPORT_VERSION}）`);
  }
  if (!Array.isArray(root.strategies)) {
    throw new Error('文件缺少 strategies 数组');
  }
  return {
    version,
    exportedAt: typeof root.exportedAt === 'string' ? root.exportedAt : new Date().toISOString(),
    strategies: root.strategies as SavedStrategy[],
  };
}

/** 校验单条策略数据（导入时使用，字段完整性 + 名称非空） */
export function validateStrategyImportData(raw: unknown): { valid: boolean; errors: string[]; data?: SavedStrategy } {
  const errors: string[] = [];
  if (!raw || typeof raw !== 'object') {
    return { valid: false, errors: ['记录不是有效的对象'] };
  }
  const r = raw as Record<string, unknown>;
  const name = typeof r.name === 'string' ? r.name : '';
  const createdAt = typeof r.createdAt === 'string' ? r.createdAt : '';
  const updatedAt = typeof r.updatedAt === 'string' ? r.updatedAt : '';
  const version = typeof r.version === 'number' ? r.version : 0;
  const state = r.state;

  if (!name.trim()) errors.push('策略名称不能为空');
  if (!createdAt || !updatedAt) errors.push('创建/更新时间缺失');
  if (version !== STRATEGY_EXPORT_VERSION) errors.push(`版本不兼容（当前 v${STRATEGY_EXPORT_VERSION}）`);
  if (!state || typeof state !== 'object') errors.push('策略状态（state）缺失');

  if (errors.length > 0) return { valid: false, errors };

  const data: SavedStrategy = {
    id: typeof r.id === 'string' ? r.id : `import_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    name,
    createdAt,
    updatedAt,
    version,
    state: state as SavedStrategy['state'],
  };
  return { valid: true, errors, data };
}

/** 计算导入预览（added/skipped/errors 明细，不写入） */
export function computeStrategyImportPreview(
  file: StrategyExportFile,
  existing: SavedStrategy[],
): StrategyImportResult {
  const existingNames = new Set(existing.map((s) => s.name));
  const errors: StrategyImportErrorDetail[] = [];
  let added = 0;
  let skipped = 0;

  file.strategies.forEach((raw, index) => {
    const v = validateStrategyImportData(raw);
    if (!v.valid || !v.data) {
      errors.push({
        index,
        name: typeof raw.name === 'string' ? raw.name : undefined,
        type: 'field_invalid',
        message: v.errors.join('；'),
      });
      return;
    }
    // 名称重复检查
    if (existingNames.has(v.data.name)) {
      errors.push({
        index,
        name: v.data.name,
        type: 'name_duplicate',
        message: `策略名称"${v.data.name}"已存在，将跳过`,
      });
      skipped++;
      return;
    }
    added++;
  });

  return { added, skipped, errors };
}

/** 合并导入策略：重名跳过、生成新 id，返回新增的策略数组 */
export function mergeImportedStrategies(
  file: StrategyExportFile,
  existing: SavedStrategy[],
): { added: SavedStrategy[]; skipped: number } {
  const existingNames = new Set(existing.map((s) => s.name));
  const added: SavedStrategy[] = [];
  let skipped = 0;

  for (const raw of file.strategies) {
    const v = validateStrategyImportData(raw);
    if (!v.valid || !v.data) continue;
    if (existingNames.has(v.data.name)) {
      skipped++;
      continue;
    }
    // 重新生成 id，避免与现有策略 id 冲突
    added.push({ ...v.data, id: generateId() });
    existingNames.add(v.data.name);
  }

  return { added, skipped };
}

// ==================== Hook ====================

/**
 * 本地存储选股策略 Hook — 负责读写 localStorage 中的选股策略
 * @param storage 存储实现，默认使用 localStorage
 * @returns 策略列表和增删改操作
 */
export function useSavedStrategies(storage?: IStrategyStorage) {
  const [strategies, setStrategies] = useState<SavedStrategy[]>([]);
  const store = useMemo(
    () => storage ?? new LocalStorageStrategyStorage(),
    [storage]
  );

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
      id: generateId(),
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
   * 批量导入策略（incoming 应为已去重/重命名后的新增策略，由 UI 层 mergeImportedStrategies 生成）
   */
  const importStrategies = useCallback((incoming: SavedStrategy[]): StrategyOperationResult => {
    if (incoming.length === 0) {
      return { ok: true as const };
    }
    const updated = [...strategies, ...incoming];
    try {
      store.save(updated);
      setStrategies(updated);
      return { ok: true as const };
    } catch (e) {
      console.error('[Screener] 导入策略失败', e);
      return { ok: false as const, error: e instanceof Error ? e.message : '导入失败' };
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
    importStrategies,
    reload,
  };
}
