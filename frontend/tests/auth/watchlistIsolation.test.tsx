/**
 * tests/auth/watchlistIsolation.test.tsx — 自选股按账号隔离（协作单 42.0 前台验收 3）
 *
 * 前端自选股存 localStorage：多账号下必须按账号命名空间隔离，
 * 避免 A 账号的自选股在 B 账号下可见（或反之）。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope } from './helpers';
import { AuthProvider } from '@/features/auth/AuthContext';
import { WatchlistProvider, useWatchlist, storageKeyFor } from '@/features/watchlist/store';

vi.setConfig({ testTimeout: 20000 });

const ALICE_KEY = storageKeyFor('alice');
const BOB_KEY = storageKeyFor('bob');

function Inspector() {
  const { state } = useWatchlist();
  return (
    <div data-testid="wl">
      {JSON.stringify({ loading: state.loading, groups: state.customGroups, stocks: state.stocks })}
    </div>
  );
}

function renderFor(username: string, role: 'admin' | 'user' = 'user') {
  installAuthMocks({ user: { username, role } });
  server.use(http.get('/api/watchlist/', () => envelope([])));
  return render(
    <AuthProvider>
      <WatchlistProvider>
        <Inspector />
      </WatchlistProvider>
    </AuthProvider>,
  );
}

const readWl = () => JSON.parse(screen.getByTestId('wl').textContent || '{}');

afterEach(() => {
  localStorage.clear();
  cleanup();
});

describe('自选股按账号隔离', () => {
  it('存储键按账号命名空间；未启用认证时回退老全局键', () => {
    expect(storageKeyFor('alice')).toBe('watchlist:alice');
    expect(storageKeyFor('')).toBe('watchlist');
  });

  it('A 账号的本地自选股不会出现在 B 账号下', async () => {
    localStorage.setItem(
      ALICE_KEY,
      JSON.stringify({
        version: 1,
        customGroups: ['A组'],
        stocks: { A组: ['000001'], 全部: ['000001'], 沪深: ['000001'] },
      }),
    );

    // A 登录 → 看到自己的 000001
    renderFor('alice');
    await waitFor(() => expect(readWl().stocks['全部']).toEqual(['000001']));
    cleanup();

    // B 登录 → 看不到 A 的自选股
    renderFor('bob');
    await waitFor(() => expect(readWl().loading).toBe(false));
    expect(readWl().stocks['全部']).toBeUndefined();
    expect(JSON.stringify(readWl())).not.toContain('000001');
  });

  it('管理员首次登录承接老全局键数据（老数据不丢失），承接后老键被清理', async () => {
    localStorage.setItem(
      'watchlist',
      JSON.stringify({
        version: 1,
        customGroups: [],
        stocks: { 默认分组: ['600036'], 全部: ['600036'], 沪深: ['600036'] },
      }),
    );

    renderFor('admin', 'admin');
    await waitFor(() => expect(readWl().stocks['全部']).toEqual(['600036']));
    await waitFor(() => expect(localStorage.getItem('watchlist')).toBeNull());
    // 老数据已落到 admin 的账号键下
    expect(localStorage.getItem(storageKeyFor('admin'))).toContain('600036');
  });

  it('普通账号不承接老全局键数据（避免串号）', async () => {
    localStorage.setItem(
      'watchlist',
      JSON.stringify({ version: 1, customGroups: [], stocks: { 全部: ['600036'] } }),
    );

    renderFor('bob');
    await waitFor(() => expect(readWl().loading).toBe(false));
    expect(JSON.stringify(readWl())).not.toContain('600036');
    // 老键保留给管理员承接
    expect(localStorage.getItem('watchlist')).not.toBeNull();
  });
});