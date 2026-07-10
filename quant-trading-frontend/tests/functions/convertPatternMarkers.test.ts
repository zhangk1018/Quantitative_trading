/**
 * convertPatternMarkersToEvents 单元测试
 *
 * 覆盖：
 * - 5 种形态到 ConditionEvent 的完整转换
 * - 仅转换用户选中的 pattern 条件
 * - 忽略 candle 集合之外的日期
 * - 空输入边界
 */
import { describe, it, expect } from 'vitest';
import { convertPatternMarkersToEvents, PATTERN_MARKER_VISUAL_MAP } from '@/features/stock-picker/components/StockAnalysisModal';
import type { ConditionConfig, ConditionEvent } from '@/lib/indicators/condition-detector';
import type { PatternMarker } from '@/features/stock-detail/api';

// ==================== 工厂函数 ====================
function makeConfig(fieldKey: string, lookbackDays?: number): ConditionConfig {
  return { fieldKey, lookbackDays };
}

/** 构建日常 candle 列表（简化，仅含 time 字段） */
function makeCandles(dates: string[]): { time: string }[] {
  return dates.map(d => ({ time: d }));
}

// ==================== PATTERN_MARKER_VISUAL_MAP ====================
describe('PATTERN_MARKER_VISUAL_MAP (5 种形态配置完整性)', () => {
  const expectedKeys = ['hammer', 'morning_star', 'evening_star', 'bullish_engulfing', 'bearish_engulfing'];

  it('包含全部 5 种形态', () => {
    expect(Object.keys(PATTERN_MARKER_VISUAL_MAP).sort()).toEqual(expectedKeys.sort());
  });

  it('各形态均包含 label/color/shape/direction', () => {
    for (const key of expectedKeys) {
      const entry = PATTERN_MARKER_VISUAL_MAP[key];
      expect(entry).toBeDefined();
      expect(typeof entry.label).toBe('string');
      expect(typeof entry.color).toBe('string');
      expect(['arrowUp', 'arrowDown', 'circle', 'square']).toContain(entry.shape);
      expect(['buy', 'sell', 'neutral']).toContain(entry.direction);
    }
  });

  it('看涨形态 direction 均为 buy', () => {
    expect(PATTERN_MARKER_VISUAL_MAP.hammer.direction).toBe('buy');
    expect(PATTERN_MARKER_VISUAL_MAP.morning_star.direction).toBe('buy');
    expect(PATTERN_MARKER_VISUAL_MAP.bullish_engulfing.direction).toBe('buy');
  });

  it('看跌形态 direction 均为 sell', () => {
    expect(PATTERN_MARKER_VISUAL_MAP.evening_star.direction).toBe('sell');
    expect(PATTERN_MARKER_VISUAL_MAP.bearish_engulfing.direction).toBe('sell');
  });
});

