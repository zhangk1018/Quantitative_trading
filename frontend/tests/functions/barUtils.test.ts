/**
 * barUtils 单元测试
 *
 * 覆盖：
 * - getter 函数（getOpen / getHigh / getLow / getClose / getVolume）
 * - isValidBar（正常/长度/价格越界/高低价矛盾/NaN/Infinity/成交量/弱类型/畸形结构）
 * - 派生计算（getBodyTop / getBodyBottom / getBodySize / getRange / isBullish / isBearish / getUpperShadow / getLowerShadow）
 * - precomputeBars（过滤无效、全有效、空输入、成交量传递、全字段断言）
 *
 * 性能测试通过 RUN_PERF_TESTS=true 环境变量开启（建议 CI 拆分任务）
 *
 * @security 防护风险：浮点精度、弱类型接口、数组越界、原型链污染、超大时间戳
 */
import { describe, it, expect } from 'vitest';
import {
  getOpen,
  getHigh,
  getLow,
  getClose,
  getVolume,
  isValidBar,
  getBodyTop,
  getBodyBottom,
  getBodySize,
  getRange,
  isBullish,
  isBearish,
  getUpperShadow,
  getLowerShadow,
  precomputeBars,
  type PrecomputedBar,
} from '@/lib/indicators/barUtils';
import type { OHLCVArray } from '@/lib/indicators/barUtils';

// ==================== 常量 ====================
const BOUNDARIES = {
  MAX_PRICE: 1e8,
  MIN_PRICE: 0.01,
  LARGE_ARRAY_SIZE: 10000,
  PERF_THRESHOLD_MS: 200,
} as const;

// ==================== 工厂函数（返回只读数组，防止污染） ====================
/** 构造标准 OHLCV 数据组 [time, open, high, low, close, volume?] */
function makeBar(
  open: number,
  high: number,
  low: number,
  close: number,
  volume = 1000,
  time = 1620000000,
): Readonly<OHLCVArray> {
  return [time, open, high, low, close, volume] as const;
}

/** 阳线：close > open */
function bullBar(): Readonly<OHLCVArray> {
  return makeBar(10, 12, 9, 11, 1000);
}

/** 阴线：close < open */
function bearBar(): Readonly<OHLCVArray> {
  return makeBar(11, 12, 9, 10, 1000);
}

/** 十字星：close === open */
function dojiBar(): Readonly<OHLCVArray> {
  return makeBar(10, 12, 9, 10, 1000);
}

// ==================== 局部 patch 工具（减少重复数组改写） ====================
/**
 * 基于基准 bar 生成新的只读数组，覆盖指定字段
 */
function patchBar(
  base: Readonly<OHLCVArray>,
  overrides: Partial<{
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    time: number;
  }>,
): Readonly<OHLCVArray> {
  const [time, open, high, low, close, volume] = base;
  return [
    overrides.time ?? time,
    overrides.open ?? open,
    overrides.high ?? high,
    overrides.low ?? low,
    overrides.close ?? close,
    overrides.volume ?? volume,
  ] as const;
}

// ==================== getter ====================
describe('getter functions', () => {
  it('getOpen returns element at OHLCV_OPEN', () => {
    expect(getOpen(makeBar(10.5, 12, 9, 11))).toBe(10.5);
  });
  it('getHigh returns element at OHLCV_HIGH', () => {
    expect(getHigh(makeBar(10, 12.5, 9, 11))).toBe(12.5);
  });
  it('getLow returns element at OHLCV_LOW', () => {
    expect(getLow(makeBar(10, 12, 9.5, 11))).toBe(9.5);
  });
  it('getClose returns element at OHLCV_CLOSE', () => {
    expect(getClose(makeBar(10, 12, 9, 11.5))).toBe(11.5);
  });
  it('getClose works with decimal', () => {
    expect(getClose(makeBar(10, 12, 9, 11.345))).toBe(11.345);
  });

  describe('getVolume', () => {
    it('returns volume when present', () => {
      expect(getVolume(makeBar(10, 12, 9, 11, 50000))).toBe(50000);
    });
    it('returns 0 when volume is undefined', () => {
      const noVol: OHLCVArray = [1620000000, 10, 12, 9, 11];
      expect(getVolume(noVol)).toBe(0);
    });
    it('returns 0 when volume is 0', () => {
      expect(getVolume(makeBar(10, 12, 9, 11, 0))).toBe(0);
    });
    it('returns negative volume as-is', () => {
      // 业务上不应为负，但 getter 只读，不做校验
      expect(getVolume(makeBar(10, 12, 9, 11, -100))).toBe(-100);
    });
  });
});

