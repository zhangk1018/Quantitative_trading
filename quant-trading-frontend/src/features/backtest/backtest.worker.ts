// backtest.worker.ts — Web Worker 计算线程
// 接收 BacktestInput，执行回测引擎，返回 BacktestOutput + 进度回调

import { runBacktest } from './backtestEngine';
import type { BacktestInput, BacktestOutput, ProgressInfo } from './backtestTypes';

// Worker 消息类型
interface WorkerRequest {
  type: 'run';
  input: BacktestInput;
}

interface WorkerResponse {
  type: 'progress' | 'result' | 'error';
  data: ProgressInfo | BacktestOutput | string;
}

const ctx: Worker = self as any;

/**
 * 校验日期字符串/时间戳是否有效。
 * 支持 ISO 日期字符串、YYYY-MM-DD 格式或数字时间戳。
 */
export function isValidTime(value: unknown): boolean {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value > 0;
  }
  if (typeof value !== 'string') return false;
  const str = value.trim();
  if (str.length === 0) return false;
  const ts = Date.parse(str);
  return !Number.isNaN(ts);
}

/**
 * 校验回测输入数据，防止非法数据进入引擎。
 * 失败时返回可读错误信息，成功返回 null。
 */
export function validateBacktestInput(input: unknown): string | null {
  if (!input || typeof input !== 'object') {
    return '回测输入格式错误：expected object';
  }

  const { bars, buyCondition, config } = input as Partial<BacktestInput>;

  if (!Array.isArray(bars) || bars.length === 0) {
    return 'K 线数据为空或格式错误';
  }

  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    if (!bar || typeof bar !== 'object') {
      return `第 ${i} 根 K 线格式错误`;
    }
    const fields: Array<keyof typeof bar> = ['time', 'open', 'high', 'low', 'close', 'volume'];
    for (const field of fields) {
      if (!(field in bar)) {
        return `第 ${i} 根 K 线缺少字段 ${String(field)}`;
      }
    }
    if (!isValidTime(bar.time)) {
      return `第 ${i} 根 K 线 time 字段不是有效日期`;
    }
    if (
      typeof bar.open !== 'number' ||
      typeof bar.high !== 'number' ||
      typeof bar.low !== 'number' ||
      typeof bar.close !== 'number' ||
      typeof bar.volume !== 'number'
    ) {
      return `第 ${i} 根 K 线价格/成交量类型错误`;
    }
  }

  if (!buyCondition || typeof buyCondition !== 'object') {
    return '买入条件格式错误';
  }
  if (!buyCondition.indicatorId || typeof buyCondition.indicatorId !== 'string') {
    return '买入条件缺少有效的自编指标 ID';
  }
  if (!buyCondition.formula || typeof buyCondition.formula !== 'string') {
    return '买入条件缺少有效的自编指标公式';
  }

  if (!config || typeof config !== 'object') {
    return '回测配置为空';
  }
  const requiredConfigFields: Array<keyof typeof config> = [
    'stockCode',
    'capital',
    'feeRate',
    'slippage',
    'riskFreeRate',
    'executionPrice',
    'maxDeferDays',
    'indicatorParams',
  ];
  for (const field of requiredConfigFields) {
    if (!(field in config)) {
      return `回测配置缺少字段 ${String(field)}`;
    }
  }

  return null;
}

ctx.onmessage = async (e: MessageEvent<WorkerRequest>) => {
  const { type, input } = e.data;

  if (type !== 'run') return;

  try {
    const validationError = validateBacktestInput(input);
    if (validationError) {
      ctx.postMessage({ type: 'error', data: validationError } as WorkerResponse);
      return;
    }

    // 进度回调：将引擎内部进度透传给主线程
    const onProgress = (info: ProgressInfo) => {
      ctx.postMessage({ type: 'progress', data: info } as WorkerResponse);
    };

    // 执行回测（引擎内部会调用 onProgress）
    const result: BacktestOutput = await runBacktest(input as BacktestInput, onProgress);

    // 发送最终结果
    ctx.postMessage({ type: 'result', data: result } as WorkerResponse);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    ctx.postMessage({ type: 'error', data: errorMsg } as WorkerResponse);
  }
};