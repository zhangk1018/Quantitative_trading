// tests/functions/buildFxRateMap.test.ts
// T6 跨市场回测：buildFxRateMap 汇率折算表单测
// 覆盖：cn 不折算 / 港美股按月锚点拉取并 forward-fill / 失败沿用前一有效值 / 全区间覆盖 / 中止传播

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildFxRateMap } from '../../src/features/strategy-backtest/utils/dataLoader';

/** 模拟后端 AS-OF 汇率：按日期返回当日及之前最近有效汇率（这里简化为固定分段）。 */
function mockFxFetch(anchorRates: Array<{ date: string; rate: number }>, abortSignal?: AbortSignal) {
  return vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    if (abortSignal?.aborted) {
      const e = new Error('The operation was aborted.');
      e.name = 'AbortError';
      throw e;
    }
    const s = String(url);
    const pairMatch = s.match(/pair=([^&]+)/);
    const dateMatch = s.match(/date=([^&]+)/);
    const pair = pairMatch ? decodeURIComponent(pairMatch[1]) : '';
    const date = dateMatch ? decodeURIComponent(dateMatch[1]) : '';

    if (!/CNY=X$/.test(pair)) {
      return { ok: true, json: async () => ({ rate: 1 }) } as unknown as Response;
    }
    // 返回 ≤ date 的最近锚点汇率（AS-OF 语义）
    let rate = 1;
    for (const a of anchorRates) {
      if (a.date <= date) rate = a.rate;
      else break;
    }
    return {
      ok: true,
      json: async () => ({ pair, date, rate, base_currency: 'CNY' }),
    } as unknown as Response;
  });
}

describe('buildFxRateMap', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('cn 市场返回 undefined（无折算，保证 A股无回归）', async () => {
    await expect(buildFxRateMap('cn', ['2026-01-05'], undefined)).resolves.toBeUndefined();
  });

  it('无交易日历返回 undefined', async () => {
    await expect(buildFxRateMap('hk', [], undefined)).resolves.toBeUndefined();
  });

  it('港股按月锚点拉取 AS-OF 汇率并 forward-fill 覆盖全部交易日', async () => {
    const anchorRates = [
      { date: '2026-01-05', rate: 0.857 },
      { date: '2026-02-03', rate: 0.860 },
    ];
    const mock = mockFxFetch(anchorRates);
    globalThis.fetch = mock as unknown as typeof fetch;

    const tradeDates = ['2026-01-05', '2026-01-06', '2026-02-03', '2026-02-04'];
    const map = await buildFxRateMap('hk', tradeDates, undefined);

    expect(map).toEqual({
      '2026-01-05': 0.857,
      '2026-01-06': 0.857,
      '2026-02-03': 0.860,
      '2026-02-04': 0.860,
    });
    // 锚点 = 每月首个交易日，注意应请求 2 次（2 个月份）
    expect(mock).toHaveBeenCalledTimes(2);
    expect(mock.mock.calls[0][0]).toContain('pair=HKDCNY');
    expect(mock.mock.calls[0][0]).toContain('date=2026-01-05');
  });

  it('美股使用 USDCNY=X 对', async () => {
    const mock = mockFxFetch([{ date: '2026-03-02', rate: 7.15 }]);
    globalThis.fetch = mock as unknown as typeof fetch;
    const map = await buildFxRateMap('us', ['2026-03-02'], undefined);
    expect(map?.['2026-03-02']).toBe(7.15);
    expect(mock.mock.calls[0][0]).toContain('pair=USDCNY');
  });

  it('请求失败时沿用前一有效汇率，不阻断回测', async () => {
    let call = 0;
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      call++;
      const date = String(url).match(/date=([^&]+)/)?.[1] ?? '';
      if (date === '2026-02-03') {
        // 2 月锚点请求失败（网络异常）
        throw new Error('network down');
      }
      return {
        ok: true,
        json: async () => ({ rate: date === '2026-01-05' ? 0.857 : 1, base_currency: 'CNY' }),
      } as unknown as Response;
    });

    const map = await buildFxRateMap('hk', ['2026-01-05', '2026-01-06', '2026-02-03', '2026-02-04'], undefined);
    // 2 月锚点失败 → 沿用 1 月 0.857
    expect(map?.['2026-02-04']).toBe(0.857);
  });

  it('中止信号时抛出异常', async () => {
    const controller = new AbortController();
    controller.abort();
    globalThis.fetch = mockFxFetch([{ date: '2026-01-05', rate: 0.857 }], controller.signal) as unknown as typeof fetch;
    await expect(
      buildFxRateMap('hk', ['2026-01-05'], controller.signal),
    ).rejects.toThrow();
  });
});