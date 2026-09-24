/**
 * tests/auth/UsersAdmin.test.tsx — 管理员页（列表 / 建号 / 重置密码 / 禁用 / 改角色）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope, authError } from './helpers';
import { AuthProvider } from '@/features/auth/AuthContext';
import UsersAdmin from '@/features/auth/UsersAdmin';

// antd Table/Modal 在 jsdom 下渲染较慢，放宽本文件用例超时
vi.setConfig({ testTimeout: 20000 });

/** 统一 userEvent（关闭逐字延迟，避免 jsdom 下超时） */
const setupUser = () => userEvent.setup({ delay: null });

interface MockRow {
  id: number;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  token_version: number;
  created_at: string | null;
  last_login_at: string | null;
}

const adminRow: MockRow = {
  id: 1,
  username: 'admin',
  display_name: '管理员',
  role: 'admin',
  is_active: true,
  token_version: 1,
  created_at: '2026-09-24 10:00:00',
  last_login_at: '2026-09-24 12:00:00',
};

const bobRow: MockRow = {
  id: 2,
  username: 'bob',
  display_name: '小博',
  role: 'user',
  is_active: true,
  token_version: 1,
  created_at: '2026-09-24 10:05:00',
  last_login_at: null,
};

function renderAdmin() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/users']}>
        <UsersAdmin />
      </MemoryRouter>
    </AuthProvider>,
  );
}

/** 在弹窗（Modal）内定位主操作按钮（antd 会在中文两字按钮中插空格，故去空格比较） */
async function clickModalOk(user: ReturnType<typeof userEvent.setup>, okText: string) {
  const dialog = await screen.findByRole('dialog');
  const target = okText.replace(/\s/g, '');
  const button = within(dialog)
    .getAllByRole('button')
    .reverse()
    .find((b) => (b.textContent || '').replace(/\s/g, '') === target);
  if (!button) throw new Error(`未找到弹窗按钮：${okText}`);
  await user.click(button);
}

/** 确认 Popconfirm（禁用/启用） */
async function confirmPopconfirm(user: ReturnType<typeof userEvent.setup>) {
  const btn = await waitFor(() => {
    const el = document.querySelector<HTMLButtonElement>('.ant-popconfirm-buttons .ant-btn-primary');
    if (!el) throw new Error('Popconfirm 未打开');
    return el;
  });
  await user.click(btn);
}

