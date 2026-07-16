/**
 * 自编指标客户端筛选器
 *
 * 在选股器后端返回结果后，通过 Pyodide Worker 执行自编指标脚本，
 * 根据脚本返回值（取最后一个值）与阈值比较，过滤不满足条件的股票。
 *
 * 流程：
 *   1. 从后端获取候选股票的 OHLCV 数据（/api/snapshot/all）
 *   2. 初始化 Pyodide Worker（如未初始化）
 *   3. 逐脚本执行，获取每只股票的指标值
 *   4. 取最后一个值 vs 阈值，过滤不满足的股票
 */

import { getCustomIndicatorRunner } from '@/features/strategy-backtest/utils/customIndicatorRunner';
import type { CustomIndicator } from '../types/customIndicator';

export interface FilterResult {
  /** 通过筛选的股票代码列表 */
  passedCodes: Set<string>;
  /** 是否已成功执行（false 时跳过筛选，显示全部） */
  executed: boolean;
  /** 错误信息 */
  error?: string;
}

/** 单个自编指标条件 */
interface CustomCondition {
  scriptId: string;
  name: string;
  formula: string;
  operator: string;
  threshold: number | [number, number];
}

/**
 * 从 filterGroup.conditions 中提取自编指标条件
 */
/** 条件的最小接口，兼容 FilterCondition 和实际运行时的条件对象 */
interface ConditionLike {
  source?: string;
  sourceId?: string;
  fieldKey?: string;
}

export function extractCustomConditions(
  conditions: ConditionLike[],
  indicators: CustomIndicator[],
): CustomCondition[] {
  const result: CustomCondition[] = [];
  for (const cond of conditions) {
    if (cond.source !== 'custom' || !cond.sourceId) continue;
    const indicator = indicators.find((i) => i.id === cond.sourceId && !i.deleted);
    if (!indicator) continue;
    result.push({
      scriptId: cond.sourceId,
      name: indicator.name,
      formula: indicator.formula,
      operator: indicator.operator,
      threshold: indicator.defaultThreshold,
    });
  }
  return result;
}

/**
 * 应用自编指标筛选
 *
 * @param stockCodes 候选股票代码列表
 * @param customConditions 自编指标条件
 * @returns 通过筛选的股票代码集合
 */
export async function applyCustomIndicatorFilter(
  stockCodes: string[],
  customConditions: CustomCondition[],
): Promise<FilterResult> {
  if (customConditions.length === 0 || stockCodes.length === 0) {
    return { passedCodes: new Set(stockCodes), executed: false };
  }

  try {
    // 1. 获取 OHLCV 数据
    const codesParam = stockCodes.join(',');
    const resp = await fetch(`/api/snapshot/all?codes=${codesParam}`);
    if (!resp.ok) {
      return { passedCodes: new Set(stockCodes), executed: false, error: `OHLCV 数据请求失败 (${resp.status})` };
    }
    const json = await resp.json();
    const stocks = json.data?.stocks ?? [];
    if (stocks.length === 0) {
      return { passedCodes: new Set(stockCodes), executed: false, error: '未获取到 OHLCV 数据' };
    }

    // 构建 OHLCV Map
    const allOhlcv = new Map<string, number[][]>();
    for (const s of stocks) {
      if (s.ohlcv && Array.isArray(s.ohlcv) && s.ohlcv.length > 0) {
        allOhlcv.set(s.code, s.ohlcv);
      }
    }

    // 2. 初始化 Pyodide Worker
    const runner = getCustomIndicatorRunner();
    if (!runner.isReady()) {
      await runner.init();
    }

    // 3. 准备脚本数据（直接从 CustomIndicator 读取 formula，不经过 scriptStore）
    const scripts = customConditions.map((cond) => {
      if (!cond.formula || !cond.formula.trim()) {
        console.warn(`自编指标「${cond.name}」公式为空，跳过`);
        return null;
      }
      return {
        id: cond.scriptId,
        name: cond.name,
        code: cond.formula,
        stockCodes,
        allOhlcv,
      };
    }).filter(Boolean) as {
      id: string;
      name: string;
      code: string;
      stockCodes: string[];
      allOhlcv: Map<string, number[][]>;
    }[];

    if (scripts.length === 0) {
      return { passedCodes: new Set(stockCodes), executed: false, error: '未找到有效的自编指标脚本' };
    }

    // 4. 执行脚本
    const results = await runner.execute(scripts);

    // 5. 过滤：取每只股票的最后一个值，与阈值比较
    const passedCodes = new Set(stockCodes);

    for (const cond of customConditions) {
      const scriptResult = results.get(cond.scriptId);
      if (!scriptResult) continue;

      for (const stockCode of stockCodes) {
        if (!passedCodes.has(stockCode)) continue;

        const values = scriptResult.values.get(stockCode);
        if (!values || values.length === 0) {
          passedCodes.delete(stockCode);
          continue;
        }

        // 取最后一个有效值
        let lastVal: number | null = null;
        for (let i = values.length - 1; i >= 0; i--) {
          if (values[i] !== null && values[i] !== undefined && !Number.isNaN(values[i])) {
            lastVal = values[i] as number;
            break;
          }
        }

        if (lastVal === null) {
          passedCodes.delete(stockCode);
          continue;
        }

        // 阈值比较
        if (!meetsThreshold(lastVal, cond.operator, cond.threshold)) {
          passedCodes.delete(stockCode);
        }
      }
    }

    return { passedCodes, executed: true };
  } catch (err) {
    console.error('自编指标筛选失败:', err);
    return {
      passedCodes: new Set(stockCodes),
      executed: false,
      error: (err as Error).message || '自编指标筛选失败',
    };
  }
}

/** 阈值比较 */
function meetsThreshold(
  value: number,
  operator: string,
  threshold: number | [number, number],
): boolean {
  switch (operator) {
    case '>':
      return value > (threshold as number);
    case '>=':
      return value >= (threshold as number);
    case '<':
      return value < (threshold as number);
    case '<=':
      return value <= (threshold as number);
    case '==':
      return value === (threshold as number);
    case 'range':
      if (Array.isArray(threshold) && threshold.length >= 2) {
        return value >= threshold[0] && value <= threshold[1];
      }
      return true;
    default:
      return true;
  }
}