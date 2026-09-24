/**
 * tests/auth/Register.test.tsx — 注册页（开关显隐、校验、错误码提示）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope, authError } from './helpers';
import { AuthProvider } from '@/features/auth/AuthContext';
import Register from '@/features/auth/Register';

// antd 表单在 jsdom 下渲染较慢，放宽本文件用例超时
vi.setConfig({ testTimeout: 20000 });

/** 统一 userEvent（关闭逐字延迟，避免 jsdom 下超时） */
const setupUser = () => userEvent.setup({ delay: null });

function renderRegister() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/login" element={<div>登录页</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('Register 页', () => {
  it('注册开关关闭：展示提示且不渲染表单，可返回登录', async () => {
    const user = setupUser();
    installAuthMocks({ user: null, allowRegister: false });
    renderRegister();

    await waitFor(() =>
      expect(screen.getByText('当前未开放自助注册，请联系管理员创建账号。')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('register-submit')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('register-back-login'));
    await waitFor(() => expect(screen.getByText('登录页')).toBeInTheDocument());
  });

  it('密码过短 / 两次不一致：前端拦截并提示', async () => {
    const user = setupUser();
    installAuthMocks({ user: null, allowRegister: true });
    renderRegister();
    await waitFor(() => expect(screen.getByTestId('register-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('register-username'), 'newbie');
    await user.type(screen.getByTestId('register-password'), 'short');
    await user.type(screen.getByTestId('register-confirm'), 'short');
    await user.click(screen.getByTestId('register-submit'));
    await waitFor(() => expect(screen.getByText('密码至少 8 位')).toBeInTheDocument());

    await user.clear(screen.getByTestId('register-password'));
    await user.type(screen.getByTestId('register-password'), 'password123');
    await user.clear(screen.getByTestId('register-confirm'));
    await user.type(screen.getByTestId('register-confirm'), 'password124');
    await user.click(screen.getByTestId('register-submit'));
    await waitFor(() => expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument());
  });

  it('保留用户名 default 被前端拦截', async () => {
    const user = setupUser();
    installAuthMocks({ user: null, allowRegister: true });
    renderRegister();
    await waitFor(() => expect(screen.getByTestId('register-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('register-username'), 'default');
    await user.type(screen.getByTestId('register-password'), 'password123');
    await user.type(screen.getByTestId('register-confirm'), 'password123');
    await user.click(screen.getByTestId('register-submit'));

    await waitFor(() => expect(screen.getByText('用户名 default 为保留名，不可使用')).toBeInTheDocument());
  });

  it('注册成功：提交 {username, password, display_name} 并跳登录页', async () => {
    const user = setupUser();
    const body = vi.fn();
    installAuthMocks({ user: null, allowRegister: true });
    server.use(
      http.post('/api/auth/register', async ({ request }) => {
        body(await request.json());
        return envelope({ username: 'newbie' }, 201);
      }),
    );

    renderRegister();
    await waitFor(() => expect(screen.getByTestId('register-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('register-username'), 'newbie');
    await user.type(screen.getByTestId('register-display-name'), '新用户');
    await user.type(screen.getByTestId('register-password'), 'password123');
    await user.type(screen.getByTestId('register-confirm'), 'password123');
    await user.click(screen.getByTestId('register-submit'));

    await waitFor(() => expect(screen.getByText('登录页')).toBeInTheDocument());
    expect(body).toHaveBeenCalledWith({
      username: 'newbie',
      password: 'password123',
      display_name: '新用户',
    });
  });

  it('重名 409：提示用户名已存在', async () => {
    const user = setupUser();
    installAuthMocks({ user: null, allowRegister: true });
    server.use(
      http.post('/api/auth/register', () => authError(409, 'username_exists', '用户名已存在')),
    );

    renderRegister();
    await waitFor(() => expect(screen.getByTestId('register-submit')).toBeInTheDocument());

    await user.type(screen.getByTestId('register-username'), 'alice');
    await user.type(screen.getByTestId('register-password'), 'password123');
    await user.type(screen.getByTestId('register-confirm'), 'password123');
    await user.click(screen.getByTestId('register-submit'));

    await waitFor(() => expect(screen.getByText('用户名已存在，请更换')).toBeInTheDocument());
  });
});