describe('UsersAdmin 页', () => {
  it('渲染用户列表（用户名 / 角色 / 状态 / 最近登录）', async () => {
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow, bobRow] });
    renderAdmin();

    await waitFor(() => expect(screen.getByText('小博')).toBeInTheDocument());
    expect(screen.getAllByText(/admin/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('管理员').length).toBeGreaterThan(0);
    expect(screen.getByText('普通用户')).toBeInTheDocument();
    expect(screen.getAllByText('启用')).toHaveLength(2);
    expect(screen.getByText('从未登录')).toBeInTheDocument();
  });

  it('建号：提交 {username, password, display_name, role} 并刷新列表', async () => {
    const user = setupUser();
    const createBody = vi.fn();
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow] });
    server.use(
      http.post('/api/auth/users', async ({ request }) => {
        createBody(await request.json());
        return envelope({ username: 'carol' }, 201);
      }),
    );

    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('users-create')).toBeInTheDocument());

    await user.click(screen.getByTestId('users-create'));
    await user.type(await screen.findByTestId('create-username'), 'carol');
    await user.type(screen.getByTestId('create-display-name'), '卡罗');
    await user.type(screen.getByTestId('create-password'), 'password123');
    await clickModalOk(user, '创建');

    await waitFor(() => expect(createBody).toHaveBeenCalled());
    expect(createBody.mock.calls[0][0]).toMatchObject({
      username: 'carol',
      password: 'password123',
      display_name: '卡罗',
      role: 'user',
    });
    await waitFor(() => expect(screen.getByText('账号 carol 创建成功')).toBeInTheDocument());
  });

  it('建号重名（409）：提示用户名已存在', async () => {
    const user = setupUser();
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow] });
    server.use(
      http.post('/api/auth/users', () => authError(409, 'username_exists', '用户名已存在')),
    );

    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('users-create')).toBeInTheDocument());

    await user.click(screen.getByTestId('users-create'));
    await user.type(await screen.findByTestId('create-username'), 'admin');
    await user.type(screen.getByTestId('create-password'), 'password123');
    await clickModalOk(user, '创建');

    await waitFor(() => expect(screen.getByText('用户名已存在，请更换')).toBeInTheDocument());
  });

  it('禁用用户：确认弹窗后提交 is_active=false', async () => {
    const user = setupUser();
    const patchBody = vi.fn();
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow, bobRow] });
    server.use(
      http.put('/api/auth/users/:id', async ({ request }) => {
        patchBody({ id: (request.url.split('/').pop() || ''), body: await request.json() });
        return envelope({ username: 'bob' });
      }),
    );

    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('user-toggle-2')).toBeInTheDocument());

    await user.click(screen.getByTestId('user-toggle-2'));
    await confirmPopconfirm(user);

    await waitFor(() => expect(patchBody).toHaveBeenCalled());
    expect(patchBody.mock.calls[0][0]).toEqual({ id: '2', body: { is_active: false } });
    await waitFor(() => expect(screen.getByText('已禁用 bob，其登录会话已失效')).toBeInTheDocument());
  });

  it('改角色：选择管理员后提交 role=admin', async () => {
    const user = setupUser();
    const patchBody = vi.fn();
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow, bobRow] });
    server.use(
      http.put('/api/auth/users/:id', async ({ request }) => {
        patchBody(await request.json());
        return envelope({ username: 'bob' });
      }),
    );

    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('user-role-2')).toBeInTheDocument());

    await user.click(screen.getByTestId('user-role-2'));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByText('管理员'));
    await clickModalOk(user, '确认');

    await waitFor(() => expect(patchBody).toHaveBeenCalledWith({ role: 'admin' }));
    await waitFor(() => expect(screen.getByText('已将 bob 的角色改为管理员')).toBeInTheDocument());
  });

  it('重置密码：提交 password 字段', async () => {
    const user = setupUser();
    const patchBody = vi.fn();
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow, bobRow] });
    server.use(
      http.put('/api/auth/users/:id', async ({ request }) => {
        patchBody(await request.json());
        return envelope({ username: 'bob' });
      }),
    );

    renderAdmin();
    await waitFor(() => expect(screen.getByTestId('user-reset-2')).toBeInTheDocument());

    await user.click(screen.getByTestId('user-reset-2'));
    await user.type(await screen.findByTestId('reset-password'), 'reset-password1');
    await clickModalOk(user, '确认重置');

    await waitFor(() => expect(patchBody).toHaveBeenCalledWith({ password: 'reset-password1' }));
  });

  it('防自锁：当前登录账号的「禁用」「改角色」按钮不可用，他人可操作', async () => {
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, users: [adminRow, bobRow] });
    renderAdmin();

    await waitFor(() => expect(screen.getByTestId('user-role-1')).toBeInTheDocument());
    expect(screen.getByTestId('user-role-1')).toBeDisabled();
    expect(screen.getByTestId('user-toggle-1')).toBeDisabled();
    expect(screen.getByTestId('user-role-2')).toBeEnabled();
    expect(screen.getByTestId('user-toggle-2')).toBeEnabled();
  });

  it('列表加载失败（503）：展示错误与重试入口', async () => {
    installAuthMocks({ user: { username: 'admin', role: 'admin' } });
    server.use(
      http.get('/api/auth/users', () => authError(503, 'db_unavailable', '认证服务暂时不可用，请稍后重试')),
    );

    renderAdmin();
    await waitFor(() =>
      expect(screen.getByText('认证服务暂时不可用，请稍后重试')).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument();
  });
});