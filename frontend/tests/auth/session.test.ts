/**
 * tests/auth/session.test.ts — 会话失效捕获（fetch 通道 + 载荷判定）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { authError, envelope } from './helpers';
import {
  installFetchSessionWatcher,
  isSessionInvalidPayload,
  notifySessionExpired,
  setSessionExpiredHandler,
} from '@/features/auth/session';

// 每个用例后恢复用例开始时的 fetch（包装器带幂等标记，跨用例复用会互相影响）
// 注意：须在 beforeEach 中捕获——此时 MSW 已 server.listen 完成（fetch 已被拦截层包装）
let fetchAtTestStart: typeof window.fetch;

beforeEach(() => {
  fetchAtTestStart = window.fetch;
});

afterEach(() => {
  window.fetch = fetchAtTestStart;
  setSessionExpiredHandler(null);
});

describe('session — isSessionInvalidPayload', () => {
  it('识别 FastAPI detail.code=unauthenticated', () => {
    expect(isSessionInvalidPayload({ detail: { code: 'unauthenticated', message: 'x' } })).toBe(true);
  });

  it('识别 detail.code=disabled（账号被禁用 → 也要踢下线）', () => {
    expect(isSessionInvalidPayload({ detail: { code: 'disabled', message: '账号已被禁用' } })).toBe(true);
  });

  it('密码错误等其它 code 不视为会话失效', () => {
    expect(isSessionInvalidPayload({ detail: { code: 'bad_credentials' } })).toBe(false);
    expect(isSessionInvalidPayload({ detail: { code: 'forbidden' } })).toBe(false);
    expect(isSessionInvalidPayload({ code: 'unauthenticated' })).toBe(true);
    expect(isSessionInvalidPayload(null)).toBe(false);
    expect(isSessionInvalidPayload('unauthenticated')).toBe(false);
  });
});

describe('session — fetch 通道捕获', () => {
  it('401 unauthenticated 触发会话失效回调', async () => {
    const handler = vi.fn();
    setSessionExpiredHandler(handler);
    installFetchSessionWatcher();
    server.use(http.get('/api/watchlist/', () => authError(401, 'unauthenticated', '未认证，请先登录')));

    const res = await fetch('/api/watchlist/');
    expect(res.status).toBe(401);
    await vi.waitFor(() => expect(handler).toHaveBeenCalledTimes(1));
  });

  it('401 disabled（账号被管理员禁用）同样触发踢下线', async () => {
    const handler = vi.fn();
    setSessionExpiredHandler(handler);
    installFetchSessionWatcher();
    server.use(http.get('/api/stocks/', () => authError(401, 'disabled', '账号已被禁用，请联系管理员')));

    const res = await fetch('/api/stocks/');
    expect(res.status).toBe(401);
    await vi.waitFor(() => expect(handler).toHaveBeenCalledTimes(1));
  });

  it('401 bad_credentials 不触发（登录页密码错不应跳登录）', async () => {
    const handler = vi.fn();
    setSessionExpiredHandler(handler);
    installFetchSessionWatcher();
    server.use(http.post('/api/auth/login', () => authError(401, 'bad_credentials', '用户名或密码错误')));

    await fetch('/api/auth/login', { method: 'POST' });
    expect(handler).not.toHaveBeenCalled();
  });

  it('非 JSON 的 401 响应体不抛异常，也不触发', async () => {
    const handler = vi.fn();
    setSessionExpiredHandler(handler);
    installFetchSessionWatcher();
    server.use(http.get('/api/plain', () => new HttpResponse('unauthorized', { status: 401 })));

    const res = await fetch('/api/plain');
    expect(res.status).toBe(401);
    expect(handler).not.toHaveBeenCalled();
  });

  it('正常响应不触发；包装幂等且可卸载', async () => {
    const handler = vi.fn();
    setSessionExpiredHandler(handler);
    const fetchBefore = window.fetch;

    const uninstallFirst = installFetchSessionWatcher();
    const wrapped = window.fetch;
    expect(wrapped).not.toBe(fetchBefore);

    // 二次安装识别已包装 → 不再重复包裹
    const uninstallSecond = installFetchSessionWatcher();
    expect(window.fetch).toBe(wrapped);
    uninstallSecond();

    server.use(http.get('/api/meta/', () => envelope({ trade_date: '2026-09-24' })));
    await fetch('/api/meta/');
    expect(handler).not.toHaveBeenCalled();

    uninstallFirst();
    expect(window.fetch).toBe(fetchBefore);
  });

  it('notifySessionExpired 无回调时安全忽略', () => {
    expect(() => notifySessionExpired()).not.toThrow();
  });
});