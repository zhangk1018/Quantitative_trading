/**
 * 预置自编指标种子测试（customIndicatorSeed）
 *
 * 背景：ScreenerProvider 启动时幂等种入「8条件选股改进」，
 * 保证用户首次进入即有可用指标；本文件固化其三条硬约束：
 * 1) 首次调用种入且默认阈值/算子正确
 * 2) 幂等：重复调用不重复种入
 * 3) 用户软删除后不再自动种回（软删除 = 彻底移除，不复活）
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { seed8ConditionIndicator } from '@/features/stock-picker/utils/customIndicatorSeed';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';

const SEED_NAME = '8条件选股改进';

beforeEach(() => {
  window.localStorage.clear();
  storage.clearAllCustomIndicators();
});

describe('customIndicatorSeed — 预置「8条件选股改进」', () => {
  it('首次调用种入指标，算子 ≥ 且默认阈值 6', () => {
    seed8ConditionIndicator();

    const list = storage.listCustomIndicators();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe(SEED_NAME);
    expect(list[0].operator).toBe('>=');
    expect(list[0].defaultThreshold).toBe(6);
    expect(list[0].formula.length).toBeGreaterThan(0);
  });

  it('幂等：重复调用只保留 1 条', () => {
    seed8ConditionIndicator();
    seed8ConditionIndicator();

    expect(storage.listCustomIndicators()).toHaveLength(1);
  });

  it('用户软删除后不再自动种回', () => {
    seed8ConditionIndicator();
    const created = storage.listCustomIndicators()[0];
    storage.removeCustomIndicator(created.id);
    expect(storage.listCustomIndicators()).toHaveLength(0);

    // 再次触发种子（如刷新页面/重进 /config）不应复活
    seed8ConditionIndicator();
    expect(storage.listCustomIndicators()).toHaveLength(0);
  });
});