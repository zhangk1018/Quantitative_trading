/**
 * 自编指标客户端筛选器（兼容旧接口）
 *
 * ⚠️  已重构为调用 CustomIndicatorService，这里仅保留对外兼容层。
 * 新代码请直接 import CustomIndicatorService。
 *
 * 保留文件原因：
 *   - 旧版首屏快速过滤逻辑仍在使用
 *   - 避免大范围改动调用方
 */

import {
  CustomIndicatorService,
  extractCustomConditions,
  meetsThreshold,
  getCustomIndicatorService,
} from '../services/CustomIndicatorService';

export type { FilterResult, CustomCondition, ComputeProgress } from '../services/CustomIndicatorService';
export { extractCustomConditions, meetsThreshold, CustomIndicatorService, getCustomIndicatorService };

/**
 * 应用自编指标筛选（兼容旧版调用方式）
 *
 * @param stockCodes 候选股票代码列表
 * @param customConditions 自编指标条件
 * @returns 通过筛选的股票代码集合
 */
export async function applyCustomIndicatorFilter(
  stockCodes: string[],
  customConditions: Parameters<CustomIndicatorService['filter']>[0],
): ReturnType<CustomIndicatorService['filter']> {
  const service = getCustomIndicatorService();
  return service.filter(customConditions, stockCodes);
}
