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
  // K 2026-06-18 任务 #8：同步标记 plans_<userId> 中所有引用该 ID 的 condition 为 invalid
  // （之前只标记了 filterGroup.conditions，遗漏了 ScreenerPlan 历史快照）
  markPlanConditionsInvalid(id, userId);
  return true;
}

/**
 * 标记 plans_<userId> 中所有引用 indicatorId 的 condition 为 invalid（K 2026-06-18 任务 #8）
 *
 * 纯函数式失效检测：被 removeCustomIndicator / 任何清理流程复用。
 * 计划加载到 state 后由 UI 层（ConditionBuilder）显示失效提示。
 */
export function markPlanConditionsInvalid(
  indicatorId: string,
  userId: string = MOCK_USER_ID,
): void {
  if (typeof window === 'undefined') return;
  const plansKey = `${STORAGE_KEY_PREFIX}plans_${userId}`;
  const plansRaw = window.localStorage.getItem(plansKey);
  if (!plansRaw) return;
  try {
    const plans = JSON.parse(plansRaw) as Array<{
      conditions?: Array<{ sourceId?: string; invalid?: boolean; invalidReason?: string }>;
    }>;
    let changed = false;
    const next = plans.map((p) => {
      if (!p.conditions) return p;
      const newConditions = p.conditions.map((c) => {
        if (c.sourceId === indicatorId && !c.invalid) {
          changed = true;
          return {
            ...c,
            invalid: true,
            invalidReason: '引用指标已删除',
          };
        }
        return c;
      });
      return { ...p, conditions: newConditions };
    });
    if (changed) {
      window.localStorage.setItem(plansKey, JSON.stringify(next));
    }
  } catch {
    // 解析失败保留原值
  }
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
  // K 2026-06-18 反馈 #3：硬删除同样要标记 plans 中的失效引用，
  // 否则已删除指标的方案条件会变成悬空引用导致选股结果错误。
  markPlanConditionsInvalid(id, userId);
  return true;
}

/**
 * 判断导入指标是否重复（K 2026-06-18 任务 #10 统一去重策略）
 *
 * 优先级：
 * 1) 若导入数据带 id → 按 id 去重（O(1)）
 * 2) 否则 → 按 name 去重（兼容手写/旧版 JSON）
 *
 * 由 importCustomIndicators 和 ImportExportButtons 预览逻辑复用，
 * 确保预览 added/skipped 数量与实际导入一致。
 */
export function isDuplicateIndicator(
  ind: CustomIndicator,
  existingIds: ReadonlySet<string>,
  existingNames: ReadonlySet<string>,
): boolean {
  const id = (ind as { id?: unknown }).id;
  if (typeof id === 'string' && id.length > 0) {
    return existingIds.has(id);
  }
  return existingNames.has(ind.name);
}

/** 检查指标是否被方案引用（供删除二次确认）
 *
 * K 2026-06-18 反馈 #4：保留作为 storage 层的 fallback 实现（无 React state 场景使用）。
 * UI 层应优先用 isIndicatorReferencedByConditions(id, conditions) 从实时 state 计算，
 * 避免 storage 读 localStorage 与 React 实时状态脱节（K 2026-06-18 任务 #9 已修）。
 */
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

/**
 * 纯函数：从实时 condition 列表中检查指标是否被引用（K 2026-06-18 反馈 #4）
 *
 * 供 UI 层（CustomIndicatorList / CustomIndicatorManager）从 React state.filterGroup.conditions
 * 实时计算引用关系，避免 storage 读 localStorage 滞后于 state 变化。
 *
 * 与 isIndicatorReferenced 的区别：
 * - 本函数：从传入的 conditions 数组计算（实时）
 * - isIndicatorReferenced：从 localStorage.plans_<userId> 读（可能滞后）
 */
