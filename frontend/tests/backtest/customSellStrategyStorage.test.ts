// tests/backtest/customSellStrategyStorage.test.ts — 自编卖出策略存储层测试
// 覆盖：CRUD、软删除、重名去重、软删除记录不阻挡同名新增

import { describe, it, expect, beforeEach } from 'vitest';
import {
  MOCK_USER_ID,
  listCustomSellStrategies,
  listAllCustomSellStrategies,
  saveCustomSellStrategy,
  removeCustomSellStrategy,
  isSellStrategyNameTaken,
  validateSellStrategyFormula,
} from '../../src/features/backtest/utils/customSellStrategyStorage';
import type { CustomSellStrategy } from '../../src/features/backtest/utils/customSellStrategyStorage';

function makeStrategy(overrides: Partial<CustomSellStrategy> = {}): Omit<
  CustomSellStrategy, 'id' | 'createdAt' | 'updatedAt' | 'userId' | 'deleted'
> & { id?: string } {
  return {
    name: '跌破5日均线卖出',
    formula: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [1 if i % 2 == 0 else 0 for i in range(len(close_prices))]',
    operator: '>=',
    defaultThreshold: 1,
    description: '测试策略',
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  // 清掉内存降级残留
  listCustomSellStrategies();
});

describe('customSellStrategyStorage', () => {
  it('新增后 list 能查到且字段完整', () => {
    const created = saveCustomSellStrategy(makeStrategy());
    expect(created.id).toBeTruthy();
    expect(listCustomSellStrategies()).toHaveLength(1);
    expect(listCustomSellStrategies()[0].name).toBe('跌破5日均线卖出');
    expect(listCustomSellStrategies()[0].deleted).toBe(false);
    expect(created.userId).toBe(MOCK_USER_ID);
  });

  it('重名保存抛错（不写入）', () => {
    saveCustomSellStrategy(makeStrategy({ name: '策略A' }));
    expect(() => saveCustomSellStrategy(makeStrategy({ name: '策略A' }))).toThrow(/已存在/);
  });

  it('软删除后 list 隐藏但记录保留（listAll 可见）', () => {
    const created = saveCustomSellStrategy(makeStrategy());
    expect(removeCustomSellStrategy(created.id)).toBe(true);
    expect(listCustomSellStrategies()).toHaveLength(0);
    expect(listAllCustomSellStrategies()).toHaveLength(1);
    expect(listAllCustomSellStrategies()[0].deleted).toBe(true);
  });

  it('软删除后同名可重新创建（软删除不阻挡同名新增）', () => {
    const created = saveCustomSellStrategy(makeStrategy({ name: '策略B' }));
    removeCustomSellStrategy(created.id);
    const recreated = saveCustomSellStrategy(makeStrategy({ name: '策略B' }));
    expect(recreated.id).not.toBe(created.id);
    expect(listCustomSellStrategies()).toHaveLength(1);
  });

  it('更新保留 createdAt 更新 updatedAt', async () => {
    const created = saveCustomSellStrategy(makeStrategy({ name: '策略C' }));
    const originalCreated = created.createdAt;
    await new Promise((r) => setTimeout(r, 5));
    const updated = saveCustomSellStrategy({ ...created, description: '改' });
    expect(updated.createdAt).toBe(originalCreated);
    expect(updated.updatedAt).not.toBe(originalCreated);
  });

  it('isSellStrategyNameTaken 排除软删除记录', () => {
    const created = saveCustomSellStrategy(makeStrategy({ name: '策略D' }));
    removeCustomSellStrategy(created.id);
    expect(isSellStrategyNameTaken('策略D')).toBe(false);
    expect(isSellStrategyNameTaken('不存在的')).toBe(false);
  });

  it('公式校验：非法 calcular 签名报错、合法通过', () => {
    const bad = validateSellStrategyFormula('def foo(): pass');
    expect(bad.valid).toBe(false);

    const good = validateSellStrategyFormula(
      'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0] * len(close_prices)',
    );
    expect(good.valid).toBe(true);
  });

  it('名称校验：与自编指标同规则（无明确导出，通过 save 抛错间接验证）', () => {
    expect(() => saveCustomSellStrategy(makeStrategy({ name: 'x' }))).toThrow(/名称/);
  });
});