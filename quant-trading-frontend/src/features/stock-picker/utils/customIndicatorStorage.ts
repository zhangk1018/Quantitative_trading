/**
 * 自编指标 localStorage 存储层（V1.0 - 前端 mock）
 *
 * 设计要点：
 * - 按 user_id 隔离数据（V1.0 mock user_id = 'mock_user_default'）
 * - key 前缀 'qt_custom_indicators_v1_' 便于未来版本迁移
 * - 软删除：标记 deleted=true 但保留记录，便于方案回显检测"指标已删除"状态
 * - localStorage 不可用时降级到内存 Map（仅本次会话有效）
 * - 导入去重：按 (userId, name) 去重，已存在则跳过
 */

import {
  CustomIndicator,
  IndicatorExportFile,
  EXPORT_FORMAT_VERSION,
  validateIndicatorName,
} from '../types/customIndicator';
export { EXPORT_FORMAT_VERSION };

// =====================================================================
// Mock User（V1.0 单用户）
// =====================================================================

export const MOCK_USER_ID = 'mock_user_default';
const STORAGE_KEY_PREFIX = 'qt_custom_indicators_v1_';

// =====================================================================
// 内存降级（localStorage 不可用时）
// =====================================================================

const memoryStore: Map<string, CustomIndicator[]> = new Map();

// =====================================================================
// 工具函数
// =====================================================================

function getStorageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`;
}

function isLocalStorageAvailable(): boolean {
  try {
    const test = '__qt_storage_test__';
    window.localStorage.setItem(test, test);
    window.localStorage.removeItem(test);
    return true;
  } catch {
    return false;
  }
}

const localStorageAvailable = isLocalStorageAvailable();

function readAll(userId: string): CustomIndicator[] {
  const key = getStorageKey(userId);
  if (localStorageAvailable) {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      console.error('[customIndicatorStorage] JSON 解析失败，清空数据', key);
      return [];
    }
  }
  return memoryStore.get(key) ?? [];
}

function writeAll(userId: string, indicators: CustomIndicator[]): void {
  const key = getStorageKey(userId);
  if (localStorageAvailable) {
    window.localStorage.setItem(key, JSON.stringify(indicators));
  } else {
    memoryStore.set(key, indicators);
  }
}

function generateId(): string {
  return `ind_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

// =====================================================================
// 公开 API
// =====================================================================