export function isIndicatorReferencedByConditions(
  indicatorId: string,
  conditions: ReadonlyArray<{ source?: string; sourceId?: string }>,
): boolean {
  return conditions.some(
    (c) => c.source === 'custom' && c.sourceId === indicatorId,
  );
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

/** 导入结果（K 2026-06-18 反馈 #3：统一类型，computeImportPreview 与 importCustomIndicators 共享）
 *
 * 字段语义：
 * - added: 通过校验 + 不重复 的指标数（预览与实际导入一致）
 * - skipped: 因 id/name 重复被跳过的指标数
 * - errors: 校验失败明细（按类型区分）
 * - errorSummary: 错误按类型分组统计
 * - addedIndicators: 实际写入的指标列表（预览时为 []，实际导入时填充；K 反馈 #3 统一字段）
 * - _validationCache: 内部缓存，预览阶段每条指标的校验结果，供 importCustomIndicators 复用
 *   （K 反馈 #2：避免双重校验耗时翻倍）。下划线前缀约定为 internal，不应被 UI 层读取。
 */
export interface ImportResult {
  added: number;
  skipped: number;
  errors: ImportErrorDetail[];
  /** 错误按类型分组统计 */
  errorSummary: Record<ImportErrorType, number>;
  /** 实际写入的指标列表（预览时为 []，实际导入时按 file.indicators 顺序填充） */
  addedIndicators: CustomIndicator[];
  /**
   * 内部缓存：file.indicators 索引 → 校验结果（K 反馈 #2）
   * @internal UI 层不应读取此字段
   */
  _validationCache: Map<number, ValidationResult>;
}

/**
 * 创建一个空的 ImportResult（含 emptyCache）
 */
function createEmptyImportResult(): ImportResult {
  return {
    added: 0,
    skipped: 0,
    errors: [],
    errorSummary: emptyErrorSummary(),
    addedIndicators: [],
    _validationCache: new Map<number, ValidationResult>(),
  };
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

/**
 * 单条指标导入的完整校验结果（K 2026-06-18 反馈 #1）
 *
 * 用途：统一预览阶段与实际导入阶段的校验逻辑，避免两套重复代码导致
 * 规则更新时不同步（K 反馈 #1 明确指出此风险）。
 */
export type ValidationResult =
  | { ok: true; duplicate: boolean }
  | { ok: false; error: ImportErrorDetail };

/**
 * 单条导入指标的完整校验（K 2026-06-18 反馈 #1）
 *
 * 串联三步校验：
 * 1) 字段合法性（validateIndicatorFields）
 * 2) 名称格式（validateIndicatorName）
 * 3) 去重（isDuplicateIndicator，id 优先 / name 兜底）
 *
 * 单一来源：computeImportPreview 和 importCustomIndicators 的写入阶段都调用此函数，
 * 保证预览 added/skipped 与实际导入 added/skipped 完全一致。
 */
export function validateIndicatorData(
  ind: unknown,
  index: number,
  existingIds: ReadonlySet<string>,
  existingNames: ReadonlySet<string>,
): ValidationResult {
  // 1) 字段合法性校验
  const fieldErr = validateIndicatorFields(ind, index);
  if (fieldErr) {
    return {
      ok: false,
      error: {
        type: 'field_invalid',
        name: typeof (ind as { name?: unknown })?.name === 'string'
          ? (ind as { name: string }).name
          : undefined,
        index,
        message: fieldErr,
      },
    };
  }

  // 此时 ind 已被 validateIndicatorFields 验证为合法对象
  const obj = ind as CustomIndicator;

  // 2) 名称格式校验
  const nameError = validateIndicatorName(obj.name);
  if (nameError) {
    return {
      ok: false,
      error: {
        type: 'name_invalid',
        name: obj.name,
        index,
        message: nameError,
      },
    };
  }

  // 3) 去重判断（K 2026-06-18 任务 #10 统一策略：id 优先 / name 兜底）
  if (isDuplicateIndicator(obj, existingIds, existingNames)) {
    return { ok: true, duplicate: true };
  }

  return { ok: true, duplicate: false };
}

/**
 * 计算导入预览（纯函数，不写入）
 * K 2026-06-18 反馈 #5：preview 和 importCustomIndicators 复用同一套校验/去重逻辑，
 * 确保预览 previewAdded/previewSkipped 数量与实际导入 result.added/result.skipped 一致。
 * K 2026-06-18 反馈 #1：进一步抽离 validateIndicatorData 纯函数，让预览/实际导入
 * 共享同一份校验源（字段+名称+去重三步），避免未来新增校验规则时漏改。
 * K 2026-06-18 反馈 #2：缓存每条指标的校验结果到 result._validationCache，
 * 供 importCustomIndicators 复用，避免双重校验耗时翻倍。
 * K 2026-06-18 反馈 #3：返回 ImportResult（与 importCustomIndicators 类型统一，含 addedIndicators 字段）。
 *
 * 写入步骤不执行（留给 importCustomIndicators 实际落库）。
 */
export function computeImportPreview(
  file: IndicatorExportFile,
  userId: string = MOCK_USER_ID,
): ImportResult {
  const result = createEmptyImportResult();
  const all = readAll(userId);
  const existingIds = new Set(all.filter((i) => i.id).map((i) => i.id));
  const existingNames = new Set(all.filter((i) => !i.deleted).map((i) => i.name));

  file.indicators.forEach((ind, index) => {
    // 单一校验源：K 反馈 #1
    const validation = validateIndicatorData(ind, index, existingIds, existingNames);
    // 缓存校验结果供 importCustomIndicators 复用：K 反馈 #2
    result._validationCache.set(index, validation);

    if (!validation.ok) {
      result.errors.push(validation.error);
      result.errorSummary[validation.error.type] += 1;
      return;
    }

    if (validation.duplicate) {
      const obj = ind as CustomIndicator;
      const isIdDup = typeof (obj as { id?: string }).id === 'string' && existingIds.has((obj as { id: string }).id);
      result.errors.push({
        type: 'name_duplicate',
        name: obj.name,
        index,
        message: `指标${isIdDup ? 'ID' : '名称'}"${isIdDup ? (obj as { id: string }).id : obj.name}"已存在，已跳过`,
      });
      result.errorSummary.name_duplicate += 1;
      result.skipped += 1;
      return;
    }

    // 通过校验 + 去重 → 计入 added
    result.added += 1;
  });

  return result;
}

/** 导入自编指标到当前用户（按 ID/名称去重，K 2026-06-18 任务 #10 统一去重策略）
 *
 * 去重优先级（K 2026-06-18 决策）：
 * 1) 若导入数据带 id（'id' in ind 且为非空字符串）→ 按 id 去重
 * 2) 否则 → 按 name 去重（兼容手写/旧版 JSON）
 *
 * 预览与实际导入使用同一套 isDuplicateIndicator（K 反馈 #1：进一步抽离为
 * validateIndicatorData 纯函数），避免预览/实际数量不符。
 * K 2026-06-18 反馈 #2：复用 computeImportPreview 的 _validationCache，避免重复校验。
 * K 2026-06-18 反馈 #3：返回 ImportResult 类型（与 computeImportPreview 统一）。
 */
export function importCustomIndicators(
  file: IndicatorExportFile,
  userId: string = MOCK_USER_ID,
): ImportResult {
  // 1) 复用预览的校验/去重逻辑（K 反馈 #5）— cache 也一并复用（K 反馈 #2）
  const result = computeImportPreview(file, userId);
  if (result.added === 0) {
    // 全部失败/重复，无需写入；同时也无新增指标
    return result;
  }

  // 2) 写入阶段：仅对通过校验的指标落库
  // K 反馈 #2：复用 _validationCache，不再调 validateIndicatorData。
  // 防御性 fallback：若 cache 中没有（理论上不会发生），则现场计算并补填 cache。
  const all = readAll(userId);
  const existingIds = new Set(all.filter((i) => i.id).map((i) => i.id));
  const existingNames = new Set(all.filter((i) => !i.deleted).map((i) => i.name));
  const addedIndicators: CustomIndicator[] = [];

  file.indicators.forEach((ind, index) => {
    let validation = result._validationCache.get(index);
    if (!validation) {
      // 防御性 fallback：cache miss 时现场计算（理论上不会发生，computeImportPreview
      // 必然先于 importCustomIndicators 内部调用并填好 cache）
      console.warn(
        '[customIndicatorStorage] _validationCache miss at index',
        index,
        '— 现场补算 validateIndicatorData',
      );
      validation = validateIndicatorData(ind, index, existingIds, existingNames);
      result._validationCache.set(index, validation);
    }
    if (!validation.ok) {
      // 理论上预览已拦截，errors 已计入 result.errors；此处不再重复 push，
      // 仅 console.warn 供排查（避免 errors 数量翻倍导致与预览不一致）
      console.warn(
        '[customIndicatorStorage] 写入阶段发现校验失败（应已被预览拦截）:',
        validation.error,
      );
      return;
    }
    if (validation.duplicate) {
      // 重复指标在预览阶段已计入 skipped + name_duplicate error；
      // 写入阶段直接跳过即可，保持 result.skipped 不变。
      return;
    }

    // 通过校验 + 去重 → 写入
    const obj = ind as CustomIndicator;
    const created: CustomIndicator = {
      ...obj,
      id: generateId(),
      userId,
      deleted: false,
      createdAt: nowIso(),
      updatedAt: nowIso(),
    };
    all.push(created);
    addedIndicators.push(created);
    // 同步更新去重集合，防止同一批次内重复添加
    existingIds.add(created.id);
    existingNames.add(created.name);
  });

  writeAll(userId, all);
  result.addedIndicators = addedIndicators;
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
