/**
 * 自编指标筛选服务（统一管道）
 *
 * 职责：
 *   - OHLCV 数据加载（支持分批、可取消）
 *   - Pyodide 自编指标执行
 *   - 结果过滤（取最后有效值 vs 阈值）
 *   - 管道式递减过滤（每步缩小候选集）
 *   - K线按需切片（按最大回溯天数）
 *
 * 两个调用方共享此服务：
 *   1. applyCustomIndicatorFilter（旧版：首屏快速过滤当前页）
 *   2. useScreenerData 全量筛选（新版：先算后显）
 */

import { getCustomIndicatorRunner } from '@/features/strategy-backtest/utils/customIndicatorRunner';
import type { CustomIndicator } from '../types/customIndicator';

// ==================== 类型定义 ====================

export interface CustomCondition {
  scriptId: string;
  name: string;
  formula: string;
  operator: string;
  threshold: number | [number, number];
}

export interface FilterResult {
  passedCodes: Set<string>;
  executed: boolean;
  error?: string;
}

export interface ComputeProgress {
  phase: 'loading-ohlcv' | 'computing';
  done: number;
  total: number;
  message: string;
}

/** 条件的最小接口，兼容 FilterCondition 和实际运行时的条件对象 */
interface ConditionLike {
  source?: string;
  sourceId?: string;
  fieldKey?: string;
}

// ==================== 配置常量 ====================

const OHLCV_BATCH_SIZE = 200;
const MAX_LOOKBACK_DEFAULT = 300;
/** 单批 OHLCV 请求最大重试次数 */
const OHLCV_MAX_RETRIES = 2;
/** 首次重试延迟（毫秒），后续指数退避 */
const OHLCV_RETRY_BASE_DELAY = 500;

// ==================== 工具函数 ====================

/**
 * 从 filterGroup.conditions 中提取自编指标条件
 */
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
 * 阈值比较
 */
export function meetsThreshold(
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
      console.warn(`[自编指标筛选] range 操作符需要区间阈值，实际收到:`, threshold);
      return false;
    case 'cross_up':
    case 'cross_down':
      console.warn(`[自编指标筛选] ${operator} 操作符暂不支持自编指标选股，请使用 >, >=, <, <=, ==, range`);
      return false;
    default:
      console.warn(`[自编指标筛选] 未知操作符: "${operator}"，跳过筛选`);
      return false;
  }
}

/**
 * 睡眠（指数退避用）
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ==================== 核心服务类 ====================

/**
 * 自编指标筛选服务
 *
 * 设计原则：
 *   - 纯服务类，无 React 依赖，可在任意上下文调用
 *   - 支持 AbortSignal 取消
 *   - 支持进度回调
 *   - 内置 OHLCV 缓存（实例级别，调用方控制生命周期）
 */
export class CustomIndicatorService {
  private ohlcvCache = new Map<string, number[][]>();

  /**
   * 清空 OHLCV 缓存
   */
  clearCache(): void {
    this.ohlcvCache.clear();
  }

  /**
   * 获取当前缓存大小
   */
  get cacheSize(): number {
    return this.ohlcvCache.size;
  }

  /**
   * 批量加载 OHLCV 数据（自动分批 + 重试 + 缓存）
   *
   * @param codes 股票代码列表
   * @param signal 取消信号
   * @param onProgress 进度回调
   * @returns OHLCV Map
   */
  async loadOhlcv(
    codes: string[],
    signal?: AbortSignal,
    onProgress?: (done: number, total: number) => void,
  ): Promise<Map<string, number[][]>> {
    if (codes.length === 0) return new Map();

    const result = new Map<string, number[][]>();
    const needFetch: string[] = [];

    for (const code of codes) {
      const cached = this.ohlcvCache.get(code);
      if (cached) {
        result.set(code, cached);
      } else {
        needFetch.push(code);
      }
    }

    const total = codes.length;
    let done = result.size;
    onProgress?.(done, total);

    if (needFetch.length === 0) return result;

    for (let i = 0; i < needFetch.length; i += OHLCV_BATCH_SIZE) {
      if (signal?.aborted) {
        throw new Error('已取消');
      }

      const batch = needFetch.slice(i, i + OHLCV_BATCH_SIZE);
      const batchMap = await this.fetchOhlcvBatch(batch, signal);

      for (const [code, ohlcv] of batchMap) {
        result.set(code, ohlcv);
        this.ohlcvCache.set(code, ohlcv);
      }

      done = result.size;
      onProgress?.(done, total);
    }

    return result;
  }

