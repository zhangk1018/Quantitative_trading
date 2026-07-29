/**
 * utils/stock-utils.ts — 股票代码工具函数（单一事实来源）
 *
 * 所有市场判定逻辑在此统一维护，避免 store / UI 层重复实现。
 */

/** 系统分组（硬编码，不可删除） */
export const SYSTEM_GROUPS = ['全部', '沪深', '港股', '美股'] as const;
export type SystemGroup = (typeof SYSTEM_GROUPS)[number];
export const SYSTEM_GROUP_SET: ReadonlySet<string> = new Set(SYSTEM_GROUPS);

/**
 * 根据代码前缀判定所属市场分组。
 * V1.0 仅支持 A 股（6位数字），港股/美股为预留分组。
 */
export function detectMarketGroup(code: string): string {
  if (!code || code.length < 2) return '沪深';
  const prefix = code.substring(0, 1);
  // 沪深：6xxxx(上海), 0xxxx/3xxxx(深圳)
  if (['6', '0', '3'].includes(prefix)) return '沪深';
  // 港股/美股：V2.0 扩展
  return '沪深';
}