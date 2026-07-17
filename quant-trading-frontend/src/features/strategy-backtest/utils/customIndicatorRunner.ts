/**
 * 自编指标执行器 — 管理 Pyodide Worker 生命周期、分批处理、进度回调
 *
 * 数据流：
 *   候选股票 OHLCV → 分批（每批 100 只）→ Pyodide Worker → 结果矩阵
 *                                                    ↓
 *                                       主线程按 [stockIdx][dayIdx] 消费
 *
 * 输出格式（预计算全量矩阵）:
 *   Map<脚本ID, { values: Map<股票代码, (number|null)[]>, errors: string[] }>
 *   values 内维 = 天数，长度与入参 OHLCV 一致
 */

import { getScript, getScriptCacheKey } from '../../settings/custom-indicators/scriptStore';

export interface BatchProgress {
  total: number;   // 总脚本数
  done: number;    // 已完成脚本数
  status: 'loading' | 'computing' | 'done' | 'error';
  message: string;
}

export interface ScriptResult {
  /** 脚本 ID */
  id: string;
  /** 脚本名称 */
  name: string;
  /** 预计算矩阵: Map<股票代码, (number|null)[] | number> */
  values: Map<string, (number | null)[] | number | null>;
  /** 错误列表（按股票索引） */
  errors: string[];
}

// 默认分批大小
const BATCH_SIZE = 100;
// 默认超时（毫秒）
const DEFAULT_TIMEOUT = 30_000;

export class CustomIndicatorRunner {
  private worker: Worker | null = null;
  private ready = false;
  private pendingResolve: ((value: any) => void) | null = null;
  private pendingReject: ((reason: any) => void) | null = null;
  private batchIdCounter = 0;

  /** Worker 是否已就绪 */
  isReady(): boolean {
    return this.ready;
  }

  /** 初始化 Worker（加载 Pyodide） */
  async init(): Promise<void> {
    if (this.worker) return;

    return new Promise((resolve, reject) => {
      try {
        this.worker = new Worker('/pyodide-worker.js', { type: 'classic' });
        const timeout = setTimeout(() => {
          this.cleanup();
          reject(new Error('Pyodide Worker 初始化超时（60s），请检查网络连接'));
        }, 60_000);

        this.worker.onmessage = (event) => {
          const { type, error } = event.data;
          if (type === 'ready') {
            clearTimeout(timeout);
            this.ready = true;
            resolve();
          } else if (type === 'error') {
            clearTimeout(timeout);
            this.cleanup();
            reject(new Error(error || 'Pyodide Worker 初始化失败'));
          }
        };

        this.worker.onerror = (err) => {
          clearTimeout(timeout);
          this.cleanup();
          reject(new Error('Worker 加载错误: ' + err.message));
        };
      } catch (err) {
        this.cleanup();
        reject(err);
      }
    });
  }

  /** 获取初始化进度（用于 UI 展示） */
  getInitProgress(): { loaded: boolean; message: string } {
    if (this.ready) return { loaded: true, message: 'Pyodide 已就绪' };
    if (this.worker) return { loaded: false, message: '正在加载 Python 解释器（~12MB）...' };
    return { loaded: false, message: '正在启动 Worker...' };
  }

  /**
   * 批量执行脚本
   *
   * @param scripts 要执行的脚本列表 [{ id, name, code, stockCodes, allOhlcv }]
   * @param onProgress 进度回调
   * @returns Map<脚本ID, ScriptResult>
   */
  async execute(
    scripts: {
      id: string;
      name: string;
      code: string;
      stockCodes: string[];
      allOhlcv: Map<string, number[][]>;
    }[],
    onProgress?: (progress: BatchProgress) => void,
  ): Promise<Map<string, ScriptResult>> {
    if (!this.ready || !this.worker) {
      throw new Error('Pyodide Worker 未就绪，请先调用 init()');
    }

    const results = new Map<string, ScriptResult>();
    const totalScripts = scripts.length;

    for (let si = 0; si < scripts.length; si++) {
      const script = scripts[si];
      const { id, name, code, stockCodes, allOhlcv } = script;

      onProgress?.({
        total: totalScripts,
        done: si,
        status: 'computing',
        message: `正在计算 [${name}]（${stockCodes.length} 只股票）...`,
      });

      // 分批处理股票
      const stockBatches = this.chunkArray(stockCodes, BATCH_SIZE);
      const allValues = new Map<string, (number | null)[] | number | null>();
      const errors: string[] = [];
      let batchId = `batch_${this.batchIdCounter++}`;

      for (let bi = 0; bi < stockBatches.length; bi++) {
        const batchCodes = stockBatches[bi];
        const batchData = this.prepareBatchData(batchCodes, allOhlcv);

        const scriptResult = await this.executeSingleBatch(
          code,
          batchData,
          batchId,
          DEFAULT_TIMEOUT,
        );

        // 解析结果
        if (scriptResult.values) {
          for (let ci = 0; ci < batchCodes.length; ci++) {
            const stockCode = batchCodes[ci];
            const stockValues = scriptResult.values[ci];
            if (stockValues !== undefined) {
              allValues.set(stockCode, stockValues);
            }
          }
        }
        if (scriptResult.error) {
          errors.push(`批次 ${bi + 1}: ${scriptResult.error}`);
        }

        onProgress?.({
          total: totalScripts,
          done: si,
          status: 'computing',
          message: `[${name}] 正在计算 ${allValues.size}/${stockCodes.length} 只...`,
        });
      }

      // 存储结果
      const result: ScriptResult = {
        id,
        name,
        values: allValues,
        errors,
      };
      results.set(id, result);
    }

    onProgress?.({
      total: totalScripts,
      done: totalScripts,
      status: 'done',
      message: '所有自编指标计算完成',
    });

    return results;
  }

