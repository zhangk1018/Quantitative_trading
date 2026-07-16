// src/features/strategy-backtest/components/ChartTabs.tsx
// 图表 Tabs：净值曲线 / 回撤曲线 / 月度收益 / 持仓明细 / 交易日志

import React, { useState, lazy, Suspense } from 'react';
import { Tabs, Spin } from 'antd';
import type { StrategyBacktestResult } from '../types';
import HoldingsTable from './HoldingsTable';
import TradeLog from './TradeLog';

// 图表组件懒加载（依赖 lightweight-charts）
const EquityChart = lazy(() => import('./EquityChart'));

interface ChartTabsProps {
  result: StrategyBacktestResult | null;
}

const ChartTabs: React.FC<ChartTabsProps> = ({ result }) => {
  const [activeTab, setActiveTab] = useState<string>('equity');

  if (!result) {
    return (
      <div className="bg-bg-panel rounded-lg border border-border-color p-4">
        <div className="text-text-disabled text-sm text-center py-4">
          运行回测后将显示图表
        </div>
      </div>
    );
  }

  const tabItems = [
    {
      key: 'equity',
      label: '净值曲线',
      children: (
        <Suspense fallback={<div className="text-center py-8"><Spin size="small" /></div>}>
          <EquityChart
            equityCurve={result.equityCurve}
            warnings={result.warnings}
          />
        </Suspense>
      ),
    },
    {
      key: 'holdings',
      label: '持仓明细',
      children: <HoldingsTable holdings={result.holdings} />,
    },
    {
      key: 'trades',
      label: '交易日志',
      children: <TradeLog trades={result.trades} />,
    },
  ];

  return (
    <div className="bg-bg-panel rounded-lg border border-border-color p-4">
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        size="small"
        items={tabItems}
      />
    </div>
  );
};

export default ChartTabs;