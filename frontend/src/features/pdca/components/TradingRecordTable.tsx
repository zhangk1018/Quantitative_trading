/**
 * TradingRecordTable.tsx — 交易台账表格
 *
 * 功能：
 * - 分页表格展示交易记录
 * - 按代码/日期/周期筛选
 * - 新增/编辑/删除记录
 * - 导出 Excel
 * - 乐观更新（删除后立即从本地移除）
 */

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Table, Button, Space, Input, DatePicker, Tag, Popconfirm,
  App, Skeleton, Card,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, SearchOutlined, ReloadOutlined, ExportOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { DEFAULT_PAGE_SIZE } from '@/config/constants';
import type { TradingRecord, ExitSlip } from '../types';
import {
  LONG_SHORT_LABELS, TRADE_GRADE_LABELS, EXIT_REASON_LABELS,
  INSTRUMENT_TYPE_LABELS,
} from '../constants';
import { fetchRecords, fetchExitSlips } from '../services/record';
import { exportRecords, downloadExcel } from '../services/import';
import { recordApi } from '../services/record';
import TradingRecordForm from './TradingRecordForm';

const { RangePicker } = DatePicker;

const TradingRecordTable: React.FC = () => {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<TradingRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [codeFilter, setCodeFilter] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<TradingRecord | null>(null);
  const [exporting, setExporting] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [exitSlipsMap, setExitSlipsMap] = useState<Record<number, ExitSlip[]>>({});
  const [loadingRecords, setLoadingRecords] = useState<Record<number, boolean>>({}); // 行展开加载锁

  // 使用 ref 保存不触发重新渲染的筛选值
  const loadParamsRef = useRef({ page, pageSize, codeFilter, dateRange });
  loadParamsRef.current = { page, pageSize, codeFilter, dateRange };

  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    const params: Record<string, unknown> = {
      page: loadParamsRef.current.page,
      limit: loadParamsRef.current.pageSize,
    };
    const cf = loadParamsRef.current.codeFilter;
    const dr = loadParamsRef.current.dateRange;
    if (cf) params.code = cf;
    if (dr) {
      params.entry_date_from = dr[0].format('YYYY-MM-DD');
      params.entry_date_to = dr[1].format('YYYY-MM-DD');
    }
    try {
      const result = await fetchRecords(params);
      setRecords(result.items || []);
      setTotal(result.total);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '网络错误，请稍后重试');
    } finally {
      setLoading(false);
      setInitialLoading(false);
    }
  }, [message]);

  // 使用 ref 持有最新引用，避免闭包陷阱
  const loadDataRef = useRef(loadData);
  loadDataRef.current = loadData;

  // 仅监听筛选参数变化触发加载，避免 useCallback 重建导致的重复请求
  useEffect(() => {
    loadDataRef.current();
  }, [page, pageSize, codeFilter, dateRange]);

  // 乐观删除：先移除本地记录，再请求后端
  const handleDelete = useCallback(async (id: number) => {
    const prevRecords = records;
    const prevTotal = total;
    // 乐观更新
    setRecords((prev) => prev.filter((r) => r.id !== id));
    setTotal((prev) => prev - 1);
    try {
      await recordApi.delete(id);
      message.success('已删除');
      // 删除成功后刷新后端数据，确保分页和排序一致
      loadDataRef.current(false);
    } catch (err) {
      setRecords(prevRecords);
      setTotal(prevTotal);
      message.error(err instanceof Error ? err.message : '网络错误，删除失败');
    }
  }, [records, total, message]);

  // 通过 ref 避免 columns 闭包陷阱
  const handleDeleteRef = useRef(handleDelete);
  handleDeleteRef.current = handleDelete;

  // 展开行时加载子单数据（带加载锁，防止并发重复请求）
  const handleExpand = useCallback(async (expanded: boolean, record: TradingRecord) => {
    if (expanded && !exitSlipsMap[record.id] && !loadingRecords[record.id]) {
      setLoadingRecords(prev => ({ ...prev, [record.id]: true }));
      try {
        const slips = await fetchExitSlips(record.id);
        setExitSlipsMap(prev => ({ ...prev, [record.id]: slips }));
      } catch {
        message.warning('加载卖出记录失败，请检查网络连接');
      } finally {
        setLoadingRecords(prev => ({ ...prev, [record.id]: false }));
      }
    }
  }, [exitSlipsMap, loadingRecords, message]);

  // 展开行渲染：子单明细表格
  const expandedRowRender = useCallback((record: TradingRecord) => {
    const slips = exitSlipsMap[record.id] || [];
    if (slips.length === 0) {
      return <div className="text-text-secondary text-center py-4">暂无卖出记录</div>;
    }
    const slipColumns: ColumnsType<ExitSlip> = [
      { title: '出场日', dataIndex: 'exit_date', key: 'exit_date', width: 100 },
      {
        title: '出场价', dataIndex: 'exit_price', key: 'exit_price', width: 80, align: 'right',
        render: (v: number) => (Number.isFinite(v) ? v.toFixed(2) : '-'),
      },
      {
        title: '数量', dataIndex: 'quantity', key: 'quantity', width: 70, align: 'right',
        render: (v: number) => (Number.isFinite(v) ? v.toLocaleString() : '-'),
      },
      {
        title: '出场原因', dataIndex: 'exit_reason', key: 'exit_reason', width: 90,
        render: (v: string | null) => (v ? EXIT_REASON_LABELS[v as keyof typeof EXIT_REASON_LABELS] : '-'),
      },
      {
        title: '出场分', dataIndex: 'exit_score', key: 'exit_score', width: 70, align: 'right',
        render: (v: number | null) => (v != null ? v.toFixed(1) : '-'),
      },
      {
        title: '佣金', dataIndex: 'commission', key: 'commission', width: 70, align: 'right',
        render: (v: number) => (Number.isFinite(v) ? v.toFixed(2) : '-'),
      },
    ];
    return (
      <Card size="small" className="bg-bg-secondary" bordered={false}>
        <Table
          columns={slipColumns}
          dataSource={slips}
          rowKey="id"
          pagination={false}
          size="small"
          bordered
        />
      </Card>
    );
  }, [exitSlipsMap]);

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
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toFixed(2) : '-';
      },
    },
    {
      title: '出场价',
      dataIndex: 'exit_price',
      key: 'exit_price',
      width: 80,
      align: 'right',
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toFixed(2) : '-';
      },
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 70,
      align: 'right',
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toLocaleString() : '-';
      },
    },
    {
      title: '持仓',
      key: 'position',
      width: 80,
      align: 'right',
      render: (_, record) => {
        const remain = record.remain_qty ?? record.quantity;
        const total = record.quantity;
        return `${remain}/${total}`;
      },
    },
    {
      title: '毛盈亏',
      dataIndex: 'gross_profit',
      key: 'gross_profit',
      width: 90,
      align: 'right',
      render: (v: unknown) => {
        const n = Number(v);
        if (!Number.isFinite(n)) return '-';
        return (
          <span className={n >= 0 ? 'text-red-500' : 'text-green-500'}>
            {n >= 0 ? '+' : ''}{n.toFixed(2)}
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
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toFixed(1) : '-';
      },
    },
    {
      title: '出场分',
      dataIndex: 'exit_score',
      key: 'exit_score',
      width: 75,
      align: 'right',
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toFixed(1) : '-';
      },
    },
    {
      title: '总评分',
      dataIndex: 'trade_score',
      key: 'trade_score',
      width: 75,
      align: 'right',
      render: (v: unknown) => {
        const n = Number(v);
        return Number.isFinite(n) ? n.toFixed(1) : '-';
      },
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
            onConfirm={() => handleDeleteRef.current(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], []); // 使用 ref 持有 handleDelete 最新引用（ref 跨渲染稳定），无需声明依赖变量

  // 添加 AbortController 支持，取消未完成的请求

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      await downloadExcel(
        exportRecords(
          dateRange
            ? { date_from: dateRange[0].format('YYYY-MM-DD'), date_to: dateRange[1].format('YYYY-MM-DD') }
            : undefined,
        ),
        '交易台账',
      );
      message.success('导出成功');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }, [dateRange, message]);

  const handleFormSuccess = useCallback(() => {
    setFormOpen(false);
    setEditingRecord(null);
    setExitSlipsMap({}); // 清除子单缓存，确保下次展开时重新加载
    loadData();
  }, [loadData]);

  // 子单删除后：刷新父表数据但不关闭表单，保留其余卖出记录供继续操作
  const handleSlipDeleted = useCallback(() => {
    setExitSlipsMap({});
    loadData();
  }, [loadData]);

  if (initialLoading) {
    return (
      <div className="p-4">
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

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
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
        </Space>
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExport} loading={exporting}>导出 Excel</Button>
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
          expandable={{
            expandedRowRender,
            onExpand: handleExpand,
            rowExpandable: () => true,
          }}
          scroll={{ x: 1500 }}
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
        onSlipDeleted={handleSlipDeleted}
      />
    </div>
  );
};

export default TradingRecordTable;