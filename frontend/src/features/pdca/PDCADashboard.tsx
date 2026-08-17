/**
 * PDCADashboard.tsx — PDCA 交易自律系统主仪表盘
 *
 * Tab 布局（左侧 PDCA 顺序，右侧资金管理+券商导入）：
 *   [周期总览] [交易计划] [交易台账] [交易日记]  |  [资金管理] [券商导入]
 *
 * 一期功能：
 * - 交易台账（CRUD 表格）
 * - 交易日记（绑定交易记录）
 * - 资金管理（资金记录 + 资金曲线）
 * - 券商导入（Excel 上传解析）
 * - 系统配置（2%/6% 风控阈值等）
 * - 数据导出/备份
 */

import React, { useEffect, useState } from 'react';
import { Tabs } from 'antd';
import { TableOutlined, EditOutlined, ImportOutlined, RadarChartOutlined, FileTextOutlined, DollarOutlined } from '@ant-design/icons';
import TradingRecordTable from './components/TradingRecordTable';
import TradingDiaryEditor from './components/TradingDiaryEditor';
import FundManagement from './components/FundManagement';
import ImportExcel from './components/ImportExcel';
import CycleOverview from './components/CycleOverview';
import TradingPlanEditor from './components/TradingPlanEditor';


const PDCADashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('cycles');

  // 注入 PDCA 页面专用 CSS（溢出滚动等）
  useEffect(() => {
    const style = document.createElement('style');
    style.id = 'pdca-custom-styles';
    style.textContent = `
      .pdca-tabs .ant-tabs-content-holder { overflow-y: auto; }
      .pdca-tabs .ant-tabs-content { height: 100%; }
      .fund-sub-tabs .ant-tabs-content-holder { overflow-y: auto; }
      .fund-sub-tabs .ant-tabs-content { height: 100%; }
      /* 隐藏 tab 栏上 fund 和 import 的重复按钮（由 tabBarExtraContent 替代） */
      .pdca-tabs .ant-tabs-nav-list > .ant-tabs-tab:nth-child(5),
      .pdca-tabs .ant-tabs-nav-list > .ant-tabs-tab:nth-child(6) {
        display: none !important;
      }
      .pdca-tab-extra { display: flex; align-items: center; gap: 8px; margin-right: 4px; }
      .pdca-tab-extra .extra-tab-item {
        display: flex; align-items: center; gap: 8px;
        padding: 12px 16px; cursor: pointer; border-radius: 0;
        font-size: 14px; line-height: 1.5714; white-space: nowrap;
        color: var(--text-secondary, rgba(234,236,239,0.65));
        transition: color 0.3s;
      }
      .pdca-tab-extra .extra-tab-item:hover { color: var(--text-primary, rgba(234,236,239,0.88)); }
      .pdca-tab-extra .extra-tab-item.active {
        color: #4080ff;
      }
    `;
    document.head.appendChild(style);
    return () => { const el = document.getElementById('pdca-custom-styles'); if (el) el.remove(); };
  }, []);

  // 左侧 PDCA 主 Tab + 右侧隐藏 Tab（内容渲染用，tab 栏上的按钮由 tabBarExtraContent 替代）
  const tabItems = [
    { key: 'cycles', label: <span className="flex items-center gap-2"><RadarChartOutlined /><span>周期总览</span></span>, children: <CycleOverview /> },
    { key: 'plans',  label: <span className="flex items-center gap-2"><FileTextOutlined /><span>交易计划</span></span>, children: <TradingPlanEditor /> },
    { key: 'records', label: <span className="flex items-center gap-2"><TableOutlined /><span>交易台账</span></span>, children: <TradingRecordTable /> },
    { key: 'diary',  label: <span className="flex items-center gap-2"><EditOutlined /><span>交易日记</span></span>, children: <TradingDiaryEditor /> },
    { key: 'fund',   label: <span className="flex items-center gap-2"><DollarOutlined /><span>资金管理</span></span>, children: <FundManagement /> },
    { key: 'import', label: <span className="flex items-center gap-2"><ImportOutlined /><span>券商导入</span></span>, children: <ImportExcel /> },
  ];

  // 右侧自定义 Tab（通过 tabBarExtraContent 渲染在 tab 栏右侧）
  const tabBarExtraContent = {
    right: (
      <div className="pdca-tab-extra">
        <div
          className={`extra-tab-item${activeTab === 'fund' ? ' active' : ''}`}
          onClick={() => setActiveTab('fund')}
        >
          <DollarOutlined />
          <span>资金管理</span>
        </div>
        <div
          className={`extra-tab-item${activeTab === 'import' ? ' active' : ''}`}
          onClick={() => setActiveTab('import')}
        >
          <ImportOutlined />
          <span>券商导入</span>
        </div>
      </div>
    ),
  };

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* Tab 内容区 */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          tabBarExtraContent={tabBarExtraContent}
          className="h-full pdca-tabs"
          tabBarStyle={{
            margin: 0,
            paddingLeft: 16,
            paddingRight: 16,
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