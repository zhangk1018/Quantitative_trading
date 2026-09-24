/**
 * tests/auth/helpers.ts — 多用户账号体系测试辅助
 *
 * 统一注册 /api/auth/* 的 MSW 处理器（setup.ts 中 onUnhandledRequest='error'，
 * 未声明的请求会直接报错，故渲染 AuthProvider 的用例必须覆盖 /auth/me + /auth/config）。
 */
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

export interface MockAuthUser {
  username: string;
  role: 'admin' | 'user';
  display_name?: string;
}

/** 统一响应信封 {code, message, data} */
export const envelope = (data: unknown, code = 200) =>
  HttpResponse.json({ code, message: 'success', data });

/** FastAPI 错误体 {detail: {code, message}} */
export const authError = (status: number, code: string, message: string) =>
  HttpResponse.json({ detail: { code, message } }, { status });

/** 204 空响应（logout / change-password） */
export const noContent = () => new HttpResponse(null, { status: 204 });

export interface AuthMockOptions {
  /** 当前登录用户；null 表示未认证（/auth/me 返回 401 unauthenticated） */
  user?: MockAuthUser | null;
  /** 注册开关（/auth/config） */
  allowRegister?: boolean;
  /** 用户列表（/auth/users） */
  users?: unknown[];
  /** 自定义 /auth/me 响应（如 503） */
  meResponse?: () => HttpResponse;
  /** 自定义 /auth/verify 响应（如认证门禁未启用） */
  verifyResponse?: () => HttpResponse;
}

/** 注册 auth 相关默认处理器（用例可用 server.use 覆盖单个接口） */
export function installAuthMocks(options: AuthMockOptions = {}): void {
  const { user = null, allowRegister = false, users = [] } = options;
  server.use(
    http.get('/api/auth/config', () => envelope({ auth_allow_register: allowRegister })),
    http.get('/api/auth/me', () => {
      if (options.meResponse) return options.meResponse();
      return user
        ? envelope({ ...user, display_name: user.display_name ?? user.username })
        : authError(401, 'unauthenticated', '未认证，请先登录');
    }),
    http.get('/api/auth/verify', () => {
      if (options.verifyResponse) return options.verifyResponse();
      return envelope({ authenticated: !!user, username: user?.username, role: user?.role });
    }),
    http.post('/api/auth/login', () => {
      if (!user) return authError(401, 'bad_credentials', '用户名或密码错误');
      return envelope({ username: user.username, role: user.role });
    }),
    http.post('/api/auth/logout', noContent),
    http.post('/api/auth/change-password', noContent),
    http.get('/api/auth/users', () => envelope(users)),
    http.post('/api/auth/users', () => envelope({ username: 'created' }, 201)),
    http.put('/api/auth/users/:id', () => envelope({ username: 'updated' })),
  );
}