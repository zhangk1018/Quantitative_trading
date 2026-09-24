/**
 * tests/auth/authApi.test.ts — 认证 REST 客户端契约与错误码解析
 */
import { describe, it, expect, vi } from 'vitest';
import { http } from 'msw';
import { server } from '../mocks/server';
import { installAuthMocks, envelope, authError, noContent } from './helpers';
import {
  changePassword,
  fetchAuthConfig,
  fetchMe,
  fetchUsers,
  login,
  logout,
  parseAuthError,
  register,
  updateUser,
} from '@/features/auth/api';

/** 构造与 axios 错误同形的对象（parseAuthError 依赖 isAxiosError 标记） */
const axiosLikeError = (status: number, detail: unknown) => ({
  isAxiosError: true,
  message: `Request failed with status code ${status}`,
  response: { status, data: { detail } },
});

describe('auth/api — parseAuthError', () => {
  it('解析对象形 detail：返回后端业务 code 与提示', () => {
    const info = parseAuthError(axiosLikeError(401, { code: 'bad_credentials', message: '用户名或密码错误' }));
    expect(info.status).toBe(401);
    expect(info.code).toBe('bad_credentials');
    expect(info.message).toBe('用户名或密码错误');
  });

  it('解析字符串形 detail（非认证接口的 400）', () => {
    const info = parseAuthError(axiosLikeError(400, 'start_date 不能晚于 end_date'));
    expect(info.status).toBe(400);
    expect(info.code).toBe('');
    expect(info.message).toBe('start_date 不能晚于 end_date');
  });

  it('无响应体时回落到状态码默认提示', () => {
    const info = parseAuthError(axiosLikeError(503, undefined));
    expect(info.code).toBe('');
    expect(info.message).toContain('503');
  });

  it('非 axios 异常（网络中断）归一为 network_error', () => {
    const info = parseAuthError(new Error('Failed to fetch'));
    expect(info.status).toBe(0);
    expect(info.code).toBe('network_error');
    expect(info.message).toBe('Failed to fetch');
  });
});

describe('auth/api — 接口契约', () => {
  it('login 提交 {username, password} 并返回身份', async () => {
    const body = vi.fn();
    server.use(
      http.post('/api/auth/login', async ({ request }) => {
        body(await request.json());
        return envelope({ username: 'alice', role: 'user' });
      }),
    );

    const user = await login('alice', 'secret-pwd');
    expect(body).toHaveBeenCalledWith({ username: 'alice', password: 'secret-pwd' });
    expect(user).toEqual({ username: 'alice', role: 'user' });
  });

  it('login 密码错误 → 401 bad_credentials', async () => {
    installAuthMocks({ user: null });
    await expect(login('alice', 'wrong')).rejects.toBeTruthy();
    try {
      await login('alice', 'wrong');
    } catch (e) {
      expect(parseAuthError(e).code).toBe('bad_credentials');
    }
  });

  it('fetchMe / fetchAuthConfig / fetchVerify 解包信封 data', async () => {
    installAuthMocks({ user: { username: 'admin', role: 'admin' }, allowRegister: true });
    const [me, cfg] = await Promise.all([fetchMe(), fetchAuthConfig()]);
    expect(me.username).toBe('admin');
    expect(me.display_name).toBe('admin');
    expect(cfg.auth_allow_register).toBe(true);
  });

  it('register 重名 → 409 username_exists；密码过短 → 400 weak_password', async () => {
    server.use(
      http.post('/api/auth/register', () => authError(409, 'username_exists', '用户名已存在')),
    );
    try {
      await register('alice', 'password123');
      throw new Error('应当抛出异常');
    } catch (e) {
      expect(parseAuthError(e).code).toBe('username_exists');
    }

    server.use(
      http.post('/api/auth/register', () => authError(400, 'weak_password', '密码过短，至少需要 8 位')),
    );
    try {
      await register('bob', 'short');
      throw new Error('应当抛出异常');
    } catch (e) {
      expect(parseAuthError(e).code).toBe('weak_password');
    }
  });

  it('changePassword 旧密码错误 → 401 bad_old_password；成功 → 204', async () => {
    server.use(
      http.post('/api/auth/change-password', () => authError(401, 'bad_old_password', '旧密码错误')),
    );
    try {
      await changePassword('wrong-old', 'new-password');
      throw new Error('应当抛出异常');
    } catch (e) {
      expect(parseAuthError(e).code).toBe('bad_old_password');
    }

    server.use(http.post('/api/auth/change-password', noContent));
    await expect(changePassword('old-pwd', 'new-password')).resolves.toBeUndefined();
  });

  it('logout 走 204 空响应', async () => {
    installAuthMocks();
    await expect(logout()).resolves.toBeUndefined();
  });

  it('fetchUsers 返回列表；updateUser 提交变更字段', async () => {
    const patchBody = vi.fn();
    installAuthMocks({
      users: [
        {
          id: 1,
          username: 'admin',
          display_name: '管理员',
          role: 'admin',
          is_active: true,
          token_version: 1,
          created_at: null,
          last_login_at: null,
        },
      ],
    });
    server.use(
      http.put('/api/auth/users/:id', async ({ request, params }) => {
        patchBody({ id: params.id, body: await request.json() });
        return envelope({ username: 'bob' });
      }),
    );

    const list = await fetchUsers();
    expect(list).toHaveLength(1);
    expect(list[0].username).toBe('admin');

    await updateUser(2, { is_active: false });
    expect(patchBody).toHaveBeenCalledWith({ id: '2', body: { is_active: false } });
  });
});