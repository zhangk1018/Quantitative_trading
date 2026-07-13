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

ctx.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const { type, input } = e.data;

  if (type !== 'run') return;

  try {
    // 进度回调：将引擎内部进度透传给主线程
    const onProgress = (info: ProgressInfo) => {
      ctx.postMessage({ type: 'progress', data: info } as WorkerResponse);
    };

    // 执行回测（引擎内部会调用 onProgress）
    const result: BacktestOutput = runBacktest(input, onProgress);

    // 发送最终结果
    ctx.postMessage({ type: 'result', data: result } as WorkerResponse);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    ctx.postMessage({ type: 'error', data: errorMsg } as WorkerResponse);
  }
};