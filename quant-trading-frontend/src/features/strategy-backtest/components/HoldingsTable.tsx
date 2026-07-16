// src/features/strategy-backtest/components/HoldingsTable.tsx
// 持仓明细表 — 虚拟滚动，懒加载

import React, { useMemo } from 'react';
import { Table, Tag } from 'antd';
import type { Position } from '../types';

interface HoldingsTableProps {
  holdings: Array<{ date: string; positions: Position[] }>;
}

const HoldingsTable: React.FC<HoldingsTableProps> = ({ holdings }) => {
  const dataSource = useMemo(() => {
    const rows: Array<{ key: string; date: string; code: string; shares: number; avgCost: string; marketValue: string }> = [];
    for (const h of holdings) {
      for (const pos of h.positions) {
        rows.push({
          key: `${h.date}_${pos.code}`,
          date: h.date,
          code: pos.code,
          shares: pos.shares,
          avgCost: pos.avgCost.toFixed(2),
          marketValue: (pos.shares * pos.avgCost).toFixed(2),
        });
      }
    }
    return rows;
  }, [holdings]);

  const columns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
    { title: '股票代码', dataIndex: 'code', key: 'code', width: 120 },
    { title: '持股数量', dataIndex: 'shares', key: 'shares', width: 100 },
    { title: '成本价', dataIndex: 'avgCost', key: 'avgCost', width: 100 },
    { title: '市值', dataIndex: 'marketValue', key: 'marketValue', width: 100 },
  ];

  if (holdings.length === 0) {
    return (
      <div className="text-text-disabled text-sm text-center py-4">
        无持仓明细
      </div>
    );
  }

  return (
    <Table
      dataSource={dataSource}
      columns={columns}
      size="small"
      pagination={{ pageSize: 50, showSizeChanger: false }}
      scroll={{ y: 400 }}
      data-testid="holdings-table"
    />
  );
};

export default HoldingsTable;