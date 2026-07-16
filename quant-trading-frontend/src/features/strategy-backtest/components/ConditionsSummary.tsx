// src/features/strategy-backtest/components/ConditionsSummary.tsx
// 策略条件摘要卡片 — 展示 FilterNode AST 的人类可读表达

import React from 'react';
import { Tag, Button, Tooltip } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { FilterNode } from '../types';

interface ConditionsSummaryProps {
  filterTree: FilterNode | null;
  onModify: () => void;
}

/** 将 FilterNode 递归渲染为人类可读的标签 */
function renderNode(node: FilterNode, depth = 0): React.ReactNode {
  const indent = depth > 0;

  switch (node.type) {
    case 'and':
    case 'or': {
      const label = node.type === 'and' ? '且 (AND)' : '或 (OR)';
      return (
        <div key={Math.random()} className="flex flex-wrap items-center gap-2">
          {indent && <span className="text-text-disabled text-xs">(</span>}
          {node.children.map((child, i) => (
            <React.Fragment key={i}>
              {i > 0 && <Tag color="geekblue">{label}</Tag>}
              {renderNode(child, depth + 1)}
            </React.Fragment>
          ))}
          {indent && <span className="text-text-disabled text-xs">)</span>}
        </div>
      );
    }
    case 'not':
      return (
        <div key={Math.random()} className="flex items-center gap-1">
          <Tag color="red">非 (NOT)</Tag>
          {renderNode(node.child, depth + 1)}
        </div>
      );
    case 'range': {
      const fieldLabels: Record<string, string> = {
        market_cap: '市值(亿)',
        close: '价格',
        change_pct: '涨跌幅%',
        pe: 'PE(静)',
        pe_ttm: 'PE(TTM)',
        pb: 'PB',
        turnover_rate: '换手率%',
        vol_ratio_5: '量比',
      };
      const fieldLabel = fieldLabels[node.field] ?? node.field;
      const minStr = node.min !== undefined ? node.min : '—';
      const maxStr = node.max !== undefined ? node.max : '—';
      return <Tag key={Math.random()} color="green">{fieldLabel}: {minStr} ~ {maxStr}</Tag>;
    }
    case 'market': {
      const boardLabels: Record<string, string> = {
        main: '主板', gem: '创业板', star: '科创板', beijing: '北交所',
      };
      const parts: string[] = [];
      if (node.boards && node.boards.length > 0) {
        parts.push(node.boards.map(b => boardLabels[b] ?? b).join('+'));
      }
      if (node.watchlistOnly) {
        parts.push('仅自选');
      }
      const label = parts.length > 0 ? parts.join('+') : '全部';
      return <Tag key={Math.random()} color="blue">{label}</Tag>;
    }
    case 'pattern': {
      const patternLabels: Record<string, string> = {
        ma_bullish: 'MA多头排列',
        macd_golden_cross: 'MACD金叉',
        rsi_golden_cross: 'RSI金叉',
        boll_break_upper: 'BOLL突破上轨',
      };
      return <Tag key={Math.random()} color="purple">{patternLabels[node.pattern] ?? node.pattern}</Tag>;
    }
    case 'kline': {
      const klineLabels: Record<string, string> = {
        morning_star: '早晨之星',
        hammer: '锤子线',
        bullish_engulfing: '阳包阴',
        piercing_line: '刺透线',
        three_white_soldiers: '三白兵',
      };
      return (
        <Tag key={Math.random()} color="orange">
          {klineLabels[node.pattern] ?? node.pattern} ({node.lookbackDays}日)
        </Tag>
      );
    }
  }
}

const ConditionsSummary: React.FC<ConditionsSummaryProps> = ({ filterTree, onModify }) => {
  if (!filterTree) {
    return (
      <div className="bg-bg-panel rounded-lg border border-border-color p-4">
        <div className="text-text-disabled text-sm text-center py-4">
          请从选股器跳转至策略回测页面
        </div>
      </div>
    );
  }

  return (
    <div className="bg-bg-panel rounded-lg border border-border-color p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium">策略条件摘要</span>
        <Button
          type="link"
          size="small"
          icon={<ArrowLeftOutlined />}
          onClick={onModify}
          data-testid="modify-conditions-btn"
        >
          修改选股条件
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {renderNode(filterTree)}
      </div>
    </div>
  );
};

export default ConditionsSummary;