import { describe, it, expect, vi, beforeEach } from 'vitest';
import { StrategyBacktestInput, StrategyBacktestResult } from '../../src/features/strategy-backtest/engine';

describe('Worker Communication Protocol', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('发送 start 消息时 input 格式正确', () => {
    // 模拟 Worker 构造函数
    const mockPostMessage = vi.fn();
    const mockWorker = { postMessage: mockPostMessage, terminate: vi.fn(), onmessage: null };
    vi.stubGlobal('Worker', vi.fn(() => mockWorker));

    // 创建 Worker 实例
    const worker = new Worker(new URL('../../src/features/strategy-backtest/worker.ts', import.meta.url), { type: 'module' });
    
    // 发送 start 消息
    worker.postMessage({
      type: 'start',
      input: {
        filterTree: { type: 'and', children: [] },
        config: {
          maxPositions: 5,
          singleStockMaxPct: 0.2,
          dailyLossLimitEnabled: false,
          dailyLossLimitPct: -0.05,
          maxDrawdownStopEnabled: false,
          maxDrawdownStopPct: -0.2,
          stopLossEnabled: false,
          stopLossPct: -0.1,
          takeProfitEnabled: false,
          takeProfitPct: 0.2,
          maxHoldDays: 60,
          slippage: 0.001,
          feeRate: 0.0003,
          minCommission: 5,
          rebalanceFrequency: 20,
        },
        startDate: '2025-01-02',
        endDate: '2025-06-30',
        allOhlcv: new Map(),
        snapshots: new Map(),
      } as StrategyBacktestInput,
    });

    // 验证消息格式
    expect(mockPostMessage).toHaveBeenCalledTimes(1);
    const sentMessage = mockPostMessage.mock.calls[0][0];
    expect(sentMessage).toHaveProperty('type', 'start');
    expect(sentMessage).toHaveProperty('input');
    expect(sentMessage.input).toHaveProperty('filterTree');
    expect(sentMessage.input).toHaveProperty('config');
    expect(sentMessage.input).toHaveProperty('startDate');
    expect(sentMessage.input).toHaveProperty('endDate');
  });

  it('接收 result 消息时格式正确', async () => {
    const mockWorker = { postMessage: vi.fn(), terminate: vi.fn() };
    let onmessageHandler: ((event: MessageEvent) => void) | null = null;
    const mockWorkerWithOnmessage = {
      ...mockWorker,
      set onmessage(handler: any) { onmessageHandler = handler; },
      get onmessage() { return onmessageHandler; },
    };
    vi.stubGlobal('Worker', vi.fn(() => mockWorkerWithOnmessage));

    // 模拟 Worker 发送 result 消息
    const resultPromise = new Promise<void>((resolve) => {
      setTimeout(() => {
        if (onmessageHandler) {
          onmessageHandler({
            data: {
              type: 'result',
              data: {
                totalReturn: 0.15,
                annualizedReturn: 0.25,
                maxDrawdown: -0.08,
                sharpeRatio: 1.5,
                winRate: 0.6,
                totalTrades: 20,
                totalBuyTrades: 10,
                totalSellTrades: 10,
                equityCurve: [{ date: '2025-01-02', strategy: 100000, benchmark: 100000 }],
                tradeLog: [],
                holdings: [],
                warnings: [],
                benchmarkTotalReturn: 0.05,
                alpha: 0.1,
                beta: 0.8,
                informationRatio: 0.5,
                calmarRatio: 1.2,
                annualizedVolatility: 0.15,
                benchmarkAnnualizedReturn: 0.1,
                benchmarkMaxDrawdown: -0.05,
                benchmarkAnnualizedVolatility: 0.12,
              } as StrategyBacktestResult,
            },
          } as MessageEvent);
        }
        resolve();
      }, 10);
    });

    const worker = new Worker('', { type: 'module' });
    
    worker.onmessage = (event: MessageEvent) => {
      const { type, data } = event.data;
      expect(type).toBe('result');
      expect(data).toHaveProperty('totalReturn');
      expect(data).toHaveProperty('annualizedReturn');
      expect(data).toHaveProperty('maxDrawdown');
      expect(data).toHaveProperty('sharpeRatio');
      expect(data).toHaveProperty('tradeLog');
      expect(data).toHaveProperty('equityCurve');
      expect(data).toHaveProperty('warnings');
    };

    await resultPromise;
  });

  it('接收 error 消息时格式正确', async () => {
    let onmessageHandler: ((event: MessageEvent) => void) | null = null;
    const mockWorker = {
      postMessage: vi.fn(),
      terminate: vi.fn(),
      set onmessage(handler: any) { onmessageHandler = handler; },
      get onmessage() { return onmessageHandler; },
    };
    vi.stubGlobal('Worker', vi.fn(() => mockWorker));

    const errorPromise = new Promise<void>((resolve) => {
      setTimeout(() => {
        if (onmessageHandler) {
          onmessageHandler({
            data: { type: 'error', data: { message: '测试错误信息' } },
          } as MessageEvent);
        }
        resolve();
      }, 10);
    });

    const worker = new Worker('', { type: 'module' });
    worker.onmessage = (event: MessageEvent) => {
      const { type, data } = event.data;
      expect(type).toBe('error');
      expect(data).toHaveProperty('message');
    };

    await errorPromise;
  });

  it('取消回测时 Worker 被正确终止', () => {
    const mockTerminate = vi.fn();
    const mockWorker = { postMessage: vi.fn(), terminate: mockTerminate };
    vi.stubGlobal('Worker', vi.fn(() => mockWorker));

    const worker = new Worker('', { type: 'module' });
    worker.terminate();
    expect(mockTerminate).toHaveBeenCalledTimes(1);
  });
});