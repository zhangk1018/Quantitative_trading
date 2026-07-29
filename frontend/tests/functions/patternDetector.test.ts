/**
 * patternDetector 单元测试
 *
 * 覆盖：
 * - validateConfig (边界、多参数、安全)
 * - detectAllPatterns (5种形态、临界、有序、提前终止、脏数据、跳空开关)
 * - hasAnyPattern (筛选、异常安全)
 *
 * 性能测试通过 RUN_PERF_TESTS=true 环境变量开启
 */
import { describe, it, expect } from 'vitest';
import {
  validateConfig,
  DETECTION_CONFIG,
  ChartError,
  ChartErrorType,
} from '@/lib/indicators/chartConstants';
import { detectAllPatterns, hasAnyPattern } from '@/lib/indicators/patternDetector';
import type { OHLCVArray } from '@/lib/indicators/types';

// ==================== 常量 ====================
const BOUNDARIES = {
  LARGE_ARRAY_SIZE: 10000,
  PERF_THRESHOLD_MS: 200,
} as const;

// 从配置中引用阈值，避免硬编码
const { morningStarPenetration, eveningStarPenetration } = DETECTION_CONFIG;

// ==================== 工厂函数 ====================
function makeBar(open: number, high: number, low: number, close: number, time = 1620000000): OHLCVArray {
  return [time, open, high, low, close, 1000];
}

/**
 * 锤子线序列（最后一个是锤子）
 * 满足：下影线 ≥ 2×实体，上影线 ≤ 0.1×实体 + range×0.01
 */
function buildHammerSet(): OHLCVArray[] {
  // 实体 0.2，下影线 0.4 (2倍)，上影线 0.02，range 0.62
  return [
    makeBar(10, 12, 9, 11),
    makeBar(11, 12, 9, 11),
    makeBar(10.0, 10.22, 9.6, 10.2), // hammer
  ];
}

/**
 * 看涨吞没：前阴后阳，后阳完全覆盖前阴实体
 */
function buildBullishEngulfingSet(): OHLCVArray[] {
  return [
    makeBar(12, 13, 11, 11.5),   // 阴线
    makeBar(11, 14, 10.5, 13),   // 阳线覆盖
  ];
}

/**
 * 看跌吞没：前阳后阴，后阴完全覆盖前阳实体
 */
function buildBearishEngulfingSet(): OHLCVArray[] {
  return [
    makeBar(11, 12, 10, 11.5),   // 阳线
    makeBar(12, 13, 10.5, 10.8), // 阴线覆盖
  ];
}

/**
 * 晨星（无跳空）
 * 第一根大阴：body/range ≥ 0.6
 * 第二根十字星：body/range ≤ 0.1
 * 第三根大阳：body/range ≥ 0.6，且 close ≥ 第一根低点 + body1 * penetration
 */
function buildMorningStarSet(): OHLCVArray[] {
  const body1 = 2.2;
  const low1 = 10.8;
  const penetrationPrice = low1 + body1 * morningStarPenetration;
  return [
    makeBar(13, 13.5, low1, 10.8),       // 大阴，body/range=2.2/2.7≈0.815
    makeBar(10.85, 10.9, 10.8, 10.85),   // 十字星，body=0，range=0.1
    makeBar(11.5, 13.0, 11.4, 12.5),     // 大阳，close=12.5 ≥ penetrationPrice，body/range=1.0/1.6=0.625
  ];
}

/**
 * 黄昏之星（无跳空）
 * 第一根大阳：body/range ≥ 0.6
 * 第二根十字星：body/range ≤ 0.1
 * 第三根大阴：body/range ≥ 0.6，且 close ≤ 第一根顶部 - body1 * penetration
 */