  /**
   * 拉取单批 OHLCV（带重试）
   */
  private async fetchOhlcvBatch(
    codes: string[],
    signal?: AbortSignal,
  ): Promise<Map<string, number[][]>> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= OHLCV_MAX_RETRIES; attempt++) {
      if (signal?.aborted) throw new Error('已取消');

      if (attempt > 0) {
        const delay = OHLCV_RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
        await sleep(delay);
      }

      try {
        const resp = await fetch(`/api/snapshot/all?codes=${codes.join(',')}`, { signal });
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const json = await resp.json();
        const stocks = json.data?.stocks ?? [];
        const result = new Map<string, number[][]>();
        for (const s of stocks) {
          if (s.ohlcv && Array.isArray(s.ohlcv) && s.ohlcv.length > 0) {
            result.set(s.code, s.ohlcv);
          }
        }
        return result;
      } catch (err) {
        if (signal?.aborted) throw new Error('已取消');
        lastError = err instanceof Error ? err : new Error(String(err));
        console.warn(`[CustomIndicatorService] OHLCV 拉取失败 (第 ${attempt + 1} 次): ${lastError.message}`);
      }
    }

    throw new Error(`OHLCV 数据拉取失败，已重试 ${OHLCV_MAX_RETRIES} 次: ${lastError?.message}`);
  }

  /**
   * 对 OHLCV 数据做尾部切片（减少 Pyodide 计算量）
   *
   * @param ohlcvMap 原始 OHLCV
   * @param days 保留最后 N 天
   * @returns 切片后的新 Map（原 Map 不变）
   */
  sliceOhlcv(ohlcvMap: Map<string, number[][]>, days: number): Map<string, number[][]> {
    const result = new Map<string, number[][]>();
    for (const [code, ohlcv] of ohlcvMap) {
      const sliced = ohlcv.slice(-days);
      result.set(code, sliced);
    }
    return result;
  }

  /**
   * 执行自编指标计算并过滤（管道式递减）
   *
   * 对每个自编指标，仅在上一步通过的股票上计算，逐步缩小候选集。
   *
   * @param conditions 自编指标条件列表
   * @param stockCodes 初始候选股票代码列表
   * @param ohlcvMap OHLCV 数据
   * @param signal 取消信号
   * @param onProgress 进度回调
   * @returns 通过筛选的股票代码集合
   */
  async computeAndFilter(
    conditions: CustomCondition[],
    stockCodes: string[],
    ohlcvMap: Map<string, number[][]>,
    signal?: AbortSignal,
    onProgress?: (progress: ComputeProgress) => void,
  ): Promise<Set<string>> {
    if (conditions.length === 0 || stockCodes.length === 0) {
      return new Set(stockCodes);
    }

    const validScripts = conditions.filter((c) => c.formula && c.formula.trim());
    if (validScripts.length === 0) {
      return new Set(stockCodes);
    }

    const runner = getCustomIndicatorRunner();
    if (!runner.isReady()) {
      await runner.init();
    }

    let passed = new Set(stockCodes);

    for (let idx = 0; idx < validScripts.length; idx++) {
      if (signal?.aborted) throw new Error('已取消');

      const cond = validScripts[idx];
      const currentCodes = Array.from(passed);

      onProgress?.({
        phase: 'computing',
        done: idx,
        total: validScripts.length,
        message: `正在计算「${cond.name}」（${currentCodes.length} 只股票）...`,
      });

      const scriptDef = {
        id: cond.scriptId,
        name: cond.name,
        code: cond.formula,
        stockCodes: currentCodes,
        allOhlcv: ohlcvMap,
      };

      const resultMap = await runner.execute([scriptDef]);
      const scriptResult = resultMap.get(cond.scriptId);

      if (!scriptResult) {
        console.warn(`[CustomIndicatorService] 未找到脚本结果: ${cond.scriptId}`);
        continue;
      }

      const nextPassed = new Set<string>();
      for (const code of currentCodes) {
        if (signal?.aborted) throw new Error('已取消');
        const values = scriptResult.values.get(code);
        const lastVal = this.getLastValidValue(values);
        if (lastVal === null) continue;
        if (meetsThreshold(lastVal, cond.operator, cond.threshold)) {
          nextPassed.add(code);
        }
      }

      passed = nextPassed;

      if (passed.size === 0) {
        break;
      }
    }

    onProgress?.({
      phase: 'computing',
      done: validScripts.length,
      total: validScripts.length,
      message: '自编指标计算完成',
    });

    return passed;
  }

  /**
   * 获取数组最后一个有效值（非 null/undefined/NaN）
   */
  private getLastValidValue(values: number | (number | null)[] | null | undefined): number | null {
    if (values === null || values === undefined) return null;
    if (typeof values === 'number') {
      return Number.isNaN(values) ? null : values;
    }
    if (Array.isArray(values)) {
      for (let i = values.length - 1; i >= 0; i--) {
        const v = values[i];
        if (v !== null && v !== undefined && !Number.isNaN(v)) {
          return v;
        }
      }
    }
    return null;
  }

  /**
   * 完整筛选流程（加载 OHLCV + 计算 + 过滤）
   *
   * 兼容旧版 applyCustomIndicatorFilter 调用方式，返回 FilterResult。
   */
  async filter(
    conditions: CustomCondition[],
    stockCodes: string[],
    signal?: AbortSignal,
    onProgress?: (progress: ComputeProgress) => void,
  ): Promise<FilterResult> {
    if (conditions.length === 0 || stockCodes.length === 0) {
      return { passedCodes: new Set(stockCodes), executed: false };
    }

    try {
      const ohlcvMap = await this.loadOhlcv(
        stockCodes,
        signal,
        (done, total) => onProgress?.({
          phase: 'loading-ohlcv',
          done,
          total,
          message: `正在加载K线数据 ${done}/${total} 只`,
        }),
      );

      const passedCodes = await this.computeAndFilter(
        conditions,
        stockCodes,
        ohlcvMap,
        signal,
        onProgress,
      );

      return { passedCodes, executed: true };
    } catch (err) {
      if ((err as Error).message === '已取消') {
        return { passedCodes: new Set(stockCodes), executed: false, error: '已取消' };
      }
      console.error('自编指标筛选失败:', err);
      return {
        passedCodes: new Set(stockCodes),
        executed: false,
        error: (err as Error).message || '自编指标筛选失败',
      };
    }
  }
}

// ==================== 单例 ====================

let globalInstance: CustomIndicatorService | null = null;

/**
 * 获取全局服务实例（旧版兼容用）
 */
export function getCustomIndicatorService(): CustomIndicatorService {
  if (!globalInstance) {
    globalInstance = new CustomIndicatorService();
  }
  return globalInstance;
}
