// src/features/strategy-backtest/components/TradeLog.tsx
// 交易日志表 — 含卖出原因过滤 + CSV 导出

import React, { useState, useMemo, useCallback } from 'react';
import { Table, Tag, Button, Checkbox, Space, Input } from 'antd';
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { Trade, SellReason } from '../types';
import { exportToCsv } from '../../stock-picker/utils/screener';

interface TradeLogProps {
  trades: Trade[];
}

const ALL_SELL_REASONS: SellReason[] = [
  'rebalance',
  'stop_loss',
  'take_profit',
  'timeout',
  'portfolio_risk',
  'delisted',
  'end',
  'trailing_stop',
  'ma_cross',
];

const sellReasonColors: Record<SellReason, string> = {
  rebalance: 'blue',
  stop_loss: 'red',
  take_profit: 'green',
  timeout: 'orange',
  portfolio_risk: 'purple',
  delisted: 'magenta',
  end: 'default',
  trailing_stop: 'gold',
  ma_cross: 'cyan',
};

const sellReasonLabels: Record<SellReason, string> = {
  rebalance: '调仓换股',
  stop_loss: '止损',
  take_profit: '止盈',
  timeout: '超时平仓',
  portfolio_risk: '组合风控',
  delisted: '退市强平',
  end: '期末清仓',
  trailing_stop: '峰值回撤',
  ma_cross: '均线破位',
};

const TradeLog: React.FC<TradeLogProps> = ({ trades }) => {
  const [selectedReasons, setSelectedReasons] = useState<SellReason[]>([]);
  const [searchText, setSearchText] = useState('');

  // 根据选中的卖出原因过滤交易记录
  const filteredTrades = useMemo(() => {
    let result = trades;
    if (selectedReasons.length > 0) {
      result = result.filter((t) => selectedReasons.includes(t.sellReason));
    }
    if (searchText.trim()) {
      const keyword = searchText.trim().toLowerCase();
      result = result.filter(
        (t) =>
          t.code.toLowerCase().includes(keyword) ||
          t.name.toLowerCase().includes(keyword),
      );
    }
    return result;
  }, [trades, selectedReasons, searchText]);

  // 切换卖出原因筛选
  const toggleReason = useCallback((reason: SellReason) => {
    setSelectedReasons((prev) =>
      prev.includes(reason)
        ? prev.filter((r) => r !== reason)
        : [...prev, reason],
    );
  }, []);

  // 全选/取消全选
  const toggleAll = useCallback(() => {
    setSelectedReasons((prev) =>
      prev.length === ALL_SELL_REASONS.length ? [] : [...ALL_SELL_REASONS],
    );
  }, []);

  // 导出 CSV
  const handleExport = useCallback(() => {
    if (filteredTrades.length === 0) {
      return;
    }
    exportToCsv(filteredTrades, {
      headers: ['股票', '代码', '建仓日', '平仓日', '持有天数', '盈亏金额', '盈亏比例', '卖出原因'],
      fields: ['name', 'code', 'entryDate', 'exitDate', 'holdDays', 'pnl', 'pnlPct', 'sellReason'],
      filename: `trade-log-${new Date().toISOString().slice(0, 10)}.csv`,
    });
  }, [filteredTrades]);

  // 自定义过滤下拉
  const filterDropdown = useCallback(
    () => (
      <div className="p-2" style={{ minWidth: 160 }}>
        <div className="border-b border-border-color pb-1 mb-1">
          <Checkbox
            checked={selectedReasons.length === ALL_SELL_REASONS.length}
            indeterminate={selectedReasons.length > 0 && selectedReasons.length < ALL_SELL_REASONS.length}
            onChange={toggleAll}
          >
            全选
          </Checkbox>
        </div>
        {ALL_SELL_REASONS.map((reason) => (
          <div key={reason} className="py-0.5">
            <Checkbox
              checked={selectedReasons.includes(reason)}
              onChange={() => toggleReason(reason)}
            >
              <Tag color={sellReasonColors[reason]} style={{ margin: 0 }}>
                {sellReasonLabels[reason]}
              </Tag>
            </Checkbox>
          </div>
        ))}
      </div>
    ),
    [selectedReasons, toggleReason, toggleAll],
  );

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
      filterDropdown,
      filteredValue: selectedReasons,
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Input
            size="small"
            placeholder="搜索股票/代码"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 180 }}
            allowClear
          />
          <span className="text-text-tertiary text-xs">
            共 {filteredTrades.length} 笔
          </span>
        </div>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          onClick={handleExport}
          disabled={filteredTrades.length === 0}
        >
          导出 CSV
        </Button>
      </div>
      <Table
        dataSource={filteredTrades}
        columns={columns}
        rowKey="code"
        size="small"
        pagination={{ pageSize: 50, showSizeChanger: false }}
        scroll={{ y: 400 }}
        data-testid="trade-log-table"
      />
    </div>
  );
};

export default TradeLog;