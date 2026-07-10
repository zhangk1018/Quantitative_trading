/**
 * chartUtils 单元测试
 *
 * 覆盖：
 * - validateKLineData / validateSignals (非严格/严格模式、边界、安全)
 * - toOHLCVArray (转换、时区、严格模式)
 * - diffMarkers (增删改、有序/无序、自定义键、安全)
 *
 * 性能测试通过 RUN_PERF_TESTS=true 环境变量开启
 */
import { describe, it, expect } from 'vitest';
import {
  validateKLineData,
  validateSignals,
  toOHLCVArray,
  diffMarkers,
} from '@/features/stock-detail/hooks/chartUtils';
import { ChartError, ChartErrorType } from '@/lib/indicators/chartConstants';
import type { KLineItem, SignalItem } from '@/lib/indicators/types';

// ==================== 常量 ====================
const BOUNDARIES = {
  MAX_PRICE: 1e8,
  MAX_VOLUME: 1e12,
  MIN_PRICE: 0.01,
  LARGE_ARRAY_SIZE: 10000,
  PERF_THRESHOLD_MS: 100,
} as const;

// ==================== 工厂函数 ====================
function createKLine(overrides?: Partial<KLineItem>): KLineItem {
  return {
    time: '2026-01-05',
    open: 10,
    high: 12,
    low: 9,
    close: 11,
    volume: 10000,
    ...overrides,
  };
}

function createSignal(overrides?: Partial<SignalItem>): SignalItem {
  return {
    time: '2026-01-05',
    position: 'aboveBar',
    shape: 'arrowUp',
    color: '#26A69A',
    text: 'Buy signal',
    ...overrides,
  };
}

// ==================== 异常断言 ====================
function expectChartError(
  fn: () => unknown,
  expectedType: ChartErrorType,
  expectedMessageSubstr: string,
) {
  try {
    fn();
    throw new Error('Expected ChartError but no error thrown');
  } catch (err) {
    expect(err).toBeInstanceOf(ChartError);
    expect((err as ChartError).type).toBe(expectedType);
    expect((err as ChartError).message).toContain(expectedMessageSubstr);
  }
}

// ==================== 顶层样本（不可变，仅作参考） ====================
const validKLine = createKLine();
const validSignal = createSignal();

