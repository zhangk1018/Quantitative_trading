import React, { Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import AppLayout from './layout/AppLayout';

// ✅ 懒加载组件
const StockDetail = React.lazy(() => import('@/features/stock-detail'));
const StockPicker = React.lazy(() => import('@/features/stock-picker'));
const Backtest = React.lazy(() => import('@/features/backtest'));
const Watchlist = React.lazy(() => import('@/features/watchlist'));
const Config = React.lazy(() => import('@/features/config'));
const StrategyBacktest = React.lazy(() => import('@/features/strategy-backtest'));

// 加载中组件
const Loading = () => (
  <div className="h-full flex items-center justify-center text-text-secondary">
    加载中...
  </div>
);

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
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
    ],
  },
]);
