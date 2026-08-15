/**
 * ExitSlipList.tsx — 卖出子单列表卡片
 *
 * 展示买入单的卖出子单列表，支持新增/编辑/删除操作。
 * 从 TradingRecordForm.tsx 抽取，降低主表单复杂度。
 */

import React, { useMemo } from 'react';
import { Button, Card, Space, Table, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined } from '@ant-design/icons';
import type { ExitSlip } from '../types';
import { EXIT_REASON_OPTIONS } from '../types';

interface Props {
  exitSlips: ExitSlip[];
  entryQty: number;
  totalExitQty: number;
  loading: boolean;
  onAdd: () => void;
  onEdit: (slip: ExitSlip) => void;
  onDelete: (id: number) => Promise<void>;
}

const ExitSlipList: React.FC<Props> = ({ exitSlips, entryQty, totalExitQty, loading, onAdd, onEdit, onDelete }) => {
  const columns = useMemo(
    () => [
      { title: '出场日期', dataIndex: 'exit_date', key: 'exit_date', width: 100 },
      {
        title: '出场价',
        dataIndex: 'exit_price',
        key: 'exit_price',
        width: 90,
        align: 'right' as const,
        render: (v: number) => (Number.isFinite(v) ? v.toFixed(2) : '-'),
      },
      {
        title: '数量',
        dataIndex: 'quantity',
        key: 'quantity',
        width: 70,
        align: 'right' as const,
        render: (v: number) => (Number.isFinite(v) ? v.toLocaleString() : '-'),
      },
      {
        title: '出场原因',
        dataIndex: 'exit_reason',
        key: 'exit_reason',
        width: 100,
        render: (v: string | null) => (v ? EXIT_REASON_OPTIONS.find(o => o.value === v)?.label || v : '-'),
      },
      {
        title: '操作',
        key: 'action',
        width: 100,
        render: (_: unknown, slip: ExitSlip) => (
          <Space size="small">
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onEdit(slip)}>
              编辑
            </Button>
            <Popconfirm
              title="确定删除此卖出记录？"
              onConfirm={() => onDelete(slip.id)}
              okText="删除"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [onEdit, onDelete],
  );

  return (
    <Card
      title={`卖出记录 — 总持仓 ${entryQty} / 已卖出 ${totalExitQty} / 剩余 ${entryQty - totalExitQty}`}
      size="small"
      className="mb-4"
      extra={
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onAdd}>
          新增卖出
        </Button>
      }
    >
      <Table
        columns={columns}
        dataSource={exitSlips}
        rowKey="id"
        pagination={false}
        size="small"
        loading={loading}
        locale={{ emptyText: '暂无卖出记录' }}
      />
      {totalExitQty > entryQty && (
        <div className="text-red-500 text-sm mt-2">
          ⚠️ 卖出数量 {totalExitQty} 超过买入数量 {entryQty}，请检查
        </div>
      )}
    </Card>
  );
};

export default ExitSlipList;