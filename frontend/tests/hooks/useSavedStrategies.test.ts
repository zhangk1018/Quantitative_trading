import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useSavedStrategies,
  sanitizeName,
  serializeState,
  buildStrategyExportFile,
  parseStrategyImportFile,
  validateStrategyImportData,
  computeStrategyImportPreview,
  mergeImportedStrategies,
  LocalStorageStrategyStorage,
  type IStrategyStorage,
  type SavedStrategy,
} from '@/features/stock-picker/hooks/useSavedStrategies';
import type { ScreenerState } from '@/features/stock-picker/context/ScreenerContext';

// ============ 内存存储实现（测试用） ============
class MemoryStorage implements IStrategyStorage {
  private data: unknown = null;
  load(): unknown { return this.data; }
  save(data: unknown): void { this.data = data; }
}

// ============ 工具函数测试 ============
describe('sanitizeName', () => {
  it('去除 HTML 标签（标签本身被移除，内部内容保留）', () => {
    // sanitizeName 移除 <tag> 标签，然后 removeSpecialChars 移除 "
    expect(sanitizeName('<script>alert("xss")</script>高ROE低PE')).toBe('alert(xss)高ROE低PE');
  });

  it('去除特殊字符', () => {
    // <"名称"> 整体匹配 <[^>]*> 被移除，留下"策略"
    expect(sanitizeName('策略<"名称">')).toBe('策略');
  });

  it('截断超过 30 个字符', () => {
    const long = '一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十超出';
    const result = sanitizeName(long);
    expect(result.length).toBeLessThanOrEqual(30);
    expect(result).toBe('一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十');
  });

  it('空字符串返回空', () => {
    expect(sanitizeName('')).toBe('');
  });

  it('trim 前后空格', () => {
    expect(sanitizeName('  高ROE低PE  ')).toBe('高ROE低PE');
  });
});

describe('serializeState', () => {
  it('移除 panels 字段', () => {
    const state = { panels: { collapsed: {} } } as unknown as ScreenerState;
    const result = serializeState(state);
    expect(result).not.toHaveProperty('panels');
  });

  it('保留其他所有字段', () => {
    const state = {
      market: { selectedMarket: 'cn' },
      panels: { collapsed: {} },
    } as unknown as ScreenerState;
    const result = serializeState(state);
    expect(result).toHaveProperty('market');
    expect((result as any).market.selectedMarket).toBe('cn');
  });
});

// ============ LocalStorageStrategyStorage ============
describe('LocalStorageStrategyStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('save 使用 Base64 编码存储', () => {
    const storage = new LocalStorageStrategyStorage('test_key');
    storage.save([{ id: '1', name: '测试' }]);
    const raw = localStorage.getItem('test_key');
    expect(raw).not.toBeNull();
    // 验证是 Base64 编码（非明文 JSON）
    expect(() => JSON.parse(raw!)).toThrow();
  });

  it('load 能正确解码 Base64 编码的数据', () => {
    const storage = new LocalStorageStrategyStorage('test_key');
    const data = [{ id: '1', name: '测试策略', version: 1 }];
    storage.save(data);
    const loaded = storage.load();
    expect(loaded).toEqual(data);
  });

  it('load 兼容旧格式（未编码的 JSON）', () => {
    const oldData = [{ id: 'old', name: '旧策略', version: 1 }];
    localStorage.setItem('test_key', JSON.stringify(oldData));
    const storage = new LocalStorageStrategyStorage('test_key');
    const loaded = storage.load();
    expect(loaded).toEqual(oldData);
  });

  it('load 空存储返回 null', () => {
    const storage = new LocalStorageStrategyStorage('test_key');
    expect(storage.load()).toBeNull();
  });

  it('load 损坏数据返回 null', () => {
    localStorage.setItem('test_key', 'not-valid-json{{{');
    const storage = new LocalStorageStrategyStorage('test_key');
    expect(storage.load()).toBeNull();
  });
});

