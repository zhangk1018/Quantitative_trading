/**
 * watchlist store 纯函数测试
 *
 * 验证：
 * - watchlistReducer 所有 action 分支（含 #4 修复的 SET_BATCH_SUMMARY）
 * - useWatchlist 在无 Provider 时抛错
 */
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';

// import 纯函数 reducer + useWatchlist hook
// 注意：import WatchlistProvider 会引入 api.ts（含 axios），但在
// 纯函数测试中无需 import provider；useWatchlist 在无 Provider 时
// 立即抛出 TypeError，不需要 axios 实例化。
import { watchlistReducer, useWatchlist, initialState } from '@/features/watchlist/store';
import type { WatchlistItem } from '@/features/watchlist/api';

// 构造 fixture item
const makeItem = (code: string, overrides: Partial<WatchlistItem> = {}): WatchlistItem => ({
  id: Number(code),
  code,
  group_name: '默认分组',
  sort_order: 0,
  ...overrides,
});

describe('watchlistReducer', () => {
  // ---------- load ----------
  it('LOAD_START → loading:true, lastError:null', () => {
    const state = watchlistReducer(initialState, { type: 'LOAD_START' });
    expect(state.loading).toBe(true);
    expect(state.lastError).toBeNull();
    // items 保持不变
    expect(state.items).toEqual([]);
  });

  it('LOAD_SUCCESS → items 替换, loading:false, lastError:null', () => {
    const items = [makeItem('000001')];
    const state = watchlistReducer(initialState, {
      type: 'LOAD_SUCCESS',
      payload: items,
    });
    expect(state.items).toEqual(items);
    expect(state.loading).toBe(false);
    expect(state.lastError).toBeNull();
  });

  it('LOAD_ERROR → lastError 设置, loading:false', () => {
    const errMsg = '网络错误';
    const state = watchlistReducer(initialState, {
      type: 'LOAD_ERROR',
      payload: errMsg,
    });
    expect(state.lastError).toBe(errMsg);
    expect(state.loading).toBe(false);
  });

  // ---------- add / dedup ----------
  it('ADD_ITEM → 追加到 items 末尾', () => {
    const pre = watchlistReducer(initialState, {
      type: 'ADD_ITEM',
      payload: makeItem('000001'),
    });
    expect(pre.items).toHaveLength(1);
    expect(pre.items[0].code).toBe('000001');

    const post = watchlistReducer(pre, {
      type: 'ADD_ITEM',
      payload: makeItem('000002'),
    });
    expect(post.items).toHaveLength(2);
    expect(post.items.map((i) => i.code)).toEqual(['000001', '000002']);
  });

  it('ADD_ITEM 重复 code → state 不变（去重）', () => {
    const item = makeItem('000001');
    const pre = watchlistReducer(initialState, { type: 'ADD_ITEM', payload: item });
    const post = watchlistReducer(pre, { type: 'ADD_ITEM', payload: item });
    expect(post.items).toHaveLength(1);
    // 引用相等（直接返回原 state）
    expect(post).toBe(pre);
  });

  // ---------- remove ----------
  it('REMOVE_ITEM → 按 code 移除', () => {
    const pre = watchlistReducer(initialState, {
      type: 'ADD_ITEM',
      payload: makeItem('000001'),
    });
    const post = watchlistReducer(pre, { type: 'REMOVE_ITEM', payload: '000001' });
    expect(post.items).toHaveLength(0);
  });

  it('REMOVE_ITEM 不存在的 code → state 不变（值相等）', () => {
    const pre = watchlistReducer(initialState, {
      type: 'ADD_ITEM',
      payload: makeItem('000001'),
    });
    const post = watchlistReducer(pre, { type: 'REMOVE_ITEM', payload: '999999' });
    expect(post).toStrictEqual(pre);
  });

  // ---------- SET_BATCH_SUMMARY（#4 修复核心） ----------
  it('SET_BATCH_SUMMARY → lastBatchSummary 被设置', () => {
    const summary = { added: 3, skipped: 1, failed: 1 };
    const state = watchlistReducer(initialState, {
      type: 'SET_BATCH_SUMMARY',
      payload: summary,
    });
    expect(state.lastBatchSummary).toEqual(summary);
    // 不应影响其它字段
    expect(state.items).toEqual([]);
    expect(state.loading).toBe(false);
  });

  it('SET_BATCH_SUMMARY 覆盖旧值', () => {
    const state1 = watchlistReducer(initialState, {
      type: 'SET_BATCH_SUMMARY',
      payload: { added: 1, skipped: 0, failed: 0 },
    });
    const state2 = watchlistReducer(state1, {
      type: 'SET_BATCH_SUMMARY',
      payload: { added: 5, skipped: 2, failed: 0 },
    });
    expect(state2.lastBatchSummary).toEqual({ added: 5, skipped: 2, failed: 0 });
  });

  // ---------- CLEAR_BATCH_SUMMARY ----------
  it('CLEAR_BATCH_SUMMARY → lastBatchSummary:null', () => {
    const pre = watchlistReducer(initialState, {
      type: 'SET_BATCH_SUMMARY',
      payload: { added: 100, skipped: 0, failed: 0 },
    });
    const post = watchlistReducer(pre, { type: 'CLEAR_BATCH_SUMMARY' });
    expect(post.lastBatchSummary).toBeNull();
  });

  // ---------- CLEAR_ERROR ----------
  it('CLEAR_ERROR → lastError:null', () => {
    const pre = watchlistReducer(initialState, {
      type: 'LOAD_ERROR',
      payload: '出错了',
    });
    const post = watchlistReducer(pre, { type: 'CLEAR_ERROR' });
    expect(post.lastError).toBeNull();
  });

  // ---------- default ----------
  it('未知 action → state 不变', () => {
    const state = watchlistReducer(initialState, { type: 'UNKNOWN' } as any);
    expect(state).toBe(initialState);
  });
});

describe('useWatchlist', () => {
  it('无 WatchlistProvider 时抛出可读错误', () => {
    expect(() => {
      renderHook(() => useWatchlist());
    }).toThrow('useWatchlist must be used within a WatchlistProvider');
  });
});