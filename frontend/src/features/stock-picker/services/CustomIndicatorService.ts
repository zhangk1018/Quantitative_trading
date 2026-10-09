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
import { inferMarketKey } from '@/features/watchlist/utils/stock-utils';
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
/** OHLCV 分批拉取的并发度（网络为瓶颈，并发可显著缩短全市场加载时间） */
const OHLCV_FETCH_CONCURRENCY = 4;
/** 单批 OHLCV 请求最大重试次数 */
const OHLCV_MAX_RETRIES = 2;
/** 首次重试延迟（毫秒），后续指数退避 */
const OHLCV_RETRY_BASE_DELAY = 500;
/** 后端数据服务（数据刷新/加载中返回 503）就绪等待最大时长（毫秒）。
 * 后端全量快照重建（全市场 OHLCV）可能超过 120s，适当放宽避免选股被误报超时。
 */
const OHLCV_READY_WAIT_MS = 240_000;
/** 就绪探测轮询间隔（毫秒） */
const READY_POLL_INTERVAL_MS = 1000;

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
 * 计算单个自编指标「自身」所需的 OHLCV 窗口长度（交易日数）。
 *
 * 从公式中提取 1~500 的数字取最大值，再加 5 天安全余量（指标公式往往需要
 * 「最大周期 + 1」根数据才能产生首个非零值，如 MA5 需 range(5, n) 至少 n=6）。
 * 无可用数字时回退 30 + 5。
 *
 * ⚠️ 关键：窗口必须按「每个指标各自」计算，不能取所选指标的全局最大值。
 * 否则某指标的输入窗口会随「同时勾选了哪些指标」而变化——对窗口敏感型公式
 * （突破窗口内前高/新低、全窗极值/均值、依赖 len(close) 等）会导致单独选与
 * 组合选时结果不一致，组合结果不再是各指标单独结果的交集（K 2026-10-09）。
 */
