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
import { Tabs, Typography } from 'antd';
import {
  TableOutlined,
  EditOutlined,
  LineChartOutlined,
  ImportOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import TradingRecordTable from './components/TradingRecordTable';
import TradingDiaryEditor from './components/TradingDiaryEditor';
import EquityCurve from './components/EquityCurve';
import ImportExcel from './components/ImportExcel';
import SystemConfig from './components/SystemConfig';

const { Text } = Typography;

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
          <span>资金曲线</span>
        </span>
      ),
      children: <EquityCurve />,
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
    {
      key: 'config',
      label: (
        <span className="flex items-center gap-2">
          <SettingOutlined />
          <span>系统配置</span>
        </span>
      ),
      children: <SystemConfig />,
    },
  ];

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* 顶部标题栏 */}
      <div className="h-12 px-4 flex items-center border-b border-border-color bg-bg-panel flex-shrink-0">
        <Text className="text-text-primary font-semibold">PDCA 交易自律</Text>
        <Text className="text-text-secondary text-xs ml-3">一期 · 基础台账 MVP</Text>
      </div>

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