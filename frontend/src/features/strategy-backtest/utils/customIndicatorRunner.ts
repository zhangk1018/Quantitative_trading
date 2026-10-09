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
  /** 预计算矩阵: Map<股票代码, (number|null)[] — 内维=天数，长度与入参 OHLCV 一致 */
  values: Map<string, (number | null)[]>;
  /** 错误列表（按股票索引） */
  errors: string[];
}

/**
 * 将自编指标预计算结果按「日期键」zip 为 customValueByDate。
 *
 * 前提：入参 OHLCV 已按 windowDates 对齐（每只股票长度一致，index j ↔ windowDates[j]），
 * 因此 values[code][j] ↔ windowDates[j]。根治旧「数组下标 + 批次右对齐 padding」的日期错位。
 *
 * @returns Map<scriptId, Map<code, Map<'YYYY-MM-DD', number|null>>>
 */
export function buildCustomValueByDate(
  results: Map<string, ScriptResult>,
  windowDates: string[],
): Map<string, Map<string, Map<string, number | null>>> {
  const out = new Map<string, Map<string, Map<string, number | null>>>();
  for (const [scriptId, result] of results) {
    const byCode = new Map<string, Map<string, number | null>>();
    for (const [code, vals] of result.values) {
      const byDate = new Map<string, number | null>();
      const len = Math.min(windowDates.length, vals.length);
      for (let j = 0; j < len; j++) {
        byDate.set(windowDates[j], vals[j]);
      }
      byCode.set(code, byDate);
    }
    out.set(scriptId, byCode);
  }
  return out;
}

// 单批股票数：配合多 Worker 池，批次更小 → 并行负载更均衡、单批更快更不易超时
const BATCH_SIZE = 50;
// 单批超时（毫秒）：全市场重公式单批可能数十秒，放宽避免误杀整轮选股
const DEFAULT_TIMEOUT = 120_000;
// Worker 单次返回的最大元素数（防止恶意脚本产出巨量数据撑爆内存）
const MAX_OUTPUT_ELEMENTS = 500_000;

/**
 * Pyodide Worker 池大小。
 *
 * 单个 Worker 串行执行 Python，而纯 Python 循环型重公式（如多因子/ADX 打分）
 * 在全市场 5000+ 只股票上需数分钟；用少量多 Worker 并行可近似线性提速。
 * 上限 4 以兼顾内存（每个 Pyodide + numpy 约数十 MB）。
 */
function getPoolSize(): number {
  const cores = (typeof navigator !== 'undefined' && Number(navigator.hardwareConcurrency)) || 4;
  return Math.min(4, Math.max(2, cores - 1));
}

/** worker 回传的单批消息 */
interface WorkerBatchMessage {
  type: 'result' | 'error';
  batchId: string;
  results?: { id: string; values?: unknown; error?: string | null }[];
  error?: string;
}

interface BatchResponse {
  values?: ((number | null)[] | number | null)[];
  error?: string;
}

export class CustomIndicatorRunner {
  private workers: Worker[] = [];
  private ready = false;
  private initPromise: Promise<void> | null = null;
  private batchIdCounter = 0;
  /** batchId → 该批的 resolve/reject/timer（多 Worker 并行时按 batchId 分发结果） */
  private pending = new Map<
    string,
    { resolve: (r: BatchResponse) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }
  >();

  /** Worker 池是否已就绪 */
  isReady(): boolean {
    return this.ready;
  }

