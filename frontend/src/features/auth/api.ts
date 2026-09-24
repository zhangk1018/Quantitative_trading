/**
 * auth/api.ts — 多用户账号体系 REST 客户端
 *
 * 对接后端 /api/auth（成功走统一信封 {code, message, data}；
 * 失败为 HTTPException，HTTP 状态码 + body {detail: {code, message}}）。
 *
 * 契约见 docs/plans/多用户账号体系改造方案.md §4.3：
 * - login 成功 200 + {username, role} + Set-Cookie
 * - 401 body code：bad_credentials（密码错）/ unauthenticated（未认证或会话失效）
 * - 403 disabled（账号禁用）/ forbidden（非管理员）；409 username_exists；429 rate_limited
 */
import axios from 'axios';
import { attachSessionWatcher } from './session';

const api = axios.create({ baseURL: '/api', withCredentials: true });

// 各业务接口未认证时（401 unauthenticated）统一走「会话失效」处理（踢下线跳登录）
attachSessionWatcher(api);

interface ApiEnvelope<T> {
  code?: number;
  message?: string;
  data: T;
}

/** 当前登录用户身份 */
export interface AuthUser {
  username: string;
  role: 'admin' | 'user';
  display_name?: string;
}

/** 认证错误（含后端业务 code，前端据此区分提示语义） */
export interface AuthErrorInfo {
  status: number;
  code: string;
  message: string;
}

/** 用户列表项（管理员页） */
export interface AuthUserItem {
  id: number;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  token_version: number;
  created_at: string | null;
  last_login_at: string | null;
}

/** 管理员建号请求体 */
export interface CreateUserPayload {
  username: string;
  password: string;
  display_name?: string;
  role?: 'admin' | 'user';
}

/** 管理员更新用户请求体（重置密码 / 禁用启用 / 改角色） */
export interface UpdateUserPayload {
  password?: string;
  is_active?: boolean;
  role?: 'admin' | 'user';
}

const STATUS_FALLBACK_MESSAGE: Record<number, string> = {
  400: '请求参数有误',
  401: '用户名或密码错误',
  403: '没有操作权限',
  404: '目标不存在',
  409: '资源已存在',
  422: '请求参数校验失败',
  429: '操作过于频繁，请稍后再试',
  503: '认证服务暂时不可用，请稍后重试',
};

/** 判断错误体是否为「未认证 / 会话失效」（区别于密码错误） */
export function isUnauthenticatedCode(code: string | undefined): boolean {
  return code === 'unauthenticated';
}

/**
 * 从请求异常中提取后端业务 code 与可读提示。
 *
 * @param err 任意捕获到的异常（通常为 axios 错误）
 * @returns 归一化的 {status, code, message}
 */
export function parseAuthError(err: unknown): AuthErrorInfo {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status ?? 0;
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
    let code = '';
    let message = '';
    if (detail && typeof detail === 'object') {
      const d = detail as { code?: string; message?: string };
      code = d.code ?? '';
      message = d.message ?? '';
    } else if (typeof detail === 'string') {
      message = detail;
    }
    if (!message) {
      message = err.message || STATUS_FALLBACK_MESSAGE[status] || '请求失败，请稍后重试';
    }
    return { status, code, message };
  }
  return {
    status: 0,
    code: 'network_error',
    message: err instanceof Error ? err.message : '网络连接失败',
  };
}

/** 登录：成功返回身份并下发 HttpOnly Cookie */
export const login = async (username: string, password: string): Promise<AuthUser> => {
  const { data } = await api.post<ApiEnvelope<AuthUser>>('/auth/login', { username, password });
  return data.data;
};

/** 登出：清除会话 Cookie（不使其它设备失效） */
export const logout = async (): Promise<void> => {
  await api.post('/auth/logout');
};

/** 当前用户信息（顶栏展示 + 路由守卫缓存来源） */
export const fetchMe = async (): Promise<AuthUser> => {
  const { data } = await api.get<ApiEnvelope<AuthUser>>('/auth/me');
  return data.data;
};

/** 会话探活（公开接口，用于区分「未认证」与「未启用认证门禁」） */
export const fetchVerify = async (): Promise<{ authenticated: boolean; username?: string; role?: string }> => {
  const { data } = await api.get<ApiEnvelope<{ authenticated: boolean; username?: string; role?: string }>>(
    '/auth/verify',
  );
  return data.data;
};

/** 认证配置（注册入口显隐） */
export const fetchAuthConfig = async (): Promise<{ auth_allow_register: boolean }> => {
  const { data } = await api.get<ApiEnvelope<{ auth_allow_register: boolean }>>('/auth/config');
  return data.data;
};

/** 自助注册（需 auth_allow_register=true） */
export const register = async (
  username: string,
  password: string,
  displayName?: string,
): Promise<{ username: string }> => {
  const { data } = await api.post<ApiEnvelope<{ username: string }>>('/auth/register', {
    username,
    password,
    display_name: displayName || undefined,
  });
  return data.data;
};

/** 修改密码（校验旧密码；成功后后端 token_version+1，当前会话需重新登录） */
export const changePassword = async (oldPassword: string, newPassword: string): Promise<void> => {
  await api.post('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  });
};

/** 登出所有设备（token_version+1） */
export const logoutAll = async (): Promise<void> => {
  await api.post('/auth/logout-all');
};

/** 用户列表（仅 admin） */
export const fetchUsers = async (): Promise<AuthUserItem[]> => {
  const { data } = await api.get<ApiEnvelope<AuthUserItem[]>>('/auth/users');
  return Array.isArray(data.data) ? data.data : [];
};

/** 管理员建号（仅 admin） */
export const createUser = async (payload: CreateUserPayload): Promise<{ username: string }> => {
  const { data } = await api.post<ApiEnvelope<{ username: string }>>('/auth/users', payload);
  return data.data;
};

/** 管理员操作用户（重置密码 / 禁用启用 / 改角色，仅 admin） */
export const updateUser = async (id: number, payload: UpdateUserPayload): Promise<{ username: string }> => {
  const { data } = await api.put<ApiEnvelope<{ username: string }>>(`/auth/users/${id}`, payload);
  return data.data;
};