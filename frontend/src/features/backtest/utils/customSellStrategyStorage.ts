/**
 * 自编卖出策略 localStorage 存储层（V1.0 - 前端 mock）
 *
 * 与自编指标存储（stock-picker/customIndicatorStorage）同模式：
 * - 按 user_id 隔离（V1.0 mock user_id = 'mock_user_default'）
 * - key 前缀 'qt_custom_sell_strategies_v1_' 与自编指标区分
 * - 软删除：标记 deleted=true 但保留记录（删除后重新导入可恢复）
 * - 名称去重校验复用 validateIndicatorName；公式校验复用 validateFormula
 */

import {
  validateIndicatorName,
  validateFormula,
  type IndicatorOperator,
} from '../../stock-picker/types/customIndicator';
import type { BacktestIndicatorOperator, BacktestIndicatorThreshold } from '../backtestTypes';

export const MOCK_USER_ID = 'mock_user_default';
const STORAGE_KEY_PREFIX = 'qt_custom_sell_strategies_v1_';

/** 自编卖出策略实体（纯信号协议脚本） */
export interface CustomSellStrategy {
  id: string;
  userId: string;
  /** 策略名称（用户内唯一，2-30 字符） */
  name: string;
  /** Python 脚本：calculate(open_prices, high_prices, low_prices, close_prices, volumes) 输出每日卖出信号数组 */
  formula: string;
  /** 判定算子（对齐自编指标口径） */
  operator: BacktestIndicatorOperator;
  /** 判定阈值（单值或区间） */
  defaultThreshold: BacktestIndicatorThreshold;
  /** 策略说明 */
  description: string;
  /** 软删除标记 */
  deleted?: boolean;
  /** 软删除时间戳（ISO 8601）— 仅 deleted=true 时有值 */
  deletedAt?: string;
  /** 创建时间（ISO 8601） */
  createdAt: string;
  /** 更新时间（ISO 8601） */
  updatedAt: string;
}

// =====================================================================
// 内存降级（localStorage 不可用时）
// =====================================================================

const memoryStore: Map<string, CustomSellStrategy[]> = new Map();

function getStorageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`;
}

function isLocalStorageAvailable(): boolean {
  try {
    const test = '__qt_sell_storage_test__';
    window.localStorage.setItem(test, test);
    window.localStorage.removeItem(test);
    return true;
  } catch {
    console.warn('[CustomSellStrategy] localStorage 不可用，降级到内存存储');
    return false;
  }
}

const localStorageAvailable = isLocalStorageAvailable();

function readAll(userId: string): CustomSellStrategy[] {
  const key = getStorageKey(userId);
  if (localStorageAvailable) {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      console.warn('[CustomSellStrategy] JSON 解析失败，清空数据', key);
      return [];
    }
  }
  return memoryStore.get(key) ?? [];
}

function writeAll(userId: string, strategies: CustomSellStrategy[]): void {
  const key = getStorageKey(userId);
  if (localStorageAvailable) {
    try {
      window.localStorage.setItem(key, JSON.stringify(strategies));
    } catch (e) {
      console.warn('Failed to save custom sell strategies to localStorage', e);
    }
  } else {
    memoryStore.set(key, strategies);
  }
}

function generateId(): string {
  return `sell_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

// =====================================================================
// 公开 API
// =====================================================================

/** 列出全部自编卖出策略（含软删除的，供 name 去重与导入恢复检测） */
export function listAllCustomSellStrategies(
  userId: string = MOCK_USER_ID,
): CustomSellStrategy[] {
  return readAll(userId);
}

/** 列出有效的自编卖出策略（排除软删除，按 updatedAt 倒序） */
export function listCustomSellStrategies(
  userId: string = MOCK_USER_ID,
): CustomSellStrategy[] {
  return readAll(userId)
    .filter((s) => !s.deleted)
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

/** 检查策略名称是否已被占用（排除软删除记录，软删除不阻挡同名新增） */
export function isSellStrategyNameTaken(
  name: string,
  excludeId: string | null = null,
  userId: string = MOCK_USER_ID,
): boolean {
  return readAll(userId).some(
    (s) => !s.deleted && s.name === name && (excludeId === null || s.id !== excludeId),
  );
}

/** 保存（新增或更新）一个自编卖出策略 */
export function saveCustomSellStrategy(
  strategy: Omit<CustomSellStrategy, 'id' | 'createdAt' | 'updatedAt' | 'userId' | 'deleted'> & {
    id?: string;
  },
  userId: string = MOCK_USER_ID,
): CustomSellStrategy {
  const nameError = validateIndicatorName(strategy.name);
  if (nameError) throw new Error(nameError);

  if (isSellStrategyNameTaken(strategy.name, strategy.id ?? null, userId)) {
    throw new Error(`卖出策略名称"${strategy.name}"已存在`);
  }

  const all = readAll(userId);
  const now = nowIso();

  if (strategy.id) {
    // 更新
    const idx = all.findIndex((s) => s.id === strategy.id);
    if (idx === -1) throw new Error(`未找到卖出策略 ${strategy.id}`);
    const updated: CustomSellStrategy = {
      ...all[idx],
      ...strategy,
      id: strategy.id,
      userId,
      updatedAt: now,
    };
    all[idx] = updated;
    writeAll(userId, all);
    return updated;
  } else {
    // 新增
    const created: CustomSellStrategy = {
      ...strategy,
      id: generateId(),
      userId,
      deleted: false,
      createdAt: now,
      updatedAt: now,
    };
    all.push(created);
    writeAll(userId, all);
    return created;
  }
}

/** 软删除一个自编卖出策略（标记 deleted=true） */
export function removeCustomSellStrategy(
  id: string,
  userId: string = MOCK_USER_ID,
): boolean {
  const all = readAll(userId);
  const idx = all.findIndex((s) => s.id === id);
  if (idx === -1) return false;
  const now = nowIso();
  all[idx] = {
    ...all[idx],
    deleted: true,
    deletedAt: now,
    updatedAt: now,
  };
  writeAll(userId, all);
  return true;
}

/** 校验卖出策略脚本公式（复用自编指标公式校验：含 calculate 签名/parens/危险关键字/import 白名单） */
export function validateSellStrategyFormula(
  formula: string,
): { valid: boolean; errors: string[]; warnings: string[] } {
  return validateFormula(formula, 'python_talib');
}

/** 复导出自编指标算子类型（管理 UI 复用 INDICATOR_OPERATORS 选项） */
export type { IndicatorOperator };