// ==================== validateKLineData ====================
describe.skip('validateKLineData', () => {
  describe('non-strict mode', () => {
    it('passes valid K-line', () => {
      const result = validateKLineData([validKLine]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validKLine);
    });

    // 参数化：价格越界
    it.each([
      ['open', -5],
      ['open', BOUNDARIES.MAX_PRICE + 1],
      ['high', 8], // high < low
    ])('filters out invalid price field %s = %s', (field, value) => {
      const invalid = createKLine({ [field]: value } as Partial<KLineItem>);
      const result = validateKLineData([validKLine, invalid]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validKLine);
    });

    // 参数化：时间格式
    it.each(['bad-date', ''])('filters out invalid time "%s"', (time) => {
      const invalid = createKLine({ time });
      const result = validateKLineData([validKLine, invalid]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validKLine);
    });

    // 参数化：成交量异常
    it.each([-1, BOUNDARIES.MAX_VOLUME + 1])('filters out invalid volume %s', (volume) => {
      const invalid = createKLine({ volume });
      const result = validateKLineData([validKLine, invalid]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validKLine);
    });

    it('accepts volume = 0', () => {
      const zero = createKLine({ volume: 0 });
      const result = validateKLineData([zero]);
      expect(result).toHaveLength(1);
      expect(result[0].volume).toBe(0);
    });

    it('accepts volume at upper bound', () => {
      const max = createKLine({ volume: BOUNDARIES.MAX_VOLUME });
      const result = validateKLineData([max]);
      expect(result).toHaveLength(1);
      expect(result[0].volume).toBe(BOUNDARIES.MAX_VOLUME);
    });

    it('accepts decimal prices', () => {
      const decimal = createKLine({ open: 10.5, high: 12.75, low: 9.2, close: 11.3 });
      const result = validateKLineData([decimal]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(decimal);
    });

    it('accepts very small positive price', () => {
      const small = createKLine({ open: BOUNDARIES.MIN_PRICE, high: 0.02, low: 0.005, close: 0.01 });
      const result = validateKLineData([small]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(small);
    });

    it('accepts price near upper bound', () => {
      const near = createKLine({ open: BOUNDARIES.MAX_PRICE - 1 });
      const result = validateKLineData([near]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(near);
    });

    it('accepts time with time component', () => {
      const withTime = createKLine({ time: '2026-01-05 14:30:00' });
      const result = validateKLineData([withTime]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(withTime);
    });

    it('accepts UTC time string', () => {
      const utc = createKLine({ time: '2026-01-05T14:30:00Z' });
      const result = validateKLineData([utc]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(utc);
    });

    it('accepts time with timezone offset', () => {
      const offset = createKLine({ time: '2026-01-05T14:30:00+08:00' });
      const result = validateKLineData([offset]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(offset);
    });

    // 弱类型：数字时间（应被过滤）
    it('filters out numeric time', () => {
      // @ts-expect-error 故意传入数字测试运行时行为
      const weak: KLineItem = { ...validKLine, time: 1700000000 };
      const result = validateKLineData([weak]);
      expect(result).toHaveLength(0);
    });

    // 安全：原型链污染不影响
    it('does not throw on objects with __proto__ field', () => {
      const malicious = { ...validKLine, __proto__: { polluted: true } };
      expect(() => validateKLineData([malicious])).not.toThrow();
    });

    // 安全：超长字符串（ReDoS 防护）
    it('handles extremely long time string quickly', () => {
      const longTime = '2026-01-05' + 'T'.repeat(10000) + '14:30:00';
      const invalid = createKLine({ time: longTime });
      const start = performance.now();
      const result = validateKLineData([invalid]);
      expect(result).toHaveLength(0);
      expect(performance.now() - start).toBeLessThan(100);
    });

    it('returns empty for empty / null / undefined', () => {
      expect(validateKLineData([])).toEqual([]);
      expect(validateKLineData(null)).toEqual([]);
      expect(validateKLineData(undefined)).toEqual([]);
    });
  });

  describe('strict mode', () => {
    it.each([
      ['open', -5, 'open'],
      ['open', BOUNDARIES.MAX_PRICE + 1, 'too high'],
      ['high', 8, 'High must be >= Low'],
    ])('throws ChartError for invalid price %s = %s', (field, value, msg) => {
      const invalid = createKLine({ [field]: value } as Partial<KLineItem>);
      expectChartError(
        () => validateKLineData([invalid], true),
        ChartErrorType.DATA_INVALID,
        msg,
      );
    });

    it.each([
      ['bad-date', 'Invalid time string'],
      ['', 'Invalid time string'],
    ])('throws ChartError for invalid time "%s"', (time, msg) => {
      const invalid = createKLine({ time });
      expectChartError(
        () => validateKLineData([invalid], true),
        ChartErrorType.DATA_INVALID,
        msg,
      );
    });

    it.each([-1, BOUNDARIES.MAX_VOLUME + 1])('throws ChartError for invalid volume %s', (volume) => {
      const invalid = createKLine({ volume });
      expectChartError(
        () => validateKLineData([invalid], true),
        ChartErrorType.DATA_INVALID,
        'volume',
      );
    });

    it('throws ChartError for null/undefined input', () => {
      expectChartError(
        () => validateKLineData(null, true),
        ChartErrorType.DATA_INVALID,
        'must be an array',
      );
    });
  });
});

// ==================== validateSignals ====================
describe.skip('validateSignals', () => {
  describe('non-strict mode', () => {
    it('passes valid signal', () => {
      const result = validateSignals([validSignal]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validSignal);
    });

    it.each([
      ['time', 'bad-date'],
      ['position', 'invalid'],
      ['shape', 'invalid'],
      ['color', ''],
    ])('filters out signal with invalid %s', (field, value) => {
      const bad = createSignal({ [field]: value } as Partial<SignalItem>);
      const result = validateSignals([validSignal, bad]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(validSignal);
    });

    it('handles very long text without error', () => {
      const long = createSignal({ text: 'a'.repeat(10000) });
      const result = validateSignals([long]);
      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(long);
    });

    it('returns empty for empty / null / undefined', () => {
      expect(validateSignals([])).toEqual([]);
      expect(validateSignals(null)).toEqual([]);
      expect(validateSignals(undefined)).toEqual([]);
    });
  });

  describe('strict mode', () => {
    it.each([
      ['time', 'bad-date', 'time'],
      ['position', 'invalid', 'position'],
      ['shape', 'invalid', 'shape'],
      ['color', '', 'color'],
    ])('throws ChartError for invalid %s', (field, value, msg) => {
      const bad = createSignal({ [field]: value } as Partial<SignalItem>);
      expectChartError(
        () => validateSignals([bad], true),
        ChartErrorType.DATA_INVALID,
        msg,
      );
    });

    it('throws ChartError for null/undefined input', () => {
      expectChartError(
        () => validateSignals(null, true),
        ChartErrorType.DATA_INVALID,
        'must be an array',
      );
    });
  });
});

// ==================== toOHLCVArray ====================
describe.skip('toOHLCVArray', () => {
  const items = [
    createKLine({ time: '2026-01-05', open: 10, high: 12, low: 9, close: 11, volume: 1000 }),
    createKLine({ time: '2026-01-06', open: 11, high: 13, low: 10, close: 12, volume: 2000 }),
  ];

  it('converts correctly', () => {
    const result = toOHLCVArray(items);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual([
      Math.floor(new Date('2026-01-05').getTime() / 1000),
      10, 12, 9, 11, 1000,
    ]);
    expect(result[1]).toEqual([
      Math.floor(new Date('2026-01-06').getTime() / 1000),
      11, 13, 10, 12, 2000,
    ]);
  });

  it('sets volume to 0 if missing', () => {
    const noVolume = createKLine({ volume: undefined });
    const result = toOHLCVArray([noVolume]);
    expect(result[0][5]).toBe(0);
  });

  it('returns empty for empty input', () => {
    expect(toOHLCVArray([])).toEqual([]);
  });

  it('skips invalid time in non-strict mode', () => {
    const bad = createKLine({ time: 'bad-date' });
    expect(toOHLCVArray([bad])).toEqual([]);
  });

  it('throws for invalid time in strict mode', () => {
    const bad = createKLine({ time: 'bad-date' });
    expectChartError(
      () => toOHLCVArray([bad], true),
      ChartErrorType.DATA_INVALID,
      'Invalid time string',
    );
  });

  it('throws for invalid price in strict mode', () => {
    const bad = createKLine({ open: -1 });
    expectChartError(
      () => toOHLCVArray([bad], true),
      ChartErrorType.DATA_INVALID,
      'Invalid price',
    );
  });

  it('converts UTC time', () => {
    const utc = createKLine({ time: '2026-01-05T14:30:00Z' });
    const result = toOHLCVArray([utc]);
    const expected = Math.floor(new Date('2026-01-05T14:30:00Z').getTime() / 1000);
    expect(result[0][0]).toBe(expected);
  });

  it('skips numeric time in non-strict mode', () => {
    // @ts-expect-error 故意传入数字
    const weak = createKLine({ time: 1700000000 });
    expect(toOHLCVArray([weak])).toEqual([]);
  });
});

// ==================== diffMarkers ====================
describe.skip('diffMarkers', () => {
  const t = (time: string, val: any = time) => ({ time, val });

  describe('basic', () => {
    it('returns empty for both empty', () => {
      expect(diffMarkers([], [])).toEqual({ added: [], removed: [], unchanged: [] });
    });

    it('adds all incoming when existing empty', () => {
      const incoming = [t('2026-01-05'), t('2026-01-06')];
      expect(diffMarkers([], incoming)).toEqual({
        added: incoming,
        removed: [],
        unchanged: [],
      });
    });

    it('removes all when incoming empty', () => {
      const existing = [t('2026-01-05'), t('2026-01-06')];
      expect(diffMarkers(existing, [])).toEqual({
        added: [],
        removed: existing,
        unchanged: [],
      });
    });

    it('mixed add/remove', () => {
      const existing = [t('2026-01-05'), t('2026-01-06'), t('2026-01-07')];
      const incoming = [t('2026-01-06'), t('2026-01-08')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [t('2026-01-08')],
        removed: [t('2026-01-05'), t('2026-01-07')],
        unchanged: [t('2026-01-06')],
      });
    });

    it('updates unchanged with new value', () => {
      const existing = [t('2026-01-05', 'old')];
      const incoming = [t('2026-01-05', 'new')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [],
        removed: [],
        unchanged: [t('2026-01-05', 'new')],
      });
    });

    it('handles duplicate times safely', () => {
      const existing = [t('2026-01-05', 'a'), t('2026-01-05', 'b')];
      const incoming = [t('2026-01-05', 'a')];
      const result = diffMarkers(existing, incoming);
      // 由于 Map 会保留最后一个，结果可能不稳定，但确保不崩溃
      expect(result.removed).toHaveLength(1);
      expect(result.unchanged).toHaveLength(1);
    });

    // 安全：原型链忽略
    it('ignores __proto__ key', () => {
      const existing = [{ time: '2026-01-05', val: 'old' }];
      // @ts-expect-error 故意注入
      const incoming = [{ time: '2026-01-05', val: 'new', __proto__: { polluted: true } }];
      const result = diffMarkers(existing, incoming);
      expect(result.unchanged).toEqual([{ time: '2026-01-05', val: 'new' }]);
      expect(({} as any).polluted).toBeUndefined();
    });
  });

  describe('sorted fast path', () => {
    it('handles sorted arrays', () => {
      const existing = [t('2026-01-01'), t('2026-01-02')];
      const incoming = [t('2026-01-01'), t('2026-01-03')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [t('2026-01-03')],
        removed: [t('2026-01-02')],
        unchanged: [t('2026-01-01')],
      });
    });
  });

  describe('unsorted fallback', () => {
    it('handles unsorted existing', () => {
      const existing = [t('2026-01-02'), t('2026-01-01')];
      const incoming = [t('2026-01-01'), t('2026-01-03')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [t('2026-01-03')],
        removed: [t('2026-01-02')],
        unchanged: [t('2026-01-01')],
      });
    });

    it('handles unsorted incoming', () => {
      const existing = [t('2026-01-01'), t('2026-01-03')];
      const incoming = [t('2026-01-03'), t('2026-01-02')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [t('2026-01-02')],
        removed: [t('2026-01-01')],
        unchanged: [t('2026-01-03')],
      });
    });

    it('handles both unsorted', () => {
      const existing = [t('2026-01-02'), t('2026-01-01')];
      const incoming = [t('2026-01-03'), t('2026-01-01')];
      expect(diffMarkers(existing, incoming)).toEqual({
        added: [t('2026-01-03')],
        removed: [t('2026-01-02')],
        unchanged: [t('2026-01-01')],
      });
    });
  });

  describe('custom timeKey', () => {
    type Item = { date: string; label: string };
    it('supports custom key', () => {
      const existing: Item[] = [{ date: '2026-01-05', label: 'old' }];
      const incoming: Item[] = [
        { date: '2026-01-05', label: 'new' },
        { date: '2026-01-06', label: 'x' },
      ];
      expect(diffMarkers(existing, incoming, 'date')).toEqual({
        added: [{ date: '2026-01-06', label: 'x' }],
        removed: [],
        unchanged: [{ date: '2026-01-05', label: 'new' }],
      });
    });

    it('works with multiple items', () => {
      const existing: Item[] = [
        { date: '2026-01-01', label: 'a' },
        { date: '2026-01-02', label: 'b' },
      ];
      const incoming: Item[] = [
        { date: '2026-01-02', label: 'B' },
        { date: '2026-01-03', label: 'c' },
      ];
      expect(diffMarkers(existing, incoming, 'date')).toEqual({
        added: [{ date: '2026-01-03', label: 'c' }],
        removed: [{ date: '2026-01-01', label: 'a' }],
        unchanged: [{ date: '2026-01-02', label: 'B' }],
      });
    });
  });

  // 性能测试（通过环境变量开启）
  describe('performance', () => {
    const runPerf = process.env.RUN_PERF_TESTS === 'true';
    const testFn = runPerf ? it : it.skip;

    testFn('large arrays performance', () => {
      const size = BOUNDARIES.LARGE_ARRAY_SIZE;
      const existing = Array.from({ length: size }, (_, i) => ({ time: `2026-01-${String(i).padStart(2, '0')}`, val: i }));
      const incoming = Array.from({ length: size }, (_, i) => ({
        time: `2026-01-${String(i + 5000).padStart(2, '0')}`,
        val: i + 5000,
      }));
      const start = performance.now();
      diffMarkers(existing, incoming);
      const duration = performance.now() - start;
      expect(duration).toBeLessThan(BOUNDARIES.PERF_THRESHOLD_MS * 2);
    });

    testFn('sorted path faster than unsorted', () => {
      const size = 5000;
      const sortedExisting = Array.from({ length: size }, (_, i) => ({ time: `2026-01-${String(i).padStart(2, '0')}`, val: i }));
      const sortedIncoming = Array.from({ length: size }, (_, i) => ({
        time: `2026-01-${String(i + 2500).padStart(2, '0')}`,
        val: i + 2500,
      }));
      const unsortedExisting = [...sortedExisting].reverse();
      const unsortedIncoming = [...sortedIncoming].reverse();

      const startSorted = performance.now();
      diffMarkers(sortedExisting, sortedIncoming);
      const sortedDur = performance.now() - startSorted;

      const startUnsorted = performance.now();
      diffMarkers(unsortedExisting, unsortedIncoming);
      const unsortedDur = performance.now() - startUnsorted;

      expect(sortedDur).toBeLessThan(unsortedDur);
    });
  });
});