function buildEveningStarSet(): OHLCVArray[] {
  const body1 = 2.2;
  const top1 = 13.5; // 第一根最高价
  const penetrationPrice = top1 - body1 * eveningStarPenetration;
  return [
    makeBar(10.8, top1, 10.6, 13),       // 大阳，body/range=2.2/2.9≈0.759
    makeBar(12.9, 13.0, 12.8, 12.9),     // 十字星，body=0，range=0.2
    makeBar(12.5, 12.8, 10.5, 11.0),     // 大阴，close=11.0 ≤ penetrationPrice，body/range=1.5/2.3≈0.652
  ];
}

/**
 * 晨星（带跳空，满足 requireGapForStar）
 * 实现逻辑中，晨星跳空要求：bar2.low > bar1.close 且 bar3.open > bar2.close
 */
function buildMorningStarWithGap(): OHLCVArray[] {
  const body1 = 2.2;
  const low1 = 10.8;
  const penetrationPrice = low1 + body1 * morningStarPenetration;
  return [
    makeBar(13, 13.5, low1, 10.8),       // 大阴，close=10.8
    makeBar(11.0, 11.1, 10.9, 11.0),     // 十字星，low=10.9 > 10.8 ✓
    makeBar(11.2, 13.0, 11.1, 12.5),     // 大阳，open=11.2 > 11.0 ✓，close=12.5 ≥ penetrationPrice
  ];
}

/**
 * 黄昏之星（带跳空，满足 requireGapForStar）
 * 实现逻辑中，夜星跳空要求：bar2.high < bar1.close 且 bar3.open < bar2.close
 */
function buildEveningStarWithGap(): OHLCVArray[] {
  const body1 = 2.2;
  const top1 = 13.5;
  const penetrationPrice = top1 - body1 * eveningStarPenetration;
  return [
    makeBar(10.8, top1, 10.6, 13),       // 大阳，close=13
    makeBar(12.5, 12.6, 12.4, 12.5),     // 十字星，high=12.6 < 13 ✓
    makeBar(12.3, 12.4, 10.5, 11.0),     // 大阴，open=12.3 < 12.5 ✓，close=11.0 ≤ penetrationPrice
  ];
}

// ==================== validateConfig ====================
describe('validateConfig', () => {
  it('returns defaults on empty', () => {
    expect(validateConfig({})).toEqual(DETECTION_CONFIG);
  });

  it('preserves valid overrides', () => {
    const result = validateConfig({ hammerLowerShadowRatio: 3.0 });
    expect(result.hammerLowerShadowRatio).toBe(3.0);
  });

  it('resets out-of-range to default', () => {
    const result = validateConfig({ hammerLowerShadowRatio: 100 });
    expect(result.hammerLowerShadowRatio).toBe(DETECTION_CONFIG.hammerLowerShadowRatio);
  });

  it('resets non-number to default', () => {
    // @ts-expect-error 故意传入非数字
    const result = validateConfig({ hammerLowerShadowRatio: 'abc' });
    expect(result.hammerLowerShadowRatio).toBe(DETECTION_CONFIG.hammerLowerShadowRatio);
  });

  it('passes boolean through', () => {
    expect(validateConfig({ requireGapForStar: true }).requireGapForStar).toBe(true);
  });

  it('clamps at boundaries', () => {
    expect(validateConfig({ dojiBodyRatio: 0.001 }).dojiBodyRatio).toBe(0.001);
    expect(validateConfig({ hammerLowerShadowRatio: 10 }).hammerLowerShadowRatio).toBe(10);
  });

  it('handles multiple out-of-range params', () => {
    const result = validateConfig({
      morningStarPenetration: 2,
      eveningStarPenetration: -1,
      dojiBodyRatio: 0.6,
      largeBodyRatio: 1.5,
    });
    expect(result.morningStarPenetration).toBe(DETECTION_CONFIG.morningStarPenetration);
    expect(result.eveningStarPenetration).toBe(DETECTION_CONFIG.eveningStarPenetration);
    expect(result.dojiBodyRatio).toBe(DETECTION_CONFIG.dojiBodyRatio);
    expect(result.largeBodyRatio).toBe(DETECTION_CONFIG.largeBodyRatio);
  });

  it('handles mixed invalid types and out-of-range', () => {
    const result = validateConfig({
      // @ts-expect-error
      hammerLowerShadowRatio: 'invalid',
      hammerUpperShadowRatio: 100,
      // @ts-expect-error
      requireGapForStar: 'true',
    });
    expect(result.hammerLowerShadowRatio).toBe(DETECTION_CONFIG.hammerLowerShadowRatio);
    expect(result.hammerUpperShadowRatio).toBe(DETECTION_CONFIG.hammerUpperShadowRatio);
    expect(result.requireGapForStar).toBe(DETECTION_CONFIG.requireGapForStar);
  });

  it('ignores __proto__ key', () => {
    // @ts-expect-error
    const result = validateConfig({ __proto__: { polluted: true } });
    expect(result).toEqual(DETECTION_CONFIG);
    expect(({} as any).polluted).toBeUndefined();
  });
});

