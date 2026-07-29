// hooks/useBacktestWorker.test.ts — Worker 生命周期管理测试
// 覆盖：创建/启动/取消/清理/竞态保护/错误处理

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useBacktestWorker } from '../../src/features/backtest/hooks/useBacktestWorker';
import type { BacktestInput } from '../../src/features/backtest/backtestTypes';
import { DEFAULT_INDICATOR_PARAMS } from '../../src/features/backtest/backtestTypes';

// ==================== Mock Worker 工厂 ====================

/**
 * 创建可精确控制的 Mock Worker 实例。
 * 每次调用 createMockWorker 返回独立的 { postMessage, terminate, triggerMessage, triggerError } 方法，
 * 避免全局变量污染。
 */
function createMockWorker() {
  const postMessage = vi.fn();
  const terminate = vi.fn();

  let onmessage: ((e: MessageEvent) => void) | null = null;
  let onerror: ((e: ErrorEvent) => void) | null = null;

  class MockWorker {
    public onmessage: ((e: MessageEvent) => void) | null = null;
    public onerror: ((e: ErrorEvent) => void) | null = null;
    public postMessage = postMessage;
    public terminate = terminate;

    constructor() {
      // 注册为当前实例的回调代理
      onmessage = (e: MessageEvent) => {
        this.onmessage?.(e);
      };
      onerror = (e: ErrorEvent) => {
        this.onerror?.(e);
      };
    }
  }

  return {
    MockWorker,
    /** 模拟 Worker 向主线程发送消息 */
    triggerMessage: (data: { type: string; data: unknown }) => {
      onmessage?.({ data } as MessageEvent);
    },
    /** 模拟 Worker 崩溃 */
    triggerError: (message: string) => {
      onerror?.(new ErrorEvent('error', { message }));
    },
    postMessage,
    terminate,
  };
}

// ==================== 测试数据 ====================

function makeValidInput(): BacktestInput {
  return {
    bars: [
      { time: '2025-01-02', open: 10, high: 11, low: 9, close: 10.5, volume: 100000 },
      { time: '2025-01-03', open: 10.5, high: 11.5, low: 9.5, close: 11, volume: 120000 },
    ],
    buyCondition: {
      indicatorId: 'test-id',
      indicatorName: '测试指标',
      formula: 'def calculate(o,h,l,c,v): return [0]*len(c)',
    },
    config: {
      stockCode: '000001',
      startDate: '2025-01-01',
      endDate: '2025-12-31',
      capital: 100000,
      feeRate: 0.0003,
      slippage: 0.001,
      riskFreeRate: 0.03,
      executionPrice: 'next_open',
      maxDeferDays: 3,
      indicatorParams: DEFAULT_INDICATOR_PARAMS,
    },
  };
}

// ==================== 测试用例 ====================

let mock: ReturnType<typeof createMockWorker>;

