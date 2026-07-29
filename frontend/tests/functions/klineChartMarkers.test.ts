import { describe, expect, it } from 'vitest';
import { buildSortedSeriesMarkers } from '@/features/stock-picker/components/KLineChart';
import type { ConditionEvent } from '@/lib/indicators/condition-detector';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function makeEvent(time: string, label: string): ConditionEvent {
  return {
    time,
    label,
    fieldKey: `pattern_${label}`,
    color: '#26A69A',
    shape: 'arrowUp',
    direction: 'buy',
  };
}

describe('buildSortedSeriesMarkers', () => {
  it('将乱序 ConditionEvent 转为按 time 升序排列的 lightweight marker', () => {
    const result = buildSortedSeriesMarkers([
      makeEvent('2026-07-08', 'late'),
      makeEvent('2026-07-01', 'early'),
      makeEvent('2026-07-07', 'middle'),
    ]);

    expect(result.map((marker) => marker.time)).toEqual([
      '2026-07-01',
      '2026-07-07',
      '2026-07-08',
    ]);
  });

  it('KLineChart 初始化和更新两条路径均使用排序后的 marker', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/features/stock-picker/components/KLineChart.tsx'),
      'utf-8'
    );
    const usages = source.match(/candle\.setMarkers\(buildSortedSeriesMarkers\(markers\)\)/g) ?? [];

    expect(usages).toHaveLength(2);
  });
});
