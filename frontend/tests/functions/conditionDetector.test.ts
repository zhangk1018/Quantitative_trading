import { describe, expect, it } from 'vitest';
import { detectConditions } from '@/lib/indicators/condition-detector';
import type { KlineBar } from '@/lib/indicators/indicators';

function makeBar(index: number, overrides: Partial<KlineBar> = {}): KlineBar {
  const day = String(index + 1).padStart(2, '0');
  return {
    time: `2026-07-${day}`,
    open: 10,
    high: 11,
    low: 9,
    close: 10,
    volume: 100,
    ...overrides,
  };
}

describe('detectConditions 后端口径对齐（纯前端计算）', () => {
  it('放量突破：volume / 5日均量 >= 1.5 即命中', () => {
    // 前 4 天 volume=100, 第 5 天 volume=180, 5日均量=116, 量比=180/116≈1.55 >= 1.5
    const bars = [
      makeBar(0, { volume: 100 }),
      makeBar(1, { volume: 100 }),
      makeBar(2, { volume: 100 }),
      makeBar(3, { volume: 100 }),
      makeBar(4, { volume: 180 }),
    ];

    const result = detectConditions(bars, [{ fieldKey: 'volume_breakout' }]);

    expect(result.events).toHaveLength(1);
    expect(result.events[0]).toMatchObject({
      time: '2026-07-05',
      fieldKey: 'volume_breakout',
    });
  });

  it('连续上涨：收盘价连续 >= 3 天高于前一天即命中', () => {
    const bars = [
      makeBar(0, { close: 10 }),
      makeBar(1, { close: 11 }),
      makeBar(2, { close: 12 }),
      makeBar(3, { close: 13 }),
      makeBar(4, { close: 12 }),
    ];

    const result = detectConditions(bars, [{ fieldKey: 'consecutive_up' }]);

    // streak=3 时在 bars[3]（第4天）产生第一个事件，streak=4 继续产生第二个事件
    // 趋势在第5天中断（close=12 < close=13）
    expect(result.events.map(e => e.time)).toEqual(['2026-07-04']);
    expect(result.events.map(e => e.value)).toEqual(['连涨3天']);
  });
});