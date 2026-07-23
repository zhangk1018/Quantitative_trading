// hooks/useBacktestWorker.ts — 回测 Worker 生命周期管理 Hook
// 封装 Worker 创建/消息分发/取消/清理，修复 isMounted 竞态

import { useRef, useCallback, useEffect, useState } from 'react';
import type { BacktestInput, BacktestOutput, ProgressInfo } from '../backtestTypes';

interface UseBacktestWorkerOptions {
  onProgress?: (info: ProgressInfo) => void;
  onResult?: (output: BacktestOutput) => void;
  onError?: (message: string) => void;
}

interface UseBacktestWorkerReturn {
  start: (input: BacktestInput) => void;
  cancel: () => void;
  isRunning: boolean;
}

export function useBacktestWorker(options: UseBacktestWorkerOptions): UseBacktestWorkerReturn {
  const { onProgress, onResult, onError } = options;

  const workerRef = useRef<Worker | null>(null);
  const runIdRef = useRef(0);
  const isMountedRef = useRef(true);
  const [isRunning, setIsRunning] = useState(false);

  // 组件卸载时标记为未挂载，并终止 Worker
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  /** 取消当前回测 */
  const cancel = useCallback(() => {
    runIdRef.current += 1;
    setIsRunning(false);
    workerRef.current?.terminate();
    workerRef.current = null;
  }, []);

  /** 启动回测 Worker */
  const start = useCallback((input: BacktestInput) => {
    // 终止旧 Worker 并递增 runId（使旧回调失效）
    workerRef.current?.terminate();
    workerRef.current = null;
    runIdRef.current += 1;
    const currentRunId = runIdRef.current;
    setIsRunning(true);

    let worker: Worker;
    try {
      worker = new Worker(
        new URL('../backtest.worker.ts', import.meta.url),
        { type: 'module' },
      );
    } catch (err) {
      setIsRunning(false);
      const msg = err instanceof Error ? err.message : String(err);
      onError?.(`Worker 创建失败: ${msg}`);
      return;
    }
    workerRef.current = worker;

    worker.onmessage = (e: MessageEvent) => {
      // 组件已卸载或回测已取消
      if (!isMountedRef.current || runIdRef.current !== currentRunId) {
        worker.terminate();
        return;
      }

      const { type, data } = e.data;

      if (type === 'progress') {
        onProgress?.(data as ProgressInfo);
      } else if (type === 'result') {
        setIsRunning(false);
        onResult?.(data as BacktestOutput);
        worker.terminate();
      } else if (type === 'error') {
        setIsRunning(false);
        onError?.((data as string) || '未知 Worker 错误');
        worker.terminate();
      }
    };

    worker.onerror = () => {
      if (!isMountedRef.current || runIdRef.current !== currentRunId) {
        worker.terminate();
        return;
      }
      setIsRunning(false);
      onError?.('Worker 异常崩溃');
      worker.terminate();
    };

    worker.postMessage({ type: 'run', input });
  }, [onProgress, onResult, onError]);

  return { start, cancel, isRunning };
}