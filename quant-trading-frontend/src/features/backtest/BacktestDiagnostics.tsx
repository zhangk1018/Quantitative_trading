// BacktestDiagnostics.tsx — 回测诊断报告面板
// 展示结构化诊断日志，按事件类型分组，高亮关键节点

import React from 'react';
import { Collapse, Tag, Timeline, Empty, Typography } from 'antd';
import {
  AimOutlined,
  RiseOutlined,
  FallOutlined,
  WarningOutlined,
  DollarOutlined,
  StopOutlined,
  CheckCircleOutlined,
  BugOutlined,
} from '@ant-design/icons';
import type { DiagnosticEntry } from './backtestTypes';

const { Text } = Typography;

interface Props {
  diagnostics: DiagnosticEntry[];
}

/** 事件类型 → 图标 + 颜色映射 */
const EVENT_CONFIG: Record<DiagnosticEntry['event'], { icon: React.ReactNode; color: string; label: string }> = {
  buy_signal: { icon: <AimOutlined />, color: 'blue', label: '买入信号' },
  sell_signal: { icon: <AimOutlined />, color: 'orange', label: '卖出信号' },
  buy_executed: { icon: <RiseOutlined />, color: '#52c41a', label: '买入执行' },
  sell_executed: { icon: <FallOutlined />, color: '#ff4d4f', label: '卖出执行' },
  forced_close: { icon: <StopOutlined />, color: '#faad14', label: '强制清仓' },
  buy_deferred: { icon: <WarningOutlined />, color: '#faad14', label: '买入顺延' },
  sell_deferred: { icon: <WarningOutlined />, color: '#faad14', label: '卖出顺延' },
  buy_expired: { icon: <StopOutlined />, color: '#ff4d4f', label: '买入失效' },
  sell_expired: { icon: <StopOutlined />, color: '#ff4d4f', label: '卖出失效' },
  insufficient_funds: { icon: <DollarOutlined />, color: '#faad14', label: '资金不足' },
  unexecuted_buy: { icon: <WarningOutlined />, color: '#faad14', label: '未执行买入' },
  script_error: { icon: <BugOutlined />, color: '#ff4d4f', label: '脚本错误' },
};

/** 按事件类型分组统计 */
function groupByEvent(diagnostics: DiagnosticEntry[]): Map<string, DiagnosticEntry[]> {
  const map = new Map<string, DiagnosticEntry[]>();
  for (const entry of diagnostics) {
    const key = entry.event;
    const group = map.get(key) || [];
    group.push(entry);
    map.set(key, group);
  }
  return map;
}

const BacktestDiagnostics: React.FC<Props> = ({ diagnostics }) => {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="无诊断记录"
        style={{ margin: '16px 0' }}
      />
    );
  }

  const grouped = groupByEvent(diagnostics);
  const summaryItems = Array.from(grouped.entries()).map(([event, entries]) => {
    const config = EVENT_CONFIG[event as DiagnosticEntry['event']] || { icon: null, color: 'default', label: event };
    return { event, entries, config };
  });

  return (
    <div style={{ marginTop: 12 }}>
      <Text strong style={{ fontSize: 13, marginBottom: 8, display: 'block' }}>
        诊断报告（共 {diagnostics.length} 条）
      </Text>

      {/* 按事件类型分组展示 */}
      <Collapse
        ghost
        size="small"
        items={summaryItems.map(({ event, entries, config }) => ({
          key: event,
          label: (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Tag color={config.color} style={{ margin: 0 }}>
                {config.icon} {config.label}
              </Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {entries.length} 次
              </Text>
            </span>
          ),
          children: (
            <Timeline
              style={{ marginTop: 8 }}
              items={entries.map((entry, idx) => ({
                key: idx,
                color: event.includes('error') || event.includes('expired') || event.includes('insufficient')
                  ? 'red'
                  : event.includes('executed') || event.includes('close')
                    ? 'green'
                    : 'blue',
                children: (
                  <div>
                    <Text style={{ fontSize: 12, fontWeight: 500 }}>{entry.time}</Text>
                    <br />
                    <Text style={{ fontSize: 12 }}>{entry.reason}</Text>
                    {entry.data && (
                      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                        {Object.entries(entry.data)
                          .filter(([, v]) => v !== undefined && v !== null)
                          .map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(2) : v}`)
                          .join(' | ')}
                      </Text>
                    )}
                  </div>
                ),
              }))}
            />
          ),
        }))}
      />
    </div>
  );
};

export default BacktestDiagnostics;