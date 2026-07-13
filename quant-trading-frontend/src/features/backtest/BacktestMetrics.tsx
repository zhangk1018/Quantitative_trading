// BacktestMetrics.tsx — 回测指标卡片

import React from 'react';
import { Card, Row, Col, Statistic, Tooltip } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { BacktestSummary } from './backtestTypes';

interface MetricsProps {
  summary: BacktestSummary;
}

function pct(val: number): string {
  return `${(val * 100).toFixed(2)}%`;
}

function formatNum(val: number, decimals = 2): string {
  return val.toFixed(decimals);
}

const BacktestMetrics: React.FC<MetricsProps> = ({ summary }) => {
  const isPositive = summary.totalReturn >= 0;

  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="总收益率"
            value={pct(summary.totalReturn)}
            valueStyle={{ color: isPositive ? '#3f8600' : '#cf1322', fontSize: 18 }}
            prefix={isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Tooltip title="年化：(1+总收益)^(252/交易天数)-1">
            <Statistic
              title="年化收益率"
              value={pct(summary.annualizedReturn)}
              valueStyle={{ color: summary.annualizedReturn >= 0 ? '#3f8600' : '#cf1322', fontSize: 18 }}
            />
          </Tooltip>
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="胜率"
            value={pct(summary.winRate)}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="盈亏比"
            value={formatNum(summary.profitLossRatio)}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Tooltip title="日度收盘净值最大回撤">
            <Statistic
              title="最大回撤"
              value={pct(summary.maxDrawdown)}
              valueStyle={{ color: '#cf1322', fontSize: 18 }}
            />
          </Tooltip>
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="夏普比率"
            value={formatNum(summary.sharpeRatio)}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="交易次数"
            value={`${summary.totalTrades}${summary.forcedCloseCount > 0 ? ` + ${summary.forcedCloseCount}清仓` : ''}`}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="基准收益"
            value={pct(summary.benchmarkReturn)}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="平均持仓"
            value={`${formatNum(summary.avgHoldDays, 1)}天`}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card size="small">
          <Statistic
            title="最大连续亏损"
            value={`${summary.maxConsecutiveLoss}次`}
            valueStyle={{ fontSize: 18 }}
          />
        </Card>
      </Col>
    </Row>
  );
};

export default BacktestMetrics;