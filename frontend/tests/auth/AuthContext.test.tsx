/**
 * tests/auth/AuthContext.test.tsx — 全局登录态（/auth/me 缓存、会话失效、注册开关）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope, authError } from './helpers';
import { AuthProvider, useAuth } from '@/features/auth/AuthContext';
import { notifySessionExpired } from '@/features/auth/session';

// antd 渲染在 jsdom 下较慢，放宽本文件用例超时
vi.setConfig({ testTimeout: 20000 });

/** 暴露 auth 状态的探针组件 */
function Probe() {
  const { user, loading, error, authDisabled, allowRegister, isAdmin } = useAuth();
  return (
    <div data-testid="probe">
      {JSON.stringify({ user, loading, error, authDisabled, allowRegister, isAdmin })}
    </div>
  );
}

const readProbe = () => JSON.parse(screen.getByTestId('probe').textContent || '{}');

const renderAuth = () => render(
  <AuthProvider>
    <Probe />
  </AuthProvider>,
);

describe('AuthContext — 登录态探测与缓存', () => {
  it('已登录：/auth/me 返回身份，缓存于内存（重渲染不重复请求）', async () => {
    const meCalls = vi.fn();
    installAuthMocks();
    server.use(
      http.get('/api/auth/me', () => {
        meCalls();
        return envelope({ username: 'admin', role: 'admin', display_name: '管理员' });
      }),
    );

    const { rerender } = renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));

    const state = readProbe();
    expect(state.user).toEqual({ username: 'admin', role: 'admin', display_name: '管理员' });
    expect(state.isAdmin).toBe(true);
    expect(state.error).toBeNull();

    rerender(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(readProbe().user?.username).toBe('admin'));
    expect(meCalls).toHaveBeenCalledTimes(1);
  });

  it('未认证：/auth/me 401 → user=null，且非错误态（守卫应跳登录页）', async () => {
    installAuthMocks({ user: null });
    renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));

    const state = readProbe();
    expect(state.user).toBeNull();
    expect(state.error).toBeNull();
    expect(state.authDisabled).toBe(false);
  });

  it('后端未启用认证门禁：/auth/me 401 但 /auth/verify authenticated=true → authDisabled 放行', async () => {
    installAuthMocks({
      user: null,
      verifyResponse: () => envelope({ authenticated: true }),
    });
    renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));

    const state = readProbe();
    expect(state.user).toBeNull();
    expect(state.authDisabled).toBe(true);
  });

  it('账号被禁用：/auth/me 401 disabled → 视为未登录（守卫跳登录页），非错误态', async () => {
    installAuthMocks({
      meResponse: () => authError(401, 'disabled', '账号已被禁用，请联系管理员'),
    });
    renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));

    const state = readProbe();
    expect(state.user).toBeNull();
    expect(state.error).toBeNull();
  });

  it('认证服务故障（503）：进入 error 态，不误判为未登录', async () => {
    installAuthMocks({
      meResponse: () => authError(503, 'db_unavailable', '认证服务暂时不可用，请稍后重试'),
    });
    renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));

    const state = readProbe();
    expect(state.user).toBeNull();
    expect(state.error).toContain('认证服务暂时不可用');
  });

  it('注册开关来自 /auth/config（默认关闭）', async () => {
    installAuthMocks({ user: { username: 'alice', role: 'user' }, allowRegister: true });
    renderAuth();
    await waitFor(() => expect(readProbe().loading).toBe(false));
    expect(readProbe().allowRegister).toBe(true);
  });

  it('会话失效（被禁用/改密）：清空登录态', async () => {
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    renderAuth();
    await waitFor(() => expect(readProbe().user?.username).toBe('alice'));

    act(() => notifySessionExpired());

    await waitFor(() => expect(readProbe().user).toBeNull());
  });
});