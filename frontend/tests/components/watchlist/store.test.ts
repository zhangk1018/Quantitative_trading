/**
 * watchlist store 纯函数测试
 *
 * 验证：
 * - watchlistReducer 所有 action 分支
 * - useWatchlist 在无 Provider 时抛错
 */
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';

import { watchlistReducer, INITIAL_STATE, useWatchlist } from '@/features/watchlist/store';

// 初始 state（纯函数测试用，loading 设为 false 避免干扰）
const baseState = { ...INITIAL_STATE, loading: false };

describe('watchlistReducer', () => {
  // ---------- LOAD ----------
  it('LOAD → stocks/customGroups 被替换, loading:false, migrated:true', () => {
    const payload = {
      version: 1,
      customGroups: ['我的分组'],
      stocks: { '我的分组': ['000001'], '全部': ['000001'], '沪深': ['000001'] },
    };
    const state = watchlistReducer(baseState, { type: 'LOAD', payload });
    expect(state.stocks).toEqual(payload.stocks);
    expect(state.customGroups).toEqual(['我的分组']);
    expect(state.loading).toBe(false);
    expect(state.migrated).toBe(true);
  });

  // ---------- ADD_STOCK ----------
  it('ADD_STOCK → 追加到目标分组、全部分组和市场分组', () => {
    const state = watchlistReducer(baseState, {
      type: 'ADD_STOCK',
      payload: { code: '000001', groupName: '我的分组' },
    });
    // 目标分组
    expect(state.stocks['我的分组']).toEqual(['000001']);
    // 自动加入"全部"
    expect(state.stocks['全部']).toEqual(['000001']);
    // 自动加入市场分组（沪深）
    expect(state.stocks['沪深']).toEqual(['000001']);
  });

  it('ADD_STOCK 重复 code → stocks 不变', () => {
    const pre = watchlistReducer(baseState, {
      type: 'ADD_STOCK',
      payload: { code: '000001', groupName: '我的分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'ADD_STOCK',
      payload: { code: '000001', groupName: '我的分组' },
    });
    expect(post.stocks).toEqual(pre.stocks);
  });

  // ---------- BATCH_ADD_STOCKS ----------
  it('BATCH_ADD_STOCKS → 批量添加到目标分组、全部和市场分组', () => {
    const state = watchlistReducer(baseState, {
      type: 'BATCH_ADD_STOCKS',
      payload: { codes: ['000001', '000002'], groupName: '我的分组' },
    });
    expect(state.stocks['我的分组']).toEqual(['000001', '000002']);
    expect(state.stocks['全部']).toEqual(['000001', '000002']);
    expect(state.stocks['沪深']).toEqual(['000001', '000002']);
  });

  it('BATCH_ADD_STOCKS 部分已存在 → 去重', () => {
    const pre = watchlistReducer(baseState, {
      type: 'ADD_STOCK',
      payload: { code: '000001', groupName: '我的分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'BATCH_ADD_STOCKS',
      payload: { codes: ['000001', '000002'], groupName: '我的分组' },
    });
    expect(post.stocks['我的分组']).toEqual(['000001', '000002']);
  });

  // ---------- REMOVE_FROM_GROUP ----------
  it('REMOVE_FROM_GROUP（系统分组）→ 从全部分组移除该股票', () => {
    const pre = watchlistReducer(baseState, {
      type: 'BATCH_ADD_STOCKS',
      payload: { codes: ['000001', '000002'], groupName: '默认分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'REMOVE_FROM_GROUP',
      payload: { code: '000001', groupName: '全部' },
    });
    // 从所有分组中移除
    for (const codes of Object.values(post.stocks)) {
      expect(codes).not.toContain('000001');
    }
    // 000002 还在
    expect(post.stocks['全部']).toContain('000002');
    expect(post.stocks['沪深']).toContain('000002');
  });

  it('REMOVE_FROM_GROUP（自建分组）→ 从该分组移除，若不在其他自建分组则同时从系统分组移除', () => {
    const pre = watchlistReducer(baseState, {
      type: 'BATCH_ADD_STOCKS',
      payload: { codes: ['000001', '000002'], groupName: '我的分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'REMOVE_FROM_GROUP',
      payload: { code: '000001', groupName: '我的分组' },
    });
    // 从我的分组中移除
    expect(post.stocks['我的分组']).toEqual(['000002']);
    // 000001 不在其他自建分组中 → 同时从系统分组移除
    expect(post.stocks['全部']).not.toContain('000001');
    expect(post.stocks['沪深']).not.toContain('000001');
    // 000002 仍在
    expect(post.stocks['全部']).toContain('000002');
    expect(post.stocks['沪深']).toContain('000002');
  });

  // ---------- CREATE_GROUP ----------
  it('CREATE_GROUP → 新增分组和空的 stocks 条目', () => {
    const state = watchlistReducer(baseState, {
      type: 'CREATE_GROUP',
      payload: { name: '新分组' },
    });
    expect(state.customGroups).toContain('新分组');
    expect(state.stocks['新分组']).toEqual([]);
  });

  it('CREATE_GROUP 重复名称 → state 不变', () => {
    const pre = watchlistReducer(baseState, {
      type: 'CREATE_GROUP',
      payload: { name: '新分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'CREATE_GROUP',
      payload: { name: '新分组' },
    });
    expect(post).toBe(pre);
  });

  it('CREATE_GROUP 系统分组名 → state 不变', () => {
    const state = watchlistReducer(baseState, {
      type: 'CREATE_GROUP',
      payload: { name: '全部' },
    });
    expect(state).toBe(baseState);
  });

  // ---------- DELETE_GROUP ----------
  it('DELETE_GROUP → 删除自建分组及其 stocks', () => {
    const pre = watchlistReducer(baseState, {
      type: 'CREATE_GROUP',
      payload: { name: '临时分组' },
    });
    const post = watchlistReducer(pre, {
      type: 'DELETE_GROUP',
      payload: { name: '临时分组' },
    });
    expect(post.customGroups).not.toContain('临时分组');
    expect(post.stocks).not.toHaveProperty('临时分组');
  });

  it('DELETE_GROUP 系统分组名 → state 不变', () => {
    const state = watchlistReducer(baseState, {
      type: 'DELETE_GROUP',
      payload: { name: '全部' },
    });
    expect(state).toBe(baseState);
  });

  // ---------- SET_LOADING ----------
  it('SET_LOADING → loading 被设置', () => {
    const state = watchlistReducer(baseState, { type: 'SET_LOADING', payload: true });
    expect(state.loading).toBe(true);
  });

  // ---------- default ----------
  it('未知 action → state 不变', () => {
    const state = watchlistReducer(baseState, { type: 'UNKNOWN' } as any);
    expect(state).toBe(baseState);
  });
});

describe('useWatchlist', () => {
  it('无 WatchlistProvider 时抛出可读错误', () => {
    expect(() => {
      renderHook(() => useWatchlist());
    }).toThrow('useWatchlist must be used within WatchlistProvider');
  });
});