export function computeConditionLookback(cond: { formula?: string }): number {
  let maxNum = 0;
  if (cond.formula) {
    const matches = cond.formula.match(/\b(\d{1,3})\b/g);
    if (matches) {
      for (const m of matches) {
        const n = parseInt(m, 10);
        if (!Number.isNaN(n) && n >= 1 && n <= 500 && n > maxNum) {
          maxNum = n;
        }
      }
    }
  }
  return (maxNum > 0 ? maxNum : 30) + 5;
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

    // 分批并发拉取（网络为瓶颈）：全市场 5000+ 只原本串行需数十秒，并发后显著缩短
    const batches: string[][] = [];
    for (let i = 0; i < needFetch.length; i += OHLCV_BATCH_SIZE) {
      batches.push(needFetch.slice(i, i + OHLCV_BATCH_SIZE));
    }

    for (let i = 0; i < batches.length; i += OHLCV_FETCH_CONCURRENCY) {
      if (signal?.aborted) {
        throw new Error('已取消');
      }

      const group = batches.slice(i, i + OHLCV_FETCH_CONCURRENCY);
      const batchMaps = await Promise.all(group.map((batch) => this.fetchOhlcvBatch(batch, signal)));

      for (const batchMap of batchMaps) {
        for (const [code, ohlcv] of batchMap) {
          result.set(code, ohlcv);
          this.ohlcvCache.set(code, ohlcv);
        }
      }

      done = result.size;
      onProgress?.(done, total);
    }

    return result;
  }

  /**
   * 等待后端快照服务就绪。
   *
   * 后端在全量数据刷新/加载期间会让 /api/snapshot/all 返回 503（数据加载中），
   * 此时不能按普通失败机械重试，而应先轮询 /api/snapshot/ready 等服务就绪后再重试。
   *
   * @returns 就绪返回 true；超时返回 false；信号取消抛「已取消」
   */
  private async waitReady(maxWaitMs: number, signal?: AbortSignal): Promise<boolean> {
    const deadline = Date.now() + maxWaitMs;
    while (Date.now() < deadline) {
      if (signal?.aborted) throw new Error('已取消');
      try {
        const resp = await fetch('/api/snapshot/ready', { signal });
        if (resp.ok) return true;
        // 非 2xx（后端仍 503）：继续轮询，等待后端刷新完成
      } catch (err) {
        if (signal?.aborted) throw new Error('已取消');
        // 连接类瞬态错误：继续轮询
      }
      await sleep(READY_POLL_INTERVAL_MS);
    }
    return false;
  }

  /**
   * 拉取单批 OHLCV（带重试 + 数据服务就绪等待）
   */
  private async fetchOhlcvBatch(
    codes: string[],
    signal?: AbortSignal,
  ): Promise<Map<string, number[][]>> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= OHLCV_MAX_RETRIES; attempt++) {
      if (signal?.aborted) throw new Error('已取消');

      if (attempt > 0) {
        // 就绪等待后重试的场景不额外退避，避免叠加延时
        const delay = OHLCV_RETRY_BASE_DELAY * Math.pow(2, attempt - 1);
        await sleep(delay);
      }

      try {
        // 按候选 codes 推断市场（.HK→hk / 字母→us / 否则 cn）并显式传 market：
        // /api/snapshot/all 缺省按 cn 过滤，港股/美股候选不传会全部被后端剔除（K 2026-09-19 港股自编指标筛 0 只）
        const mk = codes.length > 0 ? inferMarketKey(codes[0]) : undefined;
        const marketParam = mk && mk !== 'cn' ? `&market=${mk}` : '';
        const resp = await fetch(`/api/snapshot/all?codes=${codes.join(',')}${marketParam}`, { signal });
        // 数据刷新/加载中：等待后端就绪后重置重试计数，重新发起本轮请求
        if (resp.status === 503) {
          const ready = await this.waitReady(OHLCV_READY_WAIT_MS, signal);
          if (!ready) {
            throw new Error(`数据服务仍在后台刷新（已等待 ${OHLCV_READY_WAIT_MS / 1000}s），请稍后重试或换个时间再选股`);
          }
          lastError = new Error(`HTTP ${resp.status}`);
          attempt = -1; // 就绪后重置计数，重新走一次完整请求
          continue;
        }
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
   * 每个指标都按「自身」公式所需的窗口（computeConditionLookback）切片，
   * 因此同一指标在「单独选」与「和其他指标一起选」时输入数据一致，结果一致，
   * 组合结果恒等于各指标单独结果的交集。
   *
   * @param conditions 自编指标条件列表
   * @param stockCodes 初始候选股票代码列表
   * @param ohlcvMap 完整（未切片）的 OHLCV 数据，切片在方法内部按指标各自进行
   * @param signal 取消信号
   * @param onProgress 进度回调
   * @returns 通过筛选的股票代码集合及每只股票的最后有效评分
   */
  async computeAndFilter(
    conditions: CustomCondition[],
    stockCodes: string[],
    ohlcvMap: Map<string, number[][]>,
    signal?: AbortSignal,
    onProgress?: (progress: ComputeProgress) => void,
  ): Promise<{ passedCodes: Set<string>; scores: Map<string, number> }> {
    const emptyResult = { passedCodes: new Set<string>(), scores: new Map<string, number>() };
    if (conditions.length === 0 || stockCodes.length === 0) {
      emptyResult.passedCodes = new Set(stockCodes);
      return emptyResult;
    }

    const validScripts = conditions.filter((c) => c.formula && c.formula.trim());
    if (validScripts.length === 0) {
      emptyResult.passedCodes = new Set(stockCodes);
      return emptyResult;
    }

    // 候选股全部无 K 线时（后端 /api/snapshot/all 未覆盖该市场，如快照缓存按单一最新交易日加载
    // 导致最新快照日滞后的市场整市缺失），脚本对每只股票只会算出空值 → 静默返回 0 只，
    // 与"选股条件太严"混为一谈（K 2026-09-29：沪深自编指标全部选不出股票）。
    // 此处显式抛错，由调用方转成用户可见提示。
    const codesWithBars = stockCodes.filter((c) => (ohlcvMap.get(c)?.length ?? 0) > 0);
    if (codesWithBars.length === 0) {
      throw new Error('候选股票均无K线数据（行情快照缺失），自编指标无法计算，请稍后重试');
    }

    const runner = getCustomIndicatorRunner();
    if (!runner.isReady()) {
      await runner.init();
    }

    let passed = new Set(stockCodes);
    // 全局评分：每只股票的最后有效评分
    const scores = new Map<string, number>();

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

      // 按「本指标自身」的窗口切片，避免其他指标的选取改变本指标的输入窗口
      const condOhlcv = this.sliceOhlcv(ohlcvMap, computeConditionLookback(cond));

      const scriptDef = {
        id: cond.scriptId,
        name: cond.name,
        code: cond.formula,
        stockCodes: currentCodes,
        allOhlcv: condOhlcv,
      };

      // 把 runner 的「按批」进度透传给 UI：单指标在全市场计算需较久，
      // 否则进度条文案长时间停在初始值，用户会误以为卡死/超时。
      const resultMap = await runner.execute([scriptDef], (bp) => {
        onProgress?.({
          phase: 'computing',
          done: idx,
          total: validScripts.length,
          message: bp.message,
        });
      });
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
        // 记录评分（后续指标覆盖前面的评分）
        scores.set(code, lastVal);
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

    return { passedCodes: passed, scores };
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

      const { passedCodes } = await this.computeAndFilter(
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
