/**
 * auth/AuthContext.tsx — 全局登录态（多用户账号体系）
 *
 * 职责（方案 §5）：
 * - 应用启动探测一次 `/api/auth/me`，结果缓存在内存（Provider 挂在 Router 之上，
 *   路由切换复用同一份，不重复请求）；顶栏、守卫、管理员页共用。
 * - 缓存 `/api/auth/config` 的注册开关，控制注册入口显隐。
 * - 捕获 401 `unauthenticated`（被禁用 / 改密 / 重置后旧会话失效）→ 清空登录态，
 *   由路由守卫重定向 `/login`。
 * - 区分「未认证」与「后端未启用认证门禁」（auth_enabled=false 时放行）。
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import {
  AuthUser,
  fetchAuthConfig,
  fetchMe,
  fetchVerify,
  login as apiLogin,
  logout as apiLogout,
  parseAuthError,
} from './api';
import { installFetchSessionWatcher, setSessionExpiredHandler } from './session';

interface AuthContextValue {
  /** 当前登录用户；未认证时为 null */
  user: AuthUser | null;
  /** 首次探测进行中 */
  loading: boolean;
  /** 探测失败（如 503 认证服务不可用），供守卫展示重试 */
  error: string | null;
  /** 后端未启用认证门禁（API_AUTH_ENABLED=false），守卫放行 */
  authDisabled: boolean;
  /** 是否开放自助注册（/auth/config） */
  allowRegister: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  /** 重新探测登录态 */
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}

/**
 * 可选消费登录态（返回 null 表示未挂 AuthProvider）。
 * 供既可在有/无认证环境下工作的模块使用（如自选股存储按账号隔离）。
 */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authDisabled, setAuthDisabled] = useState(false);
  const [allowRegister, setAllowRegister] = useState(false);
  const probingRef = useRef(false);

  /** 探测登录态：/auth/me 为主；401 时用 /auth/verify 区分「未认证」与「未启用门禁」 */
  const reload = useCallback(async () => {
    if (probingRef.current) return;
    probingRef.current = true;
    try {
      const me = await fetchMe();
      setUser(me);
      setAuthDisabled(false);
      setError(null);
    } catch (e) {
      const info = parseAuthError(e);
      // 会话失效（未认证 / 账号被禁用）→ 视为未登录，由守卫跳登录页
      if (info.status === 401 && (info.code === 'unauthenticated' || info.code === 'disabled')) {
        let disabledGate = false;
        try {
          const probe = await fetchVerify();
          disabledGate = probe.authenticated && !probe.username;
        } catch {
          disabledGate = false;
        }
        setAuthDisabled(disabledGate);
        setUser(null);
        setError(null);
      } else {
        setError(info.message);
      }
    } finally {
      probingRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 会话失效（被禁用/改密/重置）→ 清空登录态
    setSessionExpiredHandler(() => {
      setUser(null);
      setError(null);
    });
    // 覆盖原生 fetch 通道；axios 通道在各 api 模块 attachSessionWatcher 时已挂
    const uninstallFetchWatcher = installFetchSessionWatcher();
    void reload();
    return () => {
      setSessionExpiredHandler(null);
      uninstallFetchWatcher();
    };
  }, [reload]);

  // 注册开关（注册入口显隐），失败时按关闭处理
  useEffect(() => {
    let cancelled = false;
    fetchAuthConfig()
      .then((cfg) => {
        if (!cancelled) setAllowRegister(Boolean(cfg.auth_allow_register));
      })
      .catch(() => {
        if (!cancelled) setAllowRegister(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<AuthUser> => {
    const me = await apiLogin(username, password);
    setUser(me);
    setAuthDisabled(false);
    setError(null);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (e) {
      // 登出失败不阻塞前端清态（Cookie 过期/网络异常时仍应回到登录页）
      console.warn('[auth] 登出请求失败', e);
    }
    setUser(null);
    setError(null);
  }, []);

  const value: AuthContextValue = {
    user,
    loading,
    error,
    authDisabled,
    allowRegister,
    isAdmin: user?.role === 'admin',
    login,
    logout,
    reload,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}