/** 列出当前用户全部自编指标（含软删除的，按 updatedAt 倒序） */
export function listCustomIndicators(userId: string = MOCK_USER_ID): CustomIndicator[] {
  return readAll(userId)
    .filter((i) => !i.deleted)
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

/** 列出全部（含软删除的）— 供方案失效检测使用 */
export function listAllCustomIndicators(userId: string = MOCK_USER_ID): CustomIndicator[] {
  return readAll(userId);
}

/** 按 ID 查找（忽略软删除状态） */
export function getCustomIndicatorById(
  id: string,
  userId: string = MOCK_USER_ID,
): CustomIndicator | undefined {
  return readAll(userId).find((i) => i.id === id);
}

/** 检查指标名称是否已存在（按用户隔离） */
export function isNameTaken(
  name: string,
  excludeId: string | null,
  userId: string = MOCK_USER_ID,
): boolean {
  return readAll(userId).some(
    (i) => !i.deleted && i.name === name && (excludeId === null || i.id !== excludeId),
  );
}

/** 保存（新增或更新）一个自编指标 */
export function saveCustomIndicator(
  indicator: Omit<CustomIndicator, 'id' | 'createdAt' | 'updatedAt' | 'userId' | 'deleted'> & {
    id?: string;
  },
  userId: string = MOCK_USER_ID,
): CustomIndicator {
  const nameError = validateIndicatorName(indicator.name);
  if (nameError) throw new Error(nameError);

  if (isNameTaken(indicator.name, indicator.id ?? null, userId)) {
    throw new Error(`指标名称"${indicator.name}"已存在`);
  }

  const all = readAll(userId);
  const now = nowIso();

  if (indicator.id) {
    // 更新
    const idx = all.findIndex((i) => i.id === indicator.id);
    if (idx === -1) throw new Error(`未找到指标 ${indicator.id}`);
    const updated: CustomIndicator = {
      ...all[idx],
      ...indicator,
      id: indicator.id,
      userId,
      updatedAt: now,
    };
    all[idx] = updated;
    writeAll(userId, all);
    return updated;
  } else {
    // 新增
    const created: CustomIndicator = {
      ...indicator,
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

/** 软删除一个自编指标（标记 deleted=true） */
export function removeCustomIndicator(
  id: string,
  userId: string = MOCK_USER_ID,
): boolean {
  const all = readAll(userId);
  const idx = all.findIndex((i) => i.id === id);
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

/** 硬删除（仅供方案清理时使用） */
export function purgeCustomIndicator(
  id: string,
  userId: string = MOCK_USER_ID,
): boolean {
  const all = readAll(userId);
  const next = all.filter((i) => i.id !== id);
  if (next.length === all.length) return false;
  writeAll(userId, next);
  return true;
}

/** 检查指标是否被方案引用（供删除二次确认） */
export function isIndicatorReferenced(
  id: string,
  userId: string = MOCK_USER_ID,
): boolean {
  if (typeof window === 'undefined') return false;
  const plansRaw = window.localStorage.getItem(`${STORAGE_KEY_PREFIX}plans_${userId}`);
  if (!plansRaw) return false;
  try {
    const plans = JSON.parse(plansRaw) as Array<{ conditions?: Array<{ sourceId: string }> }>;
    return plans.some((p) => p.conditions?.some((c) => c.sourceId === id));
  } catch {
    return false;
  }
}

// =====================================================================
// 导入导出（JSON）
// =====================================================================

/** 导入错误类型（K 评审优化 1：按类型分类）
 *
 * 3 个 file-level 类型（format_invalid/version_unsupported/indicators_not_array）
 * 由 parseImportFile 抛错，UI 层捕获展示，不计入 ImportResult。
 *
 * 4 个 indicator-level 类型由 importCustomIndicators 计入 ImportResult。
 */
export type ImportErrorType = 'name_invalid' | 'name_duplicate' | 'field_invalid' | 'parse_error';

export interface ImportErrorDetail {
  /** 错误类型 */
  type: ImportErrorType;
  /** 错误指标名称（若可识别） */
  name?: string;
  /** 错误指标索引（在 indicators 数组中的位置） */
  index?: number;
  /** 错误描述 */
  message: string;
}

/** 导入结果（K 评审优化 1：分类型统计） */
export interface ImportResult {
  added: number;
  skipped: number;
  errors: ImportErrorDetail[];
  /** 错误按类型分组统计 */
  errorSummary: Record<ImportErrorType, number>;
}

function emptyErrorSummary(): Record<ImportErrorType, number> {
  return {
    name_invalid: 0,
    name_duplicate: 0,
    field_invalid: 0,
    parse_error: 0,
  };
}

/** 导出当前用户全部自编指标为 JSON 文件 */
export function exportCustomIndicators(userId: string = MOCK_USER_ID): IndicatorExportFile {
  return {
    version: EXPORT_FORMAT_VERSION,
    exportedAt: nowIso(),
    userId,
    indicators: listCustomIndicators(userId),
  };
}

/** 解析 JSON 字符串为 IndicatorExportFile
 *
 * @throws {Error} file-level 错误（格式无效/版本不支持/indicators 非数组）
 */
export function parseImportFile(jsonText: string): IndicatorExportFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch (e) {
    throw new Error(`文件格式无效：JSON 解析失败（${(e as Error).message}）`);
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('文件格式无效：根对象缺失');
  }
  const obj = parsed as Record<string, unknown>;
  if (typeof obj.version !== 'number') {
    throw new Error('文件格式无效：缺少 version 字段');
  }
  if (obj.version > EXPORT_FORMAT_VERSION) {
    throw new Error(
      `文件版本 v${obj.version} 高于当前支持版本 v${EXPORT_FORMAT_VERSION}，请升级应用`,
    );
  }
  if (!Array.isArray(obj.indicators)) {
    throw new Error('文件格式无效：indicators 必须为数组');
  }
  return parsed as IndicatorExportFile;
}

/** 校验单条指标必填字段 */
function validateIndicatorFields(ind: unknown, index: number): string | null {
  if (typeof ind !== 'object' || ind === null) {
    return `索引 ${index} 的指标不是对象`;
  }
  const obj = ind as Record<string, unknown>;
  const required: Array<[string, string]> = [
    ['name', 'string'],
    ['category', 'string'],
    ['formula', 'string'],
    ['operator', 'string'],
  ];
  for (const [field, type] of required) {
    if (typeof obj[field] !== type) {
      return `字段 ${field} 缺失或类型错误（期望 ${type}）`;
    }
  }
  if (!Array.isArray(obj.params)) {
    return '字段 params 必须为数组';
  }
  if (obj.defaultThreshold !== undefined && obj.defaultThreshold !== null) {
    const t = obj.defaultThreshold;
    if (typeof t === 'number') {
      // OK
    } else if (Array.isArray(t) && t.every((v) => typeof v === 'number')) {
      // OK
    } else {
      return '字段 defaultThreshold 类型错误（期望 number 或 number[]）';
    }
  }
  return null;
}

/** 导入自编指标到当前用户（按名称去重，已存在则跳过） */
export function importCustomIndicators(
  file: IndicatorExportFile,
  userId: string = MOCK_USER_ID,
): ImportResult {
  const result: ImportResult = {
    added: 0,
    skipped: 0,
    errors: [],
    errorSummary: emptyErrorSummary(),
  };
  const all = readAll(userId);

  file.indicators.forEach((ind, index) => {
    // 1) 字段合法性校验
    const fieldErr = validateIndicatorFields(ind, index);
    if (fieldErr) {
      result.errors.push({
        type: 'field_invalid',
        name: typeof (ind as { name?: unknown })?.name === 'string' ? (ind as { name: string }).name : undefined,
        index,
        message: fieldErr,
      });
      result.errorSummary.field_invalid += 1;
      return;
    }

    // 2) 名称格式校验
    const nameError = validateIndicatorName(ind.name);
    if (nameError) {
      result.errors.push({
        type: 'name_invalid',
        name: ind.name,
        index,
        message: nameError,
      });
      result.errorSummary.name_invalid += 1;
      return;
    }

    // 3) 名称去重
    if (isNameTaken(ind.name, null, userId)) {
      result.errors.push({
        type: 'name_duplicate',
        name: ind.name,
        index,
        message: `指标名称"${ind.name}"已存在，已跳过`,
      });
      result.errorSummary.name_duplicate += 1;
      result.skipped += 1;
      return;
    }

    // 4) 写入
    try {
      all.push({
        ...ind,
        id: generateId(),
        userId,
        deleted: false,
        createdAt: nowIso(),
        updatedAt: nowIso(),
      });
      result.added += 1;
    } catch (e) {
      result.errors.push({
        type: 'parse_error',
        name: ind.name,
        index,
        message: (e as Error).message,
      });
      result.errorSummary.parse_error += 1;
    }
  });

  writeAll(userId, all);
  return result;
}

// =====================================================================
// 测试/调试用：清空所有数据
// =====================================================================

export function clearAllCustomIndicators(userId: string = MOCK_USER_ID): void {
  if (localStorageAvailable) {
    window.localStorage.removeItem(getStorageKey(userId));
    window.localStorage.removeItem(`${STORAGE_KEY_PREFIX}plans_${userId}`);
  } else {
    memoryStore.delete(getStorageKey(userId));
  }
}