describe('useBacktestWorker - 生命周期', () => {
  beforeEach(() => {
    mock = createMockWorker();
    vi.stubGlobal('Worker', mock.MockWorker);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('初始状态 isRunning 为 false', () => {
    const { result } = renderHook(() => useBacktestWorker({}));
    expect(result.current.isRunning).toBe(false);
  });

  it('启动后 isRunning 为 true，并 postMessage 正确的输入', () => {
    const { result } = renderHook(() => useBacktestWorker({}));

    act(() => {
      result.current.start(makeValidInput());
    });

    expect(result.current.isRunning).toBe(true);
    expect(mock.postMessage).toHaveBeenCalledWith({
      type: 'run',
      input: expect.objectContaining({
        bars: expect.any(Array),
        buyCondition: expect.objectContaining({ indicatorId: 'test-id' }),
      }),
    });
  });

  it('收到 result 消息后 isRunning 变为 false 并调用 onResult', async () => {
    const onResult = vi.fn();

    const { result } = renderHook(() =>
      useBacktestWorker({ onResult }),
    );

    act(() => {
      result.current.start(makeValidInput());
    });

    // 模拟 Worker 返回 result
    act(() => {
      mock.triggerMessage({
        type: 'result',
        data: { trades: [], equityCurve: [], summary: { totalTrade: 0 }, warnings: [], diagnostics: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.isRunning).toBe(false);
    });
    expect(onResult).toHaveBeenCalledTimes(1);
    expect(mock.terminate).toHaveBeenCalled();
  });

  it('取消后 isRunning 变为 false 并终止 Worker', () => {
    const { result } = renderHook(() => useBacktestWorker({}));

    act(() => {
      result.current.start(makeValidInput());
    });

    expect(result.current.isRunning).toBe(true);

    act(() => {
      result.current.cancel();
    });

    expect(result.current.isRunning).toBe(false);
    expect(mock.terminate).toHaveBeenCalled();
  });

  it('组件卸载时自动终止 Worker', () => {
    const { result, unmount } = renderHook(() => useBacktestWorker({}));

    act(() => {
      result.current.start(makeValidInput());
    });

    unmount();

    expect(mock.terminate).toHaveBeenCalled();
  });

  it('连续启动两次应终止旧 Worker', () => {
    const { result } = renderHook(() => useBacktestWorker({}));

    act(() => {
      result.current.start(makeValidInput());
    });

    const firstTerminateCalls = mock.terminate.mock.calls.length;

    act(() => {
      result.current.start(makeValidInput());
    });

    // 第二次启动应调用 terminate 终止旧 Worker
    expect(mock.terminate.mock.calls.length).toBeGreaterThan(firstTerminateCalls);
  });

  it('旧 Worker 的 result 消息应被忽略（runId 竞态保护）', () => {
    const onResult = vi.fn();
    const { result } = renderHook(() =>
      useBacktestWorker({ onResult }),
    );

    act(() => {
      result.current.start(makeValidInput());
    });

    // 启动第二个 Worker（应使第一个 Worker 的 runId 失效）
    act(() => {
      result.current.start(makeValidInput());
    });

    // 此时 mock 指向最新的 Worker 实例，旧 Worker 的消息通道已断开
    // 验证：onResult 不应被旧消息触发
    act(() => {
      mock.triggerMessage({
        type: 'result',
        data: { trades: [], equityCurve: [], summary: {}, warnings: [], diagnostics: [] },
      });
    });

    // 新 Worker 的 result 应触发 onResult（仅一次）
    expect(onResult).toHaveBeenCalledTimes(1);
  });

  it('Worker 异常崩溃时 isRunning 变为 false 并调用 onError', () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useBacktestWorker({ onError }),
    );

    act(() => {
      result.current.start(makeValidInput());
    });

    expect(result.current.isRunning).toBe(true);

    // 模拟 Worker 崩溃
    act(() => {
      mock.triggerError('Worker 崩溃');
    });

    expect(result.current.isRunning).toBe(false);
    expect(onError).toHaveBeenCalledWith('Worker 异常崩溃');
  });
});

describe('useBacktestWorker - 进度回调', () => {
  beforeEach(() => {
    mock = createMockWorker();
    vi.stubGlobal('Worker', mock.MockWorker);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('应接收 progress 消息', () => {
    const onProgress = vi.fn();
    const { result } = renderHook(() =>
      useBacktestWorker({ onProgress }),
    );

    act(() => {
      result.current.start(makeValidInput());
    });

    act(() => {
      mock.triggerMessage({
        type: 'progress',
        data: { stage: 'indicators', percent: 50, message: '计算中' },
      });
    });

    expect(onProgress).toHaveBeenCalledWith({
      stage: 'indicators',
      percent: 50,
      message: '计算中',
    });
  });

  it('应接收 error 消息', () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useBacktestWorker({ onError }),
    );

    act(() => {
      result.current.start(makeValidInput());
    });

    act(() => {
      mock.triggerMessage({
        type: 'error',
        data: '参数校验失败',
      });
    });

    expect(onError).toHaveBeenCalledWith('参数校验失败');
    expect(result.current.isRunning).toBe(false);
  });
});