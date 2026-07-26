// scriptStore.test.ts — 自编指标脚本存储（localStorage CRUD + 版本控制）
//
// 覆盖场景：
//   - 创建/读取/更新/删除
//   - 列表查询
//   - 版本号递增
//   - 缓存键生成
//   - 不存在脚本的处理
//   - localStorage 异常降级

import { describe, it, expect, beforeEach } from 'vitest';
import {
  listScripts,
  getScript,
  createScript,
  updateScript,
  deleteScript,
  getScriptCacheKey,
  type CustomScript,
  type CustomScriptMeta,
} from '../../src/features/settings/custom-indicators/scriptStore';

beforeEach(() => {
  localStorage.clear();
});

// ==================== createScript ====================

describe('createScript', () => {
  it('创建新脚本返回完整元数据', () => {
    const script = createScript('测试指标', 'close > ma(close, 20)');
    expect(script.name).toBe('测试指标');
    expect(script.code).toBe('close > ma(close, 20)');
    expect(script.version).toBe(1);
    expect(script.id).toMatch(/^cs_/);
    expect(typeof script.createdAt).toBe('number');
    expect(typeof script.updatedAt).toBe('number');
  });

  it('创建后可通过 getScript 读取', () => {
    const script = createScript('我的指标', 'return close');
    const loaded = getScript(script.id);
    expect(loaded).not.toBeNull();
    expect(loaded!.name).toBe('我的指标');
    expect(loaded!.code).toBe('return close');
  });

  it('创建后出现在 listScripts 中', () => {
    createScript('指标A', 'code A');
    createScript('指标B', 'code B');
    const list = listScripts();
    expect(list).toHaveLength(2);
    expect(list.map((s) => s.name)).toContain('指标A');
    expect(list.map((s) => s.name)).toContain('指标B');
  });

  it('ID 唯一', () => {
    const a = createScript('A', 'a');
    const b = createScript('B', 'b');
    expect(a.id).not.toBe(b.id);
  });
});

// ==================== listScripts ====================

describe('listScripts', () => {
  it('空存储返回空数组', () => {
    expect(listScripts()).toEqual([]);
  });

  it('返回元数据列表不含 code', () => {
    const script = createScript('测试', 'formula');
    const list = listScripts();
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe(script.id);
    expect(list[0].name).toBe('测试');
    // 元数据不应包含 code
    expect((list[0] as any).code).toBeUndefined();
  });

  it('损坏的脚本数据被跳过', () => {
    createScript('正常', 'formula');
    // 手动写入损坏数据
    const brokenId = 'cs_broken_1';
    const index = JSON.parse(localStorage.getItem('custom_scripts_index') || '[]');
    index.push(brokenId);
    localStorage.setItem('custom_scripts_index', JSON.stringify(index));
    localStorage.setItem('custom_script_' + brokenId, '{invalid');
    const list = listScripts();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe('正常');
  });
});

// ==================== getScript ====================

describe('getScript', () => {
  it('不存在的脚本返回 null', () => {
    expect(getScript('non-existent')).toBeNull();
  });

  it('返回完整脚本（含 code）', () => {
    const script = createScript('测试', 'return close');
    const loaded = getScript(script.id);
    expect(loaded).not.toBeNull();
    expect(loaded!.code).toBe('return close');
    expect(loaded!.version).toBe(1);
  });

  it('损坏的 JSON 返回 null', () => {
    localStorage.setItem('custom_script_cs_test', '{not json');
    expect(getScript('cs_test')).toBeNull();
  });
});

// ==================== updateScript ====================

describe('updateScript', () => {
  it('更新名称和公式', () => {
    const script = createScript('旧名称', 'old code');
    const updated = updateScript(script.id, '新名称', 'new code');
    expect(updated).not.toBeNull();
    expect(updated!.name).toBe('新名称');
    expect(updated!.code).toBe('new code');
  });

  it('公式变化时版本号 +1', () => {
    const script = createScript('测试', 'v1');
    const updated = updateScript(script.id, '测试', 'v2');
    expect(updated!.version).toBe(2);
  });

  it('公式不变时版本号不变', () => {
    const script = createScript('测试', 'same code');
    const updated = updateScript(script.id, '新名', 'same code');
    expect(updated!.version).toBe(1);
  });

  it('不存在的脚本返回 null', () => {
    const updated = updateScript('non-existent', 'name', 'code');
    expect(updated).toBeNull();
  });
});

// ==================== deleteScript ====================

describe('deleteScript', () => {
  it('删除存在的脚本', () => {
    const script = createScript('测试', 'code');
    const result = deleteScript(script.id);
    expect(result).toBe(true);
    expect(getScript(script.id)).toBeNull();
    expect(listScripts()).toHaveLength(0);
  });

  it('删除不存在的脚本返回 false', () => {
    const result = deleteScript('non-existent');
    expect(result).toBe(false);
  });

  it('删除后不影响其他脚本', () => {
    const a = createScript('A', 'a');
    const b = createScript('B', 'b');
    deleteScript(a.id);
    const list = listScripts();
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe(b.id);
  });
});

// ==================== getScriptCacheKey ====================

describe('getScriptCacheKey', () => {
  it('返回 {id}_v{version} 格式', () => {
    const script = createScript('测试', 'code');
    const key = getScriptCacheKey(script.id);
    expect(key).toBe(`${script.id}_v1`);
  });

  it('更新后缓存键变化', () => {
    const script = createScript('测试', 'v1');
    const key1 = getScriptCacheKey(script.id);
    updateScript(script.id, '测试', 'v2');
    const key2 = getScriptCacheKey(script.id);
    expect(key1).not.toBe(key2);
    expect(key2).toContain('_v2');
  });

  it('不存在的脚本返回 null', () => {
    expect(getScriptCacheKey('non-existent')).toBeNull();
  });
});