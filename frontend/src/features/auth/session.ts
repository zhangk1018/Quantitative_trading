/**
 * auth/session.ts — 会话失效（被踢下线）统一捕获
 *
 * 场景：管理员禁用账号 / 重置密码 / 用户改密后，后端 `token_version` 变化，
 * 该用户浏览器上的旧会话在**下一次任意请求**时被判 401 `unauthenticated`。
 * 前端需统一捕获并让路由守卫跳回登录页（方案 §5：401 `unauthenticated` 才跳登录页）。
 *
 * 覆盖两条网络通道：
 * - axios 实例：`attachSessionWatcher(instance)` 注册响应拦截器
 * - 原生 fetch：`installFetchSessionWatcher()` 包装 window.fetch（幂等）
 *
 * 触发条件：401 且 body code 为 `unauthenticated`（未认证/改密重置）或 `disabled`（账号被禁用）；
 * 登录页的 401 `bad_credentials` 与 403 `disabled` 不触发，避免误跳。
 */
import type { AxiosInstance } from 'axios';

type SessionExpiredHandler = () => void;

let sessionExpiredHandler: SessionExpiredHandler | null = null;

/**
 * 会话失效语义的 body `code` 集合：
 * - `unauthenticated`：未认证 / token 过期 / 改密重置后旧 token（ver 不匹配）
 * - `disabled`：账号被管理员禁用（`get_current_user` 返回 401 disabled）
 * 二者都需清空登录态并跳登录页；登录页的 `bad_credentials`（401）/`disabled`（403）不在其列。
 */
const SESSION_INVALID_CODES = ['unauthenticated', 'disabled'];

/** 注册会话失效回调（由 AuthProvider 注入） */
export function setSessionExpiredHandler(handler: SessionExpiredHandler | null): void {
  sessionExpiredHandler = handler;
}

/** 通知会话已失效（清空本地会话 → 守卫重定向登录页） */
export function notifySessionExpired(): void {
  if (!sessionExpiredHandler) return;
  try {
    sessionExpiredHandler();
  } catch (e) {
    console.warn('[auth] 会话失效处理失败', e);
  }
}

/**
 * 判断响应体是否为「会话失效」语义。
 *
 * 兼容两种形状：FastAPI 错误体 `{detail: {code, message}}` 与统一信封 `{code}`。
 */
export function isSessionInvalidPayload(body: unknown): boolean {
  if (!body || typeof body !== 'object') return false;
  const detail = (body as { detail?: unknown }).detail;
  if (detail && typeof detail === 'object') {
    const code = (detail as { code?: string }).code;
    if (code && SESSION_INVALID_CODES.includes(code)) return true;
  }
  const code = (body as { code?: unknown }).code;
  return typeof code === 'string' && SESSION_INVALID_CODES.includes(code);
}

/** 为 axios 实例注册会话失效拦截器（401 会话失效 → 通知） */
export function attachSessionWatcher(instance: AxiosInstance): void {
  instance.interceptors.response.use(
    (response) => response,
    (error: unknown) => {
      const response = (error as { response?: { status?: number; data?: unknown } })?.response;
      if (response?.status === 401 && isSessionInvalidPayload(response.data)) {
        notifySessionExpired();
      }
      return Promise.reject(error);
    },
  );
}

const FETCH_FLAG = '__quantSessionWatcherInstalled';

/**
 * 包装 window.fetch：任一请求返回 401 unauthenticated 时通知会话失效（幂等）。
 *
 * @returns 卸载函数（恢复原始 fetch）
 */
export function installFetchSessionWatcher(): () => void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
    return () => {};
  }
  const originalFetch = window.fetch;
  if ((originalFetch as unknown as Record<string, unknown>)[FETCH_FLAG]) {
    return () => {};
  }
  const wrappedFetch: typeof window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (response.status === 401) {
      try {
        const body = await response.clone().json();
        if (isSessionInvalidPayload(body)) notifySessionExpired();
      } catch {
        // 非 JSON 响应体：忽略（不影响业务错误处理）
      }
    }
    return response;
  };
  (wrappedFetch as unknown as Record<string, unknown>)[FETCH_FLAG] = true;
  window.fetch = wrappedFetch;
  return () => {
    window.fetch = originalFetch;
  };
}