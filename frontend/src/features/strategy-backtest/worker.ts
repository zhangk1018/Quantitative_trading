// src/features/strategy-backtest/worker.ts
// Web Worker 封装 | 在后台线程运行策略回测引擎
// 迁移自 features/backtest/strategyBacktest.worker.ts

import { runStrategyBacktest } from './engine';
import type { StrategyBacktestInput, ProgressInfo } from './engine';
import type { StrategyBacktestResult } from './types';

// Worker 消息类型
interface WorkerMessage {
  type: 'start' | 'cancel';
  input?: StrategyBacktestInput;
}

interface WorkerResponse {
  type: 'progress' | 'result' | 'error';
  data?: ProgressInfo | StrategyBacktestResult | string;
}

// 全局取消标志
let cancelRequested = false;

// 监听主线程消息
self.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const { type, input } = event.data;

  if (type === 'cancel') {
    cancelRequested = true;
    return;
  }

  if (type === 'start' && input) {
    cancelRequested = false;

    try {
      // 包装进度回调，转发到主线程
      const onProgress = (info: ProgressInfo) => {
        if (cancelRequested) {
          throw new Error('回测已取消');
        }
        const response: WorkerResponse = {
          type: 'progress',
          data: info,
        };
        self.postMessage(response);
      };

      // 运行回测
      const result = runStrategyBacktest({
        ...input,
        onProgress,
      });

      // 发送结果
      const response: WorkerResponse = {
        type: 'result',
        data: result,
      };
      self.postMessage(response);
    } catch (error) {
      // 发送错误
      const response: WorkerResponse = {
        type: 'error',
        data: error instanceof Error ? error.message : '未知错误',
      };
      self.postMessage(response);
    }
  }
};

// 导出类型供主线程使用
export type StrategyBacktestWorker = Worker;