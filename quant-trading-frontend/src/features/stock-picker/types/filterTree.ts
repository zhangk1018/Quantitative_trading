/**
 * 条件构建器（ConditionBuilder）数据模型
 * 设计原则：扁平无嵌套，FilterTree.conditions[] 是有序列表
 * 关系（op）由"下一个待添加"决定，已添加的条件关系不会随后续选择改变
 */

/** 条件关系（3 种互斥单选） */
export type FilterOp = 'AND' | 'OR' | 'NOT';

/**
 * 条件来源（K 2026-06-16 代码审阅建议）
 * - system：系统预设（6 个 + custom 预留位），fieldKey 即唯一键
 * - custom：用户自编指标，fieldKey = `custom_${sourceId}`，sourceId = CustomIndicator.id
 * 用于：
 *   ① 失效检测（自定义指标被删除时自动标记 invalid）
 *   ② 条件渲染（自编指标带【自编】tag）
 *   ③ 未来方案回显（PlanCondition.source 对应）
 */
export type FilterSource = 'system' | 'custom';

/** 6 个预设 + 自定义的可选 fieldKey */
export type ConditionFieldKey =
  | 'rsi_oversold'          // RSI超卖
  | 'volume_breakout'       // 放量突破
  | 'macd_golden_cross'     // MACD金叉
  | 'bottom_volume_macd'    // 底部放量+MACD金叉
  | 'consecutive_up'        // 连续上涨
  | 'low_valuation'         // 低估值
  | 'custom';               // 自定义（预留）

/** 自定义指标 fieldKey 命名约定：`custom_<id>`（K 2026-06-16 约定） */
export const CUSTOM_FIELD_KEY_PREFIX = 'custom_';

/** 从 fieldKey 提取自编指标 ID（仅 fieldKey 以 `custom_` 开头时有效） */
export function extractCustomIndicatorId(fieldKey: string): string | null {
  if (!fieldKey.startsWith(CUSTOM_FIELD_KEY_PREFIX)) return null;
  return fieldKey.slice(CUSTOM_FIELD_KEY_PREFIX.length);
}

/** 构造自编指标 fieldKey */
export function buildCustomFieldKey(id: string): string {
  return `${CUSTOM_FIELD_KEY_PREFIX}${id}`;
}

/** 单个条件 */
export interface FilterCondition {
  /** 唯一 id（自增或 uuid），用于删除/更新 */
  id: string;
  /** 该条件的关系（影响"和上一个条件怎么连接"），首条件 op 实际无效（K 2026-06-16 决策） */
  op: FilterOp;
  /** 字段 key（系统预设使用固定 key；自编使用 `custom_<id>`） */
  fieldKey: ConditionFieldKey | string;
  /** 显示标签（如 "RSI超卖"） */
  label: string;
  /** 条件来源（K 2026-06-16 扩展），默认 'system' 兼容老数据 */
  source?: FilterSource;
  /** 自编指标 ID（仅 source='custom' 时有值，fieldKey 也按 `custom_<sourceId>` 拼） */
  sourceId?: string;
  /** 失效标记（K 2026-06-16 扩展）：true 表示该条件引用的指标已删除/不可用 */
  invalid?: boolean;
  /** 失效原因（仅 invalid=true 时有值） */
  invalidReason?: string;
}

/** 整棵树（扁平无嵌套） */
export interface FilterTree {
  conditions: FilterCondition[];
}

/** 6 个预设定义（应用时替换当前 conditions） */
export interface FilterPreset {
  fieldKey: ConditionFieldKey;
  label: string;
  /** 该预设包含的条件（单条件预设 length=1，组合预设 length>1） */
  conditions: Omit<FilterCondition, 'id'>[];
}

export const FILTER_PRESETS: FilterPreset[] = [
  {
    fieldKey: 'rsi_oversold',
    label: 'RSI超卖',
    conditions: [{ op: 'AND', fieldKey: 'rsi_oversold', label: 'RSI超卖' }],
  },
  {
    fieldKey: 'volume_breakout',
    label: '放量突破',
    conditions: [{ op: 'AND', fieldKey: 'volume_breakout', label: '放量突破' }],
  },
  {
    fieldKey: 'macd_golden_cross',
    label: 'MACD金叉',
    conditions: [{ op: 'AND', fieldKey: 'macd_golden_cross', label: 'MACD金叉' }],
  },
  {
    fieldKey: 'bottom_volume_macd',
    // K 2026-06-17 调整：preset 按钮文案简化（详见截图说明）
    label: '底部放量',
    conditions: [
      { op: 'AND', fieldKey: 'volume_breakout', label: '底部放量' },
      { op: 'AND', fieldKey: 'macd_golden_cross', label: 'MACD金叉' },
    ],
  },
  {
    fieldKey: 'consecutive_up',
    label: '连续上涨',
    conditions: [{ op: 'AND', fieldKey: 'consecutive_up', label: '连续上涨' }],
  },
  {
    fieldKey: 'low_valuation',
    label: '低估值',
    conditions: [{ op: 'AND', fieldKey: 'low_valuation', label: '低估值' }],
  },
];

/** 简单的递增 id 生成器（避免引入 uuid 依赖） */
let __idCounter = 0;
export function genConditionId(): string {
  __idCounter += 1;
  return `cond_${Date.now()}_${__idCounter}`;
}
