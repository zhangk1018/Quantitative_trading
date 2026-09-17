// tests/backtest/customSellStrategySeed.test.ts — 预置卖出策略种子测试
// 覆盖：预置创建、幂等、软删除不复活、用户同名不覆盖、公式通过校验

import { describe, it, expect, beforeEach } from 'vitest';
import {
  seedDefaultSellStrategies,
  PRESET_SELL_STRATEGIES,
} from '../../src/features/backtest/utils/customSellStrategySeed';
import {
  listCustomSellStrategies,
  listAllCustomSellStrategies,
  removeCustomSellStrategy,
  saveCustomSellStrategy,
  validateSellStrategyFormula,
} from '../../src/features/backtest/utils/customSellStrategyStorage';

beforeEach(() => {
  window.localStorage.clear();
  listCustomSellStrategies(); // 清掉内存降级残留
});

describe('customSellStrategySeed 预置卖出策略', () => {
  it('首次 seed 创建「调仓换股」「分层止盈」两条预置策略，字段完整', () => {
    seedDefaultSellStrategies();

    const all = listCustomSellStrategies();
    expect(all).toHaveLength(2);

    const names = all.map((s) => s.name);
    expect(names).toContain('调仓换股');
    expect(names).toContain('分层止盈');

    for (const s of all) {
      expect(s.deleted).toBe(false);
      expect(s.formula).toContain('def calculate(open_prices, high_prices, low_prices, close_prices, volumes)');
      expect(s.operator).toBe('>');
      expect(s.defaultThreshold).toBe(0);
      expect(s.description.length).toBeGreaterThan(0);
    }
  });

  it('seed 幂等：重复调用不重复写入', () => {
    seedDefaultSellStrategies();
    seedDefaultSellStrategies();
    seedDefaultSellStrategies();
    expect(listCustomSellStrategies()).toHaveLength(2);
  });

  it('用户自定义策略不被影响，预置策略追加', () => {
    saveCustomSellStrategy({
      name: '我的策略',
      formula: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0] * len(close_prices)',
      operator: '>=',
      defaultThreshold: 1,
      description: 'desc',
    });
    seedDefaultSellStrategies();
    expect(listCustomSellStrategies()).toHaveLength(3);
  });

  it('用户已有同名策略（含软删除）时预置不覆盖/不复活', () => {
    // 软删除预置策略 → 用户彻底移除
    seedDefaultSellStrategies();
    const layered = listAllCustomSellStrategies().find((s) => s.name === '分层止盈')!;
    removeCustomSellStrategy(layered.id);

    // 再次 seed：分层止盈不应复活
    seedDefaultSellStrategies();
    const alive = listCustomSellStrategies();
    expect(alive.map((s) => s.name)).not.toContain('分层止盈');
    expect(alive).toHaveLength(1);
    // 软删除记录仍保留（listAll 可见）
    expect(listAllCustomSellStrategies().some((s) => s.name === '分层止盈' && s.deleted)).toBe(true);
  });

  it('两条预置公式均通过公式校验（validateSellStrategyFormula）', () => {
    expect(PRESET_SELL_STRATEGIES).toHaveLength(2);
    for (const preset of PRESET_SELL_STRATEGIES) {
      const check = validateSellStrategyFormula(preset.formula);
      expect(check.errors, `${preset.name} 公式错误: ${check.errors.join('；')}`).toEqual([]);
      expect(check.valid, `${preset.name} 公式校验未通过`).toBe(true);
    }
  });

  it('预置策略名称符合命名规范（2-30 字符）', () => {
    for (const preset of PRESET_SELL_STRATEGIES) {
      expect(preset.name.length).toBeGreaterThanOrEqual(2);
      expect(preset.name.length).toBeLessThanOrEqual(30);
    }
  });
});