// ==================== isValidBar ====================
describe('isValidBar', () => {
  it('accepts standard bull bar', () => {
    expect(isValidBar(bullBar())).toBe(true);
  });
  it('accepts standard bear bar', () => {
    expect(isValidBar(bearBar())).toBe(true);
  });
  it('accepts doji bar', () => {
    expect(isValidBar(dojiBar())).toBe(true);
  });
  it('accepts bar with zero volume', () => {
    expect(isValidBar(makeBar(10, 12, 9, 11, 0))).toBe(true);
  });
  it('accepts small positive prices', () => {
    expect(isValidBar(makeBar(BOUNDARIES.MIN_PRICE, 0.02, 0.005, 0.015, 100))).toBe(true);
  });
  it('accepts price at max bound', () => {
    expect(isValidBar(makeBar(
      BOUNDARIES.MAX_PRICE, BOUNDARIES.MAX_PRICE + 2,
      BOUNDARIES.MAX_PRICE - 1, BOUNDARIES.MAX_PRICE + 1,
    ))).toBe(true);
  });

  // 科学计数法 / 循环小数
  it('accepts scientific notation prices', () => {
    expect(isValidBar(makeBar(1e-5, 2e-5, 0.5e-5, 1.5e-5))).toBe(true);
  });
  it('accepts repeating decimal prices', () => {
    expect(isValidBar(makeBar(10 / 3, 12 / 3, 9 / 3, 11 / 3))).toBe(true);
  });

  // 弱类型：字符串数字（应被接受，因为 Number.isFinite 会转换）
  it('rejects string numbers (Number.isFinite returns false for strings)', () => {
    const strBar: any = [1620000000, '10', '12', '9', '11', '1000'];
    expect(isValidBar(strBar)).toBe(false);
  });
  // BigInt 会被 Number 转换，有限数值则通过
  it('rejects BigInt values (Number.isFinite returns false for BigInt)', () => {
  const bigBar: any = [1620000000, 10n, 12n, 9n, 11n, 1000n];
  expect(isValidBar(bigBar)).toBe(false);
  });

  // 超大时间戳（仍为数字，应通过）
  it('accepts extremely large timestamp', () => {
    expect(isValidBar(makeBar(10, 12, 9, 11, 1000, Number.MAX_SAFE_INTEGER))).toBe(true);
  });

  describe('rejects', () => {
    // 使用 any 绕过类型，但未用 @ts-expect-error
    it('null / undefined', () => {
      expect(isValidBar(null as any)).toBe(false);
      expect(isValidBar(undefined as any)).toBe(false);
    });
    it('array shorter than 6', () => {
      expect(isValidBar([1620000000, 10, 12] as any)).toBe(false);
    });
    // 注意：长度 >6 的数组不会被拒绝，此处仅测试不崩溃
    it('handles array longer than 6 without crashing', () => {
      const long = [1620000000, 10, 12, 9, 11, 1000, 'extra'] as any;
      // isValidBar 只检查 length < 6，所以长数组会通过
      expect(isValidBar(long)).toBe(true);
    });

    // 嵌套数组污染（传入数组元素为数组）
    it('rejects nested array structure', () => {
      const nested: any = [1620000000, [10], 12, 9, 11, 1000];
      expect(isValidBar(nested)).toBe(false);
    });

    // 价格越界（参数化，带类型注解）
    const invalidPriceCases: Array<[field: 'open' | 'high' | 'low' | 'close', value: number]> = [
      ['open', -1],
      ['open', 0],
      ['high', 0],
      ['low', -0.01],
      ['close', 0],
    ];
    it.each(invalidPriceCases)('rejects %s = %s (non-positive)', (field, value) => {
      const base = makeBar(10, 12, 9, 11, 1000);
      const overrides = { [field]: value } as Partial<{ open: number; high: number; low: number; close: number }>;
      const bar = patchBar(base, overrides) as OHLCVArray;
      expect(isValidBar(bar)).toBe(false);
    });

    // NaN / Infinity（参数化，带类型注解）
    const invalidNumberCases: Array<[field: 'open' | 'high' | 'low' | 'close', value: number]> = [
      ['open', NaN],
      ['high', Infinity],
      ['low', -Infinity],
      ['close', NaN],
    ];
    it.each(invalidNumberCases)('rejects %s = %s', (field, value) => {
      const base = makeBar(10, 12, 9, 11, 1000);
      const overrides = { [field]: value } as Partial<{ open: number; high: number; low: number; close: number }>;
      const bar = patchBar(base, overrides) as OHLCVArray;
      expect(isValidBar(bar)).toBe(false);
    });

    // 逻辑矛盾
    it('high < low', () => {
      expect(isValidBar(makeBar(10, 9, 12, 11, 1000))).toBe(false);
    });
    it('high < max(open, close)', () => {
      expect(isValidBar(makeBar(10, 9, 9.5, 14, 1000))).toBe(false);
    });
    it('low > min(open, close)', () => {
      expect(isValidBar(makeBar(10, 12, 11.5, 9, 1000))).toBe(false);
    });

    // 成交量
    it('negative volume', () => {
      expect(isValidBar(makeBar(10, 12, 9, 11, -1))).toBe(false);
    });
    it('NaN volume', () => {
      expect(isValidBar(makeBar(10, 12, 9, 11, NaN))).toBe(false);
    });
    it('Infinity volume', () => {
      expect(isValidBar(makeBar(10, 12, 9, 11, Infinity))).toBe(false);
    });

    // 字符串数字但包含非数字字符（应拒绝）
    it('rejects string with non-numeric chars', () => {
      const badBar: any = [1620000000, '10a', '12', '9', '11', '1000'];
      expect(isValidBar(badBar)).toBe(false);
    });
  });
});

