// customIndicatorRunner.test.ts — 自编指标执行器单元测试
// 覆盖 K 2026-10-09：runner 不再按批次最大长度做前导 null 补齐，
// 每只股票保持自身 K 线长度（前导 null 会让 ADX 预热 tr[:14] 等位置敏感公式静默失效）。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { CustomIndicatorRunner } from '@/features/strategy-backtest/utils/customIndicatorRunner';

/** 假 Worker：ready 后，把每只股票输入数组的长度作为该股票的返回值回传 */
class FakeWorker {
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onerror: ((e: { message: string }) => void) | null = null;

  constructor(_url: string, _opts?: unknown) {
    setTimeout(() => this.onmessage?.({ data: { type: 'ready' } }), 0);
  }

  postMessage(msg: {
    type: string;
    batchId: string;
    scripts: { id: string; stockData: { close: unknown[] } }[];
  }): void {
    if (msg?.type === 'execute') {
      const stockData = msg.scripts[0].stockData;
      const values = stockData.close.map((arr) => (arr as unknown[]).length);
      setTimeout(() => {
        this.onmessage?.({
          data: { type: 'result', batchId: msg.batchId, results: [{ id: 'single', values, error: null }] },
        });
      }, 0);
    }
  }

  terminate(): void {}
}

function makeBars(n: number): number[][] {
  return Array.from({ length: n }, (_, i) => [1700000000 + i * 86400, 10, 11, 9, 10.5, 1000]);
}

describe('CustomIndicatorRunner — 不补齐 K 线长度', () => {
  beforeEach(() => {
    vi.stubGlobal('Worker', FakeWorker as unknown as typeof Worker);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('每只股票保持自身长度，短历史股票不被补齐到批次最大长度', async () => {
    const runner = new CustomIndicatorRunner();
    await runner.init();

    const allOhlcv = new Map<string, number[][]>([
      ['AAA', makeBars(120)],
      ['BBB', makeBars(80)],
    ]);

    const result = await runner.execute([
      { id: 's1', name: 'S', code: 'x', stockCodes: ['AAA', 'BBB'], allOhlcv },
    ]);

    const scriptResult = result.get('s1');
    expect(scriptResult).toBeDefined();
    // 若仍做前导补齐，BBB 的输入会被拉到 120 → 这里会是 120
    expect(scriptResult!.values.get('AAA')?.length).toBe(120);
    expect(scriptResult!.values.get('BBB')?.length).toBe(80);
  });
});