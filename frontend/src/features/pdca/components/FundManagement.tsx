/**
 * FundManagement.tsx — 资金管理父Tab
 *
 * 内嵌子Tab：
 * - 资金记录（手动录入 CRUD）
 * - 资金曲线（自动计算净值曲线）
 */

import React, { useState } from 'react';
import { Tabs } from 'antd';
import { LineChartOutlined, FundOutlined } from '@ant-design/icons';
import EquityCurve from './EquityCurve';
import EquityAutoCurve from './EquityAutoCurve';

const FundManagement: React.FC = () => {
  const [subTab, setSubTab] = useState('equity');

  return (
    <Tabs
      activeKey={subTab}
      onChange={setSubTab}
      items={[
        {
          key: 'equity',
          label: (
            <span className="flex items-center gap-2">
              <LineChartOutlined />
              <span>资金记录</span>
            </span>
          ),
          children: <EquityCurve />,
        },
        {
          key: 'equity-curve',
          label: (
            <span className="flex items-center gap-2">
              <FundOutlined />
              <span>资金曲线</span>
            </span>
          ),
          children: <EquityAutoCurve />,
        },
      ]}
      className="fund-sub-tabs"
      tabBarStyle={{
        margin: 0,
        paddingLeft: 16,
        background: 'transparent',
        borderBottom: '1px solid var(--border-color, #2a2a3e)',
      }}
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
    />
  );
};

export default FundManagement;