// ==================== 派生计算 ====================
describe('derived calculations', () => {
  describe('getBodyTop / getBodyBottom', () => {
    it('bull bar: bodyTop = close, bodyBottom = open', () => {
      const bar = bullBar();
      expect(getBodyTop(bar)).toBe(11);
      expect(getBodyBottom(bar)).toBe(10);
    });
    it('bear bar: bodyTop = open, bodyBottom = close', () => {
      const bar = bearBar();
      expect(getBodyTop(bar)).toBe(11);
      expect(getBodyBottom(bar)).toBe(10);
    });
    it('doji: bodyTop = bodyBottom', () => {
      const bar = dojiBar();
      expect(getBodyTop(bar)).toBe(10);
      expect(getBodyBottom(bar)).toBe(10);
    });
  });

  describe('getBodySize', () => {
    it('bull bar: |11 - 10| = 1', () => {
      expect(getBodySize(bullBar())).toBe(1);
    });
    it('bear bar: |10 - 11| = 1', () => {
      expect(getBodySize(bearBar())).toBe(1);
    });
    it('doji: |10 - 10| = 0', () => {
      expect(getBodySize(dojiBar())).toBe(0);
    });
  });

  describe('getRange', () => {
    it('bull bar: 12 - 9 = 3', () => {
      expect(getRange(bullBar())).toBe(3);
    });
  });

  describe('isBullish / isBearish', () => {
    it('bull bar: bullish=true, bearish=false', () => {
      expect(isBullish(bullBar())).toBe(true);
      expect(isBearish(bullBar())).toBe(false);
    });
    it('bear bar: bullish=false, bearish=true', () => {
      expect(isBullish(bearBar())).toBe(false);
      expect(isBearish(bearBar())).toBe(true);
    });
    it('doji: both false', () => {
      expect(isBullish(dojiBar())).toBe(false);
      expect(isBearish(dojiBar())).toBe(false);
    });
  });

  describe('getUpperShadow', () => {
    it('bull bar: high - close', () => {
      expect(getUpperShadow(bullBar())).toBe(12 - 11);
    });
    it('bear bar: high - open', () => {
      expect(getUpperShadow(bearBar())).toBe(12 - 11);
    });
  });

  describe('getLowerShadow', () => {
    it('bull bar: open - low', () => {
      expect(getLowerShadow(bullBar())).toBe(10 - 9);
    });
    it('bear bar: close - low', () => {
      expect(getLowerShadow(bearBar())).toBe(10 - 9);
    });
  });
});