  /** 初始化 Worker 池（每个 Worker 各自加载 Pyodide） */
  async init(): Promise<void> {
    if (this.ready) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      const created: Worker[] = [];
      try {
        await Promise.all(
          Array.from({ length: getPoolSize() }, () => this.spawnWorker(created)),
        );
        this.workers = created;
        this.ready = true;
      } catch (err) {
        created.forEach((w) => {
          try { w.terminate(); } catch { /* ignore */ }
        });
        this.workers = [];
        this.ready = false;
        throw err;
      } finally {
        this.initPromise = null;
      }
    })();

    return this.initPromise;
  }

  /** 创建一个 Worker 并等待其 Pyodide ready */
  private spawnWorker(sink: Worker[]): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      let worker: Worker;
      try {
        worker = new Worker('/pyodide-worker.js', { type: 'classic' });
      } catch (err) {
        reject(err instanceof Error ? err : new Error(String(err)));
        return;
      }
      sink.push(worker);

      const timeout = setTimeout(() => {
        this.detachWorker(worker);
        reject(new Error('Pyodide Worker 初始化超时（60s），请检查网络连接'));
      }, 60_000);

      worker.onmessage = (event) => {
        const { type, error } = event.data ?? {};
        if (type === 'ready') {
          clearTimeout(timeout);
          worker.onmessage = this.handleWorkerMessage;
          resolve();
        } else if (type === 'error') {
          clearTimeout(timeout);
          this.detachWorker(worker);
          reject(new Error(error || 'Pyodide Worker 初始化失败'));
        }
      };

      worker.onerror = (err) => {
        clearTimeout(timeout);
        this.detachWorker(worker);
        reject(new Error('Worker 加载错误: ' + err.message));
      };
    });
  }

  /** 终止单个 Worker（并从池中摘除） */
  private detachWorker(worker: Worker): void {
    try { worker.terminate(); } catch { /* ignore */ }
    const i = this.workers.indexOf(worker);
    if (i >= 0) this.workers.splice(i, 1);
  }

  /** 结果分发：按 batchId 找到对应批次的 resolve */
  private handleWorkerMessage = (event: MessageEvent): void => {
    const msg = event.data as WorkerBatchMessage | undefined;
    if (!msg || (msg.type !== 'result' && msg.type !== 'error')) return;
    const entry = this.pending.get(msg.batchId);
    if (!entry) return;
    this.pending.delete(msg.batchId);
    clearTimeout(entry.timer);
    entry.resolve(this.parseWorkerMessage(msg));
  };

  /** 解析 worker 回传的单批消息（含输出规模上限保护） */
  private parseWorkerMessage(msg: WorkerBatchMessage): BatchResponse {
    if (msg.type === 'error') return { error: msg.error };
    const result = msg.results?.[0];
    if (result?.error) return { error: result.error };
    if (result?.values) {
      const totalElements = (result.values as unknown[]).reduce(
        (sum: number, arr) => sum + (Array.isArray(arr) ? arr.length : 1),
        0,
      );
      if (totalElements > MAX_OUTPUT_ELEMENTS) {
        this.cleanup();
        this.init().catch(() => {});
        return { error: `脚本输出超出上限（${totalElements} > ${MAX_OUTPUT_ELEMENTS}），Worker 已重建` };
      }
      return { values: result.values as BatchResponse['values'] };
    }
    return { error: '脚本未返回有效结果' };
  }

  /** 获取初始化进度（用于 UI 展示） */
  getInitProgress(): { loaded: boolean; message: string } {
    if (this.ready) return { loaded: true, message: 'Pyodide 已就绪' };
    if (this.workers.length > 0) return { loaded: false, message: '正在加载 Python 解释器（~12MB）...' };
    return { loaded: false, message: '正在启动 Worker...' };
  }

  /**
   * 单脚本/单只股票执行，返回每日信号序列。
   *
   * @param scriptCode Python 脚本内容
   * @param data 单只股票 OHLCV（一维数组）
   * @param timeoutMs 超时时间（默认 60 秒）
   * @returns 每日信号数组，长度与输入数据一致
   */
  async executeSingle(
    scriptCode: string,
    data: {
      open: number[];
      high: number[];
      low: number[];
      close: number[];
      volume: number[];
      /** 预计算量比（5日均量比），由回测引擎提供，脚本可直接使用 */
      volRatio5?: number[];
    },
    timeoutMs: number = 60_000,
  ): Promise<(number | null)[]> {
    const worker = this.workers[0];
    if (!this.ready || !worker) {
      throw new Error('Pyodide Worker 未就绪，请先调用 init()');
    }

    const batchId = `single_${this.batchIdCounter++}`;
    const stockData: {
      close: (number | null)[][];
      high: (number | null)[][];
      low: (number | null)[][];
      open: (number | null)[][];
      volume: (number | null)[][];
      volRatio5?: (number | null)[][];
    } = {
      open: [data.open.map((v) => (Number.isFinite(v) ? v : null))],
      high: [data.high.map((v) => (Number.isFinite(v) ? v : null))],
      low: [data.low.map((v) => (Number.isFinite(v) ? v : null))],
      close: [data.close.map((v) => (Number.isFinite(v) ? v : null))],
      volume: [data.volume.map((v) => (Number.isFinite(v) ? v : null))],
    };
    if (data.volRatio5) {
      stockData.volRatio5 = [data.volRatio5.map((v) => (Number.isFinite(v) ? v : null))];
    }

    const result = await this.executeSingleBatch(worker, scriptCode, stockData, batchId, timeoutMs);
    if (result.error) {
      throw new Error(result.error);
    }
    if (!result.values || result.values.length === 0) {
      throw new Error('脚本未返回有效结果');
    }

    const rawVal = result.values[0];
    const daysCount = data.close.length;
    
    // 处理 TypedArray（Pyodide 可能返回 Int32Array/Float64Array 等）
    let jsArray: any[];
    if (rawVal && typeof rawVal === 'object' && 'length' in rawVal && typeof rawVal[Symbol.iterator] === 'function') {
      // TypedArray 或类似数组的对象，转换为普通 Array
      jsArray = Array.from(rawVal);
    } else if (Array.isArray(rawVal)) {
      jsArray = rawVal;
    } else {
      // 兼容旧脚本：返回标量时，视为最后一天的结果，前面补 0
      return new Array(daysCount - 1).fill(0).concat(rawVal === null ? [0] : [rawVal as number]);
    }
    
    // 兼容处理：如果脚本返回长度为1的数组，视为仅最后一天的信号，前面补0
    if (jsArray.length === 1 && daysCount > 1) {
      return new Array(daysCount - 1).fill(0).concat(jsArray);
    }
    
    if (jsArray.length !== daysCount) {
      throw new Error(
        `脚本返回数组长度 ${jsArray.length} 与 K 线数量 ${daysCount} 不一致`,
      );
    }
    return jsArray as (number | null)[];
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
    if (!this.ready || this.workers.length === 0) {
      throw new Error('Pyodide Worker 未就绪，请先调用 init()');
    }

    const results = new Map<string, ScriptResult>();
    const totalScripts = scripts.length;
    const poolSize = this.workers.length;

    for (let si = 0; si < scripts.length; si++) {
      const script = scripts[si];
      const { id, name, code, stockCodes, allOhlcv } = script;

      onProgress?.({
        total: totalScripts,
        done: si,
        status: 'computing',
        message: `正在计算 [${name}]（${stockCodes.length} 只股票）...`,
      });

      // 分批后轮转分发给各 Worker：Worker 之间并行、单个 Worker 内串行
      const stockBatches = this.chunkArray(stockCodes, BATCH_SIZE);
      const allValues = new Map<string, (number | null)[]>();
      const errors: string[] = [];
      let completedBatches = 0;

      const queues: string[][][] = Array.from({ length: poolSize }, () => []);
      stockBatches.forEach((batch, i) => queues[i % poolSize].push(batch));

      await Promise.all(
        this.workers.map((worker, wi) =>
          (async () => {
            for (const batchCodes of queues[wi]) {
              // 每只股票使用自身 K 线长度（不做补齐）：worker 逐只调用 calculate，
              // 前导 null 补齐会按位置从 0 起算的公式（如 ADX 预热 tr[:14]）静默失效。
              const batchData = this.prepareBatchData(batchCodes, allOhlcv);
              const batchId = `batch_${this.batchIdCounter++}`;
              const scriptResult = await this.executeSingleBatch(
                worker,
                code,
                batchData,
                batchId,
                DEFAULT_TIMEOUT,
              );

              // 解析结果：每只股票按其「自身」K 线长度对齐（不再统一补齐）
              if (scriptResult.values) {
                for (let ci = 0; ci < batchCodes.length; ci++) {
                  const stockCode = batchCodes[ci];
                  const daysCount = batchData.close[ci]?.length ?? 0;
                  const rawVal = scriptResult.values[ci];
                  if (rawVal === undefined || rawVal === null) {
                    allValues.set(stockCode, new Array(daysCount).fill(null));
                  } else if (rawVal && typeof rawVal === 'object' && 'length' in rawVal && typeof rawVal[Symbol.iterator] === 'function') {
                    // TypedArray 或类似数组的对象，转换为普通 Array
                    const converted = Array.from(rawVal) as (number | null)[];
                    // 兼容处理：如果脚本返回长度为1的数组，视为仅最后一天的信号，前面补0
                    if (converted.length === 1 && daysCount > 1) {
                      allValues.set(stockCode, new Array(daysCount - 1).fill(0).concat(converted));
                    } else {
                      allValues.set(stockCode, converted);
                    }
                  } else if (Array.isArray(rawVal)) {
                    // 兼容处理：如果脚本返回长度为1的数组，视为仅最后一天的信号，前面补0
                    if (rawVal.length === 1 && daysCount > 1) {
                      allValues.set(stockCode, new Array(daysCount - 1).fill(0).concat(rawVal));
                    } else {
                      allValues.set(stockCode, rawVal as (number | null)[]);
                    }
                  } else {
                    allValues.set(stockCode, new Array(daysCount).fill(rawVal as number));
                  }
                }
              }
              if (scriptResult.error) {
                errors.push(scriptResult.error);
              }

              completedBatches++;
              onProgress?.({
                total: totalScripts,
                done: si,
                status: 'computing',
                message: `[${name}] 已计算 ${completedBatches}/${stockBatches.length} 批（${allValues.size}/${stockCodes.length} 只）`,
              });
            }
          })(),
        ),
      );

      // 存储结果
      results.set(id, { id, name, values: allValues, errors });
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
   * 将 OHLCV 转换为行优先的二维数组，每只股票保持「自身」真实长度（不做补齐）。
   *
   * 注：worker 会逐只调用 calculate，因此无需按批次最大长度对齐；前导 null 补齐
   * 会让按位置从 0 起算的公式（如 ADX 预热 tr[:14] 含 NaN）静默失效、分数偏移。
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
        close.push([]);
        high.push([]);
        low.push([]);
        open.push([]);
        volume.push([]);
        continue;
      }

      const cArr: (number | null)[] = new Array(bars.length);
      const hArr: (number | null)[] = new Array(bars.length);
      const lArr: (number | null)[] = new Array(bars.length);
      const oArr: (number | null)[] = new Array(bars.length);
      const vArr: (number | null)[] = new Array(bars.length);

      for (let di = 0; di < bars.length; di++) {
        const bar = bars[di];
        cArr[di] = bar[OHLCV_CLOSE] ?? null;
        oArr[di] = bar[OHLCV_OPEN] ?? null;
        hArr[di] = bar[OHLCV_HIGH] ?? null;
        lArr[di] = bar[OHLCV_LOW] ?? null;
        vArr[di] = (bar[OHLCV_VOLUME] ?? null) as number | null;
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
    worker: Worker,
    code: string,
    stockData: {
      close: (number | null)[][];
      high: (number | null)[][];
      low: (number | null)[][];
      open: (number | null)[][];
      volume: (number | null)[][];
      volRatio5?: (number | null)[][];
    },
    batchId: string,
    timeoutMs: number,
  ): Promise<BatchResponse> {
    return new Promise<BatchResponse>((resolve, reject) => {
      const timer = setTimeout(() => {
        // 超时 → 终止并重建整个 Worker 池，本轮选股以错误收尾（避免静默丢股票）
        const entry = this.pending.get(batchId);
        if (entry) {
          this.pending.delete(batchId);
          entry.reject(new Error(`脚本执行超时（${timeoutMs}ms），Worker 已重建`));
        }
        this.cleanup();
        this.init().catch(() => {});
      }, timeoutMs);

      this.pending.set(batchId, { resolve, reject, timer });

      worker.postMessage({
        type: 'execute',
        batchId,
        scripts: [{ id: 'single', code, stockData }],
        timeoutMs,
      });
    });
  }

  /** 释放 Worker 池资源（未完成的批次以错误收尾） */
  cleanup(): void {
    this.pending.forEach((entry) => {
      clearTimeout(entry.timer);
      entry.reject(new Error('Worker 已重建'));
    });
    this.pending.clear();

    this.workers.forEach((w) => {
      try {
        w.postMessage({ type: 'terminate' });
      } catch {
        console.warn('[CustomIndicatorRunner] Worker terminate 消息发送失败');
      }
      try {
        w.terminate();
      } catch { /* ignore */ }
    });
    this.workers = [];
    this.ready = false;
    this.initPromise = null;
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