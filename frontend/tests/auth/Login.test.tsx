/**
 * tests/auth/Login.test.tsx — 登录页（用户名+密码、错误 code 区分、注册入口显隐）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope, authError } from './helpers';
import { AuthProvider } from '@/features/auth/AuthContext';
import Login from '@/features/auth/Login';

// antd 表单在 jsdom 下渲染较慢，放宽本文件用例超时
vi.setConfig({ testTimeout: 20000 });

/** 统一 userEvent（关闭逐字延迟，避免 jsdom 下超时） */
const setupUser = () => userEvent.setup({ delay: null });

/** 渲染登录页（含 /login、/register、/ 三个路由探针） */
function renderLogin() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<div>注册页</div>} />
          <Route path="/" element={<div>选股主页</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('Login 页', () => {
  it('提交 {username, password} 并进入主页（不再使用 access_key）', async () => {
    const user = setupUser();
    const loginBody = vi.fn();
    installAuthMocks({ user: null });
    server.use(
      http.post('/api/auth/login', async ({ request }) => {
        loginBody(await request.json());
        return envelope({ username: 'alice', role: 'user' });
      }),
    );

    renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('login-username'), 'alice');
    await user.type(screen.getByTestId('login-password'), 'secret-pwd');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getByText('选股主页')).toBeInTheDocument());
    expect(loginBody).toHaveBeenCalledWith({ username: 'alice', password: 'secret-pwd' });
  });

  it('密码错误：提示「用户名或密码错误」并停留登录页', async () => {
    const user = setupUser();
    installAuthMocks({ user: null }); // login 默认返回 401 bad_credentials

    renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('login-username'), 'alice');
    await user.type(screen.getByTestId('login-password'), 'wrong');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getByText('用户名或密码错误')).toBeInTheDocument());
    expect(screen.queryByText('选股主页')).not.toBeInTheDocument();
  });

  it('账号被禁用：提示「账号已被禁用，请联系管理员」', async () => {
    const user = setupUser();
    installAuthMocks({ user: null });
    server.use(
      http.post('/api/auth/login', () => authError(403, 'disabled', '账号已被禁用，请联系管理员')),
    );

    renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('login-username'), 'bob');
    await user.type(screen.getByTestId('login-password'), 'secret-pwd');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getByText('账号已被禁用，请联系管理员')).toBeInTheDocument());
  });

  it('认证服务故障（503）：提示服务不可用', async () => {
    const user = setupUser();
    installAuthMocks({ user: null });
    server.use(
      http.post('/api/auth/login', () => authError(503, 'db_unavailable', '认证服务暂时不可用，请稍后重试')),
    );

    renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('login-username'), 'alice');
    await user.type(screen.getByTestId('login-password'), 'secret-pwd');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getByText('认证服务暂时不可用，请稍后重试')).toBeInTheDocument());
  });

  it('注册入口：开关关闭时不显示，开启时可跳注册页', async () => {
    installAuthMocks({ user: null, allowRegister: false });
    const view = renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-submit')).toBeInTheDocument());
    expect(screen.queryByTestId('login-register-link')).not.toBeInTheDocument();
    view.unmount();

    const user = setupUser();
    installAuthMocks({ user: null, allowRegister: true });
    renderLogin();
    await waitFor(() => expect(screen.getByTestId('login-register-link')).toBeInTheDocument());

    await user.click(screen.getByTestId('login-register-link'));
    await waitFor(() => expect(screen.getByText('注册页')).toBeInTheDocument());
  });

  it('已登录用户访问 /login 自动回主页', async () => {
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    renderLogin();
    await waitFor(() => expect(screen.getByText('选股主页')).toBeInTheDocument());
  });
});