/** PDCA 交易自律系统 — 常量定义（标签映射、下拉选项） */

import type {
  CycleType,
  PlanTemplateType,
  SecurityTagValue,
  InstrumentType,
  LongShort,
  OrderType,
  TradeGrade,
  ExitReason,
  TriggerSource,
} from './types';

/**
 * 周期类型标签映射
 */
export const CYCLE_TYPE_LABELS: Record<CycleType, string> = {
  day: '日周期',
  week: '周周期',
  month: '月周期',
  quarter: '季周期',
  year: '年周期',
};

/**
 * 周期类型下拉选项
 */
export const CYCLE_TYPE_OPTIONS = Object.entries(CYCLE_TYPE_LABELS).map(([value, label]) => ({ value, label }));

/**
 * 计划模板类型标签映射
 */
export const PLAN_TEMPLATE_TYPE_LABELS: Record<PlanTemplateType, string> = {
  short_term: '短线模板',
  mid_term: '中线模板',
  long_term: '长线模板',
};

/**
 * 计划模板类型下拉选项
 */
export const PLAN_TEMPLATE_TYPE_OPTIONS = Object.entries(PLAN_TEMPLATE_TYPE_LABELS).map(([value, label]) => ({ value, label }));

/**
 * 标的 ABC 分类标签映射
 */
export const SECURITY_TAG_LABELS: Record<SecurityTagValue, string> = {
  A: 'A类（熟悉且验证）',
  B: 'B类（一般熟悉）',
  C: 'C类（不熟悉或验证失败）',
};

/**
 * 标的 ABC 分类下拉选项
 */
export const SECURITY_TAG_OPTIONS = (
  Object.entries(SECURITY_TAG_LABELS) as [SecurityTagValue, string][]
).map(([value, label]) => ({ value, label }));

/**
 * 证券类型标签映射
 */
export const INSTRUMENT_TYPE_LABELS: Record<InstrumentType, string> = {
  stock: '股票',
  futures: '期货',
  forex: '外汇',
  option: '期权',
};

/**
 * 多空方向标签映射
 */
export const LONG_SHORT_LABELS: Record<LongShort, string> = {
  long: '做多',
  short: '做空',
};

/**
 * 订单类型标签映射
 */
export const ORDER_TYPE_LABELS: Record<OrderType, string> = {
  limit: '限价',
  market: '市价',
  stop: '止损',
};

/**
 * 交易等级标签映射
 */
export const TRADE_GRADE_LABELS: Record<TradeGrade, string> = {
  A: 'A级',
  B: 'B级',
  C: 'C级',
};

/**
 * 出场原因标签映射
 */
export const EXIT_REASON_LABELS: Record<ExitReason, string> = {
  take_profit: '止盈出场',
  stop_loss: '止损出场',
  impulsive: '冲动出场',
  plan_expired: '计划到期',
  others: '其他',
};

/**
 * 触发来源标签映射
 */
export const TRIGGER_SOURCE_LABELS: Record<TriggerSource, string> = {
  system_plan: '系统计划',
  news: '新闻驱动',
  impulse: '盘中冲动',
  scanner: '选股器',
  manual: '手动',
};

/**
 * 预计算 Select options 数组，避免组件内重复 Object.entries 转换
 */
export const INSTRUMENT_TYPE_OPTIONS = Object.entries(INSTRUMENT_TYPE_LABELS).map(([value, label]) => ({ value, label }));
export const LONG_SHORT_OPTIONS = Object.entries(LONG_SHORT_LABELS).map(([value, label]) => ({ value, label }));
export const ORDER_TYPE_OPTIONS = Object.entries(ORDER_TYPE_LABELS).map(([value, label]) => ({ value, label }));
export const TRADE_GRADE_OPTIONS = Object.entries(TRADE_GRADE_LABELS).map(([value, label]) => ({ value, label }));
export const EXIT_REASON_OPTIONS = Object.entries(EXIT_REASON_LABELS).map(([value, label]) => ({ value, label }));
export const TRIGGER_SOURCE_OPTIONS = Object.entries(TRIGGER_SOURCE_LABELS).map(([value, label]) => ({ value, label }));
