import React, { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppLayout from './layout/AppLayout';
import { useAuth } from '@/features/auth/AuthContext';

// ✅ 懒加载组件
const StockDetail = React.lazy(() => import('@/features/stock-detail'));
const StockPicker = React.lazy(() => import('@/features/stock-picker'));
const Backtest = React.lazy(() => import('@/features/backtest'));
const Watchlist = React.lazy(() => import('@/features/watchlist'));
const Config = React.lazy(() => import('@/features/config'));
const StrategyBacktest = React.lazy(() => import('@/features/strategy-backtest'));
const PDCA = React.lazy(() => import('@/features/pdca'));
const Login = React.lazy(() => import('@/features/auth/Login'));
const Register = React.lazy(() => import('@/features/auth/Register'));
const ChangePassword = React.lazy(() => import('@/features/auth/ChangePassword'));
const UsersAdmin = React.lazy(() => import('@/features/auth/UsersAdmin'));

// 加载中组件
const Loading = () => (
  <div className="h-full flex items-center justify-center text-text-secondary">
    加载中...
  </div>
);

/**
 * 认证探测失败兜底（如后端 503「认证服务暂时不可用」）——
 * 不误跳登录页，提供重试。
 */
const AuthErrorPanel: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <div className="h-full flex flex-col items-center justify-center gap-3 text-text-secondary">
    <span>{message}</span>
    <button
      className="px-4 py-1 rounded border border-border-color text-text-primary hover:border-border-hover"
      onClick={onRetry}
      data-testid="auth-retry"
    >
      重试
    </button>
  </div>
);

// ── 路由守卫：登录态取自 AuthProvider 的 /auth/me 缓存（导航不重复请求） ──
// 401 `unauthenticated`（含被禁用/改密/重置后会话失效）→ 重定向 /login
const AuthGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { loading, user, error, authDisabled, reload } = useAuth();

  if (loading) {
    return <Loading />;
  }

  if (error) {
    return <AuthErrorPanel message={error} onRetry={() => void reload()} />;
  }

  // authDisabled：后端未启用认证门禁（API_AUTH_ENABLED=false）时放行
  if (!user && !authDisabled) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// ── 管理员守卫：按 role 控制入口（非 admin 回选股页） ──
const AdminGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, authDisabled } = useAuth();

  if (!authDisabled && user?.role !== 'admin') {
    return <Navigate to="/picker" replace />;
  }

  return <>{children}</>;
};

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <Suspense fallback={<Loading />}>
        <Login />
      </Suspense>
    ),
  },
  {
    path: '/register',
    element: (
      <Suspense fallback={<Loading />}>
        <Register />
      </Suspense>
    ),
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <AppLayout />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/picker" replace /> },
      { 
        path: 'picker', 
        element: (
          <Suspense fallback={<Loading />}>
            <StockPicker />
          </Suspense>
        ) 
      },
      { 
        path: 'watchlist', 
        element: (
          <Suspense fallback={<Loading />}>
            <Watchlist />
          </Suspense>
        ) 
      },
      { 
        path: 'backtest', 
        element: (
          <Suspense fallback={<Loading />}>
            <Backtest />
          </Suspense>
        ) 
      },
      { 
        path: 'config', 
        element: (
          <Suspense fallback={<Loading />}>
            <Config />
          </Suspense>
        ) 
      },
      { 
        path: 'stock/:code', 
        element: (
          <Suspense fallback={<Loading />}>
            <StockDetail />
          </Suspense>
        ) 
      },
      { 
        path: 'strategy-backtest', 
        element: (
          <Suspense fallback={<Loading />}>
            <StrategyBacktest />
          </Suspense>
        ) 
      },
      { 
        path: 'pdca', 
        element: (
          <Suspense fallback={<Loading />}>
            <PDCA />
          </Suspense>
        ) 
      },
      {
        path: 'change-password',
        element: (
          <Suspense fallback={<Loading />}>
            <ChangePassword />
          </Suspense>
        ),
      },
      {
        path: 'users',
        element: (
          <AdminGuard>
            <Suspense fallback={<Loading />}>
              <UsersAdmin />
            </Suspense>
          </AdminGuard>
        ),
      },
    ],
  },
]);