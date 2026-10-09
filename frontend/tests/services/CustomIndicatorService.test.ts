/**
 * CustomIndicatorService 单测
 *
 * 覆盖 K 2026-09-29 反馈：自编指标选股「一只都不中」时，需区分
 * ① 选股条件确实太严（正常返回 0 只）
 * ② 候选股缺失 K 线（后端快照未覆盖该市场，如快照缓存按单一最新交易日加载，
 *    最新快照日滞后的市场整市被剔除）→ 必须显式报错，不得静默显示 0 只
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  CustomIndicatorService,
  meetsThreshold,
  extractCustomConditions,
  computeConditionLookback,
  type CustomCondition,
} from '@/features/stock-picker/services/CustomIndicatorService';
import type { CustomIndicator } from '@/features/stock-picker/types/customIndicator';

// 避免加载 Pyodide Worker（jsdom 无 Worker）
const { executeMock } = vi.hoisted(() => ({ executeMock: vi.fn() }));

vi.mock('@/features/strategy-backtest/utils/customIndicatorRunner', () => ({
  getCustomIndicatorRunner: () => ({
    isReady: () => true,
    init: async () => undefined,
    execute: executeMock,
  }),
}));

const SCRIPT = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    close = np.array(close_prices, dtype=float)
    return [1 for _ in close]
`;

function makeCondition(overrides: Partial<CustomCondition> = {}): CustomCondition {
  return {
    scriptId: 'ind_test',
    name: 'T1',
    formula: SCRIPT,
    operator: '>=',
    threshold: 1,
    ...overrides,
  };
}

/** 构造单只股票 OHLCV：[ts, open, high, low, close, volume] */
function bars(n = 6): number[][] {
  return Array.from({ length: n }, (_, i) => [1700000000 + i * 86400, 10, 11, 9, 10.5, 1000]);
}

describe('CustomIndicatorService', () => {
  let service: CustomIndicatorService;

  beforeEach(() => {
    service = new CustomIndicatorService();
    executeMock.mockReset();
  });

  describe('computeAndFilter — 候选股缺 K 线守卫', () => {
    it('候选股全部无 K 线时显式抛错（不得静默返回 0 只）', async () => {
      const ohlcvMap = new Map<string, number[][]>([
        ['600519', []],
        ['000001', []],
      ]);

      await expect(
        service.computeAndFilter([makeCondition()], ['600519', '000001'], ohlcvMap),
      ).rejects.toThrow(/K线数据/);

      // 守卫在脚本执行前生效，不应调用 Pyodide
      expect(executeMock).not.toHaveBeenCalled();
    });

    it('候选股 K 线完整时正常执行脚本并返回命中集合', async () => {
      const codes = ['600519', '000001'];
      const ohlcvMap = new Map<string, number[][]>(codes.map((c) => [c, bars()]));
      executeMock.mockResolvedValue(
        new Map([
          [
            'ind_test',
            {
              id: 'ind_test',
              name: 'T1',
              // 600519 末值命中，000001 末值不命中
              values: new Map<string, (number | null)[]>([
                ['600519', [0, 0, 1]],
                ['000001', [0, 0, 0]],
              ]),
              errors: [],
            },
          ],
        ]),
      );

      const { passedCodes } = await service.computeAndFilter([makeCondition()], codes, ohlcvMap);

      expect(Array.from(passedCodes)).toEqual(['600519']);
      expect(executeMock).toHaveBeenCalledTimes(1);
    });
  });

  describe('computeAndFilter — 每个指标按自身窗口切片（K 2026-10-09 多选自编指标 0 只）', () => {
    // A 公式含 100 → 窗口 105；B 公式含 10 → 窗口 15（不能被 A 拉大）
    const FORMULA_100 = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    _ = 100
    return [1 for _ in close_prices]
`;
    const FORMULA_10 = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    _ = 10
    return [1 for _ in close_prices]
`;

    it('各指标使用各自窗口，B 不被 A 的窗口拉大；组合结果 = 各单独结果交集', async () => {
      const codes = ['600519', '000001'];
      const longBars = Array.from({ length: 300 }, (_, i) =>
        [1700000000 + i * 86400, 10, 11, 9, 10.5, 1000]);
      const ohlcvMap = new Map<string, number[][]>(codes.map((c) => [c, longBars]));

      const condA = makeCondition({ scriptId: 'ind_a', name: 'A', formula: FORMULA_100 });
      const condB = makeCondition({ scriptId: 'ind_b', name: 'B', formula: FORMULA_10 });

      const captured: { id: string; windowLen: number }[] = [];
      executeMock.mockImplementation(async (defs: { id: string; allOhlcv: Map<string, number[][]> }[]) => {
        const s = defs[0];
        captured.push({ id: s.id, windowLen: s.allOhlcv.get('600519')?.length ?? 0 });
        // A/B 都：600519 命中、000001 不命中
        return new Map([[s.id, {
          id: s.id,
          name: s.id,
          values: new Map<string, (number | null)[]>([
            ['600519', [1]],
            ['000001', [0]],
          ]),
          errors: [],
        }]]);
      });

      const { passedCodes } = await service.computeAndFilter([condA, condB], codes, ohlcvMap);

      expect(Array.from(passedCodes)).toEqual(['600519']);
      // 关键：B 的窗口为 15，未因与 A 组合被放大到 105
      expect(captured).toEqual([
        { id: 'ind_a', windowLen: 105 },
        { id: 'ind_b', windowLen: 15 },
      ]);
    });

    it('computeConditionLookback 按公式最大数字 +5，无数字回退 35', () => {
      expect(computeConditionLookback({ formula: FORMULA_100 })).toBe(105);
      expect(computeConditionLookback({ formula: FORMULA_10 })).toBe(15);
      expect(computeConditionLookback({ formula: 'return result' })).toBe(35);
    });
  });

  describe('meetsThreshold', () => {
    it('range 需要区间阈值，标量阈值判为不命中', () => {
      expect(meetsThreshold(5, 'range', [1, 10])).toBe(true);
      expect(meetsThreshold(11, 'range', [1, 10])).toBe(false);
      expect(meetsThreshold(5, 'range', 5)).toBe(false);
    });

    it('cross_up / cross_down 暂不支持，返回 false', () => {
      expect(meetsThreshold(5, 'cross_up', [1, 10])).toBe(false);
      expect(meetsThreshold(5, 'cross_down', [1, 10])).toBe(false);
    });
  });

  describe('extractCustomConditions', () => {
    const indicator: CustomIndicator = {
      id: 'ind_a',
      userId: 'mock_user_default',
      name: 'A',
      category: 'trend',
      formula: SCRIPT,
      syntax: 'python_talib',
      params: [],
      operator: '>=',
      defaultThreshold: 1,
      description: '',
      visibility: 'private',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
    };

    it('仅提取 source=custom 且指标存在（未软删除）的条件', () => {
      const result = extractCustomConditions(
        [
          { source: 'system', fieldKey: 'rsi_oversold' },
          { source: 'custom', sourceId: 'ind_a' },
          { source: 'custom', sourceId: 'ind_missing' },
        ],
        [indicator],
      );

      expect(result).toHaveLength(1);
      expect(result[0].scriptId).toBe('ind_a');
    });

    it('指标被软删除时不提取', () => {
      const result = extractCustomConditions(
        [{ source: 'custom', sourceId: 'ind_a' }],
        [{ ...indicator, deleted: true }],
      );

      expect(result).toHaveLength(0);
    });
  });
});