  /**
   * 准备发送给 Worker 的批次数据
   * 将 OHLCV 转换为行优先的二维数组，新股前面补 null
   */
  private prepareBatchData(
    stockCodes: string[],
    allOhlcv: Map<string, number[][]>,
  ): {
    close: (number | null)[][];
    high: (number | null)[][];
    low: (number | null)[][];
    open: (number | null)[][];
    volume: (number | null)[][];
  } {
    // 找到该批次中最长的天数
    let maxDays = 0;
    for (const code of stockCodes) {
      const bars = allOhlcv.get(code);
      if (bars && bars.length > maxDays) {
        maxDays = bars.length;
      }
    }

    const OHLCV_TIMESTAMP = 0;
    const OHLCV_OPEN = 1;
    const OHLCV_HIGH = 2;
    const OHLCV_LOW = 3;
    const OHLCV_CLOSE = 4;
    const OHLCV_VOLUME = 5;

    const close: (number | null)[][] = [];
    const high: (number | null)[][] = [];
    const low: (number | null)[][] = [];
    const open: (number | null)[][] = [];
    const volume: (number | null)[][] = [];

    for (const code of stockCodes) {
      const bars = allOhlcv.get(code);
      if (!bars || bars.length === 0) {
        close.push(new Array(maxDays).fill(null));
        high.push(new Array(maxDays).fill(null));
        low.push(new Array(maxDays).fill(null));
        open.push(new Array(maxDays).fill(null));
        volume.push(new Array(maxDays).fill(null));
        continue;
      }

      const padLen = maxDays - bars.length;
      const cArr = new Array(maxDays).fill(null);
      const hArr = new Array(maxDays).fill(null);
      const lArr = new Array(maxDays).fill(null);
      const oArr = new Array(maxDays).fill(null);
      const vArr = new Array(maxDays).fill(null);

      for (let di = 0; di < bars.length; di++) {
        const bar = bars[di];
        cArr[padLen + di] = bar[OHLCV_CLOSE] ?? null;
        oArr[padLen + di] = bar[OHLCV_OPEN] ?? null;
        hArr[padLen + di] = bar[OHLCV_HIGH] ?? null;
        lArr[padLen + di] = bar[OHLCV_LOW] ?? null;
        vArr[padLen + di] = (bar[OHLCV_VOLUME] ?? null) as number | null;
      }

      close.push(cArr);
      high.push(hArr);
      low.push(lArr);
      open.push(oArr);
      volume.push(vArr);
    }

    return { close, high, low, open, volume };
  }

  /**
   * 执行单批次脚本
   * 返回 Promise，超时自动 reject
   */
  private executeSingleBatch(
    code: string,
    stockData: {
      close: (number | null)[][];
      high: (number | null)[][];
      low: (number | null)[][];
      open: (number | null)[][];
      volume: (number | null)[][];
    },
    batchId: string,
    timeoutMs: number,
  ): Promise<{ values?: ((number | null)[] | number | null)[]; error?: string }> {
    return new Promise((resolve, reject) => {
      if (!this.worker) {
        reject(new Error('Worker 已终止'));
        return;
      }

      const timeout = setTimeout(() => {
        // 超时 → 终止当前 Worker，创建新 Worker
        this.cleanup();
        // 自动重建（异步，不阻塞当前流程）
        this.init().catch(() => {});
        reject(new Error(`脚本执行超时（${timeoutMs}ms），Worker 已重建`));
      }, timeoutMs);

      this.worker.onmessage = (event) => {
        const msg = event.data;
        if (msg.type === 'result' && msg.batchId === batchId) {
          clearTimeout(timeout);
          // 解析结果
          const result = msg.results?.[0];
          if (result?.error) {
            resolve({ error: result.error });
          } else if (result?.values) {
            resolve({ values: result.values });
          } else {
            resolve({ error: '脚本未返回有效结果' });
          }
        } else if (msg.type === 'error' && msg.batchId === batchId) {
          clearTimeout(timeout);
          resolve({ error: msg.error });
        }
      };

      this.worker.postMessage({
        type: 'execute',
        batchId,
        scripts: [{ id: 'single', code, stockData }],
        timeoutMs,
      });
    });
  }

  /** 释放 Worker 资源 */
  cleanup(): void {
    if (this.worker) {
      try {
        this.worker.postMessage({ type: 'terminate' });
      } catch { /* ignore */ }
      this.worker.terminate();
      this.worker = null;
    }
    this.ready = false;
    this.pendingResolve = null;
    this.pendingReject = null;
  }

  private chunkArray<T>(arr: T[], size: number): T[][] {
    const result: T[][] = [];
    for (let i = 0; i < arr.length; i += size) {
      result.push(arr.slice(i, i + size));
    }
    return result;
  }
}

/** 单例 */
let runnerInstance: CustomIndicatorRunner | null = null;

export function getCustomIndicatorRunner(): CustomIndicatorRunner {
  if (!runnerInstance) {
    runnerInstance = new CustomIndicatorRunner();
  }
  return runnerInstance;
}