// ============ useSavedStrategies Hook ============
describe('useSavedStrategies', () => {
  let storage: MemoryStorage;

  beforeEach(() => {
    storage = new MemoryStorage();
  });

  const mockState = {
    market: { selectedMarket: 'cn', selectedBoards: ['all'], stockRange: 'all' },
    marketIndicators: { selected: [], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: { indicators: [], activeTab: 'system' as const },
    factor: { weights: {} },
    panels: { collapsed: {} },
  } as unknown as ScreenerState;

  it('初始化时自动加载存储中的策略', () => {
    storage.save([{ id: 's1', name: '已有策略', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z', version: 1, state: mockState }]);
    const { result } = renderHook(() => useSavedStrategies(storage));
    expect(result.current.strategies).toHaveLength(1);
    expect(result.current.strategies[0].name).toBe('已有策略');
  });

  it('默认 storage 在 rerender 时保持稳定，避免加载 effect 反复触发 setState', () => {
    localStorage.clear();
    const loadSpy = vi.spyOn(LocalStorageStrategyStorage.prototype, 'load');

    const { rerender } = renderHook(() => useSavedStrategies());
    rerender();
    rerender();

    expect(loadSpy).toHaveBeenCalledTimes(1);
    loadSpy.mockRestore();
  });

  it('saveStrategy 创建新策略', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    let saveResult: { ok: boolean; error?: string };
    act(() => {
      saveResult = result.current.saveStrategy('高ROE低PE', mockState);
    });
    expect(saveResult!).toEqual({ ok: true });
    expect(result.current.strategies).toHaveLength(1);
    expect(result.current.strategies[0].name).toBe('高ROE低PE');
    expect(result.current.strategies[0].version).toBe(1);
    expect(result.current.strategies[0].state).not.toHaveProperty('panels');
  });

  it('saveStrategy 空名称返回错误', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    let saveResult: { ok: boolean; error?: string };
    act(() => {
      saveResult = result.current.saveStrategy('', mockState);
    });
    expect(saveResult!).toEqual({ ok: false, error: '策略名称不能为空' });
    expect(result.current.strategies).toHaveLength(0);
  });

  it('saveStrategy 仅空格的名称返回错误', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    let saveResult: { ok: boolean; error?: string };
    act(() => {
      saveResult = result.current.saveStrategy('   ', mockState);
    });
    expect(saveResult!).toEqual({ ok: false, error: '策略名称不能为空' });
  });

  it('updateStrategyName 重命名策略', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    act(() => {
      result.current.saveStrategy('原名', mockState);
    });
    const id = result.current.strategies[0].id;
    act(() => {
      result.current.updateStrategyName(id, '新名称');
    });
    expect(result.current.strategies[0].name).toBe('新名称');
    // updatedAt 应存在（同一毫秒内可能等于 createdAt）
    expect(result.current.strategies[0].updatedAt).toBeDefined();
  });

  it('updateStrategyName 空名称返回错误', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    act(() => {
      result.current.saveStrategy('原名', mockState);
    });
    const id = result.current.strategies[0].id;
    let updateResult: { ok: boolean; error?: string };
    act(() => {
      updateResult = result.current.updateStrategyName(id, '');
    });
    expect(updateResult!).toEqual({ ok: false, error: '策略名称不能为空' });
    expect(result.current.strategies[0].name).toBe('原名');
  });

  it('deleteStrategy 删除策略', async () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    act(() => {
      result.current.saveStrategy('策略A', mockState);
    });
    act(() => {
      result.current.saveStrategy('策略B', mockState);
    });
    expect(result.current.strategies).toHaveLength(2);
    const id = result.current.strategies[0].id;
    act(() => {
      result.current.deleteStrategy(id);
    });
    expect(result.current.strategies).toHaveLength(1);
    expect(result.current.strategies[0].name).toBe('策略B');
  });

  it('deleteStrategy 不存在的 id 不影响列表', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    act(() => {
      result.current.saveStrategy('策略A', mockState);
    });
    const countBefore = result.current.strategies.length;
    act(() => {
      result.current.deleteStrategy('non-existent-id');
    });
    expect(result.current.strategies).toHaveLength(countBefore);
  });

  it('loadAll 过滤掉版本不兼容的策略', () => {
    storage.save([
      { id: 's1', name: '兼容', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z', version: 1, state: mockState },
      { id: 's2', name: '不兼容', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z', version: 99, state: mockState },
    ]);
    const { result } = renderHook(() => useSavedStrategies(storage));
    expect(result.current.strategies).toHaveLength(1);
    expect(result.current.strategies[0].name).toBe('兼容');
  });

  it('loadAll 非数组格式返回空列表', () => {
    storage.save({ not: 'an array' });
    const { result } = renderHook(() => useSavedStrategies(storage));
    expect(result.current.strategies).toEqual([]);
  });

  it('reload 重新加载存储中的策略', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    expect(result.current.strategies).toEqual([]);
    // 直接修改存储（绕过 Hook）
    storage.save([{ id: 's1', name: '直接写入', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z', version: 1, state: mockState }]);
    act(() => {
      result.current.reload();
    });
    expect(result.current.strategies).toHaveLength(1);
  });

  it('多个策略按保存顺序排列', () => {
    const { result } = renderHook(() => useSavedStrategies(storage));
    act(() => {
      result.current.saveStrategy('策略A', mockState);
    });
    act(() => {
      result.current.saveStrategy('策略B', mockState);
    });
    act(() => {
      result.current.saveStrategy('策略C', mockState);
    });
    expect(result.current.strategies.map(s => s.name)).toEqual(['策略A', '策略B', '策略C']);
  });
});

// ============ buildStrategyExportFile 导出文件构造 ============
describe('buildStrategyExportFile', () => {
  const make = (id: string, name: string): SavedStrategy => ({
    id,
    name,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    state: {
      market: { selectedMarket: 'cn', selectedBoards: ['all'], stockRange: 'all' },
      marketIndicators: { selected: [], ranges: {} },
      financialIndicators: { selected: [], ranges: {} },
      technical: { selected: {}, openModalId: null },
      patterns: { selected: {}, panelCollapsed: true },
      condition: { filterGroup: null, nextOp: 'AND' },
      custom: { indicators: [], activeTab: 'system' },
      factor: { weights: {} },
    } as unknown as SavedStrategy['state'],
  });

  it('不传 ids 时导出全部策略', () => {
    const strategies = [make('s1', '策略A'), make('s2', '策略B')];
    const file = buildStrategyExportFile(strategies);
    expect(file.version).toBe(1);
    expect(file.exportedAt).toBeTruthy();
    expect(file.strategies).toHaveLength(2);
  });

  it('传入 ids 只导出指定策略（保持原顺序）', () => {
    const strategies = [make('s1', '策略A'), make('s2', '策略B'), make('s3', '策略C')];
    const file = buildStrategyExportFile(strategies, ['s2', 's1']);
    expect(file.strategies.map((s) => s.name)).toEqual(['策略A', '策略B']);
  });

  it('ids 为空数组等价于导出全部', () => {
    const strategies = [make('s1', '策略A')];
    expect(buildStrategyExportFile(strategies, []).strategies).toHaveLength(1);
  });

  it('策略内容完整保留（含 state 快照）', () => {
    const strategies = [make('s1', '策略A')];
    const file = buildStrategyExportFile(strategies);
    expect(file.strategies[0]).toEqual(strategies[0]);
    expect(file.strategies[0].state).toBeDefined();
  });
});

// ============ 导入纯函数 ============
describe('导入纯函数', () => {
  const state = {
    market: { selectedMarket: 'cn', selectedBoards: ['all'], stockRange: 'all' },
    marketIndicators: { selected: [], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: { indicators: [], activeTab: 'system' },
    factor: { weights: {} },
  };

  const makeStrategy = (id: string, name: string): SavedStrategy => ({
    id,
    name,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    version: 1,
    state: state as SavedStrategy['state'],
  });

  describe('parseStrategyImportFile', () => {
    it('合法 JSON 解析成功', () => {
      const file = parseStrategyImportFile(
        JSON.stringify({ version: 1, exportedAt: '2026-01-02T00:00:00Z', strategies: [makeStrategy('s1', '策略A')] }),
      );
      expect(file.version).toBe(1);
      expect(file.strategies).toHaveLength(1);
    });

    it('非法 JSON 抛错', () => {
      expect(() => parseStrategyImportFile('not json')).toThrow(/JSON 解析失败/);
    });

    it('版本不匹配抛错', () => {
      expect(() =>
        parseStrategyImportFile(JSON.stringify({ version: 99, strategies: [] })),
      ).toThrow(/版本/);
    });

    it('缺少 strategies 数组抛错', () => {
      expect(() =>
        parseStrategyImportFile(JSON.stringify({ version: 1 })),
      ).toThrow(/strategies/);
    });
  });

  describe('validateStrategyImportData', () => {
    it('字段完整时通过', () => {
      const v = validateStrategyImportData(makeStrategy('s1', '策略A'));
      expect(v.valid).toBe(true);
      expect(v.data?.name).toBe('策略A');
    });

    it('缺字段时不通过', () => {
      const v = validateStrategyImportData({ id: 's1', name: '策略A' });
      expect(v.valid).toBe(false);
      expect(v.errors.length).toBeGreaterThan(0);
    });
  });

  describe('computeStrategyImportPreview', () => {
    it('全部可新增', () => {
      const existing = [makeStrategy('s1', '已有')];
      const file = { version: 1, exportedAt: '', strategies: [makeStrategy('s2', '新增A'), makeStrategy('s3', '新增B')] };
      const r = computeStrategyImportPreview(file, existing);
      expect(r.added).toBe(2);
      expect(r.skipped).toBe(0);
      expect(r.errors).toHaveLength(0);
    });

    it('重名策略计入跳过', () => {
      const existing = [makeStrategy('s1', '同名')];
      const file = { version: 1, exportedAt: '', strategies: [makeStrategy('s9', '同名')] };
      const r = computeStrategyImportPreview(file, existing);
      expect(r.added).toBe(0);
      expect(r.skipped).toBe(1);
      expect(r.errors[0].type).toBe('name_duplicate');
    });

    it('字段无效计入错误', () => {
      const existing: SavedStrategy[] = [];
      const file = { version: 1, exportedAt: '', strategies: [{ id: 'x' } as SavedStrategy] };
      const r = computeStrategyImportPreview(file, existing);
      expect(r.added).toBe(0);
      expect(r.errors[0].type).toBe('field_invalid');
    });
  });

  describe('mergeImportedStrategies', () => {
    it('新增策略重新生成 id，重名跳过', () => {
      const existing = [makeStrategy('s1', '同名')];
      const file = { version: 1, exportedAt: '', strategies: [makeStrategy('s9', '同名'), makeStrategy('s10', '新策略')] };
      const { added, skipped } = mergeImportedStrategies(file, existing);
      expect(added).toHaveLength(1);
      expect(added[0].name).toBe('新策略');
      expect(added[0].id).not.toBe('s10'); // id 已重新生成
      expect(skipped).toBe(1);
    });
  });
});