// ==================== convertPatternMarkersToEvents ====================
describe('convertPatternMarkersToEvents', () => {
  const candles = makeCandles(['2026-07-01', '2026-07-02', '2026-07-03', '2026-07-06']);

  it('单个日期单种形态', () => {
    const markers: PatternMarker[] = [{ trade_date: '2026-07-03', patterns: ['hammer'] }];
    const configs = [makeConfig('pattern_hammer')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      time: '2026-07-03',
      label: '锤子线',
      fieldKey: 'pattern_hammer',
      direction: 'buy',
    });
    expect(['arrowUp', 'arrowDown', 'circle', 'square']).toContain(result[0].shape);
  });

  it('单个日期多种形态', () => {
    const markers: PatternMarker[] = [{
      trade_date: '2026-07-06',
      patterns: ['morning_star', 'bullish_engulfing'],
    }];
    const configs = [makeConfig('pattern_morning_star'), makeConfig('pattern_bullish_engulfing')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(2);
    expect(result.map(e => e.fieldKey).sort()).toEqual(['pattern_bullish_engulfing', 'pattern_morning_star']);
  });

  it('多个日期各一种形态', () => {
    const markers: PatternMarker[] = [
      { trade_date: '2026-07-02', patterns: ['hammer'] },
      { trade_date: '2026-07-03', patterns: ['evening_star'] },
    ];
    const configs = [makeConfig('pattern_hammer'), makeConfig('pattern_evening_star')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(2);
    expect(result[0].time).toBe('2026-07-02');
    expect(result[1].time).toBe('2026-07-03');
  });

  it('仅转换用户选中的 pattern 条件，忽略未选中的', () => {
    const markers: PatternMarker[] = [{ trade_date: '2026-07-03', patterns: ['hammer', 'bullish_engulfing'] }];
    // 用户只选中了 hammer
    const configs = [makeConfig('pattern_hammer')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(1);
    expect(result[0].fieldKey).toBe('pattern_hammer');
  });

  it('跳过 candle 集合之外的日期', () => {
    const markers: PatternMarker[] = [
      { trade_date: '2026-06-30', patterns: ['hammer'] },  // 不在 candle 中
      { trade_date: '2026-07-03', patterns: ['evening_star'] },
    ];
    const configs = [makeConfig('pattern_hammer'), makeConfig('pattern_evening_star')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(1);
    expect(result[0].fieldKey).toBe('pattern_evening_star');
  });

  it('不选中任何 pattern 时返回空数组', () => {
    const markers: PatternMarker[] = [{ trade_date: '2026-07-03', patterns: ['hammer'] }];
    // 用户选中了非 pattern 条件（如 RSI），无 pattern 配置
    const configs = [makeConfig('rsi_oversold')];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toEqual([]);
  });

  it('空 markers 返回空数组', () => {
    const configs = [makeConfig('pattern_hammer')];
    expect(convertPatternMarkersToEvents([], configs, candles)).toEqual([]);
  });

  it('空 candles 返回空数组', () => {
    const markers: PatternMarker[] = [{ trade_date: '2026-07-03', patterns: ['hammer'] }];
    expect(convertPatternMarkersToEvents(markers, [makeConfig('pattern_hammer')], [])).toEqual([]);
  });

  it('空 configs 返回空数组', () => {
    const markers: PatternMarker[] = [{ trade_date: '2026-07-03', patterns: ['hammer'] }];
    expect(convertPatternMarkersToEvents(markers, [], candles)).toEqual([]);
  });

  it('markers 和 configs 均为空返回空数组', () => {
    expect(convertPatternMarkersToEvents([], [], candles)).toEqual([]);
  });

  it('全 5 种形态同时转换', () => {
    const markers: PatternMarker[] = [{
      trade_date: '2026-07-06',
      patterns: ['hammer', 'morning_star', 'evening_star', 'bullish_engulfing', 'bearish_engulfing'],
    }];
    const configs = [
      makeConfig('pattern_hammer'),
      makeConfig('pattern_morning_star'),
      makeConfig('pattern_evening_star'),
      makeConfig('pattern_bullish_engulfing'),
      makeConfig('pattern_bearish_engulfing'),
    ];
    const result = convertPatternMarkersToEvents(markers, configs, candles);

    expect(result).toHaveLength(5);
    const fieldKeys = result.map(e => e.fieldKey).sort();
    expect(fieldKeys).toEqual([
      'pattern_bearish_engulfing',
      'pattern_bullish_engulfing',
      'pattern_evening_star',
      'pattern_hammer',
      'pattern_morning_star',
    ]);
    // 每个事件的 direction 都符合预期
    const buyKeys = result.filter(e => e.direction === 'buy').map(e => e.fieldKey).sort();
    expect(buyKeys).toEqual(['pattern_bullish_engulfing', 'pattern_hammer', 'pattern_morning_star']);
    const sellKeys = result.filter(e => e.direction === 'sell').map(e => e.fieldKey).sort();
    expect(sellKeys).toEqual(['pattern_bearish_engulfing', 'pattern_evening_star']);
  });
});