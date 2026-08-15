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

  it('早晨之星：严格按3K线形态检测', () => {
    /**
     * 构造标准早晨之星（3天）：
     * 第1天（index 1）：大阴线 open=12, close=10, high=12, low=10 → body=2, range=2, body/range=1.0 >= 0.6 ✓
     * 第2天（index 2）：十字星 open=10.5, close=10.5, high=11, low=10 → body=0, range=1, body/range=0 <= 0.1 ✓
     * 第3天（index 3）：大阳线 open=10.5, close=12, high=12, low=10.5 → body=1.5, range=1.5, body/range=1.0 >= 0.6 ✓
     * 穿透率：body1_bottom=10, body1_size=2, 穿透价=10+0.3*2=10.6, close=12 >= 10.6 ✓
     */
    const bars = [
      makeBar(0, { open: 10, close: 10, high: 11, low: 9, volume: 100 }),
      makeBar(1, { open: 12, close: 10, high: 12, low: 10, volume: 100 }),
      makeBar(2, { open: 10.5, close: 10.5, high: 11, low: 10, volume: 100 }),
      makeBar(3, { open: 10.5, close: 12, high: 12, low: 10.5, volume: 100 }),
      makeBar(4, { open: 11, close: 11, high: 11.5, low: 10.5, volume: 100 }),
    ];

    const result = detectConditions(bars, [{ fieldKey: 'pattern_morning_star' }]);

    expect(result.events).toHaveLength(1);
    expect(result.events[0]).toMatchObject({
      time: '2026-07-04', // 第3天（index 3）
      fieldKey: 'pattern_morning_star',
    });
  });

  it('晨星放量：早晨之星与放量突破同日发生', () => {
    /**
     * 前 5 天：volume=100，用于填充 5 日均量计算
     * 第6天（index 5）：大阴线 open=12, close=10, high=12, low=10
     * 第7天（index 6）：十字星 open=10.5, close=10.5, high=11, low=10
     * 第8天（index 7）：大阳线 open=10.5, close=12, high=12, low=10.5, volume=300
     * 第8天 volume=300，5日均量=(100+100+100+100+300)/5=140，量比=300/140=2.14 >= 1.5 ✓
     */
    const fillBars = Array.from({ length: 5 }, (_, i) =>
      makeBar(i, { open: 10, close: 10, high: 11, low: 9, volume: 100 })
    );
    const morningStarBars = [
      makeBar(5, { open: 12, close: 10, high: 12, low: 10, volume: 100 }),
      makeBar(6, { open: 10.5, close: 10.5, high: 11, low: 10, volume: 100 }),
      makeBar(7, { open: 10.5, close: 12, high: 12, low: 10.5, volume: 300 }),
    ];
    const bars = [...fillBars, ...morningStarBars];

    const result = detectConditions(bars, [
      { fieldKey: 'pattern_morning_star' },
      { fieldKey: 'volume_breakout' },
    ]);

    // 应有 2 个事件：早晨之星 + 放量突破
    expect(result.events.length).toBeGreaterThanOrEqual(2);
    const morningStarEvents = result.events.filter(e => e.fieldKey === 'pattern_morning_star');
    const volumeBreakoutEvents = result.events.filter(e => e.fieldKey === 'volume_breakout');
    expect(morningStarEvents.length).toBe(1);
    expect(volumeBreakoutEvents.length).toBe(1);
    // 两个事件应在同一天
    expect(morningStarEvents[0].time).toBe(volumeBreakoutEvents[0].time);
    const day8 = 7 + 1; // index 7 → 第8天
    const dayStr = `2026-07-${String(day8).padStart(2, '0')}`;
    expect(morningStarEvents[0].time).toBe(dayStr);
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