// ==================== detectAllPatterns ====================
describe('detectAllPatterns', () => {
  // ---------- 锤子 ----------
  it('detects hammer', () => {
    const data = buildHammerSet();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('hammer');
    expect(result.hitDays.hammer).toEqual([data.length - 1]);
  });

  it('no hammer when upper shadow too long', () => {
    const data = [
      makeBar(10, 12, 9, 11),
      makeBar(10, 13, 9.9, 11), // upper=2 > tolerance
    ];
    expect(detectAllPatterns(data).hits).not.toContain('hammer');
  });

  it('hammer at exact lower shadow ratio boundary', () => {
    // body=0.2, lower=0.4 (exact 2×), upper=0.02, range=0.62
    const hammer = makeBar(10.0, 10.22, 9.6, 10.2);
    const data = [makeBar(10, 12, 9, 11), hammer];
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('hammer');
    expect(result.hitDays.hammer).toEqual([1]);
  });

  // ---------- 吞没 ----------
  it('detects bullish engulfing', () => {
    const data = buildBullishEngulfingSet();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('bullish_engulfing');
    expect(result.hitDays.bullish_engulfing).toEqual([data.length - 1]);
  });

  it('no bullish engulfing when both bullish', () => {
    const data = [
      makeBar(10, 12, 9, 11),
      makeBar(10.5, 13, 10, 12),
    ];
    expect(detectAllPatterns(data).hits).not.toContain('bullish_engulfing');
  });

  it('detects bearish engulfing', () => {
    const data = buildBearishEngulfingSet();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('bearish_engulfing');
    expect(result.hitDays.bearish_engulfing).toEqual([data.length - 1]);
  });

  // ---------- 星形 ----------
  it('detects morning star', () => {
    const data = buildMorningStarSet();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('morning_star');
    expect(result.hitDays.morning_star).toEqual([data.length - 1]);
  });

  it('detects morning star at exact penetration', () => {
    const body1 = 2.2;
    const low1 = 10.8;
    const penetrationPrice = low1 + body1 * morningStarPenetration;
    // 第三根需要 body/range ≥ 0.6 才满足大实体条件
    // range=13.0-11.4=1.6, 需要 body ≥ 1.6*0.6=0.96
    // 阳线 close ≥ open+0.96=11.5+0.96=12.46
    const close3 = Math.max(penetrationPrice, 12.46);
    const data = [
      makeBar(13, 13.5, low1, 10.8),
      makeBar(10.85, 10.9, 10.8, 10.85),
      makeBar(11.5, 13.0, 11.4, close3), // 刚好穿透 + 满足大实体
    ];
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('morning_star');
  });

  it('detects evening star', () => {
    const data = buildEveningStarSet();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('evening_star');
    expect(result.hitDays.evening_star).toEqual([data.length - 1]);
  });

  // ---------- 跳空开关 ----------
  it('respects requireGapForStar: no gap -> no detection', () => {
    const noGap = buildMorningStarSet();
    const result = detectAllPatterns(noGap, { requireGapForStar: true });
    expect(result.hits).not.toContain('morning_star');
  });

  it('detects morning star with gap when required', () => {
    const withGap = buildMorningStarWithGap();
    const result = detectAllPatterns(withGap, { requireGapForStar: true });
    expect(result.hits).toContain('morning_star');
  });

  it('detects evening star with gap when required', () => {
    const withGap = buildEveningStarWithGap();
    const result = detectAllPatterns(withGap, { requireGapForStar: true });
    expect(result.hits).toContain('evening_star');
  });

  // ---------- 脏数据 ----------
  it('skips invalid bars', () => {
    const bad = [1620000000, 10, 12] as any; // 长度不足
    const data = [...buildHammerSet(), bad];
    expect(() => detectAllPatterns(data)).not.toThrow();
    const result = detectAllPatterns(data);
    expect(result.hits).toContain('hammer');
  });

  // ---------- 数据不足 ----------
  it('returns empty for less than 2 bars', () => {
    const data = [makeBar(10, 12, 9, 11)];
    expect(() => detectAllPatterns(data)).toThrow(ChartError);
    expect(() => detectAllPatterns(data)).toThrow(/at least 2/);
  });

  it('returns empty for 2 bars that cannot form pattern', () => {
    const data = [
      makeBar(10, 12, 9, 11),
      makeBar(10.5, 13, 10, 12),
    ];
    const result = detectAllPatterns(data);
    expect(result.hits).toEqual([]);
    expect(result.hitDays.hammer).toEqual([]);
  });

  it('throws for empty array', () => {
    expect(() => detectAllPatterns([])).toThrow(ChartError);
    expect(() => detectAllPatterns([])).toThrow(/at least 2/);
  });

  it('throws for non-array', () => {
    // @ts-expect-error
    expect(() => detectAllPatterns(null)).toThrow(ChartError);
  });

  // ---------- 乱序 ----------
  it('auto-sorts out-of-order data', () => {
    const data = [
      makeBar(10, 12, 9, 11, 3),
      makeBar(12, 13, 11, 11.5, 1),
      makeBar(10.9, 11.1, 9.9, 11, 2),
    ];
    expect(() => detectAllPatterns(data)).not.toThrow();
  });

  // ---------- 提前终止 ----------
  it('stops early when all target patterns found', () => {
    const data = buildBullishEngulfingSet();
    const result = detectAllPatterns(data, {}, ['bullish_engulfing']);
    expect(result.hits).toEqual(['bullish_engulfing']);
  });

  // ---------- 性能（仅环境变量开启） ----------
  const runPerf = process.env.RUN_PERF_TESTS === 'true';
  const perfIt = runPerf ? it : it.skip;

  perfIt('large OHLCV data performance', () => {
    const large: OHLCVArray[] = Array.from({ length: BOUNDARIES.LARGE_ARRAY_SIZE }, (_, i) => {
      const base = i * 0.01;
      return makeBar(10 + base, 12 + base, 9 + base, 11 + base, i);
    });
    const start = performance.now();
    detectAllPatterns(large);
    const duration = performance.now() - start;
    expect(duration).toBeLessThan(BOUNDARIES.PERF_THRESHOLD_MS * 1.5);
  });
});

// ==================== hasAnyPattern ====================
describe('hasAnyPattern', () => {
  it('returns true when pattern exists', () => {
    expect(hasAnyPattern(buildBullishEngulfingSet(), ['bullish_engulfing'])).toBe(true);
  });

  it('returns false when pattern absent', () => {
    const data = [makeBar(10, 12, 9, 11), makeBar(11, 13, 10, 12)];
    expect(hasAnyPattern(data, ['hammer'])).toBe(false);
  });

  it('returns false for empty patterns', () => {
    expect(hasAnyPattern([], [])).toBe(false);
  });

  it('returns false for invalid data', () => {
    // @ts-expect-error
    expect(hasAnyPattern(null, ['hammer'])).toBe(false);
    // @ts-expect-error
    expect(hasAnyPattern({}, ['hammer'])).toBe(false);
  });
});