// src/features/strategy-backtest/index.tsx
// 策略回测模块入口 — 懒加载

import React, { Suspense, lazy } from 'react';
import { Spin } from 'antd';

const StrategyBacktestView = lazy(() => import('./StrategyBacktestView'));

const StrategyBacktest: React.FC = () => (
  <Suspense
    fallback={
      <div className="flex items-center justify-center h-64">
        <Spin size="large" tip="加载中..." />
      </div>
    }
  >
    <StrategyBacktestView />
  </Suspense>
);

export default StrategyBacktest;