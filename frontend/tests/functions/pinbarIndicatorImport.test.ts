/**
 * 自编指标导入文件回归测试（Pinbar 关键位反转）
 *
 * 目的：确保随仓库提供的自编指标 JSON 始终能通过前端自身的导入校验
 * （字段完整性 + 名称格式 + 公式校验 + 去重逻辑），避免 K 导入时才发现失效。
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  validateFormula,
  validateIndicatorName,
  type IndicatorExportFile,
} from '@/features/stock-picker/types/customIndicator';
import { validateIndicatorData } from '@/features/stock-picker/utils/customIndicatorStorage';

const FILE = 'docs/自编指标-导入-Pinbar关键位反转.json';

function loadFile(): IndicatorExportFile {
  const raw = readFileSync(resolve(process.cwd(), FILE), 'utf-8');
  return JSON.parse(raw) as IndicatorExportFile;
}

describe('Pinbar关键位反转 导入文件', () => {
  it('JSON 结构与版本合法，且包含 1 条指标', () => {
    const file = loadFile();
    expect(file.version).toBe(1);
    expect(Array.isArray(file.indicators)).toBe(true);
    expect(file.indicators).toHaveLength(1);
  });

  it('不携带 id，确保重复导入时按名称去重（跳过而非重复新增）', () => {
    const ind = loadFile().indicators[0] as unknown as Record<string, unknown>;
    expect(ind.id).toBeUndefined();
  });

  it('字段与名称格式通过导入校验', () => {
    const file = loadFile();
    const result = validateIndicatorData(file.indicators[0], 0, new Set(), new Set());
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.duplicate).toBe(false);

    expect(validateIndicatorName(file.indicators[0].name)).toBeNull();
  });

  it('公式通过 validateFormula（签名 / 禁用关键字 / 长度 / 括号）', () => {
    const ind = loadFile().indicators[0];
    const result = validateFormula(ind.formula, ind.syntax);
    expect(result.errors).toEqual([]);
    expect(result.valid).toBe(true);
  });

  it('运算符与阈值配置符合预期（阈值 6，可上调至 7 严格全满足）', () => {
    const ind = loadFile().indicators[0];
    expect(ind.operator).toBe('>=');
    expect(ind.defaultThreshold).toBe(6);
    expect(ind.params).toEqual([]);
  });

  it('第5项为"实体吞没"口径（内包口径会与第4项假突破互斥）', () => {
    const { formula } = loadFile().indicators[0];
    expect(formula).toContain('body_top[i] >= bt2[i]');
    expect(formula).not.toContain('h[i] <= h2[i]');
  });
});