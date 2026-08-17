/**
 * DoExecutionTracker.tsx — Do 模块执行跟踪（Phase B）
 *
 * 功能：
 * - 展示 PDCA 周期执行进度：计划 vs 实际交易对比
 * - 统计摘要（执行率、总计划数、已完成数、裸交易数）
 * - 计划执行明细表格（每笔计划的执行状态、价格偏差、数量完成率）
 * - 裸交易列表（无交易计划的交易记录）
 *
 * 依赖后端 API：
 * - GET /api/pdca/cycles/{cycle_id}/execution-summary
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Progress, Spin, Empty, Typography, Alert, Tooltip } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ExecutionSummary, ExecutionPlanDetail, NakedTradeDetail } from '../types';
import { LONG_SHORT_LABELS, TRIGGER_SOURCE_LABELS } from '../types';
import { fetchExecutionSummary } from '../api';

const { Text } = Typography;

interface DoExecutionTrackerProps {
  cycleId: number;
  cycleName: string;
}

const DoExecutionTracker: React.FC<DoExecutionTrackerProps> = ({ cycleId, cycleName }) => {
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchExecutionSummary(cycleId);
      if (res.code === 200) {
        setSummary(res.data);
      } else {
        setError(res.message || '加载执行摘要失败');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载执行摘要失败');
    } finally {
      setLoading(false);
    }
  }, [cycleId]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Spin tip="加载执行跟踪数据..." />
      </div>
    );
  }

  if (error) {
    return <Alert type="error" message={error} showIcon className="mb-3" />;
  }

  if (!summary) {
    return <Empty description="暂无执行数据" />;
  }

  // ── 统计卡片 ──
  const StatsCard = ({ label, value, color }: { label: string; value: string | number; color: string }) => (
    <div className="flex flex-col items-center p-3 rounded-lg bg-bg-secondary min-w-[100px]">
      <Text className="text-text-secondary text-xs mb-1">{label}</Text>
      <Text strong style={{ color, fontSize: 20 }}>{value}</Text>
    </div>
  );

  // ── 计划明细列 ──
  const planColumns: ColumnsType<ExecutionPlanDetail> = [
    {
      title: '标的', dataIndex: 'code', key: 'code', width: 100,
      render: (_: unknown, r: ExecutionPlanDetail) => (
        <div className="flex flex-col">
          <Text strong>{r.code}</Text>
          {r.security_name && <Text type="secondary" className="text-xs">{r.security_name}</Text>}
        </div>
      ),
    },
    {
      title: '方向', dataIndex: 'long_short', key: 'long_short', width: 60,
      render: (v: string) => {
        const label = LONG_SHORT_LABELS[v as 'long' | 'short'] || v;
        return <Tag color={v === 'long' ? 'red' : 'green'}>{label}</Tag>;
      },
    },
    {
      title: '状态', dataIndex: 'execution_status', key: 'execution_status', width: 80,
      render: (v: string) => {
        if (v === 'executed') {
          return <Tag color="green" icon={<CheckCircleOutlined />}>已执行</Tag>;
        }
        return <Tag color="orange" icon={<ClockCircleOutlined />}>待执行</Tag>;
      },
    },
    {
      title: '计划入场价', dataIndex: 'plan_entry_price', key: 'plan_entry_price', width: 95, align: 'right',
      render: (v: number) => v.toFixed(2),
    },
    {
      title: '实际入场价', dataIndex: 'actual_entry_price', key: 'actual_entry_price', width: 95, align: 'right',
      render: (v: number | null) => (v != null ? v.toFixed(2) : '-'),
    },
    {
      title: '偏差', dataIndex: 'price_deviation', key: 'price_deviation', width: 85, align: 'right',
      render: (v: number | null, r: ExecutionPlanDetail) => {
        if (v == null) return '-';
        const isOver = r.long_short === 'long' ? v > 0 : v < 0;
        return (
          <span className={isOver ? 'text-red-500' : 'text-green-500'}>
            {v > 0 ? '+' : ''}{v.toFixed(2)}
            {isOver ? <ArrowUpOutlined className="ml-1" /> : <ArrowDownOutlined className="ml-1" />}
          </span>
        );
      },
    },
    {
      title: '计划数量', dataIndex: 'plan_quantity', key: 'plan_quantity', width: 80, align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '实际数量', dataIndex: 'actual_quantity', key: 'actual_quantity', width: 80, align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '完成率', dataIndex: 'fill_rate', key: 'fill_rate', width: 120,
      render: (v: number) => (
        <Tooltip title={`${(v * 100).toFixed(1)}%`}>
          <Progress
            percent={Math.round(v * 100)}
            size="small"
            strokeColor={v >= 1 ? '#52c41a' : v >= 0.5 ? '#faad14' : '#ff4d4f'}
            format={() => `${(v * 100).toFixed(0)}%`}
          />
        </Tooltip>
      ),
    },
    {
      title: '入场日', dataIndex: 'first_entry_date', key: 'first_entry_date', width: 95,
      render: (v: string | null) => v || '-',
    },
  ];

  // ── 裸交易列 ──
  const nakedColumns: ColumnsType<NakedTradeDetail> = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 90 },
    { title: '名称', dataIndex: 'security_name', key: 'security_name', width: 90, render: (v: string | null) => v || '-' },
    { title: '入场日', dataIndex: 'entry_date', key: 'entry_date', width: 100 },
    { title: '入场价', dataIndex: 'entry_price', key: 'entry_price', width: 85, align: 'right', render: (v: number) => v.toFixed(2) },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 80, align: 'right', render: (v: number) => v.toLocaleString() },
    {
      title: '触发来源', dataIndex: 'trigger_source', key: 'trigger_source', width: 90,
      render: (v: string | null) => {
        if (!v) return '-';
        const label = TRIGGER_SOURCE_LABELS[v as keyof typeof TRIGGER_SOURCE_LABELS] || v;
        return <Tag>{label}</Tag>;
      },
    },
  ];

  return (
    <div className="do-execution-tracker">
      {/* 标题 */}
      <div className="mb-3">
        <Text strong className="text-base">执行跟踪：{cycleName}</Text>
      </div>

      {/* 统计卡片 */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <StatsCard label="执行率" value={`${(summary.fill_rate * 100).toFixed(0)}%`} color="#52c41a" />
        <StatsCard label="总计划数" value={summary.total_plans} color="#1677ff" />
        <StatsCard label="已执行" value={summary.executed_plans} color="#52c41a" />
        <StatsCard label="待执行" value={summary.pending_plans} color="#faad14" />
        <StatsCard label="总交易笔数" value={summary.total_trades} color="#1677ff" />
        {summary.naked_trades > 0 && (
          <StatsCard label="裸交易" value={summary.naked_trades} color="#ff4d4f" />
        )}
      </div>

      {/* 执行进度条 */}
      <Card size="small" className="mb-3" styles={{ body: { padding: '12px 16px' } }}>
        <div className="flex items-center gap-3">
          <Text className="text-text-secondary text-sm flex-shrink-0">执行进度</Text>
          <Progress
            percent={Math.round(summary.fill_rate * 100)}
            strokeColor={{
              '0%': '#1677ff',
              '100%': '#52c41a',
            }}
            className="flex-1"
            format={() => `${summary.executed_plans}/${summary.total_plans} 已完成`}
          />
        </div>
      </Card>

      {/* 计划执行明细 */}
      <Card
        title="计划执行明细"
        size="small"
        className="mb-3"
        styles={{ header: { padding: '8px 16px' }, body: { padding: 0 } }}
      >
        {summary.details.length === 0 ? (
          <div className="py-4"><Empty description="该周期暂无交易计划" /></div>
        ) : (
          <Table
            rowKey="plan_id"
            columns={planColumns}
            dataSource={summary.details}
            size="small"
            pagination={false}
            bordered
          />
        )}
      </Card>

      {/* 裸交易列表 */}
      {summary.naked_trade_details.length > 0 && (
        <Card
          title={
            <span className="flex items-center gap-2">
              <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
              <span>裸交易记录（无关联交易计划）</span>
            </span>
          }
          size="small"
          styles={{ header: { padding: '8px 16px' }, body: { padding: 0 } }}
        >
          <Table
            rowKey="record_id"
            columns={nakedColumns}
            dataSource={summary.naked_trade_details}
            size="small"
            pagination={false}
            bordered
          />
        </Card>
      )}
    </div>
  );
};

export default DoExecutionTracker;