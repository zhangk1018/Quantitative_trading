/**
 * TradingRecordTable.tsx — 交易台账表格
 *
 * 功能：
 * - 分页表格展示交易记录
 * - 按代码/日期/周期筛选
 * - 新增/编辑/删除记录
 * - 数值校验（前后端双重）
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Table, Button, Space, Input, DatePicker, Tag, Popconfirm,
  App,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, SearchOutlined, ReloadOutlined, ExportOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { TradingRecord } from '../types';
import {
  LONG_SHORT_LABELS, TRADE_GRADE_LABELS, EXIT_REASON_LABELS,
  INSTRUMENT_TYPE_LABELS,
} from '../types';
import { fetchRecords, deleteRecord, exportRecords } from '../api';
import TradingRecordForm from './TradingRecordForm';

const { RangePicker } = DatePicker;

const TradingRecordTable: React.FC = () => {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<TradingRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [codeFilter, setCodeFilter] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<TradingRecord | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        limit: pageSize,
      };
      if (codeFilter) params.code = codeFilter;
      if (dateRange) {
        params.entry_date_from = dateRange[0].format('YYYY-MM-DD');
        params.entry_date_to = dateRange[1].format('YYYY-MM-DD');
      }
      const res = await fetchRecords(params);
      if (res.code === 200) {
        setRecords(res.data.items);
        setTotal(res.data.total);
      } else {
        message.error(res.message || '加载失败');
      }
    } catch {
      message.error('网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, codeFilter, dateRange, message]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      const res = await deleteRecord(id);
      if (res.code === 200) {
        message.success('已删除');
        loadData();
      } else {
        message.error(res.message || '删除失败');
      }
    } catch {
      message.error('网络错误');
    }
  }, [message, loadData]);

  const handleExport = useCallback(async () => {
    try {
      const blob = await exportRecords(
        dateRange
          ? { date_from: dateRange[0].format('YYYY-MM-DD'), date_to: dateRange[1].format('YYYY-MM-DD') }
          : undefined,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `交易台账_${dayjs().format('YYYYMMDD')}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch {
      message.error('导出失败');
    }
  }, [dateRange, message]);

  const handleFormSuccess = useCallback(() => {
    setFormOpen(false);
    setEditingRecord(null);
    loadData();
  }, [loadData]);

  const columns: ColumnsType<TradingRecord> = useMemo(() => [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 90,
      fixed: 'left',
      render: (code: string, record) => (
        <div>
          <div className="text-text-primary font-medium">{code}</div>
          <div className="text-text-secondary text-xs">{record.security_name}</div>
        </div>
      ),
    },
    {
      title: '方向',
      dataIndex: 'long_short',
      key: 'long_short',
      width: 60,
      render: (v: string) => (
        <Tag color={v === 'long' ? 'red' : 'green'}>{LONG_SHORT_LABELS[v as keyof typeof LONG_SHORT_LABELS]}</Tag>
      ),
    },
    {
      title: '入场日',
      dataIndex: 'entry_date',
      key: 'entry_date',
      width: 100,
      sorter: true,
    },
    {
      title: '出场日',
      dataIndex: 'exit_date',
      key: 'exit_date',
      width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '入场价',
      dataIndex: 'entry_price',
      key: 'entry_price',
      width: 80,
      align: 'right',
      render: (v: number) => v?.toFixed(2),
    },
    {
      title: '出场价',
      dataIndex: 'exit_price',
      key: 'exit_price',
      width: 80,
      align: 'right',
      render: (v: number | null) => v?.toFixed(2) ?? '-',
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 70,
      align: 'right',
      render: (v: number) => v?.toLocaleString(),
    },
    {
      title: '毛盈亏',
      dataIndex: 'gross_profit',
      key: 'gross_profit',
      width: 90,
      align: 'right',
      render: (v: number | null) => {
        if (v == null) return '-';
        return (
          <span className={v >= 0 ? 'text-red-500' : 'text-green-500'}>
            {v >= 0 ? '+' : ''}{v.toFixed(2)}
          </span>
        );
      },
    },
    {
      title: '进场分',
      dataIndex: 'entry_score',
      key: 'entry_score',
      width: 75,
      align: 'right',
      render: (v: number | null) => v?.toFixed(1) ?? '-',
    },
    {
      title: '出场分',
      dataIndex: 'exit_score',
      key: 'exit_score',
      width: 75,
      align: 'right',
      render: (v: number | null) => v?.toFixed(1) ?? '-',
    },
    {
      title: '总评分',
      dataIndex: 'trade_score',
      key: 'trade_score',
      width: 75,
      align: 'right',
      render: (v: number | null) => v?.toFixed(1) ?? '-',
    },
    {
      title: '等级',
      dataIndex: 'trade_grade',
      key: 'trade_grade',
      width: 60,
      render: (v: string | null) => {
        if (!v) return '-';
        const colors: Record<string, string> = { A: 'green', B: 'blue', C: 'orange' };
        return <Tag color={colors[v]}>{TRADE_GRADE_LABELS[v as keyof typeof TRADE_GRADE_LABELS]}</Tag>;
      },
    },
    {
      title: '出场原因',
      dataIndex: 'exit_reason',
      key: 'exit_reason',
      width: 90,
      render: (v: string | null) => v ? EXIT_REASON_LABELS[v as keyof typeof EXIT_REASON_LABELS] : '-',
    },
    {
      title: '品种',
      dataIndex: 'instrument_type',
      key: 'instrument_type',
      width: 60,
      render: (v: string) => INSTRUMENT_TYPE_LABELS[v as keyof typeof INSTRUMENT_TYPE_LABELS],
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditingRecord(record);
              setFormOpen(true);
            }}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除此交易记录？"
            description="删除后可在回收站中恢复"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], [handleDelete]);

  return (
    <div className="h-full flex flex-col">
      {/* 工具栏 */}
      <div className="px-4 py-2 flex items-center justify-between border-b border-border-color bg-bg-panel flex-shrink-0">
        <Space>
          <Input
            placeholder="股票代码"
            prefix={<SearchOutlined />}
            value={codeFilter}
            onChange={(e) => { setCodeFilter(e.target.value); setPage(1); }}
            allowClear
            style={{ width: 140 }}
          />
          <RangePicker
            value={dateRange}
            onChange={(v) => { setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null); setPage(1); }}
            placeholder={['入场日期起', '入场日期止']}
            style={{ width: 240 }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExport}>导出 Excel</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingRecord(null); setFormOpen(true); }}>
            新增交易
          </Button>
        </Space>
      </div>

      {/* 表格 */}
      <div className="flex-1 overflow-auto min-h-0">
        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1400 }}
          size="small"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
          locale={{ emptyText: '暂无交易记录，点击"新增交易"开始' }}
        />
      </div>

      {/* 新增/编辑弹窗 */}
      <TradingRecordForm
        open={formOpen}
        record={editingRecord}
        onClose={() => { setFormOpen(false); setEditingRecord(null); }}
        onSuccess={handleFormSuccess}
      />
    </div>
  );
};

export default TradingRecordTable;