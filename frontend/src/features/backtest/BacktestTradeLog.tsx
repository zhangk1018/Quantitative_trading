// BacktestTradeLog.tsx — 交易明细表格（虚拟滚动 + 点击定位）

import React, { useMemo } from 'react';
import { Table, Tag, Typography } from 'antd';
import type { Trade } from './backtestTypes';

const { Text } = Typography;

interface TradeLogProps {
  trades: Trade[];
  /** 点击某笔交易时回调，返回该交易的买入日期 */
  onTradeClick?: (trade: Trade) => void;
}

const BacktestTradeLog: React.FC<TradeLogProps> = ({ trades, onTradeClick }) => {
  const columns = useMemo(() => [
    {
      title: '#',
      dataIndex: 'id',
      key: 'id',
      width: 50,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      width: 60,
      render: (_: unknown, record: Trade) => {
        if (record.direction === 'buy') {
          return <Tag color="red">买入</Tag>;
        }
        if (record.direction === 'close') {
          return <Tag color="orange">清仓</Tag>;
        }
        return <Tag color="green">卖出</Tag>;
      },
    },
    {
      title: '买入日期',
      dataIndex: 'entryTime',
      key: 'entryTime',
      width: 110,
      render: (val: string, record: Trade) => (
        <Text
          style={{ cursor: 'pointer', color: '#1677ff' }}
          onClick={() => onTradeClick?.(record)}
        >
          {val}
        </Text>
      ),
    },
    {
      title: '卖出日期',
      dataIndex: 'exitTime',
      key: 'exitTime',
      width: 110,
      render: (val: string) => val || '-',
    },
    {
      title: '买入价',
      dataIndex: 'entryPrice',
      key: 'entryPrice',
      width: 80,
      render: (val: number) => val.toFixed(2),
    },
    {
      title: '卖出价',
      dataIndex: 'exitPrice',
      key: 'exitPrice',
      width: 80,
      render: (val: number) => val > 0 ? val.toFixed(2) : '-',
    },
    {
      title: '股数',
      dataIndex: 'shares',
      key: 'shares',
      width: 70,
    },
    {
      title: '收益率',
      dataIndex: 'profitPct',
      key: 'profitPct',
      width: 80,
      render: (val: number) => (
        <Text style={{ color: val >= 0 ? '#3f8600' : '#cf1322' }}>
          {val.toFixed(2)}%
        </Text>
      ),
    },
    {
      title: '持仓天数',
      dataIndex: 'holdDays',
      key: 'holdDays',
      width: 80,
    },
    {
      title: '触发原因',
      dataIndex: 'exitReason',
      key: 'exitReason',
      ellipsis: true,
      render: (val: string, record: Trade) => {
        if (record.direction === 'buy') return record.entryReason;
        return val || record.entryReason;
      },
    },
  ], [onTradeClick]);

  // 过滤掉买入记录，只显示已完成的交易（卖出 + 清仓）
  const completedTrades = useMemo(
    () => trades.filter((t) => t.direction !== 'buy'),
    [trades],
  );

  return (
    <Table
      dataSource={completedTrades}
      columns={columns}
      rowKey="id"
      size="small"
      pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (total) => `共 ${total} 笔` }}
      scroll={{ y: 300 }}
      locale={{ emptyText: '暂无交易记录' }}
    />
  );
};

export default BacktestTradeLog;