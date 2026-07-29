import { describe, it, expect } from 'vitest';
import {
  MARKET_INDICATORS,
  FINANCIAL_INDICATORS,
  TECHNICAL_INDICATORS,
  FACTOR_CONFIG,
  type IndicatorItem,
  type FactorItem,
} from '@/features/stock-picker/config/indicatorConfig';

describe('indicatorConfig', () => {
  describe('MARKET_INDICATORS', () => {
    it('包含行情指标基础字段', () => {
      expect(MARKET_INDICATORS.length).toBeGreaterThan(0);
      MARKET_INDICATORS.forEach((indicator: IndicatorItem) => {
        expect(indicator).toHaveProperty('id');
        expect(indicator).toHaveProperty('label');
        expect(indicator).toHaveProperty('field');
        expect(typeof indicator.id).toBe('string');
        expect(typeof indicator.label).toBe('string');
      });
    });

    it('id 唯一', () => {
      const ids = MARKET_INDICATORS.map((i) => i.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it('label 唯一', () => {
      const labels = MARKET_INDICATORS.map((i) => i.label);
      expect(new Set(labels).size).toBe(labels.length);
    });

    it('field 不为空（行情指标都映射到后端字段）', () => {
      MARKET_INDICATORS.forEach((indicator) => {
        expect(indicator.field).not.toBeNull();
        expect(indicator.field).not.toBe('');
      });
    });

    it('必含核心指标：市值/价格/换手率', () => {
      const ids = MARKET_INDICATORS.map((i) => i.id);
      expect(ids).toContain('market_cap');
      expect(ids).toContain('price');
      expect(ids).toContain('turnover');
    });
  });

  describe('FINANCIAL_INDICATORS', () => {
    it('包含财务指标基础字段', () => {
      expect(FINANCIAL_INDICATORS.length).toBeGreaterThan(0);
      FINANCIAL_INDICATORS.forEach((indicator: IndicatorItem) => {
        expect(indicator).toHaveProperty('id');
        expect(indicator).toHaveProperty('label');
        expect(indicator).toHaveProperty('field');
      });
    });

    it('id 唯一', () => {
      const ids = FINANCIAL_INDICATORS.map((i) => i.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it('label 唯一', () => {
      const labels = FINANCIAL_INDICATORS.map((i) => i.label);
      expect(new Set(labels).size).toBe(labels.length);
    });
  });

  describe('TECHNICAL_INDICATORS', () => {
    it('包含技术指标基础字段', () => {
      expect(TECHNICAL_INDICATORS.length).toBeGreaterThan(0);
      TECHNICAL_INDICATORS.forEach((indicator) => {
        expect(indicator).toHaveProperty('id');
        expect(indicator).toHaveProperty('label');
        expect(indicator).toHaveProperty('options');
      });
    });

    it('id 唯一', () => {
      const ids = TECHNICAL_INDICATORS.map((i) => i.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it('field 为 undefined（技术指标由配置面板单独管理，无单一后端字段）', () => {
      TECHNICAL_INDICATORS.forEach((indicator) => {
        expect(indicator.field).toBeUndefined();
      });
    });
  });

  describe('FACTOR_CONFIG', () => {
    it('权重和为 100', () => {
      const totalWeight = FACTOR_CONFIG.reduce(
        (sum: number, f: FactorItem) => sum + f.defaultWeight,
        0
      );
      expect(totalWeight).toBe(100);
    });

    it('每个因子有 id/label/defaultWeight/color 字段', () => {
      FACTOR_CONFIG.forEach((factor: FactorItem) => {
        expect(factor).toHaveProperty('id');
        expect(factor).toHaveProperty('label');
        expect(factor).toHaveProperty('defaultWeight');
        expect(factor).toHaveProperty('color');
        expect(typeof factor.id).toBe('string');
        expect(typeof factor.label).toBe('string');
        expect(typeof factor.defaultWeight).toBe('number');
      });
    });

    it('color 是有效的 6 位 hex 值', () => {
      FACTOR_CONFIG.forEach((factor) => {
        expect(factor.color).toMatch(/^#[0-9A-Fa-f]{6}$/);
      });
    });

    it('id 唯一', () => {
      const ids = FACTOR_CONFIG.map((f) => f.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it('defaultWeight 在 0-100 之间', () => {
      FACTOR_CONFIG.forEach((factor) => {
        expect(factor.defaultWeight).toBeGreaterThanOrEqual(0);
        expect(factor.defaultWeight).toBeLessThanOrEqual(100);
      });
    });
  });

  describe('IndicatorItem 接口', () => {
    it('disabled 字段可选（默认 undefined）', () => {
      // 当前配置中所有指标都未禁用，验证默认值
      const all = [...MARKET_INDICATORS, ...FINANCIAL_INDICATORS, ...TECHNICAL_INDICATORS];
      all.forEach((indicator) => {
        // 关键：未设置时应为 undefined 或 false
        expect(indicator.disabled === undefined || indicator.disabled === false).toBe(true);
      });
    });
  });
});
