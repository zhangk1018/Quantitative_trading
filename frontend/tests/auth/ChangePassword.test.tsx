/**
 * tests/auth/ChangePassword.test.tsx — 改密页（旧密码校验、成功后清会话回登录页）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, authError, noContent } from './helpers';
import { AuthProvider } from '@/features/auth/AuthContext';
import ChangePassword from '@/features/auth/ChangePassword';

// antd 表单在 jsdom 下渲染较慢，放宽本文件用例超时
vi.setConfig({ testTimeout: 20000 });

/** 统一 userEvent（关闭逐字延迟，避免 jsdom 下超时） */
const setupUser = () => userEvent.setup({ delay: null });

function renderPage() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/change-password']}>
        <Routes>
          <Route path="/change-password" element={<ChangePassword />} />
          <Route path="/login" element={<div>登录页</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

async function fill(user: ReturnType<typeof userEvent.setup>, oldPwd: string, newPwd: string, confirm: string) {
  await user.type(screen.getByTestId('change-pwd-old'), oldPwd);
  await user.type(screen.getByTestId('change-pwd-new'), newPwd);
  await user.type(screen.getByTestId('change-pwd-confirm'), confirm);
  await user.click(screen.getByTestId('change-pwd-submit'));
}

describe('ChangePassword 页', () => {
  it('两次新密码不一致：前端拦截', async () => {
    const user = setupUser();
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('change-pwd-submit')).toBeInTheDocument());

    await fill(user, 'old-password', 'new-password1', 'new-password2');
    await waitFor(() => expect(screen.getByText('两次输入的新密码不一致')).toBeInTheDocument());
  });

  it('旧密码错误 → 401 bad_old_password 提示', async () => {
    const user = setupUser();
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    server.use(
      http.post('/api/auth/change-password', () => authError(401, 'bad_old_password', '旧密码错误')),
    );

    renderPage();
    await waitFor(() => expect(screen.getByTestId('change-pwd-submit')).toBeInTheDocument());

    await fill(user, 'wrong-old', 'new-password1', 'new-password1');
    await waitFor(() => expect(screen.getByText('旧密码错误')).toBeInTheDocument());
  });

  it('新密码过短 → 前端拦截（与后端策略一致 ≥8 位）', async () => {
    const user = setupUser();
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('change-pwd-submit')).toBeInTheDocument());

    await fill(user, 'old-password', 'short', 'short');
    await waitFor(() => expect(screen.getByText('新密码至少 8 位')).toBeInTheDocument());
  });

  it('改密成功：提交旧/新密码 → 清会话（logout）→ 回登录页', async () => {
    const user = setupUser();
    const changeBody = vi.fn();
    const logoutCalled = vi.fn();
    installAuthMocks({ user: { username: 'alice', role: 'user' } });
    server.use(
      http.post('/api/auth/change-password', async ({ request }) => {
        changeBody(await request.json());
        return noContent();
      }),
      http.post('/api/auth/logout', () => {
        logoutCalled();
        return noContent();
      }),
    );

    renderPage();
    await waitFor(() => expect(screen.getByTestId('change-pwd-submit')).toBeInTheDocument());

    await fill(user, 'old-password', 'new-password1', 'new-password1');

    await waitFor(() => expect(screen.getByText('登录页')).toBeInTheDocument());
    expect(changeBody).toHaveBeenCalledWith({ old_password: 'old-password', new_password: 'new-password1' });
    expect(logoutCalled).toHaveBeenCalled();
  });
});