// ==================== precomputeBars ====================
describe('precomputeBars', () => {
  it('skips invalid bars, precomputes valid ones', () => {
    const input: OHLCVArray[] = [
      makeBar(10, 12, 9, 11, 500) as OHLCVArray, // valid
      makeBar(NaN, 12, 9, 11, 500) as OHLCVArray, // invalid
      makeBar(10, 8, 9, 11, 500) as OHLCVArray, // invalid
      makeBar(12, 14, 10, 13, 2000) as OHLCVArray, // valid
    ];
    const result = precomputeBars(input);
    expect(result).toHaveLength(2);

    // 使用 toStrictEqual 完整比对第一项
    const expectedFirst: PrecomputedBar = {
      index: 0,
      open: 10,
      high: 12,
      low: 9,
      close: 11,
      volume: 500,
      bodySize: 1,
      range: 3,
      upperShadow: 1, // 12 - 11
      lowerShadow: 1, // 10 - 9
      bullish: true,
      bearish: false,
      bodyTop: 11,
      bodyBottom: 10,
    };
    expect(result[0]).toStrictEqual(expectedFirst);

    // 第二项
    const expectedSecond: PrecomputedBar = {
      index: 3,
      open: 12,
      high: 14,
      low: 10,
      close: 13,
      volume: 2000,
      bodySize: 1,
      range: 4,
      upperShadow: 1,
      lowerShadow: 2,
      bullish: true,
      bearish: false,
      bodyTop: 13,
      bodyBottom: 12,
    };
    expect(result[1]).toStrictEqual(expectedSecond);
  });

  it('captures bearish correctly', () => {
    const input: OHLCVArray[] = [makeBar(11, 12, 9, 10, 1000) as OHLCVArray];
    const result = precomputeBars(input);
    expect(result[0].bullish).toBe(false);
    expect(result[0].bearish).toBe(true);
    expect(result[0].bodyTop).toBe(11);
    expect(result[0].bodyBottom).toBe(10);
  });

  it('returns empty for all invalid input', () => {
    const input: OHLCVArray[] = [
      makeBar(NaN, 12, 9, 11, 500) as OHLCVArray,
      makeBar(10, 8, 9, 11, 500) as OHLCVArray,
    ];
    expect(precomputeBars(input)).toEqual([]);
  });

  it('returns empty for empty input', () => {
    expect(precomputeBars([])).toEqual([]);
  });

  it('preserves volume from each bar', () => {
    const v1 = 100, v2 = 99999;
    const input: OHLCVArray[] = [
      makeBar(10, 12, 9, 11, v1) as OHLCVArray,
      makeBar(11, 13, 10, 12, v2) as OHLCVArray,
    ];
    const result = precomputeBars(input);
    expect(result[0].volume).toBe(v1);
    expect(result[1].volume).toBe(v2);
  });

  it('does not modify original input', () => {
    const input: OHLCVArray[] = [makeBar(10, 12, 9, 11, 1000) as OHLCVArray];
    Object.freeze(input[0]);
    expect(() => precomputeBars(input)).not.toThrow();
  });

  describe('performance', () => {
    const runPerf = process.env.RUN_PERF_TESTS === 'true';
    const testFn = runPerf ? it : it.skip;

    testFn('large array with all valid bars', () => {
      const large: OHLCVArray[] = Array.from(
        { length: BOUNDARIES.LARGE_ARRAY_SIZE },
        (_, i) => makeBar(10 + i * 0.01, 12 + i * 0.01, 9 + i * 0.01, 11 + i * 0.01, 1000, i) as OHLCVArray,
      );
      const start = performance.now();
      const result = precomputeBars(large);
      const dur = performance.now() - start;
      expect(result).toHaveLength(BOUNDARIES.LARGE_ARRAY_SIZE);
      expect(dur).toBeLessThan(BOUNDARIES.PERF_THRESHOLD_MS * 1.5);
    });

    testFn('mixed valid/invalid large array', () => {
      const mixed: OHLCVArray[] = Array.from(
        { length: BOUNDARIES.LARGE_ARRAY_SIZE },
        (_, i) => {
          if (i % 3 === 0) {
            return makeBar(NaN, 12, 9, 11, 1000, i) as OHLCVArray;
          } else if (i % 3 === 1) {
            return makeBar(10, 8, 9, 11, 1000, i) as OHLCVArray;
          } else {
            return makeBar(10 + i * 0.01, 12 + i * 0.01, 9 + i * 0.01, 11 + i * 0.01, 1000, i) as OHLCVArray;
          }
        },
      );
      const start = performance.now();
      const result = precomputeBars(mixed);
      const dur = performance.now() - start;
      expect(result.length).toBeGreaterThan(0);
      expect(dur).toBeLessThan(BOUNDARIES.PERF_THRESHOLD_MS * 2);
    });
  });
});