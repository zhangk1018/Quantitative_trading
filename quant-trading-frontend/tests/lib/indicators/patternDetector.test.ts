import { describe, it, expect } from 'vitest';
import {
  isHammer,
  isBullishEngulfing,
  isBearishEngulfing,
  isMorningStar,
  isEveningStar,
  detectAllPatterns,
  hasAnyPattern,
} from '@/lib/indicators/patternDetector';
import type { OHLCVArray } from '@/lib/indicators/types';

function makeBar({
  time = 1700000000,
  open,
  high,
  low,
  close,
  volume = 1000000,
}: {
  time?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}): OHLCVArray {
  return [time, open, high, low, close, volume];
}

describe('patternDetector', () => {
  describe('isHammer', () => {
    it('标准锤子线（阳线）→ true', () => {
      const bar = makeBar({ open: 100, high: 102.1, low: 95, close: 102 });
      expect(isHammer(bar)).toBe(true);
    });

    it('标准锤子线（阴线）→ true', () => {
      const bar = makeBar({ open: 102, high: 102.1, low: 95, close: 100 });
      expect(isHammer(bar)).toBe(true);
    });

    it('普通K线（非锤子）→ false', () => {
      const bar = makeBar({ open: 100, high: 105, low: 95, close: 102 });
      expect(isHammer(bar)).toBe(false);
    });

    it('上影线太长 → false', () => {
      const bar = makeBar({ open: 100, high: 108, low: 95, close: 102 });
      expect(isHammer(bar)).toBe(false);
    });

    it('下影线不够长 → false', () => {
      const bar = makeBar({ open: 100, high: 101, low: 98, close: 102 });
      expect(isHammer(bar)).toBe(false);
    });

    it('一字板（range=0）→ false', () => {
      const bar = makeBar({ open: 100, high: 100, low: 100, close: 100 });
      expect(isHammer(bar)).toBe(false);
    });

    // 【新增】对齐最新逻辑：支持 body=0 的蜻蜓十字
    it('实体为0的蜻蜓十字（上影线极短，下影线长）→ true', () => {
      const bar = makeBar({ open: 100, high: 100, low: 90, close: 100 });
      expect(isHammer(bar)).toBe(true);
    });

    it('实体为0的普通十字星（上下影线均长）→ false', () => {
      const bar = makeBar({ open: 100, high: 110, low: 90, close: 100 });
      expect(isHammer(bar)).toBe(false);
    });

    it('含 NaN 数据 → false', () => {
      const bar = [1700000000, 100, NaN, 95, 102, 1000000] as unknown as OHLCVArray;
      expect(isHammer(bar)).toBe(false);
    });

    it('high < low 无效数据 → false', () => {
      const bar = makeBar({ open: 100, high: 90, low: 95, close: 102 });
      expect(isHammer(bar)).toBe(false);
    });

    it('null bar → false', () => {
      expect(isHammer(null as unknown as OHLCVArray)).toBe(false);
    });
  });

  describe('isBullishEngulfing', () => {
    // 【修改】对齐最新逻辑：完全包裹且当前实体 > 前一根实体
    it('标准看涨吞没（完全包裹且实体更大）→ true', () => {
      const prev = makeBar({ open: 105, high: 106, low: 100, close: 100 }); // body=5
      const curr = makeBar({ open: 99, high: 108, low: 98, close: 108 });  // body=9, 包裹[100,105]
      expect(isBullishEngulfing(prev, curr)).toBe(true);
    });

    // 【新增】拦截并列线
    it('当前实体完全包裹但大小相等（并列线）→ false', () => {
      const prev = makeBar({ open: 105, high: 106, low: 100, close: 100 }); // body=5
      const curr = makeBar({ open: 100, high: 106, low: 99, close: 105 });  // body=5
      expect(isBullishEngulfing(prev, curr)).toBe(false);
    });

    it('前日非阴线 → false', () => {
      const prev = makeBar({ open: 100, high: 106, low: 99, close: 105 });
      const curr = makeBar({ open: 99, high: 108, low: 98, close: 108 });
      expect(isBullishEngulfing(prev, curr)).toBe(false);
    });

    it('当日非阳线 → false', () => {
      const prev = makeBar({ open: 105, high: 106, low: 100, close: 100 });
      const curr = makeBar({ open: 108, high: 109, low: 98, close: 99 });
      expect(isBullishEngulfing(prev, curr)).toBe(false);
    });

    it('当日开盘 > 前日实体底（未完全低开包裹）→ false', () => {
      const prev = makeBar({ open: 105, high: 106, low: 100, close: 100 });
      const curr = makeBar({ open: 102, high: 108, low: 99, close: 108 }); // open 102 > 100
      expect(isBullishEngulfing(prev, curr)).toBe(false);
    });

    it('prev 无效 → false', () => {
      const prev = [1700000000, 105, NaN, 100, 100, 0] as unknown as OHLCVArray;
      const curr = makeBar({ open: 99, high: 108, low: 98, close: 108 });
      expect(isBullishEngulfing(prev, curr)).toBe(false);
    });
  });

  describe('isBearishEngulfing', () => {
    it('标准看跌吞没（完全包裹且实体更大）→ true', () => {
      const prev = makeBar({ open: 100, high: 108, low: 99, close: 105 }); // body=5
      const curr = makeBar({ open: 106, high: 109, low: 98, close: 98 });  // body=8, 包裹[100,105]
      expect(isBearishEngulfing(prev, curr)).toBe(true);
    });

    it('当前实体完全包裹但大小相等（并列线）→ false', () => {
      const prev = makeBar({ open: 100, high: 106, low: 99, close: 105 }); // body=5
      const curr = makeBar({ open: 105, high: 108, low: 98, close: 100 }); // body=5
      expect(isBearishEngulfing(prev, curr)).toBe(false);
    });

    it('前日非阳线 → false', () => {
      const prev = makeBar({ open: 105, high: 106, low: 99, close: 100 });
      const curr = makeBar({ open: 106, high: 109, low: 98, close: 98 });
      expect(isBearishEngulfing(prev, curr)).toBe(false);
    });
  });

  describe('isMorningStar', () => {
    it('标准早晨之星（不要求跳空）→ true', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 }); // 阴线 body=10
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 }); // 十字
      const b3 = makeBar({ open: 101, high: 108, low: 100, close: 108 });  // 阳线，穿透 100+10*0.3=103
      expect(isMorningStar(b1, b2, b3)).toBe(true);
    });

    // 【修改】对齐最新逻辑：默认不要求跳空
    it('bar2 未跳空（实体与bar1重叠）→ true', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 101, high: 102, low: 100, close: 101 }); // 未跳空
      const b3 = makeBar({ open: 103, high: 108, low: 102, close: 107 });
      expect(isMorningStar(b1, b2, b3)).toBe(true);
    });

    it('bar3 强势突破（超过bar1实体顶）→ true', () => {
      const b1 = makeBar({ open: 110, high: 116, low: 100, close: 100 }); // body=10, range=16, ratio=0.625
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 });
      const b3 = makeBar({ open: 101, high: 115, low: 100, close: 115 });  // close=115 > 110
      expect(isMorningStar(b1, b2, b3)).toBe(true);
    });

    it('bar3 穿透不足（<30%）→ false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 }); // 穿透目标 103
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 });
      const b3 = makeBar({ open: 100, high: 103, low: 99, close: 102 });   // close < 103
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });

    it('启用 requireGap，满足跳空 → true', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 });
      const b3 = makeBar({ open: 103, high: 109, low: 102, close: 108 });
      expect(isMorningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(true);
    });

    it('启用 requireGap，bar2 未跳空 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 101, high: 102, low: 99, close: 101 });
      const b3 = makeBar({ open: 103, high: 109, low: 102, close: 108 });
      expect(isMorningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(false);
    });

    it('启用 requireGap，bar3 开盘未跳空 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 });
      const b3 = makeBar({ open: 101, high: 109, low: 100, close: 108 });
      expect(isMorningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(false);
    });

    it('bar2 非十字星 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 98, high: 105, low: 97, close: 105 });
      const b3 = makeBar({ open: 103, high: 109, low: 102, close: 108 });
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });

    it('bar3 非大实体 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 100 });
      const b2 = makeBar({ open: 102, high: 103, low: 101, close: 102 });
      const b3 = makeBar({ open: 103, high: 106, low: 102, close: 105 });
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });

    it('bar1 无效 → false', () => {
      const b1 = [1, 110, NaN, 100, 101, 0] as unknown as OHLCVArray;
      const b2 = makeBar({ open: 99, high: 100, low: 97, close: 99 });
      const b3 = makeBar({ open: 100, high: 108, low: 99, close: 107 });
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });

    it('bar2 无效 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 101 });
      const b2 = [2, 99, 100, NaN, 99, 0] as unknown as OHLCVArray;
      const b3 = makeBar({ open: 100, high: 108, low: 99, close: 107 });
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });

    it('bar3 无效 → false', () => {
      const b1 = makeBar({ open: 110, high: 111, low: 100, close: 101 });
      const b2 = makeBar({ open: 99, high: 100, low: 97, close: 99 });
      const b3 = [3, 100, 108, 99, NaN, 0] as unknown as OHLCVArray;
      expect(isMorningStar(b1, b2, b3)).toBe(false);
    });
  });

  describe('isEveningStar', () => {
    it('标准黄昏之星（不要求跳空）→ true', () => {
      const b1 = makeBar({ open: 100, high: 110, low: 99, close: 110 }); // 阳线 body=10
      const b2 = makeBar({ open: 108, high: 109, low: 107, close: 108 }); // 十字
      const b3 = makeBar({ open: 109, high: 110, low: 100, close: 102 });  // 阴线，穿透 110-10*0.3=107
      expect(isEveningStar(b1, b2, b3)).toBe(true);
    });

    it('bar3 强势跌破（超过bar1实体底）→ true', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 }); // body=16, range=16, ratio=1.0
      const b2 = makeBar({ open: 114, high: 115, low: 113, close: 114 });
      const b3 = makeBar({ open: 114, high: 115, low: 95, close: 95 });   // close=95 < 100
      expect(isEveningStar(b1, b2, b3)).toBe(true);
    });

    it('启用 requireGap，满足跳空 → true', () => {
      const b1 = makeBar({ open: 100, high: 120, low: 99, close: 120 }); // body=20, range=21, ratio≈0.95
      const b2 = makeBar({ open: 110, high: 112, low: 108, close: 110 }); // doji, high=112 < 120 (跳空向下)
      const b3 = makeBar({ open: 109, high: 110, low: 90, close: 90 });   // open=109 < 110 (跳空向下)
      expect(isEveningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(true);
    });

    it('启用 requireGap，bar2 未跳空 → false', () => {
      const b1 = makeBar({ open: 100, high: 110, low: 99, close: 110 });
      const b2 = makeBar({ open: 109, high: 110, low: 108, close: 109 });
      const b3 = makeBar({ open: 111, high: 112, low: 100, close: 101 });
      expect(isEveningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(false);
    });

    it('启用 requireGap，bar3 开盘未跳空 → false', () => {
      const b1 = makeBar({ open: 100, high: 120, low: 99, close: 120 }); // bar1.close=120
      const b2 = makeBar({ open: 110, high: 112, low: 108, close: 110 }); // bar2.high=112 < 120 ✅
      const b3 = makeBar({ open: 112, high: 113, low: 90, close: 90 });   // bar3.open=112 >= 110 ❌
      expect(isEveningStar(b1, b2, b3, 0.3, 0.1, 0.6, true)).toBe(false);
    });

    it('bar2 非十字星 → false', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 });
      const b2 = makeBar({ open: 110, high: 120, low: 109, close: 120 }); // 实体 10，振幅 11，比例 0.9 非十字星
      const b3 = makeBar({ open: 114, high: 115, low: 95, close: 95 });
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar3 非大实体 → false', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 });
      const b2 = makeBar({ open: 114, high: 115, low: 113, close: 114 });
      const b3 = makeBar({ open: 114, high: 115, low: 108, close: 113 }); // 实体 1，振幅 7，比例 0.14 < 0.6
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar3 非阴线 → false', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 });
      const b2 = makeBar({ open: 114, high: 115, low: 113, close: 114 });
      const b3 = makeBar({ open: 105, high: 115, low: 104, close: 114 }); // 阳线
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar1 一字板（range=0，非大实体）→ false', () => {
      const b1 = makeBar({ open: 100, high: 100, low: 100, close: 100 });
      const b2 = makeBar({ open: 114, high: 115, low: 113, close: 114 });
      const b3 = makeBar({ open: 114, high: 115, low: 95, close: 95 });
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar2 一字板（range=0，十字星）→ 形态继续判定', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 });
      const b2 = makeBar({ open: 114, high: 114, low: 114, close: 114 }); // range=0 → doji
      const b3 = makeBar({ open: 114, high: 115, low: 95, close: 95 });
      expect(isEveningStar(b1, b2, b3)).toBe(true);
    });

    it('bar1 无效 → false', () => {
      const b1 = [1, 100, NaN, 99, 109, 0] as unknown as OHLCVArray;
      const b2 = makeBar({ open: 110, high: 112, low: 109, close: 111 });
      const b3 = makeBar({ open: 109, high: 110, low: 100, close: 101 });
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar2 无效 → false', () => {
      const b1 = makeBar({ open: 100, high: 110, low: 99, close: 109 });
      const b2 = [2, 110, 112, NaN, 111, 0] as unknown as OHLCVArray;
      const b3 = makeBar({ open: 109, high: 110, low: 100, close: 101 });
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });

    it('bar3 无效 → false', () => {
      const b1 = makeBar({ open: 100, high: 110, low: 99, close: 109 });
      const b2 = makeBar({ open: 110, high: 112, low: 109, close: 111 });
      const b3 = [3, 109, 110, 100, NaN, 0] as unknown as OHLCVArray;
      expect(isEveningStar(b1, b2, b3)).toBe(false);
    });
  });

  describe('detectAllPatterns', () => {
    it('空数组 → 空结果', () => {
      const result = detectAllPatterns('TEST', []);
      expect(result.code).toBe('TEST');
      expect(result.hits).toEqual([]);
    });

    it('1根K线（锤子线）→ 只检测到锤子线', () => {
      const bars = [makeBar({ open: 100, high: 102.1, low: 95, close: 102 })];
      const result = detectAllPatterns('TEST', bars);
      expect(result.hits).toContain('hammer');
      expect(result.hits).not.toContain('bullish_engulfing');
    });

    // 【新增】验证窗口语义修正：lookbackDays=2 时，3根K线的晨星不应被检测
    it('lookbackDays=2 时，完整晨星形态不应被检测（窗口语义严格）', () => {
      const bars = [
        makeBar({ open: 110, high: 111, low: 100, close: 100 }),
        makeBar({ open: 102, high: 103, low: 101, close: 102 }),
        makeBar({ open: 101, high: 108, low: 100, close: 108 }),
      ];
      const result = detectAllPatterns('TEST', bars, { lookbackDays: 2 });
      expect(result.hits).not.toContain('morning_star');
    });

    it('2根K线（看跌吞没）→ 检测到看跌吞没', () => {
      const prev = makeBar({ open: 100, high: 108, low: 99, close: 108 }); // body=8, 阳线
      const curr = makeBar({ open: 109, high: 110, low: 95, close: 95 }); // body=14 > 8, 阴线
      const result = detectAllPatterns('TEST', [prev, curr]);
      expect(result.hits).toContain('bearish_engulfing');
      expect(result.hitDays.bearish_engulfing).toEqual([1]);
    });

    it('3根K线（黄昏之星）→ 检测到黄昏之星', () => {
      const b1 = makeBar({ open: 100, high: 116, low: 100, close: 116 }); // 大阳线
      const b2 = makeBar({ open: 114, high: 115, low: 113, close: 114 }); // 十字星
      const b3 = makeBar({ open: 114, high: 115, low: 95, close: 95 }); // 大阴线
      const result = detectAllPatterns('TEST', [b1, b2, b3]);
      expect(result.hits).toContain('evening_star');
      expect(result.hitDays.evening_star).toEqual([2]);
    });

    it('lookbackDays 参数生效', () => {
      const bars = [
        makeBar({ open: 100, high: 102.1, low: 95, close: 102 }),
        makeBar({ open: 105, high: 106, low: 100, close: 101 }),
        makeBar({ open: 100, high: 108, low: 99, close: 107 }),
      ];
      const result = detectAllPatterns('TEST', bars, { lookbackDays: 1 });
      expect(result.hitDays.hammer.length).toBe(0);
    });

    it('多形态同时命中', () => {
      const prev = makeBar({ open: 105, high: 106, low: 100, close: 100 }); // body=5
      const curr = makeBar({ open: 99, high: 109, low: 80, close: 108 }); // body=9, lower=19 >= 9*2=18
      const result = detectAllPatterns('TEST', [prev, curr]);
      expect(result.hits).toContain('bullish_engulfing');
      expect(result.hits).toContain('hammer');
    });

    it('含无效数据 → 跳过无效bar，不崩溃', () => {
      const bars = [
        makeBar({ open: 105, high: 106, low: 100, close: 100 }),
        [1, NaN, NaN, NaN, NaN, 0] as unknown as OHLCVArray,
        makeBar({ open: 99, high: 108, low: 98, close: 108 }),
      ];
      expect(() => detectAllPatterns('TEST', bars)).not.toThrow();
    });

    it('自定义阈值：放宽大实体比例 → 原不通过的变为通过', () => {
      const bars = [
        makeBar({ open: 110, high: 111, low: 100, close: 100 }), // body=10, range=11, ratio=0.91
        makeBar({ open: 105, high: 106, low: 104, close: 105 }), // body=1, range=2, ratio=0.5 (十字星)
        makeBar({ open: 104, high: 105, low: 100, close: 105 }), // body=1, range=5, ratio=0.2 (非大实体)
      ];
      const resultDefault = detectAllPatterns('TEST', bars);
      const resultRelaxed = detectAllPatterns('TEST', bars, { lookbackDays: 3, largeBodyRatio: 0.15 });
      expect(resultDefault.hits).not.toContain('morning_star');
      expect(resultRelaxed.hits).toContain('morning_star');
    });

    it('targetPatterns 提前退出：找到目标后停止扫描', () => {
      const bars = [
        makeBar({ open: 100, high: 102.1, low: 95, close: 102 }), // 锤子线 index 0
        makeBar({ open: 105, high: 106, low: 100, close: 101 }),
        makeBar({ open: 99, high: 108, low: 98, close: 108 }), // 锤子线 + 看涨吞没 index 2
      ];
      const result = detectAllPatterns('TEST', bars, { lookbackDays: 3 }, ['hammer']);
      expect(result.hits).toContain('hammer');
      expect(result.hitDays.hammer.length).toBe(1);
    });

    it('requireGapForStar 配置项生效', () => {
      const bars = [
        makeBar({ open: 110, high: 111, low: 100, close: 100 }),
        makeBar({ open: 98, high: 99, low: 97, close: 98 }),
        makeBar({ open: 99, high: 108, low: 98, close: 107 }),
      ];
      const resultNoGap = detectAllPatterns('TEST', bars, { lookbackDays: 3, requireGapForStar: false });
      const resultWithGap = detectAllPatterns('TEST', bars, { lookbackDays: 3, requireGapForStar: true });
      expect(resultNoGap.hits).toContain('morning_star');
      expect(resultWithGap.hits).not.toContain('morning_star');
    });
  });

  describe('hasAnyPattern', () => {
    it('有命中 → true', () => {
      const bars = [makeBar({ open: 100, high: 102.1, low: 95, close: 102 })];
      expect(hasAnyPattern('TEST', bars, ['hammer'])).toBe(true);
    });

    // 【新增】验证空数组保护逻辑
    it('传入空目标数组 [] → 返回 false', () => {
      const bars = [makeBar({ open: 100, high: 102.1, low: 95, close: 102 })];
      expect(hasAnyPattern('TEST', bars, [])).toBe(false);
    });

    it('lookbackDays 参数传递正确', () => {
      const bars = [
        makeBar({ open: 100, high: 102.1, low: 95, close: 102 }),
        makeBar({ open: 100, high: 105, low: 95, close: 102 }),
      ];
      expect(hasAnyPattern('TEST', bars, ['hammer'], 1)).toBe(false);
      expect(hasAnyPattern('TEST', bars, ['hammer'], 2)).toBe(true);
    });
  });
});