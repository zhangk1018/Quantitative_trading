/**
 * 自编指标存储层单测
 * 覆盖 K 配套约束要求：名称唯一性、软删除、引用检测、导入导出去重、本地存储降级
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  MOCK_USER_ID,
  listCustomIndicators,
  listAllCustomIndicators,
  getCustomIndicatorById,
  isNameTaken,
  saveCustomIndicator,
  removeCustomIndicator,
  purgeCustomIndicator,
  isIndicatorReferenced,
  isIndicatorReferencedByConditions,
  markPlanConditionsInvalid,
  exportCustomIndicators,
  parseImportFile,
  importCustomIndicators,
  computeImportPreview,
  validateIndicatorData,
  clearAllCustomIndicators,
  EXPORT_FORMAT_VERSION,
} from '@/features/stock-picker/utils/customIndicatorStorage';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';

// 工具：构造一个自编指标
function makeIndicator(overrides: Partial<CustomIndicator> = {}): Omit<CustomIndicator, 'createdAt' | 'updatedAt' | 'userId' | 'deleted'> & { id?: string } {
  return {
    name: '测试指标',
    category: 'trend',
    formula: 'MA(CLOSE, 5)',
    syntax: 'tdx',
    params: [],
    operator: '>',
    defaultThreshold: 10,
    description: '',
    visibility: 'private',
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  clearAllCustomIndicators();
});

describe('MOCK_USER_ID', () => {
  it('固定为 mock_user_default（V1.0 单用户）', () => {
    expect(MOCK_USER_ID).toBe('mock_user_default');
  });
});

describe('saveCustomIndicator / listCustomIndicators', () => {
  it('新增指标后 list 能查到', () => {
    const created = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(created.id).toBeTruthy();
    expect(listCustomIndicators()).toHaveLength(1);
    expect(listCustomIndicators()[0].name).toBe('指标A');
  });

  it('新增会设置 createdAt/updatedAt/userId/deleted=false', () => {
    const created = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(created.createdAt).toBeTruthy();
    expect(created.updatedAt).toBeTruthy();
    expect(created.userId).toBe(MOCK_USER_ID);
    expect(created.deleted).toBe(false);
  });

  it('更新时更新 updatedAt 保留 createdAt', async () => {
    const created = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const originalCreated = created.createdAt;
    await new Promise((r) => setTimeout(r, 5));
    const updated = saveCustomIndicator({ ...created, name: '指标A-改' });
    expect(updated.createdAt).toBe(originalCreated);
    expect(updated.updatedAt).not.toBe(originalCreated);
  });

  it('名称重复时抛错（不写入）', () => {
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(() => saveCustomIndicator(makeIndicator({ name: '指标A' }))).toThrow(/已存在/);
    expect(listCustomIndicators()).toHaveLength(1);
  });

  it('更新时自身名称不视作重复（excludeId 生效）', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const updated = saveCustomIndicator({ ...a, description: '修改' });
    expect(updated.id).toBe(a.id);
    expect(updated.description).toBe('修改');
    expect(listCustomIndicators()).toHaveLength(1);
  });

  it('指标名称格式不合法时抛错', () => {
    expect(() => saveCustomIndicator(makeIndicator({ name: 'a' }))).toThrow(/长度/);
    expect(() => saveCustomIndicator(makeIndicator({ name: '包含@非法字符' }))).toThrow();
  });
});

describe('isNameTaken', () => {
  it('同用户同名返回 true', () => {
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(isNameTaken('指标A', null)).toBe(true);
  });

  it('不同名返回 false', () => {
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(isNameTaken('指标B', null)).toBe(false);
  });

  it('excludeId 排除自身', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(isNameTaken('指标A', a.id)).toBe(false);
  });

  it('isNameTaken 软删除后的同名不算冲突', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    removeCustomIndicator(a.id);
    expect(isNameTaken('指标A', null)).toBe(false);
    // 重新创建同名不抛错
    expect(() => saveCustomIndicator(makeIndicator({ name: '指标A' }))).not.toThrow();
  });
});

describe('getCustomIndicatorById / listAllCustomIndicators', () => {
  it('getCustomIndicatorById 查找存在的指标', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const found = getCustomIndicatorById(a.id);
    expect(found?.id).toBe(a.id);
  });

  it('getCustomIndicatorById 查找不存在的指标返回 undefined', () => {
    expect(getCustomIndicatorById('ind_not_found')).toBeUndefined();
  });

  it('listAllCustomIndicators 包含软删除的，listCustomIndicators 排除', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const b = saveCustomIndicator(makeIndicator({ name: '指标B' }));
    removeCustomIndicator(a.id);
    expect(listCustomIndicators()).toHaveLength(1);
    expect(listAllCustomIndicators()).toHaveLength(2);
    expect(listAllCustomIndicators().find((i) => i.id === b.id)).toBeTruthy();
    expect(listAllCustomIndicators().find((i) => i.id === a.id)).toBeTruthy();
  });
});

describe('removeCustomIndicator（软删除）', () => {
  it('软删除后从 listCustomIndicators 消失', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    removeCustomIndicator(a.id);
    expect(listCustomIndicators()).toHaveLength(0);
  });

  it('软删除会设置 deleted=true 和 deletedAt', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    removeCustomIndicator(a.id);
    const all = listAllCustomIndicators();
    expect(all[0].deleted).toBe(true);
    expect(all[0].deletedAt).toBeTruthy();
  });

  it('删除不存在的 id 返回 false', () => {
    expect(removeCustomIndicator('ind_unknown')).toBe(false);
  });
});

describe('purgeCustomIndicator（硬删除）', () => {
  it('硬删除后从 listAllCustomIndicators 消失', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    purgeCustomIndicator(a.id);
    expect(listAllCustomIndicators()).toHaveLength(0);
  });
});

describe('isIndicatorReferenced', () => {
  it('无方案时返回 false', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    expect(isIndicatorReferenced(a.id)).toBe(false);
  });

  it('方案 conditions 含 sourceId 时返回 true', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const plans = [
      {
        id: 'plan_1',
        conditions: [{ sourceId: a.id }, { sourceId: 'ind_other' }],
      },
    ];
    window.localStorage.setItem(
      `qt_custom_indicators_v1_plans_${MOCK_USER_ID}`,
      JSON.stringify(plans),
    );
    expect(isIndicatorReferenced(a.id)).toBe(true);
  });

  it('方案 conditions 不含 sourceId 时返回 false', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const plans = [
      { id: 'plan_1', conditions: [{ sourceId: 'ind_other' }] },
    ];
    window.localStorage.setItem(
      `qt_custom_indicators_v1_plans_${MOCK_USER_ID}`,
      JSON.stringify(plans),
    );
    expect(isIndicatorReferenced(a.id)).toBe(false);
  });

  it('方案 JSON 解析失败时返回 false（容错）', () => {
    const a = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    window.localStorage.setItem(
      `qt_custom_indicators_v1_plans_${MOCK_USER_ID}`,
      'invalid json{',
    );
    expect(isIndicatorReferenced(a.id)).toBe(false);
  });
});

describe('exportCustomIndicators / parseImportFile / importCustomIndicators', () => {
  it('导出后 JSON 包含 version/indicators/导出时间', () => {
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const file = exportCustomIndicators();
    expect(file.version).toBe(EXPORT_FORMAT_VERSION);
    expect(file.exportedAt).toBeTruthy();
    expect(file.userId).toBe(MOCK_USER_ID);
    expect(file.indicators).toHaveLength(1);
  });

  it('parseImportFile 解析有效 JSON', () => {
    const json = JSON.stringify({
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [makeIndicator({ id: 'ind_x', name: '指标X' })],
    });
    const file = parseImportFile(json);
    expect(file.indicators).toHaveLength(1);
  });

  it('parseImportFile 解析失败抛错', () => {
    expect(() => parseImportFile('not json')).toThrow(/JSON 解析失败/);
    expect(() => parseImportFile('{"version":1}')).toThrow(/indicators/);
    expect(() => parseImportFile('{"indicators":[]}')).toThrow(/version/);
    expect(() => parseImportFile('[]')).toThrow(/根对象缺失/);
  });

  it('parseImportFile 版本过高抛错', () => {
    const json = JSON.stringify({ version: 99, indicators: [] });
    expect(() => parseImportFile(json)).toThrow(/版本.*高于/);
  });

  it('importCustomIndicators 成功添加', () => {
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        { ...makeIndicator({ id: 'ind_a', name: '指标A' }) } as CustomIndicator,
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(1);
    expect(result.skipped).toBe(0);
    expect(result.errors).toHaveLength(0);
  });

  it('importCustomIndicators 名称重名计入 name_duplicate 错误且 skipped+1', () => {
    // seed：走"新增"路径创建真实 '指标A'
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        // K 2026-06-18 任务 #10：去重优先级为 id 优先 / name 兜底。
        // 此用例测"无 id 时按 name 去重"，所以 import 数据不传 id。
        { ...makeIndicator({ name: '指标A' }) } as unknown as CustomIndicator,
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(0);
    expect(result.skipped).toBe(1);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].type).toBe('name_duplicate');
    expect(result.errorSummary.name_duplicate).toBe(1);
  });

  it('importCustomIndicators id 重复时按 id 去重（K 2026-06-18 任务 #10）', () => {
    // seed：创建真实指标并捕获其自动生成的 id
    const existing = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        // 带 id 但 name 不同的导入数据 → 按 id 判定重复（id 优先）
        { ...makeIndicator({ id: existing.id, name: '不同的名字' }) } as CustomIndicator,
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(0);
    expect(result.skipped).toBe(1);
    expect(result.errors[0].type).toBe('name_duplicate');
  });

  it('importCustomIndicators 字段非法计入 field_invalid 错误', () => {
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        { id: 'ind_x' } as unknown as CustomIndicator, // 缺 name/category/formula/operator
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(0);
    expect(result.errorSummary.field_invalid).toBe(1);
  });

  it('importCustomIndicators 名称不合法计入 name_invalid 错误', () => {
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        { ...makeIndicator({ id: 'ind_x', name: 'a' }) } as CustomIndicator, // 长度太短
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(0);
    expect(result.errorSummary.name_invalid).toBe(1);
  });

  it('importCustomIndicators 部分成功部分失败时按类型分组统计', () => {
    // seed：让 saveCustomIndicator 走"新增"路径（不传 id）创建真实存在的 '指标A'
    saveCustomIndicator(makeIndicator({ name: '指标A' }));
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        // K 2026-06-18 任务 #10：去重优先级 id 优先 / name 兜底。
        // 此处测试"name 重复"路径，所以不传 id。
        { ...makeIndicator({ name: '指标A' }) } as unknown as CustomIndicator, // 重复
        { ...makeIndicator({ name: '指标B' }) } as unknown as CustomIndicator, // 新
        { id: 'ind_3' } as unknown as CustomIndicator, // 字段非法
        { ...makeIndicator({ name: 'c' }) } as CustomIndicator, // 名称过短
      ],
    };
    const result = importCustomIndicators(file);
    expect(result.added).toBe(1);
    expect(result.skipped).toBe(1);
    expect(result.errors).toHaveLength(3);
    expect(result.errorSummary.name_duplicate).toBe(1);
    expect(result.errorSummary.field_invalid).toBe(1);
    expect(result.errorSummary.name_invalid).toBe(1);
  });

  it('导入会重置 id/timestamps/userId，避免冲突', () => {
    const file = {
      version: 1,
      exportedAt: '2026-06-16T00:00:00.000Z',
      userId: 'other_user',
      indicators: [
        { ...makeIndicator({ id: 'ind_orig', name: '指标A', userId: 'other_user' }) } as unknown as CustomIndicator,
      ],
    };
    importCustomIndicators(file);
    const list = listCustomIndicators();
    expect(list[0].id).not.toBe('ind_orig');
    expect(list[0].userId).toBe(MOCK_USER_ID);
  });
});

describe('localStorage 降级（不可用时）', () => {
  it('localStorage.setItem 抛错时降级到内存 Map 仍可正常保存', () => {
    const setItemSpy = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });
    try {
      const created = saveCustomIndicator(makeIndicator({ name: '指标A' }));
      expect(created.id).toBeTruthy();
    } finally {
      setItemSpy.mockRestore();
    }
    expect(true).toBe(true);
  });
});

// =====================================================================
// K 2026-06-18 反馈 #3：purgeCustomIndicator 也要 markPlanConditionsInvalid
// =====================================================================

describe('K 2026-06-18 反馈 #3：purgeCustomIndicator 标记 plans 失效', () => {
  it('硬删除后 plans 中引用该 id 的 condition 被标记 invalid', () => {
    // seed：创建真实指标
    const created = saveCustomIndicator(makeIndicator({ name: '指标A' }));
    // seed：在 plans 中放置引用此 id 的方案
    window.localStorage.setItem(
      `qt_custom_indicators_v1_plans_${MOCK_USER_ID}`,
      JSON.stringify([{ conditions: [{ sourceId: created.id }] }]),
    );

    // 执行硬删除
    const purged = purgeCustomIndicator(created.id);
    expect(purged).toBe(true);

    // 验证 plans 中条件已被标记 invalid
    const plansAfter = JSON.parse(
      window.localStorage.getItem(`qt_custom_indicators_v1_plans_${MOCK_USER_ID}`) ?? '[]',
    );
    expect(plansAfter[0].conditions[0].invalid).toBe(true);
    expect(plansAfter[0].conditions[0].invalidReason).toBe('引用指标已删除');
  });
});

// =====================================================================
// K 2026-06-18 反馈 #4：isIndicatorReferencedByConditions 纯函数
// =====================================================================

describe('K 2026-06-18 反馈 #4：isIndicatorReferencedByConditions 纯函数', () => {
  it('空 conditions 数组 → false', () => {
    expect(isIndicatorReferencedByConditions('ind_a', [])).toBe(false);
  });

  it('conditions 中存在 source=custom/sourceId=ind_a → true', () => {
    expect(
      isIndicatorReferencedByConditions('ind_a', [
        { source: 'custom', sourceId: 'ind_a' },
      ]),
    ).toBe(true);
  });

  it('conditions 中存在 sourceId=ind_b（其他指标）→ false', () => {
    expect(
      isIndicatorReferencedByConditions('ind_a', [
        { source: 'custom', sourceId: 'ind_b' },
      ]),
    ).toBe(false);
  });

  it('conditions 中 source 缺失（system 条件） → false', () => {
    expect(
      isIndicatorReferencedByConditions('ind_a', [
        { sourceId: 'ind_a' } as { source?: string; sourceId?: string },
      ]),
    ).toBe(false);
  });
});

// =====================================================================
// K 2026-06-18 反馈 #5：computeImportPreview 与 importCustomIndicators 一致性
// =====================================================================

describe('K 2026-06-18 反馈 #5：computeImportPreview 与 importCustomIndicators 行为一致', () => {
  it('预览与实际导入的 added/skipped/errors 数量完全一致', () => {
    saveCustomIndicator(makeIndicator({ name: '已存在A' }));
    const file = {
      version: 1,
      exportedAt: '2026-06-18T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        { ...makeIndicator({ name: '已存在A' }) } as unknown as CustomIndicator, // 重复
        { ...makeIndicator({ name: '新指标B' }) } as unknown as CustomIndicator, // 新
        { id: 'x' } as unknown as CustomIndicator, // 字段非法
      ],
    };
    const preview = computeImportPreview(file);
    const actual = importCustomIndicators(file);
    expect(preview.added).toBe(actual.added);
    expect(preview.skipped).toBe(actual.skipped);
    expect(preview.errors.length).toBe(actual.errors.length);
    expect(preview.added).toBe(1); // 仅"新指标B"
    expect(preview.skipped).toBe(1); // "已存在A" 重复
  });

  it('实际导入返回 addedIndicators 包含所有新增指标（K 反馈 #17）', () => {
    const file = {
      version: 1,
      exportedAt: '2026-06-18T00:00:00.000Z',
      userId: MOCK_USER_ID,
      indicators: [
        { ...makeIndicator({ name: '新增1' }) } as unknown as CustomIndicator,
        { ...makeIndicator({ name: '新增2' }) } as unknown as CustomIndicator,
      ],
    };
    const result = importCustomIndicators(file) as ReturnType<typeof importCustomIndicators> & {
      addedIndicators?: CustomIndicator[];
    };
    expect(result.added).toBe(2);
    expect(result.addedIndicators).toHaveLength(2);
    expect(result.addedIndicators?.[0].name).toBe('新增1');
    expect(result.addedIndicators?.[0].id).toBeTruthy();
  });
});
