import React, { Suspense, useEffect, useState } from 'react';
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom';
import AppLayout from './layout/AppLayout';

// ✅ 懒加载组件
const StockDetail = React.lazy(() => import('@/features/stock-detail'));
const StockPicker = React.lazy(() => import('@/features/stock-picker'));
const Backtest = React.lazy(() => import('@/features/backtest'));
const Watchlist = React.lazy(() => import('@/features/watchlist'));
const Config = React.lazy(() => import('@/features/config'));
const StrategyBacktest = React.lazy(() => import('@/features/strategy-backtest'));
const PDCA = React.lazy(() => import('@/features/pdca'));
const Login = React.lazy(() => import('@/features/auth/Login'));

// 加载中组件
const Loading = () => (
  <div className="h-full flex items-center justify-center text-text-secondary">
    加载中...
  </div>
);

// ── 路由守卫：检查认证状态，未认证则重定向到 /login ──
const AuthGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'unauthenticated'>('loading');
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch('/api/auth/verify', { credentials: 'include' });
        const body = await res.json();
        if (!cancelled) {
          setStatus(body?.data?.authenticated ? 'authenticated' : 'unauthenticated');
        }
      } catch {
        if (!cancelled) setStatus('unauthenticated');
      }
    };
    check();
    return () => { cancelled = true; };
  }, [location.pathname]);

  if (status === 'loading') {
    return <Loading />;
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />;
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
    ],
  },
]);
