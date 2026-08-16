/**
 * PDCADashboard.tsx — PDCA 交易自律系统主仪表盘
 *
 * 一期功能：
 * - 交易台账（CRUD 表格）
 * - 交易日记（绑定交易记录）
 * - 资金曲线（ECharts）
 * - 券商导入（Excel 上传解析）
 * - 系统配置（2%/6% 风控阈值等）
 * - 数据导出/备份
 */

import React, { useState } from 'react';
import { Tabs } from 'antd';
import { TableOutlined, EditOutlined, LineChartOutlined, FundOutlined, ImportOutlined, RadarChartOutlined, FileTextOutlined } from '@ant-design/icons';
import TradingRecordTable from './components/TradingRecordTable';
import TradingDiaryEditor from './components/TradingDiaryEditor';
import EquityCurve from './components/EquityCurve';
import EquityAutoCurve from './components/EquityAutoCurve';
import ImportExcel from './components/ImportExcel';
import CycleOverview from './components/CycleOverview';
import TradingPlanEditor from './components/TradingPlanEditor';


const PDCADashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('records');

  const tabItems = [
    {
      key: 'records',
      label: (
        <span className="flex items-center gap-2">
          <TableOutlined />
          <span>交易台账</span>
        </span>
      ),
      children: <TradingRecordTable />,
    },
    {
      key: 'diary',
      label: (
        <span className="flex items-center gap-2">
          <EditOutlined />
          <span>交易日记</span>
        </span>
      ),
      children: <TradingDiaryEditor />,
    },
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
    {
      key: 'cycles',
      label: (
        <span className="flex items-center gap-2">
          <RadarChartOutlined />
          <span>周期总览</span>
        </span>
      ),
      children: <CycleOverview />,
    },
    {
      key: 'plans',
      label: (
        <span className="flex items-center gap-2">
          <FileTextOutlined />
          <span>交易计划</span>
        </span>
      ),
      children: <TradingPlanEditor />,
    },
    {
      key: 'import',
      label: (
        <span className="flex items-center gap-2">
          <ImportOutlined />
          <span>券商导入</span>
        </span>
      ),
      children: <ImportExcel />,
    },
  ];

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* Tab 内容区 */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          className="h-full pdca-tabs"
          tabBarStyle={{
            margin: 0,
            paddingLeft: 16,
            background: 'var(--bg-panel, #1a1a2e)',
            borderBottom: '1px solid var(--border-color, #2a2a3e)',
          }}
          style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
        />
      </div>
    </div>
  );
};

export default PDCADashboard;