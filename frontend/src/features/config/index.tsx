/**
 * 系统配置页（K 2026-06-17 决策升级）
 *
 * V1.1 变更：
 * - 改造为 Tabs：涨跌颜色方案 + 自编指标
 * - useSearchParams 解析 ?tab=indicators 自动激活指标 Tab
 * - 自编指标 Tab 承载 CustomIndicatorManager（从 ConditionBuilder 迁移）
 *
 * 设计原则：
 * - URL 是 Tab 状态的唯一来源（K 偏好：避免状态/URL 不一致）
 * - 切 Tab 时同步更新 searchParams（replace 不污染 history）
 */

import React, { useState } from 'react';
import { Card, Radio, Space, Typography, Divider, Tag, Tabs } from 'antd';
import { BgColorsOutlined, CodeOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { useSettings, COLOR_SCHEMES, ColorScheme } from '@/shared/contexts/SettingsContext';
import { CustomIndicatorManager } from './components/CustomIndicatorManager';
import CombinedBacktestPanel from './components/CombinedBacktestPanel';

const { Title, Text } = Typography;

/** 涨跌颜色方案面板（从 V1.0 整体迁移） */
const ColorSchemePanel: React.FC = () => {
  const { colorScheme, setColorScheme, colors } = useSettings();

  return (
    <Card
      className="!bg-bg-panel !border-border-color"
      title={<span className="!text-text-primary">涨跌颜色方案</span>}
      extra={
        <Tag color="blue" className="!border-0">
          当前：{COLOR_SCHEMES[colorScheme].label}
        </Tag>
      }
    >
      <Text className="!text-text-secondary block mb-3">
        控制股票列表中价格和涨跌幅的显示颜色：
      </Text>

      <Radio.Group
        value={colorScheme}
        onChange={(e) => setColorScheme(e.target.value as ColorScheme)}
        className="w-full"
      >
        <Space direction="vertical" size="middle" className="w-full">
          {(Object.keys(COLOR_SCHEMES) as ColorScheme[]).map((key) => {
            const opt = COLOR_SCHEMES[key];
            const checked = colorScheme === key;
            return (
              <div
                key={key}
                data-testid={`color-scheme-${key}`}
                className={`flex items-center justify-between p-3 rounded border cursor-pointer transition-colors ${
                  checked
                    ? 'border-color-accent bg-color-accent/5'
                    : 'border-border-color hover:border-text-secondary'
                }`}
                onClick={() => setColorScheme(key)}
              >
                <div className="flex items-center gap-3">
                  <Radio value={key} />
                  <div>
                    <div className="text-text-primary font-medium">{opt.label}</div>
                    <Text className="!text-text-secondary text-xs">
                      {opt.description}
                    </Text>
                  </div>
                </div>
                <Space size="small">
                  <span
                    data-testid={`scheme-${key}-up-block`}
                    className="px-3 py-1 rounded font-mono text-sm text-white"
                    style={{ backgroundColor: opt.colors.up }}
                  >
                    涨
                  </span>
                  <span
                    data-testid={`scheme-${key}-down-block`}
                    className="px-3 py-1 rounded font-mono text-sm text-white"
                    style={{ backgroundColor: opt.colors.down }}
                  >
                    跌
                  </span>
                </Space>
              </div>
            );
          })}
        </Space>
      </Radio.Group>

      <Divider className="!my-4 !border-border-color" />

      <div className="flex items-center text-text-secondary text-sm">
        <span>预览：</span>
        <span
          data-testid="preview-up-block"
          className="px-3 py-1 rounded font-mono text-sm text-white ml-2"
          style={{ backgroundColor: colors.up }}
        >
          涨 ↑
        </span>
        <span
          data-testid="preview-down-block"
          className="px-3 py-1 rounded font-mono text-sm text-white ml-2"
          style={{ backgroundColor: colors.down }}
        >
          跌 ↓
        </span>
      </div>
    </Card>
  );
};

const Config: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // 从 URL 读取初始 activeKey（K 2026-06-17 决策：URL 是状态唯一来源）
  const initialTab = searchParams.get('tab') === 'indicators' ? 'indicators'
    : searchParams.get('tab') === 'backtest' ? 'backtest'
    : 'color';
  const [activeTab, setActiveTab] = useState(initialTab);

  /**
   * 切换 Tab 时同步 URL
   * - indicators → ?tab=indicators
   * - color → 删除 ?tab
   * K 偏好：URL 是状态唯一来源，避免状态/URL 不一致
   */
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    const next = new URLSearchParams(searchParams);
    if (key === 'indicators') {
      next.set('tab', 'indicators');
    } else if (key === 'backtest') {
      next.set('tab', 'backtest');
    } else {
      next.delete('tab');
    }
    // replace 不污染 history（避免浏览器后退按钮每 Tab 一次）
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="flex flex-col h-full bg-bg-base p-6">
      <div className="max-w-2xl w-full mx-auto flex flex-col h-full">
        <Title level={4} className="!text-text-primary !mb-0 !flex-shrink-0">
          系统设置
        </Title>

        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          data-testid="config-tabs"
          className="config-tabs flex-1 flex flex-col min-h-0 mt-4"
          items={[
            {
              key: 'color',
              label: (
                <span data-testid="config-tab-color">
                  <BgColorsOutlined className="mr-1" />
                  涨跌颜色方案
                </span>
              ),
              children: (
                <div className="h-full overflow-auto pr-1">
                  <ColorSchemePanel />
                </div>
              ),
            },
            {
              key: 'backtest',
              label: (
                <span data-testid="config-tab-backtest">
                  <ExperimentOutlined className="mr-1" />
                  回测设置
                </span>
              ),
              children: <CombinedBacktestPanel />,
            },
            {
              key: 'indicators',
              label: (
                <span data-testid="config-tab-indicators">
                  <CodeOutlined className="mr-1" />
                  自编指标
                </span>
              ),
              children: (
                <div className="h-full overflow-auto pr-1">
                  <CustomIndicatorManager />
                </div>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
};

export default Config;
