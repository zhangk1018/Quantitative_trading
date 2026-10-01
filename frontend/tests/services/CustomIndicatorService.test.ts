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