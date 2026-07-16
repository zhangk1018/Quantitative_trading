// src/features/strategy-backtest/components/TradeLog.tsx
// 交易日志表 — 含 7 色卖出原因 Tag

import React from 'react';
import { Table, Tag } from 'antd';
import type { Trade, SellReason } from '../types';

interface TradeLogProps {
  trades: Trade[];
}

const sellReasonColors: Record<SellReason, string> = {
  rebalance: 'blue',
  stop_loss: 'red',
  take_profit: 'green',
  timeout: 'orange',
  portfolio_risk: 'purple',
  delisted: 'magenta',
  end: 'default',
};

const sellReasonLabels: Record<SellReason, string> = {
  rebalance: '调仓换股',
  stop_loss: '止损',
  take_profit: '止盈',
  timeout: '超时平仓',
  portfolio_risk: '组合风控',
  delisted: '退市强平',
  end: '期末清仓',
};

const TradeLog: React.FC<TradeLogProps> = ({ trades }) => {
  if (trades.length === 0) {
    return (
      <div className="text-text-disabled text-sm text-center py-4">
        无交易记录
      </div>
    );
  }

  const columns = [
    { title: '股票', dataIndex: 'name', key: 'name', width: 80 },
    { title: '代码', dataIndex: 'code', key: 'code', width: 100 },
    { title: '建仓日', dataIndex: 'entryDate', key: 'entryDate', width: 100 },
    { title: '平仓日', dataIndex: 'exitDate', key: 'exitDate', width: 100 },
    {
      title: '持有天数',
      dataIndex: 'holdDays',
      key: 'holdDays',
      width: 80,
      sorter: (a: Trade, b: Trade) => a.holdDays - b.holdDays,
    },
    {
      title: '盈亏金额',
      dataIndex: 'pnl',
      key: 'pnl',
      width: 100,
      render: (v: number) => (
        <span className={v >= 0 ? 'text-profit' : 'text-loss'}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}
        </span>
      ),
      sorter: (a: Trade, b: Trade) => a.pnl - b.pnl,
    },
    {
      title: '盈亏比例',
      dataIndex: 'pnlPct',
      key: 'pnlPct',
      width: 90,
      render: (v: number) => (
        <span className={v >= 0 ? 'text-profit' : 'text-loss'}>
          {v >= 0 ? '+' : ''}{(v * 100).toFixed(1)}%
        </span>
      ),
      sorter: (a: Trade, b: Trade) => a.pnlPct - b.pnlPct,
    },
    {
      title: '卖出原因',
      dataIndex: 'sellReason',
      key: 'sellReason',
      width: 100,
      render: (reason: SellReason) => (
        <Tag color={sellReasonColors[reason]}>{sellReasonLabels[reason]}</Tag>
      ),
      filters: Object.entries(sellReasonLabels).map(([value, text]) => ({ text, value })),
      onFilter: (value: unknown, record: Trade) => record.sellReason === value,
    },
  ];

  return (
    <Table
      dataSource={trades}
      columns={columns}
      rowKey="code"
      size="small"
      pagination={{ pageSize: 50, showSizeChanger: false }}
      scroll={{ y: 400 }}
      data-testid="trade-log-table"
    />
  );
};

export default TradeLog;